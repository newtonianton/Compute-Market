"""
Tokens — each contract becomes a real Token-2022 mint, automatically.

The whitepaper's line "on Solana each contract is one SPL token mint" stops
being a comment here. Per contract (grade x ISO week) this module lazily
creates a Token-2022 mint on devnet — the first time capacity is credited for
that contract — so new weekly windows get tokens as needed, forever, with no
manual step.

Mirroring rule: whenever the ledger credits capacity to an account whose id is
a real Solana pubkey (a connected wallet), the same quantity is minted to that
wallet's associated token account. Provider mints and auction wins both land
as real, wallet-visible, transferable Token-2022 tokens. Internal demo
accounts (acct_...) are skipped — the in-memory ledger stays the source of
truth, the chain mirrors it.

Honest boundary: mirroring is one-way (acquisition only). Burning on redeem
would need the *holder's* signature on a Burn instruction — the protocol
cannot take tokens out of a wallet it doesn't own. That client-signed burn is
the natural next step, not quietly faked here.

Mechanics: the escrow keypair (app/onchain.py) is fee payer and mint
authority. All minting runs on a background worker thread so a devnet
confirmation (~1-2 s) never blocks an auction round. Mint addresses persist in
token-mints-devnet.json; recent mirror events are inspectable at GET /tokens.
"""

import json
import queue
import threading
import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, Depends

from . import onchain
from .deps import get_store
from .errors import BadRequest
from .store import Store

try:
    from solders.instruction import AccountMeta, Instruction
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.system_program import CreateAccountParams, create_account
    from solders.transaction import Transaction
    _HAVE_SOLDERS = True
except ImportError:
    _HAVE_SOLDERS = False

router = APIRouter(tags=["tokens (Token-2022, devnet)"])

# Token-2022: same instruction layout as classic SPL Token for the base set
# (no extensions used yet), but minted under the newer program so extensions
# (metadata pointer, transfer hooks) are a flag away, not a migration.
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ATA_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
SYSTEM_PROGRAM = "11111111111111111111111111111111"

DECIMALS = 2          # capacity trades in hours; 0.01 h resolution
MINT_SPACE = 82       # Token-2022 mint account size without extensions
_IX_INIT_MINT2 = 20   # TokenInstruction::InitializeMint2
_IX_MINT_TO = 7       # TokenInstruction::MintTo
_MIN_FEE_LAMPORTS = 10_000_000  # below 0.01 SOL, try a devnet airdrop top-up

_MINTFILE = Path(__file__).resolve().parent.parent / "token-mints-devnet.json"

ENABLED = _HAVE_SOLDERS and onchain.ESCROW_KEYPAIR is not None

# contract_id -> mint address (base58). Contract ids are deterministic
# (grade@week), so the mapping survives market resets by design.
_mints: dict[str, str] = {}
_mint_lock = threading.Lock()
_events: deque = deque(maxlen=100)   # recent mirror activity, newest last
_queue: "queue.Queue[tuple[str, str, float]]" = queue.Queue()
_worker_started = False
_worker_guard = threading.Lock()

if _MINTFILE.exists():
    try:
        _mints.update(json.loads(_MINTFILE.read_text()))
    except (OSError, ValueError):
        pass


def _save_mints() -> None:
    try:
        _MINTFILE.write_text(json.dumps(_mints, indent=1))
    except OSError:
        pass  # read-only FS: registry lives in memory for this instance


def _event(**kw) -> None:
    _events.append({"ts": time.time(), **kw})


# --- transaction plumbing (shared with onchain.py) ------------------------------

_send_tx = onchain._send_tx       # send + confirm at matching commitment levels
_blockhash = onchain._blockhash


def _ensure_fee_funding() -> None:
    """The escrow pays rent + fees. On devnet, top it up with an airdrop when
    it runs low; deposits landing there also fund it."""
    escrow = str(onchain.ESCROW_KEYPAIR.pubkey())
    bal = onchain._rpc("getBalance", [escrow])["value"]
    if bal >= _MIN_FEE_LAMPORTS:
        return
    if onchain.NETWORK == "devnet":
        try:  # faucets rate-limit (429) — best effort, then re-check
            sig = onchain._rpc("requestAirdrop", [escrow, 1_000_000_000])
            for _ in range(30):
                st = onchain._rpc("getSignatureStatuses", [[sig]])
                info = (st or {}).get("value", [None])[0]
                if info and info.get("confirmationStatus") in ("confirmed", "finalized"):
                    return
                time.sleep(1)
        except BadRequest:
            pass
        bal = onchain._rpc("getBalance", [escrow])["value"]
        if bal >= _MIN_FEE_LAMPORTS:
            return
    raise BadRequest(
        f"escrow {escrow} holds {bal / 1e9:g} SOL — too low to pay token mint "
        f"fees. Fund it: make a small on-chain deposit in the app (deposits "
        f"land at this address), or send devnet SOL from https://faucet.solana.com"
    )


def _ata(owner: "Pubkey", mint: "Pubkey") -> "Pubkey":
    return Pubkey.find_program_address(
        [bytes(owner), bytes(Pubkey.from_string(TOKEN_2022_PROGRAM)), bytes(mint)],
        Pubkey.from_string(ATA_PROGRAM),
    )[0]


def _create_mint_onchain(contract_id: str) -> str:
    """Create one Token-2022 mint for a contract: a fresh account owned by the
    Token-2022 program, initialized with the escrow as mint authority."""
    payer = onchain.ESCROW_KEYPAIR
    token_prog = Pubkey.from_string(TOKEN_2022_PROGRAM)
    mint_kp = Keypair()
    rent = onchain._rpc("getMinimumBalanceForRentExemption", [MINT_SPACE])

    ix_create = create_account(CreateAccountParams(
        from_pubkey=payer.pubkey(), to_pubkey=mint_kp.pubkey(),
        lamports=rent, space=MINT_SPACE, owner=token_prog))

    # InitializeMint2: tag, decimals, mint_authority, freeze_authority=None
    data = bytes([_IX_INIT_MINT2, DECIMALS]) + bytes(payer.pubkey()) + bytes([0])
    ix_init = Instruction(token_prog, data,
                          [AccountMeta(mint_kp.pubkey(), False, True)])

    _ensure_fee_funding()
    tx = Transaction.new_signed_with_payer(
        [ix_create, ix_init], payer.pubkey(), [payer, mint_kp], _blockhash())
    sig = _send_tx(tx)
    addr = str(mint_kp.pubkey())
    _event(type="mint_created", contract=contract_id, mint=addr, sig=sig)
    return addr


def ensure_mint(contract_id: str) -> str:
    """Get the contract's Token-2022 mint, creating it on first need."""
    with _mint_lock:
        if contract_id in _mints:
            return _mints[contract_id]
        addr = _create_mint_onchain(contract_id)
        _mints[contract_id] = addr
        _save_mints()
        return addr


def _mint_to_wallet(owner_addr: str, contract_id: str, qty: float) -> str:
    """Mint qty hours of the contract's token to the wallet's ATA (created
    idempotently in the same transaction)."""
    payer = onchain.ESCROW_KEYPAIR
    token_prog = Pubkey.from_string(TOKEN_2022_PROGRAM)
    owner = Pubkey.from_string(owner_addr)
    mint = Pubkey.from_string(ensure_mint(contract_id))
    ata = _ata(owner, mint)

    ix_ata = Instruction(  # AssociatedTokenAccount::CreateIdempotent
        Pubkey.from_string(ATA_PROGRAM), bytes([1]),
        [AccountMeta(payer.pubkey(), True, True),
         AccountMeta(ata, False, True),
         AccountMeta(owner, False, False),
         AccountMeta(mint, False, False),
         AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM), False, False),
         AccountMeta(token_prog, False, False)])

    amount = round(qty * 10 ** DECIMALS)
    ix_mint = Instruction(  # Token::MintTo
        token_prog, bytes([_IX_MINT_TO]) + amount.to_bytes(8, "little"),
        [AccountMeta(mint, False, True),
         AccountMeta(ata, False, True),
         AccountMeta(payer.pubkey(), True, False)])

    _ensure_fee_funding()
    tx = Transaction.new_signed_with_payer(
        [ix_ata, ix_mint], payer.pubkey(), [payer], _blockhash())
    return _send_tx(tx)


# --- the mirror: ledger capacity credits -> wallet tokens -----------------------

def _worker() -> None:
    while True:
        account_id, contract_id, qty = _queue.get()
        try:
            for attempt in range(3):
                try:
                    sig = _mint_to_wallet(account_id, contract_id, qty)
                    break
                except BadRequest as e:
                    # Retry only send-time rejections ("RPC error ..."): the tx
                    # provably never landed, so a retry cannot double-mint.
                    # Confirmation timeouts are ambiguous — never blind-retry.
                    if attempt == 2 or not str(e).startswith("RPC error"):
                        raise
                    time.sleep(2)
            _event(type="minted", account=account_id, contract=contract_id,
                   qty=qty, sig=sig, status="ok")
        except Exception as e:  # never kill the worker; surface via /tokens
            _event(type="minted", account=account_id, contract=contract_id,
                   qty=qty, status="error", error=str(e))


def _ensure_worker() -> None:
    global _worker_started
    with _worker_guard:
        if not _worker_started:
            threading.Thread(target=_worker, daemon=True,
                             name="token-mirror").start()
            _worker_started = True


def mirror_capacity_credit(account_id: str, contract_id: str, qty: float) -> None:
    """Store hook (see Store.on_capacity_credit). Filters to real wallets,
    then queues the on-chain mint so the trading path never waits on devnet."""
    if not ENABLED or qty <= 0:
        return
    if account_id == str(onchain.ESCROW_KEYPAIR.pubkey()):
        return
    try:
        Pubkey.from_string(account_id)   # demo ids (acct_...) fail here
    except Exception:
        return
    _ensure_worker()
    _queue.put((account_id, contract_id, qty))
    _event(type="queued", account=account_id, contract=contract_id, qty=qty)


# Register the hook. Import-time, once; Store calls it fire-and-forget.
Store.on_capacity_credit = mirror_capacity_credit


# --- endpoints -------------------------------------------------------------------

@router.get("/tokens", summary="Contract -> Token-2022 mint map + mirror activity")
def tokens(store: Store = Depends(get_store)) -> dict:
    return {
        "enabled": ENABLED,
        "network": onchain.NETWORK,
        "token_program": TOKEN_2022_PROGRAM,
        "decimals": DECIMALS,
        "mints": dict(_mints),
        "events": list(_events)[-20:],
    }


@router.post("/tokens/ensure/{contract_id}",
             summary="Create the contract's Token-2022 mint now (otherwise lazy)")
def ensure(contract_id: str, store: Store = Depends(get_store)) -> dict:
    store.get_contract(contract_id)
    if not ENABLED:
        raise BadRequest(
            "token mirroring disabled: needs `solders` installed and a local "
            "escrow keypair (unset MWNT_ESCROW_ADDRESS or remove it)")
    return {"contract_id": contract_id, "mint": ensure_mint(contract_id),
            "token_program": TOKEN_2022_PROGRAM}

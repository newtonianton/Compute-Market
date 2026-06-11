"""
On-chain link (devnet) — turning the wallet string into real custody.

The rest of the market treats an account id as an opaque key. This module is
the one place that talks to Solana: it owns an escrow address, and it verifies
that a real SOL transfer to that address actually landed on devnet before any
in-app balance is credited. Nothing here trusts the client — the deposit
endpoint re-fetches the transaction from an RPC node and reads the escrow
account's own balance delta, so a forged or replayed signature credits nothing.

Scope (deliberately): deposits only. Withdrawing real SOL back out would need
the escrow secret to sign outgoing transfers; that is left to the off-chain
settlement stub until the on-chain settlement layer in the whitepaper exists.

Config (all optional; sensible devnet defaults):
  MWNT_SOLANA_NETWORK   default "devnet"
  MWNT_SOLANA_RPC       default "https://api.<network>.solana.com"
  MWNT_ESCROW_ADDRESS   a devnet address you control; if unset, a keypair is
                        generated once and saved to escrow-devnet.json so the
                        address is stable across restarts (and sweepable with
                        the solana CLI using that keyfile).
"""

import json
import os
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .deps import get_store
from .errors import BadRequest
from .models import Account
from .store import Store

router = APIRouter(tags=["solana (devnet)"])

NETWORK = os.getenv("MWNT_SOLANA_NETWORK", "devnet")
RPC_URL = os.getenv("MWNT_SOLANA_RPC", f"https://api.{NETWORK}.solana.com")
LAMPORTS_PER_SOL = 1_000_000_000

_KEYFILE = Path(__file__).resolve().parent.parent / "escrow-devnet.json"

# Replay guard: a confirmed signature may be credited exactly once. In-memory,
# like the rest of the demo store; signatures are globally unique regardless.
_processed: set[str] = set()


def _resolve_escrow_address() -> str | None:
    """Operator-provided address wins; otherwise generate+persist a devnet
    keypair (needs `solders`). Returns None if neither is available."""
    env = os.getenv("MWNT_ESCROW_ADDRESS")
    if env:
        return env
    try:
        from solders.keypair import Keypair
    except ImportError:
        return None
    if _KEYFILE.exists():
        kp = Keypair.from_bytes(bytes(json.loads(_KEYFILE.read_text())))
    else:
        kp = Keypair()
        _KEYFILE.write_text(json.dumps(list(bytes(kp))))
    return str(kp.pubkey())


ESCROW_ADDRESS = _resolve_escrow_address()


class OnchainDeposit(BaseModel):
    account_id: str = Field(description="The depositing wallet address.")
    signature: str = Field(description="Confirmed devnet transfer signature.")


def _rpc(method: str, params: list) -> dict:
    try:
        r = httpx.post(RPC_URL, timeout=30, json={
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise BadRequest(f"could not reach Solana RPC: {e}")
    body = r.json()
    if body.get("error"):
        raise BadRequest(f"RPC error: {body['error']}")
    return body.get("result")


def _fetch_transfer_to_escrow(signature: str) -> int:
    """Return lamports the escrow account gained in this tx (0 if it wasn't a
    recipient). Retries briefly: a just-confirmed tx can lag the RPC index."""
    result = None
    for attempt in range(4):
        result = _rpc("getTransaction", [signature, {
            "encoding": "json", "commitment": "confirmed",
            "maxSupportedTransactionVersion": 0}])
        if result is not None:
            break
        time.sleep(1)
    if result is None:
        raise BadRequest("transaction not found / not yet confirmed — try again in a moment")

    meta = result.get("meta") or {}
    if meta.get("err") is not None:
        raise BadRequest("transaction failed on-chain")

    keys = result["transaction"]["message"]["accountKeys"]  # base58 strings (json encoding)
    if ESCROW_ADDRESS not in keys:
        return 0
    i = keys.index(ESCROW_ADDRESS)
    return meta["postBalances"][i] - meta["preBalances"][i]


@router.get("/solana/config", summary="Network, RPC and escrow address for the client")
def solana_config() -> dict:
    return {
        "network": NETWORK,
        "rpc_url": RPC_URL,
        "escrow_address": ESCROW_ADDRESS,
        "configured": ESCROW_ADDRESS is not None,
        "lamports_per_sol": LAMPORTS_PER_SOL,
    }


@router.post("/solana/deposit", response_model=Account,
             summary="Credit an account from a verified on-chain SOL deposit")
def solana_deposit(req: OnchainDeposit, store: Store = Depends(get_store)) -> Account:
    """Verify a real devnet transfer landed in escrow, then credit the in-app
    balance. Demo convention: 1 SOL credits 1 quote unit (no SOL/USDC oracle on
    devnet). Idempotent per signature."""
    if ESCROW_ADDRESS is None:
        raise BadRequest(
            "escrow not configured: set MWNT_ESCROW_ADDRESS or `pip install solders`")
    if req.signature in _processed:
        raise BadRequest("this transaction has already been credited")

    lamports = _fetch_transfer_to_escrow(req.signature)
    if lamports <= 0:
        raise BadRequest("transaction did not transfer SOL to the escrow address")

    # Get-or-create: the wallet proved custody by signing the on-chain transfer,
    # so an unknown id here (e.g. after a market reset) is safe to register.
    if req.account_id not in store.accounts:
        store.add_account(Account(id=req.account_id, label="Wallet"))

    _processed.add(req.signature)
    sol = lamports / LAMPORTS_PER_SOL
    store.credit_quote(req.account_id, sol)
    return store.get_account(req.account_id)

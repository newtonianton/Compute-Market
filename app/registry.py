"""
Registry — who is in the market and what they're allowed to do.

This is the "verified providers / verified purchasers" half of the
stablecoin-style design. Whitelisting here is a simple boolean flag; in
production you'd replace the whitelist endpoints with real provider attestation
(KYC, hardware proof, staking) and purchaser checks.
"""

from fastapi import APIRouter, Depends, Query

from . import config
from .deps import get_store
from .models import Account, CreateAccount, Deposit, Role
from .store import Store, new_id

router = APIRouter(tags=["registry"])


@router.post("/providers", response_model=Account, summary="Register a GPU provider")
def create_provider(req: CreateAccount, store: Store = Depends(get_store)) -> Account:
    """Suppliers of compute. Whitelisted on registration when
    AUTO_WHITELIST_PROVIDERS is True (the default)."""
    acct = Account(
        id=req.wallet or new_id("acct"),
        label=req.label or "provider",
        is_provider=True,
        provider_whitelisted=config.AUTO_WHITELIST_PROVIDERS,
    )
    return store.add_account(acct)


@router.post("/accounts", response_model=Account, summary="Register a trading account")
def create_account(req: CreateAccount, store: Store = Depends(get_store)) -> Account:
    """Any participant: a buyer, a pure trader, or (via flags) a provider /
    purchaser. Plain traders need no role — they can still hold and flip
    capacity tokens."""
    acct = Account(
        id=req.wallet or new_id("acct"),
        label=req.label,
        is_provider=req.provider,
        is_purchaser=req.purchaser,
        provider_whitelisted=req.provider and config.AUTO_WHITELIST_PROVIDERS,
        purchaser_whitelisted=req.purchaser,
    )
    return store.add_account(acct)


@router.get("/accounts", response_model=list[Account], summary="List accounts")
def list_accounts(store: Store = Depends(get_store)) -> list[Account]:
    return store.list_accounts()


@router.get("/accounts/{account_id}", response_model=Account, summary="Account detail + balances")
def get_account(account_id: str, store: Store = Depends(get_store)) -> Account:
    return store.get_account(account_id)


@router.post("/accounts/{account_id}/whitelist", response_model=Account, summary="Approve a role")
def whitelist(account_id: str, role: Role = Query(...), store: Store = Depends(get_store)) -> Account:
    acct = store.get_account(account_id)
    if role == Role.provider:
        acct.is_provider = True
        acct.provider_whitelisted = True
    else:
        acct.is_purchaser = True
        acct.purchaser_whitelisted = True
    return acct


@router.post("/accounts/{account_id}/revoke", response_model=Account, summary="Revoke a role")
def revoke(account_id: str, role: Role = Query(...), store: Store = Depends(get_store)) -> Account:
    acct = store.get_account(account_id)
    if role == Role.provider:
        acct.provider_whitelisted = False
    else:
        acct.purchaser_whitelisted = False
    return acct


@router.post("/accounts/{account_id}/deposit", response_model=Account, summary="Fund quote balance")
def deposit(account_id: str, req: Deposit, store: Store = Depends(get_store)) -> Account:
    """Funding stub: credits the account with quote currency (e.g. USDC). Swap
    this for a real on-chain deposit watcher when you wire up settlement."""
    store.get_account(account_id)  # ensure exists
    store.credit_quote(account_id, req.amount)
    return store.get_account(account_id)

"""
Settlement — moving earned value out of the market to capacity sellers.

Inside the book, settlement of each trade is already atomic (quote moves to the
seller the instant a fill happens). This module is the *exit*: a seller pulling
their accumulated quote balance out to a wallet.

Right now it's a stub that just debits the internal balance and logs a payout.
This is the natural place to wire real rails: a USDC transfer on Solana, an
x402 settlement, or a Tempo/MPP streaming payout. Keep the endpoint shape and
swap the body.
"""

from fastapi import APIRouter, Depends

from .deps import get_store
from .models import Payout, WithdrawRequest
from .store import Store, new_id

router = APIRouter(tags=["settlement"])


@router.post("/accounts/{account_id}/withdraw", response_model=Payout, summary="Settle quote out to a wallet")
def withdraw(account_id: str, req: WithdrawRequest, store: Store = Depends(get_store)) -> Payout:
    store.get_account(account_id)  # ensure exists
    store.withdraw_quote(account_id, req.amount)  # raises InsufficientFunds
    payout = Payout(
        id=new_id("payout"),
        account_id=account_id,
        amount=req.amount,
        destination=req.destination or account_id,
    )
    return store.append_payout(payout)


@router.get("/settlements", response_model=list[Payout], summary="Payout history")
def settlements(store: Store = Depends(get_store)) -> list[Payout]:
    return store.list_payouts()

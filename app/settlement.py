"""
Settlement — escrow, delivery, and the no-show math (Layer 5).

The buyer's payment sat down in a per-trade escrow at clearing time. From here:

  * Redeem: the buyer burns tokens; deliveries are created against their
    escrows FIFO (oldest trade first). Burning is what would emit the Solana
    event our delivery layer fulfils.
  * Delivered: escrow releases to the seller; reputation ticks up (which also
    nudges the bond rate down).
  * No-show: the buyer is refunded 100% from escrow, compensated COMP_RATE
    from the seller's bond, and the seller is slashed a further SLASH_RATE
    into the shared insurance pool — never to either party. slash > comp is
    the anti-fraud arithmetic: self-dealing nets a guaranteed loss per cycle.

The delivery oracle here is two endpoints (confirm/fail) so the demo can act
out both branches. In production it is metered usage; making it
manipulation-resistant is the honest open problem in the submission.
"""

from fastapi import APIRouter, Depends

from . import config
from .deps import get_store
from .errors import BadRequest, InsufficientCapacity
from .models import (
    Delivery,
    DeliveryStatus,
    PoolStatus,
    RedeemRequest,
    WithdrawRequest,
)
from .store import EPS, Store, new_id

router = APIRouter(tags=["settlement"])


@router.post("/redeem", response_model=list[Delivery],
             summary="Burn tokens to take delivery")
def redeem(req: RedeemRequest, store: Store = Depends(get_store)) -> list[Delivery]:
    acct = store.get_account(req.account_id)
    store.get_contract(req.contract_id)

    # Escrow coverage check: deliveries are funded by the redeemer's own
    # purchase escrows (FIFO). See README "Resale & the escrow chain" caveat.
    escrows = [e for e in store.escrows.values()
               if e.buyer_id == acct.id and e.contract_id == req.contract_id
               and e.qty_remaining > EPS]
    covered = sum(e.qty_remaining for e in escrows)
    if covered + EPS < req.qty:
        raise InsufficientCapacity(
            f"only {covered:g} hours of {req.contract_id} have escrow held for "
            f"{acct.id}; cannot redeem {req.qty:g}"
        )

    store.burn_capacity(acct.id, req.contract_id, req.qty)

    deliveries: list[Delivery] = []
    left = req.qty
    for e in escrows:  # dict preserves insertion order => FIFO by trade
        if left <= EPS:
            break
        take = min(left, e.qty_remaining)
        e.qty_remaining -= take
        d = Delivery(id=new_id("dlv"), escrow_id=e.id, contract_id=req.contract_id,
                     buyer_id=acct.id, seller_id=e.seller_id, qty=take,
                     amount=take * e.price, note=req.note)
        deliveries.append(store.add_delivery(d))
        left -= take
    return deliveries


@router.post("/deliveries/{delivery_id}/confirm", response_model=Delivery,
             summary="Oracle: delivery succeeded")
def confirm_delivery(delivery_id: str, store: Store = Depends(get_store)) -> Delivery:
    d = _pending(store, delivery_id)
    store.credit_quote(d.seller_id, d.amount)         # escrow releases to the seller
    store.get_account(d.seller_id).delivered_qty += d.qty  # reputation up, bond rate down
    d.status = DeliveryStatus.delivered
    return d


@router.post("/deliveries/{delivery_id}/fail", response_model=Delivery,
             summary="Oracle: no-show")
def fail_delivery(delivery_id: str, store: Store = Depends(get_store)) -> Delivery:
    d = _pending(store, delivery_id)

    # 1. Full refund from escrow — the buyer's principal was never at risk.
    store.credit_quote(d.buyer_id, d.amount)

    # 2. Compensation for re-buying at short notice, paid from the bond and
    #    capped at provable loss (a flat rate here).
    comp = store.slash_bond(d.seller_id, config.COMP_RATE * d.amount)
    store.credit_quote(d.buyer_id, comp)

    # 3. The punitive slash, strictly larger than comp, goes to the shared
    #    insurance pool — never back to either party.
    slashed = store.slash_bond(d.seller_id, config.SLASH_RATE * d.amount)
    store.pay_insurance_pool(slashed)

    store.get_account(d.seller_id).failed_qty += d.qty  # failure rate now taxes every future auction
    d.status = DeliveryStatus.failed
    d.note = (d.note + " | " if d.note else "") + \
        f"refund {d.amount:.2f}, comp {comp:.2f}, slashed {slashed:.2f} to pool"
    return d


def _pending(store: Store, delivery_id: str) -> Delivery:
    d = store.get_delivery(delivery_id)
    if d.status != DeliveryStatus.pending:
        raise BadRequest(f"delivery {delivery_id} already {d.status.value}")
    return d


@router.get("/deliveries", response_model=list[Delivery], summary="Delivery tickets")
def list_deliveries(store: Store = Depends(get_store)) -> list[Delivery]:
    return list(store.deliveries.values())


@router.get("/pool", response_model=PoolStatus, summary="Insurance pool balance")
def pool(store: Store = Depends(get_store)) -> PoolStatus:
    return PoolStatus(insurance_pool=store.insurance_pool)


@router.post("/accounts/{account_id}/withdraw", summary="Withdraw earned quote")
def withdraw(account_id: str, req: WithdrawRequest,
             store: Store = Depends(get_store)) -> dict:
    store.debit_quote(account_id, req.amount)
    return {"account_id": account_id, "amount": req.amount,
            "destination": req.destination, "status": "settled"}

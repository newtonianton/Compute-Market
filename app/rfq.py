"""
RFQ — the side door for bespoke demand (Layer 3, escape hatch).

Some demand genuinely doesn't fit a grade ("32 H100s, same building, 72h
contiguous"). Buyers broadcast a request; providers who are willing to respond
live quote; the buyer accepts one. Acceptance reuses the same escrow + delivery
machinery as the main floor, so RFQ deals are bonded and slashable too.

RFQ is the escape hatch, not the main floor — the main floor must work for
sellers who never look at it.
"""

from fastapi import APIRouter, Depends

from .deps import get_store
from .errors import BadRequest, NotFound
from .models import (
    AcceptQuote,
    CreateRFQ,
    Delivery,
    Escrow,
    Quote,
    QuoteRequest,
    RFQ,
    RFQStatus,
    Trade,
)
from .store import Store, new_id

router = APIRouter(tags=["rfq"])


@router.post("/rfqs", response_model=RFQ, summary="Broadcast a bespoke request")
def create_rfq(req: CreateRFQ, store: Store = Depends(get_store)) -> RFQ:
    store.get_account(req.buyer_id)
    rfq = RFQ(id=new_id("rfq"), buyer_id=req.buyer_id, spec=req.spec, qty=req.qty)
    store.rfqs[rfq.id] = rfq
    return rfq


@router.get("/rfqs", response_model=list[RFQ], summary="Open requests")
def list_rfqs(store: Store = Depends(get_store)) -> list[RFQ]:
    return list(store.rfqs.values())


@router.post("/rfqs/{rfq_id}/quotes", response_model=Quote, summary="Quote on a request")
def quote(rfq_id: str, req: QuoteRequest, store: Store = Depends(get_store)) -> Quote:
    rfq = store.get_rfq(rfq_id)
    if rfq.status != RFQStatus.open:
        raise BadRequest(f"RFQ is {rfq.status.value}")
    store.get_account(req.provider_id)
    q = Quote(id=new_id("quote"), rfq_id=rfq_id, provider_id=req.provider_id,
              price=req.price)
    store.quotes[q.id] = q
    return q


@router.get("/rfqs/{rfq_id}/quotes", response_model=list[Quote], summary="Quotes received")
def list_quotes(rfq_id: str, store: Store = Depends(get_store)) -> list[Quote]:
    store.get_rfq(rfq_id)
    return [q for q in store.quotes.values() if q.rfq_id == rfq_id]


@router.post("/rfqs/{rfq_id}/accept", response_model=Delivery,
             summary="Accept a quote (escrows funds, opens a delivery)")
def accept(rfq_id: str, req: AcceptQuote, store: Store = Depends(get_store)) -> Delivery:
    rfq = store.get_rfq(rfq_id)
    if rfq.status != RFQStatus.open:
        raise BadRequest(f"RFQ is {rfq.status.value}")
    q = store.quotes.get(req.quote_id)
    if q is None or q.rfq_id != rfq_id:
        raise NotFound(f"quote {req.quote_id!r} not found on this RFQ")

    amount = rfq.qty * q.price
    store.debit_quote(rfq.buyer_id, amount)  # straight into protocol escrow

    contract_id = f"RFQ:{rfq.id}"
    trade = Trade(id=new_id("trade"), contract_id=contract_id, auction_id="rfq",
                  price=q.price, qty=rfq.qty, buyer_id=rfq.buyer_id,
                  seller_id=q.provider_id)
    store.append_trade(trade)
    escrow = store.add_escrow(Escrow(id=new_id("escrow"), trade_id=trade.id,
                                     contract_id=contract_id, buyer_id=rfq.buyer_id,
                                     seller_id=q.provider_id, price=q.price,
                                     qty_remaining=0.0))  # delivery opens immediately
    d = Delivery(id=new_id("dlv"), escrow_id=escrow.id, contract_id=contract_id,
                 buyer_id=rfq.buyer_id, seller_id=q.provider_id, qty=rfq.qty,
                 amount=amount, note=f"RFQ: {rfq.spec}")
    store.add_delivery(d)
    rfq.status = RFQStatus.accepted
    return d

"""
Auction — one round, one price (Layer 3).

A uniform-price batch auction per contract:

  * Sellers post a one-time standing floor ("sell at anything >= X"); posting
    reserves their capacity so it can't be double-sold.
  * Buyers post a standing maximum ("buy at anything <= Y"); posting escrows
    qty * max_price so bids are always fully collateralized.
  * A clearing round stacks all floors (cheapest first) and bids (highest
    first) and finds the single price where supply meets demand. Everyone
    trades at that one price, so truthful quoting is the dominant strategy.

Reliability premium: each floor is *ranked* at floor * (1 + failure_rate)
(newcomers get a small default rate), so a flaky $2.00 can rank behind a
reliable $2.20 — but everyone who clears is still paid the same clearing price.

A round with no crossing clears with no trade. That is a correct outcome,
not an error.
"""

from fastapi import APIRouter, Depends

from . import config
from .deps import get_store
from .errors import BadRequest
from .models import (
    AuctionResult,
    Bid,
    BidRequest,
    Book,
    Escrow,
    Floor,
    FloorRequest,
    OrderStatus,
    PriceLevel,
    Trade,
)
from .store import EPS, Store, new_id

router = APIRouter(tags=["auction"])


# --- reliability premium -------------------------------------------------------

def effective_price(store: Store, floor: Floor) -> float:
    """Rank-only price: the floor bumped by the seller's measured failure rate
    (or the newcomer default). Payment still happens at the clearing price."""
    acct = store.get_account(floor.account_id)
    rate = acct.failure_rate
    if rate is None:
        rate = config.NEWCOMER_FAILURE_RATE
    return floor.floor_price * (1.0 + rate)


# --- the clearing engine --------------------------------------------------------

def clear_auction(store: Store, contract_id: str) -> AuctionResult:
    contract = store.get_contract(contract_id)
    floors = sorted(store.open_floors(contract_id),
                    key=lambda f: (effective_price(store, f), f.seq))
    bids = sorted(store.open_bids(contract_id),
                  key=lambda b: (-b.max_price, b.seq))

    # Candidate prices: every quoted level. For each, executable volume is
    # min(supply willing at <= p, demand willing at >= p).
    candidates = sorted(
        {effective_price(store, f) for f in floors} | {b.max_price for b in bids}
    )
    best_price, best_volume = None, 0.0
    for p in candidates:
        supply = sum(f.remaining for f in floors if effective_price(store, f) <= p + EPS)
        demand = sum(b.remaining for b in bids if b.max_price >= p - EPS)
        vol = min(supply, demand)
        # Prefer max volume; at equal volume prefer the higher price (the
        # demand-side end of the crossing range, matching the worked example).
        if vol > best_volume + EPS or (abs(vol - best_volume) <= EPS and vol > EPS
                                       and (best_price is None or p > best_price)):
            best_price, best_volume = p, vol

    auction = AuctionResult(
        id=new_id("auction"), contract_id=contract_id,
        clearing_price=None, volume=0.0,
    )

    if best_price is None or best_volume <= EPS:
        return store.append_auction(auction)  # empty round: valid outcome

    price = best_price
    auction.clearing_price = price
    auction.volume = best_volume
    contract.last_clearing_price = price  # the public index point
    grade = store.get_grade(contract.grade_id)
    grade.reference_price = price         # bond sizing now tracks the index

    # Allocate greedily in priority order until the crossing volume is done.
    eligible_floors = [f for f in floors if effective_price(store, f) <= price + EPS]
    eligible_bids = [b for b in bids if b.max_price >= price - EPS]
    remaining = best_volume
    fi = bi = 0
    while remaining > EPS and fi < len(eligible_floors) and bi < len(eligible_bids):
        floor, bid = eligible_floors[fi], eligible_bids[bi]
        fill = min(floor.remaining, bid.remaining, remaining)
        if fill > EPS:
            _settle_fill(store, auction, contract_id, floor, bid, price, fill)
            remaining -= fill
        if floor.remaining <= EPS:
            floor.status = OrderStatus.filled
            fi += 1
        if bid.remaining <= EPS:
            bid.status = OrderStatus.filled
            bi += 1

    return store.append_auction(auction)


def _settle_fill(store: Store, auction: AuctionResult, contract_id: str,
                 floor: Floor, bid: Bid, price: float, fill: float) -> None:
    """Atomic with the match: tokens move seller -> buyer now; the buyer's
    money moves bid-escrow -> trade escrow, held until delivery confirms
    (Layer 5). Overpay headroom (max_price - clearing) refunds immediately."""
    store.move_locked_capacity(floor.account_id, bid.account_id, contract_id, fill)

    store.spend_locked_quote(bid.account_id, fill * bid.max_price)
    store.credit_quote(bid.account_id, fill * (bid.max_price - price))  # refund headroom
    bid.locked_quote -= fill * bid.max_price

    trade = Trade(id=new_id("trade"), contract_id=contract_id, auction_id=auction.id,
                  price=price, qty=fill, buyer_id=bid.account_id,
                  seller_id=floor.account_id)
    store.append_trade(trade)
    auction.trades.append(trade)

    store.add_escrow(Escrow(id=new_id("escrow"), trade_id=trade.id,
                            contract_id=contract_id, buyer_id=bid.account_id,
                            seller_id=floor.account_id, price=price,
                            qty_remaining=fill))

    floor.remaining -= fill
    bid.remaining -= fill


# --- order endpoints -----------------------------------------------------------

@router.post("/floors", response_model=Floor, summary="Post a standing sell floor")
def post_floor(req: FloorRequest, store: Store = Depends(get_store)) -> Floor:
    """Set and forget: reserves the seller's tokens and participates in every
    round until filled or cancelled. Any token holder may post — that is what
    lets capacity behave like inventory and resell into later rounds."""
    store.get_account(req.account_id)
    store.get_contract(req.contract_id)
    store.reserve_capacity(req.account_id, req.contract_id, req.qty)
    floor = Floor(id=new_id("floor"), seq=store.next_seq(), account_id=req.account_id,
                  contract_id=req.contract_id, floor_price=req.floor_price,
                  qty=req.qty, remaining=req.qty)
    store.floors[floor.id] = floor
    return floor


@router.post("/bids", response_model=Bid, summary="Post a standing buy maximum")
def post_bid(req: BidRequest, store: Store = Depends(get_store)) -> Bid:
    store.get_account(req.account_id)
    store.get_contract(req.contract_id)
    cost = req.qty * req.max_price
    store.lock_quote(req.account_id, cost)  # raises InsufficientFunds
    bid = Bid(id=new_id("bid"), seq=store.next_seq(), account_id=req.account_id,
              contract_id=req.contract_id, max_price=req.max_price,
              qty=req.qty, remaining=req.qty, locked_quote=cost)
    store.bids[bid.id] = bid
    return bid


@router.post("/floors/{floor_id}/cancel", response_model=Floor, summary="Cancel a floor")
def cancel_floor(floor_id: str, store: Store = Depends(get_store)) -> Floor:
    floor = store.get_floor(floor_id)
    if floor.status != OrderStatus.open:
        raise BadRequest(f"floor is {floor.status.value}, cannot cancel")
    store.release_capacity(floor.account_id, floor.contract_id, floor.remaining)
    floor.status = OrderStatus.cancelled
    return floor


@router.post("/bids/{bid_id}/cancel", response_model=Bid, summary="Cancel a bid")
def cancel_bid(bid_id: str, store: Store = Depends(get_store)) -> Bid:
    bid = store.get_bid(bid_id)
    if bid.status != OrderStatus.open:
        raise BadRequest(f"bid is {bid.status.value}, cannot cancel")
    store.unlock_quote(bid.account_id, bid.locked_quote)
    bid.locked_quote = 0.0
    bid.status = OrderStatus.cancelled
    return bid


# --- market views -----------------------------------------------------------------

@router.post("/auctions/{contract_id}/clear", response_model=AuctionResult,
             summary="Run a clearing round now")
def run_auction(contract_id: str, store: Store = Depends(get_store)) -> AuctionResult:
    """In production a scheduler calls this every interval; the demo triggers
    it manually so judges can watch a round happen."""
    return clear_auction(store, contract_id)


@router.get("/auctions", response_model=list[AuctionResult],
            summary="Clearing history — the public index")
def list_auctions(store: Store = Depends(get_store)) -> list[AuctionResult]:
    return store.auctions


@router.get("/book/{contract_id}", response_model=Book, summary="Standing orders")
def book(contract_id: str, store: Store = Depends(get_store)) -> Book:
    store.get_contract(contract_id)
    bid_levels: dict[float, float] = {}
    for b in store.open_bids(contract_id):
        bid_levels[b.max_price] = bid_levels.get(b.max_price, 0.0) + b.remaining
    ask_levels: dict[float, float] = {}
    for f in store.open_floors(contract_id):
        p = round(effective_price(store, f), 6)
        ask_levels[p] = ask_levels.get(p, 0.0) + f.remaining
    return Book(
        contract_id=contract_id,
        bids=[PriceLevel(price=p, qty=q) for p, q in sorted(bid_levels.items(), reverse=True)],
        asks=[PriceLevel(price=p, qty=q) for p, q in sorted(ask_levels.items())],
    )


@router.get("/trades", response_model=list[Trade], summary="Trade history (the tape)")
def trades(store: Store = Depends(get_store)) -> list[Trade]:
    return store.trades

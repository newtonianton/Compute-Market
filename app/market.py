"""
Market — price discovery, order flow, and settlement.

A compact continuous order book (CLOB) with price-time priority and partial
fills. This is where "supply, demand, pricing, and settlement" become obvious:

  * A SELL reserves the seller's capacity (free -> locked) so it can't be
    double-sold.
  * A BUY escrows the buyer's quote currency (free -> locked) so it can't be
    double-spent.
  * On a match, the resting order (the "maker") sets the price. Capacity moves
    seller -> buyer and quote moves buyer -> seller in the same step: settlement
    is atomic with the fill. A taking buyer who crossed above the maker price is
    refunded the difference.

If you'd rather price by AMM, auction, or RFQ, replace `match()` and keep the
reserve/escrow accounting — the rest of the system doesn't care how price is
formed.
"""

from fastapi import APIRouter, Depends

from .deps import get_store
from .errors import BadRequest
from .models import (
    Order,
    OrderBook,
    OrderRequest,
    OrderResult,
    OrderStatus,
    PriceLevel,
    Side,
    Trade,
)
from .store import EPS, Store, new_id

router = APIRouter(tags=["market"])


def match(store: Store, order: Order) -> list[Trade]:
    """Match `order` against the resting book, mutating balances and recording
    trades. Returns the trades produced. Any unfilled remainder rests as an open
    order."""
    trades: list[Trade] = []

    if order.side == Side.buy:
        # Cross against asks: cheapest first, then oldest first.
        book = sorted(store.open_orders(order.sku, Side.sell), key=lambda o: (o.price, o.seq))
        for ask in book:
            if order.remaining <= EPS:
                break
            if ask.price > order.price + EPS:
                break  # best ask is above our limit -> nothing left to match
            fill = min(order.remaining, ask.remaining)
            price = ask.price  # maker sets the price

            store.move_locked_capacity(ask.account_id, order.account_id, order.sku, fill)
            store.spend_locked_quote(order.account_id, fill * order.price)   # release buyer escrow
            store.credit_quote(order.account_id, fill * (order.price - price))  # refund overpay
            store.credit_quote(ask.account_id, fill * price)                 # pay the seller

            order.locked_quote -= fill * order.price
            order.remaining -= fill
            ask.remaining -= fill
            if ask.remaining <= EPS:
                ask.status = OrderStatus.filled
            trades.append(_record(store, order.sku, price, fill, order.account_id, ask.account_id, order.id, ask.id))

    else:  # SELL
        # Cross against bids: highest first, then oldest first.
        book = sorted(store.open_orders(order.sku, Side.buy), key=lambda o: (-o.price, o.seq))
        for bid in book:
            if order.remaining <= EPS:
                break
            if bid.price < order.price - EPS:
                break
            fill = min(order.remaining, bid.remaining)
            price = bid.price  # maker sets the price (== buyer's escrowed price)

            store.move_locked_capacity(order.account_id, bid.account_id, order.sku, fill)
            store.spend_locked_quote(bid.account_id, fill * bid.price)
            store.credit_quote(order.account_id, fill * price)

            bid.locked_quote -= fill * bid.price
            order.remaining -= fill
            bid.remaining -= fill
            if bid.remaining <= EPS:
                bid.status = OrderStatus.filled
            trades.append(_record(store, order.sku, price, fill, bid.account_id, order.account_id, bid.id, order.id))

    if order.remaining <= EPS:
        order.status = OrderStatus.filled
    return trades


def _record(store, sku, price, qty, buyer_id, seller_id, buy_oid, sell_oid) -> Trade:
    t = Trade(
        id=new_id("trade"),
        sku=sku,
        price=price,
        qty=qty,
        buyer_id=buyer_id,
        seller_id=seller_id,
        buy_order_id=buy_oid,
        sell_order_id=sell_oid,
    )
    return store.append_trade(t)


@router.post("/orders", response_model=OrderResult, summary="Place a buy or sell order")
def place_order(req: OrderRequest, store: Store = Depends(get_store)) -> OrderResult:
    store.get_account(req.account_id)  # ensure the account exists
    from . import config

    if req.sku not in {s.sku for s in config.DEFAULT_SKUS}:
        raise BadRequest(f"unknown sku {req.sku!r}; see GET /skus")

    order = Order(
        id=new_id("order"),
        seq=store.next_seq(),
        account_id=req.account_id,
        side=req.side,
        sku=req.sku,
        price=req.price,
        qty=req.qty,
        remaining=req.qty,
    )

    # Reserve up front so resting orders are always fully collateralized.
    if order.side == Side.buy:
        cost = req.qty * req.price
        store.lock_quote(req.account_id, cost)  # raises InsufficientFunds
        order.locked_quote = cost
    else:
        store.reserve_capacity(req.account_id, req.sku, req.qty)  # raises InsufficientCapacity

    store.add_order(order)
    trades = match(store, order)
    return OrderResult(order=order, trades=trades)


@router.post("/orders/{order_id}/cancel", response_model=Order, summary="Cancel a resting order")
def cancel_order(order_id: str, store: Store = Depends(get_store)) -> Order:
    order = store.get_order(order_id)
    if order.status != OrderStatus.open:
        raise BadRequest(f"order {order_id} is {order.status.value}, cannot cancel")
    if order.side == Side.buy:
        store.unlock_quote(order.account_id, order.locked_quote)
        order.locked_quote = 0.0
    else:
        store.release_capacity(order.account_id, order.sku, order.remaining)
    order.status = OrderStatus.cancelled
    return order


@router.get("/orderbook/{sku}", response_model=OrderBook, summary="Aggregated order book")
def orderbook(sku: str, store: Store = Depends(get_store)) -> OrderBook:
    bids = _aggregate(store.open_orders(sku, Side.buy), reverse=True)
    asks = _aggregate(store.open_orders(sku, Side.sell), reverse=False)
    return OrderBook(sku=sku, bids=bids, asks=asks)


def _aggregate(orders: list[Order], reverse: bool) -> list[PriceLevel]:
    levels: dict[float, float] = {}
    for o in orders:
        levels[o.price] = levels.get(o.price, 0.0) + o.remaining
    return [PriceLevel(price=p, qty=q) for p, q in sorted(levels.items(), reverse=reverse)]


@router.get("/orders", response_model=list[Order], summary="List all orders")
def list_orders(store: Store = Depends(get_store)) -> list[Order]:
    return store.list_orders()


@router.get("/orders/{order_id}", response_model=Order, summary="Order detail")
def get_order(order_id: str, store: Store = Depends(get_store)) -> Order:
    return store.get_order(order_id)


@router.get("/trades", response_model=list[Trade], summary="Trade history (the tape)")
def trades(store: Store = Depends(get_store)) -> list[Trade]:
    return store.list_trades()

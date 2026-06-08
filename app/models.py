"""
Data models.

These Pydantic models double as (a) the domain entities the store holds and
(b) the request/response schemas FastAPI uses to validate input and render the
interactive docs at /docs. Keeping them in one place means the API and the
internal state never drift apart.

Note: balances are plain floats for readability. Real money should use integer
minor-units or Decimal to avoid rounding error — see the README's "Money"
caveat. Swapping the type here is a deliberate, localized change.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Side(str, Enum):
    buy = "buy"
    sell = "sell"


class OrderStatus(str, Enum):
    open = "open"
    filled = "filled"
    cancelled = "cancelled"


class Role(str, Enum):
    provider = "provider"
    purchaser = "purchaser"


# --- Domain entities ---------------------------------------------------------

class Account(BaseModel):
    """A market participant. Any account may hold capacity and trade it — that
    is what lets pure speculators provide liquidity without ever taking
    delivery. Roles only gate the privileged actions: minting and (optionally)
    redeeming."""

    id: str
    label: str = ""
    is_provider: bool = False
    is_purchaser: bool = False
    provider_whitelisted: bool = False
    purchaser_whitelisted: bool = False

    # quote-currency balances (e.g. USDC credits)
    quote_free: float = 0.0
    quote_locked: float = 0.0  # escrowed behind resting buy orders

    # capacity-token balances, keyed by SKU
    capacity_free: dict[str, float] = Field(default_factory=dict)
    capacity_locked: dict[str, float] = Field(default_factory=dict)  # behind resting sells


class Order(BaseModel):
    id: str
    seq: int  # monotonic; gives time priority at equal price
    account_id: str
    side: Side
    sku: str
    price: float
    qty: float
    remaining: float
    locked_quote: float = 0.0  # for buys: quote still escrowed
    status: OrderStatus = OrderStatus.open
    created_at: datetime = Field(default_factory=_now)


class Trade(BaseModel):
    id: str
    sku: str
    price: float
    qty: float
    buyer_id: str
    seller_id: str
    buy_order_id: str
    sell_order_id: str
    created_at: datetime = Field(default_factory=_now)


class Mint(BaseModel):
    id: str
    provider_id: str
    sku: str
    qty: float
    created_at: datetime = Field(default_factory=_now)


class Redemption(BaseModel):
    """A buyer burning capacity tokens to take delivery. In a real system this
    is where you'd hand back a signed voucher / API key / cluster lease."""

    id: str
    account_id: str
    sku: str
    qty: float
    note: str = ""
    status: str = "delivered"
    created_at: datetime = Field(default_factory=_now)


class Payout(BaseModel):
    """A seller withdrawing earned quote currency out of the market."""

    id: str
    account_id: str
    amount: float
    destination: str = ""
    status: str = "settled"
    created_at: datetime = Field(default_factory=_now)


# --- Request bodies ----------------------------------------------------------

class CreateAccount(BaseModel):
    label: str = ""
    wallet: Optional[str] = Field(
        default=None, description="Optional account id (e.g. a Solana address). Auto-generated if omitted."
    )
    provider: bool = False
    purchaser: bool = False


class Deposit(BaseModel):
    amount: float = Field(gt=0, examples=[1000.0])


class MintRequest(BaseModel):
    provider_id: str
    sku: str = Field(examples=["H100-HOUR"])
    qty: float = Field(gt=0, examples=[100.0])


class RedeemRequest(BaseModel):
    account_id: str
    sku: str = Field(examples=["H100-HOUR"])
    qty: float = Field(gt=0, examples=[10.0])
    note: str = ""


class OrderRequest(BaseModel):
    account_id: str
    side: Side
    sku: str = Field(examples=["H100-HOUR"])
    qty: float = Field(gt=0, examples=[10.0])
    price: float = Field(gt=0, examples=[2.50], description="Price per unit in the quote currency.")


class WithdrawRequest(BaseModel):
    amount: float = Field(gt=0, examples=[50.0])
    destination: str = Field(default="", description="Where funds settle to, e.g. a wallet address.")


# --- Response shapes ---------------------------------------------------------

class OrderResult(BaseModel):
    order: Order
    trades: list[Trade] = Field(default_factory=list)


class PriceLevel(BaseModel):
    price: float
    qty: float


class OrderBook(BaseModel):
    sku: str
    bids: list[PriceLevel]  # highest price first
    asks: list[PriceLevel]  # lowest price first

"""
Data models.

Pydantic models double as (a) the entities the in-memory store holds and
(b) the FastAPI request/response schemas, so the API and internal state never
drift apart.

Money note: balances are floats for hackathon readability. Production should
use integer minor-units or Decimal; the swap is deliberately localized here.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Layer 1: grades & contracts ---------------------------------------------

class Grade(BaseModel):
    """A predicate SKU: a checklist with a permanent fingerprint."""

    id: str                      # e.g. "EU-H100.v1"
    code: str
    version: int
    checklist: str               # the human-readable contract text
    fingerprint: str             # sha256(checklist) — the id can't drift
    requirements: dict           # machine-checkable form, used by attestation
    reference_price: float       # bond sizing seed; replaced by the live index


class Contract(BaseModel):
    """A tradeable book: grade x delivery window. On Solana this is one SPL
    token mint; here it is one order book and one balance key."""

    id: str                      # e.g. "EU-H100.v1@2026-W30"
    grade_id: str
    window: str
    last_clearing_price: Optional[float] = None


# --- Layer 4: participants ----------------------------------------------------

class Account(BaseModel):
    id: str
    label: str = ""

    # quote-currency balances
    quote_free: float = 0.0
    quote_locked: float = 0.0    # escrowed behind resting bids

    # collateral (Layer 4: bonding)
    bond: float = 0.0

    # capacity-token balances, keyed by contract id
    capacity_free: dict[str, float] = Field(default_factory=dict)
    capacity_locked: dict[str, float] = Field(default_factory=dict)  # behind floors

    # attestation: grade ids this account may mint
    attested_grades: list[str] = Field(default_factory=list)

    # reputation (Layer 4): drives both the bond rate and the auction premium
    minted_qty: float = 0.0
    delivered_qty: float = 0.0
    failed_qty: float = 0.0

    @property
    def failure_rate(self) -> Optional[float]:
        total = self.delivered_qty + self.failed_qty
        return (self.failed_qty / total) if total > 0 else None

    @property
    def outstanding_qty(self) -> float:
        """Minted hours not yet resolved — what the bond must cover."""
        return max(0.0, self.minted_qty - self.delivered_qty - self.failed_qty)


# --- Layer 3: orders, auctions, trades -----------------------------------------

class OrderStatus(str, Enum):
    open = "open"
    filled = "filled"
    cancelled = "cancelled"


class Floor(BaseModel):
    """A seller's standing floor: set once, participates in every round."""

    id: str
    seq: int
    account_id: str
    contract_id: str
    floor_price: float
    qty: float
    remaining: float
    status: OrderStatus = OrderStatus.open
    created_at: datetime = Field(default_factory=_now)


class Bid(BaseModel):
    """A buyer's standing maximum. Escrow = remaining * max_price."""

    id: str
    seq: int
    account_id: str
    contract_id: str
    max_price: float
    qty: float
    remaining: float
    locked_quote: float = 0.0
    status: OrderStatus = OrderStatus.open
    created_at: datetime = Field(default_factory=_now)


class Trade(BaseModel):
    id: str
    contract_id: str
    auction_id: str
    price: float                 # the uniform clearing price
    qty: float
    buyer_id: str
    seller_id: str
    created_at: datetime = Field(default_factory=_now)


class AuctionResult(BaseModel):
    """One clearing round. clearing_price is the public index point."""

    id: str
    contract_id: str
    clearing_price: Optional[float]  # None => round cleared with no trade (a valid outcome)
    volume: float
    trades: list[Trade] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


# --- Layer 5: escrow, delivery, pool --------------------------------------------

class Escrow(BaseModel):
    """Buyer money held by the protocol per trade until delivery confirms."""

    id: str
    trade_id: str
    contract_id: str
    buyer_id: str
    seller_id: str
    price: float
    qty_remaining: float


class DeliveryStatus(str, Enum):
    pending = "pending"
    delivered = "delivered"
    failed = "failed"


class Delivery(BaseModel):
    """Created when a buyer burns tokens. The delivery oracle (here: an
    endpoint; in prod: metered usage) resolves it to delivered or failed."""

    id: str
    escrow_id: str
    contract_id: str
    buyer_id: str
    seller_id: str
    qty: float
    amount: float                # qty * trade price
    note: str = ""
    status: DeliveryStatus = DeliveryStatus.pending
    created_at: datetime = Field(default_factory=_now)


class Mint(BaseModel):
    id: str
    provider_id: str
    contract_id: str
    qty: float
    bond_rate: float
    created_at: datetime = Field(default_factory=_now)


# --- RFQ side door ---------------------------------------------------------------

class RFQStatus(str, Enum):
    open = "open"
    accepted = "accepted"
    cancelled = "cancelled"


class RFQ(BaseModel):
    id: str
    buyer_id: str
    spec: str                    # free text — bespoke by definition
    qty: float
    status: RFQStatus = RFQStatus.open
    created_at: datetime = Field(default_factory=_now)


class Quote(BaseModel):
    id: str
    rfq_id: str
    provider_id: str
    price: float
    created_at: datetime = Field(default_factory=_now)


# --- Request bodies ---------------------------------------------------------------

class CreateAccount(BaseModel):
    label: str = ""
    wallet: Optional[str] = Field(
        default=None, description="Optional account id (e.g. a Solana address)."
    )


class DepositRequest(BaseModel):
    amount: float = Field(gt=0, examples=[1000.0])


class BondRequest(BaseModel):
    amount: float = Field(gt=0, examples=[120.0], description="Moves quote_free into bond.")


class AttestRequest(BaseModel):
    """Hackathon attestation: a benchmark result checked against the grade
    checklist. Roadmap: TEE attestation signed by the chip itself."""

    grade_id: str = Field(examples=["EU-H100.v1"])
    gpu_model: str = Field(examples=["H100-SXM"])
    vram_gb: float = Field(examples=[80])
    interconnect_tbps: float = Field(examples=[3.2])
    region: str = Field(examples=["EU-WEST"])


class MintRequest(BaseModel):
    provider_id: str
    contract_id: str = Field(examples=["EU-H100.v1@2026-W30"])
    qty: float = Field(gt=0, examples=[40.0])


class FloorRequest(BaseModel):
    account_id: str
    contract_id: str
    qty: float = Field(gt=0, examples=[40.0])
    floor_price: float = Field(gt=0, examples=[1.50], description="Sell at anything >= this.")


class BidRequest(BaseModel):
    account_id: str
    contract_id: str
    qty: float = Field(gt=0, examples=[30.0])
    max_price: float = Field(gt=0, examples=[2.40], description="Buy at anything <= this.")


class RedeemRequest(BaseModel):
    account_id: str
    contract_id: str
    qty: float = Field(gt=0, examples=[30.0])
    note: str = ""


class WithdrawRequest(BaseModel):
    amount: float = Field(gt=0)
    destination: str = ""


class CreateRFQ(BaseModel):
    buyer_id: str
    spec: str = Field(examples=["32x H100 same building, 3.2Tbps all-to-all, 72h contiguous"])
    qty: float = Field(gt=0)


class QuoteRequest(BaseModel):
    provider_id: str
    price: float = Field(gt=0)


class AcceptQuote(BaseModel):
    quote_id: str


# --- Response shapes ----------------------------------------------------------------

class PriceLevel(BaseModel):
    price: float
    qty: float


class BookSide(BaseModel):
    levels: list[PriceLevel]


class Book(BaseModel):
    contract_id: str
    bids: list[PriceLevel]           # highest first
    asks: list[PriceLevel]           # ranked by effective (reliability-bumped) price
    next_clearing_hint: str = "POST /auctions/{contract_id}/clear to run a round"


class PoolStatus(BaseModel):
    insurance_pool: float

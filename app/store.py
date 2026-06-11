"""
Store — single in-memory source of truth plus the balance-moving primitives.

Every transfer of value goes through a named method here (lock_quote,
slash_bond, move_capacity, ...). The market/auction/settlement layers compose
these primitives but never touch balances directly, which is what keeps the
accounting auditable and the engine swappable.

Swap this class for Postgres or on-chain programs without touching the routers.
"""

import hashlib
import itertools
import uuid

from . import config
from .errors import (
    BadRequest,
    InsufficientBond,
    InsufficientCapacity,
    InsufficientFunds,
    NotFound,
)
from .models import (
    Account,
    AuctionResult,
    Bid,
    Contract,
    Delivery,
    Escrow,
    Floor,
    Grade,
    Mint,
    OrderStatus,
    Quote,
    RFQ,
    Trade,
)

EPS = 1e-9


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Store:
    def __init__(self) -> None:
        self.accounts: dict[str, Account] = {}
        self.grades: dict[str, Grade] = {}
        self.contracts: dict[str, Contract] = {}
        self.floors: dict[str, Floor] = {}
        self.bids: dict[str, Bid] = {}
        self.trades: list[Trade] = []
        self.auctions: list[AuctionResult] = []
        self.escrows: dict[str, Escrow] = {}
        self.deliveries: dict[str, Delivery] = {}
        self.mints: list[Mint] = []
        self.rfqs: dict[str, RFQ] = {}
        self.quotes: dict[str, Quote] = {}
        self.insurance_pool: float = 0.0
        self._seq = itertools.count(1)
        self._bootstrap()

    # --- bootstrap: grades x windows = books -----------------------------------

    def _bootstrap(self) -> None:
        windows = config.upcoming_windows()
        for g in config.GRADE_CATALOGUE:
            gid = f"{g['code']}.v{g['version']}"
            self.grades[gid] = Grade(
                id=gid,
                code=g["code"],
                version=g["version"],
                checklist=g["checklist"],
                fingerprint=fingerprint(g["checklist"]),
                requirements=g["requirements"],
                reference_price=g["reference_price"],
            )
            for w in windows:
                cid = f"{gid}@{w}"
                self.contracts[cid] = Contract(id=cid, grade_id=gid, window=w)

    def next_seq(self) -> int:
        return next(self._seq)

    # --- lookups -----------------------------------------------------------------

    def get_account(self, account_id: str) -> Account:
        if account_id not in self.accounts:
            raise NotFound(f"unknown account {account_id!r}")
        return self.accounts[account_id]

    def add_account(self, acct: Account) -> Account:
        if acct.id in self.accounts:
            raise BadRequest(f"account {acct.id!r} already exists")
        self.accounts[acct.id] = acct
        return acct

    def get_grade(self, grade_id: str) -> Grade:
        if grade_id not in self.grades:
            raise NotFound(f"unknown grade {grade_id!r}; see GET /grades")
        return self.grades[grade_id]

    def get_contract(self, contract_id: str) -> Contract:
        if contract_id not in self.contracts:
            raise NotFound(f"unknown contract {contract_id!r}; see GET /contracts")
        return self.contracts[contract_id]

    def get_floor(self, floor_id: str) -> Floor:
        if floor_id not in self.floors:
            raise NotFound(f"unknown floor {floor_id!r}")
        return self.floors[floor_id]

    def get_bid(self, bid_id: str) -> Bid:
        if bid_id not in self.bids:
            raise NotFound(f"unknown bid {bid_id!r}")
        return self.bids[bid_id]

    def get_escrow(self, escrow_id: str) -> Escrow:
        if escrow_id not in self.escrows:
            raise NotFound(f"unknown escrow {escrow_id!r}")
        return self.escrows[escrow_id]

    def get_delivery(self, delivery_id: str) -> Delivery:
        if delivery_id not in self.deliveries:
            raise NotFound(f"unknown delivery {delivery_id!r}")
        return self.deliveries[delivery_id]

    def get_rfq(self, rfq_id: str) -> RFQ:
        if rfq_id not in self.rfqs:
            raise NotFound(f"unknown RFQ {rfq_id!r}")
        return self.rfqs[rfq_id]

    def open_floors(self, contract_id: str) -> list[Floor]:
        return [f for f in self.floors.values()
                if f.contract_id == contract_id and f.status == OrderStatus.open]

    def open_bids(self, contract_id: str) -> list[Bid]:
        return [b for b in self.bids.values()
                if b.contract_id == contract_id and b.status == OrderStatus.open]

    # --- quote-currency primitives --------------------------------------------------

    def credit_quote(self, account_id: str, amount: float) -> None:
        self.get_account(account_id).quote_free += amount

    def debit_quote(self, account_id: str, amount: float) -> None:
        acct = self.get_account(account_id)
        if acct.quote_free + EPS < amount:
            raise InsufficientFunds(
                f"{account_id} has {acct.quote_free:.2f} free, needs {amount:.2f}"
            )
        acct.quote_free -= amount

    def lock_quote(self, account_id: str, amount: float) -> None:
        self.debit_quote(account_id, amount)
        self.get_account(account_id).quote_locked += amount

    def unlock_quote(self, account_id: str, amount: float) -> None:
        acct = self.get_account(account_id)
        acct.quote_locked = max(0.0, acct.quote_locked - amount)
        acct.quote_free += amount

    def spend_locked_quote(self, account_id: str, amount: float) -> None:
        """Burn escrowed quote out of the account (it moves into a trade Escrow)."""
        acct = self.get_account(account_id)
        if acct.quote_locked + EPS < amount:
            raise InsufficientFunds(f"{account_id} locked balance too low")
        acct.quote_locked -= amount

    # --- bond primitives (Layer 4) ----------------------------------------------------

    def post_bond(self, account_id: str, amount: float) -> None:
        self.debit_quote(account_id, amount)
        self.get_account(account_id).bond += amount

    def bond_rate(self, acct: Account) -> float:
        """150% for newcomers; every cleanly delivered hour earns it down;
        never below the floor that keeps a failure fully covered."""
        rate = config.BOND_RATE_NEW - config.BOND_RATE_STEP * acct.delivered_qty
        return max(config.BOND_RATE_FLOOR, rate)

    def required_bond(self, acct: Account, extra_qty: float, ref_price: float) -> float:
        return self.bond_rate(acct) * (acct.outstanding_qty + extra_qty) * ref_price

    def slash_bond(self, account_id: str, amount: float) -> float:
        """Take up to `amount` from the bond; returns what was actually taken."""
        acct = self.get_account(account_id)
        taken = min(acct.bond, amount)
        acct.bond -= taken
        return taken

    # --- capacity primitives -------------------------------------------------------------

    def credit_capacity(self, account_id: str, contract_id: str, qty: float) -> None:
        acct = self.get_account(account_id)
        acct.capacity_free[contract_id] = acct.capacity_free.get(contract_id, 0.0) + qty

    def reserve_capacity(self, account_id: str, contract_id: str, qty: float) -> None:
        acct = self.get_account(account_id)
        free = acct.capacity_free.get(contract_id, 0.0)
        if free + EPS < qty:
            raise InsufficientCapacity(
                f"{account_id} has {free:g} free of {contract_id}, needs {qty:g}"
            )
        acct.capacity_free[contract_id] = free - qty
        acct.capacity_locked[contract_id] = acct.capacity_locked.get(contract_id, 0.0) + qty

    def release_capacity(self, account_id: str, contract_id: str, qty: float) -> None:
        acct = self.get_account(account_id)
        acct.capacity_locked[contract_id] = max(
            0.0, acct.capacity_locked.get(contract_id, 0.0) - qty
        )
        acct.capacity_free[contract_id] = acct.capacity_free.get(contract_id, 0.0) + qty

    def move_locked_capacity(self, frm: str, to: str, contract_id: str, qty: float) -> None:
        src = self.get_account(frm)
        locked = src.capacity_locked.get(contract_id, 0.0)
        if locked + EPS < qty:
            raise InsufficientCapacity(f"{frm} locked capacity too low for {contract_id}")
        src.capacity_locked[contract_id] = locked - qty
        self.credit_capacity(to, contract_id, qty)

    def burn_capacity(self, account_id: str, contract_id: str, qty: float) -> None:
        acct = self.get_account(account_id)
        free = acct.capacity_free.get(contract_id, 0.0)
        if free + EPS < qty:
            raise InsufficientCapacity(
                f"{account_id} has {free:g} free of {contract_id}, cannot redeem {qty:g}"
            )
        acct.capacity_free[contract_id] = free - qty

    # --- ledger appends ----------------------------------------------------------------------

    def append_trade(self, t: Trade) -> Trade:
        self.trades.append(t)
        return t

    def append_auction(self, a: AuctionResult) -> AuctionResult:
        self.auctions.append(a)
        return a

    def add_escrow(self, e: Escrow) -> Escrow:
        self.escrows[e.id] = e
        return e

    def add_delivery(self, d: Delivery) -> Delivery:
        self.deliveries[d.id] = d
        return d

    def pay_insurance_pool(self, amount: float) -> None:
        self.insurance_pool += amount


# Module-level singleton; deps.get_store yields it (override in tests).
store = Store()

"""
The store is the single source of truth for market state, and the single place
balance invariants are enforced. It is also the main swap point: to move from a
demo to something durable or on-chain, implement the abstract `Store` methods
against your backend (SQLite, Postgres, a Solana program) and leave everything
else untouched.

Design:
  * Abstract methods = persistence (how entities are stored and fetched).
  * Concrete methods  = accounting (mint, burn, lock, transfer). These are
    written once here in terms of `get_account`, so the rules can't diverge
    between backends.

IMPORTANT for non-memory backends: the accounting methods mutate the Account
object returned by `get_account` and assume that mutation is persisted. A
DB-backed store should either return a live/session-bound object or re-save the
account at the end of each accounting call.
"""

from __future__ import annotations

import itertools
import uuid
from abc import ABC, abstractmethod

from .errors import InsufficientCapacity, InsufficientFunds, NotFound
from .models import Account, Mint, Order, OrderStatus, Payout, Redemption, Side, Trade

# Floating-point slack so that 0.1 + 0.2 style noise never blocks a legitimate
# fill. Real money should use integers/Decimal and drop this entirely.
EPS = 1e-9


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class Store(ABC):
    # --- persistence: accounts ---
    @abstractmethod
    def add_account(self, account: Account) -> Account: ...

    @abstractmethod
    def get_account(self, account_id: str) -> Account: ...

    @abstractmethod
    def list_accounts(self) -> list[Account]: ...

    # --- persistence: orders ---
    @abstractmethod
    def add_order(self, order: Order) -> Order: ...

    @abstractmethod
    def get_order(self, order_id: str) -> Order: ...

    @abstractmethod
    def list_orders(self) -> list[Order]: ...

    @abstractmethod
    def open_orders(self, sku: str, side: Side) -> list[Order]: ...

    @abstractmethod
    def next_seq(self) -> int: ...

    # --- persistence: append-only logs ---
    @abstractmethod
    def append_trade(self, t: Trade) -> Trade: ...

    @abstractmethod
    def list_trades(self) -> list[Trade]: ...

    @abstractmethod
    def append_mint(self, m: Mint) -> Mint: ...

    @abstractmethod
    def list_mints(self) -> list[Mint]: ...

    @abstractmethod
    def append_redemption(self, r: Redemption) -> Redemption: ...

    @abstractmethod
    def list_redemptions(self) -> list[Redemption]: ...

    @abstractmethod
    def append_payout(self, p: Payout) -> Payout: ...

    @abstractmethod
    def list_payouts(self) -> list[Payout]: ...

    # --- accounting: quote currency (written once, reused everywhere) ---
    def credit_quote(self, account_id: str, amount: float) -> None:
        self.get_account(account_id).quote_free += amount

    def lock_quote(self, account_id: str, amount: float) -> None:
        a = self.get_account(account_id)
        if a.quote_free + EPS < amount:
            raise InsufficientFunds(
                f"account {account_id} has {a.quote_free:.4f} free, needs {amount:.4f}"
            )
        a.quote_free -= amount
        a.quote_locked += amount

    def unlock_quote(self, account_id: str, amount: float) -> None:
        a = self.get_account(account_id)
        a.quote_locked -= amount
        a.quote_free += amount

    def spend_locked_quote(self, account_id: str, amount: float) -> None:
        """Consume escrowed quote (it leaves the buyer; the seller is credited
        separately via credit_quote)."""
        self.get_account(account_id).quote_locked -= amount

    def withdraw_quote(self, account_id: str, amount: float) -> None:
        a = self.get_account(account_id)
        if a.quote_free + EPS < amount:
            raise InsufficientFunds(
                f"account {account_id} has {a.quote_free:.4f} free, needs {amount:.4f}"
            )
        a.quote_free -= amount

    # --- accounting: capacity tokens ---
    def mint_capacity(self, account_id: str, sku: str, qty: float) -> None:
        a = self.get_account(account_id)
        a.capacity_free[sku] = a.capacity_free.get(sku, 0.0) + qty

    def burn_capacity(self, account_id: str, sku: str, qty: float) -> None:
        a = self.get_account(account_id)
        if a.capacity_free.get(sku, 0.0) + EPS < qty:
            raise InsufficientCapacity(
                f"account {account_id} holds {a.capacity_free.get(sku, 0.0):.4f} {sku}, needs {qty:.4f}"
            )
        a.capacity_free[sku] -= qty

    def reserve_capacity(self, account_id: str, sku: str, qty: float) -> None:
        a = self.get_account(account_id)
        if a.capacity_free.get(sku, 0.0) + EPS < qty:
            raise InsufficientCapacity(
                f"account {account_id} holds {a.capacity_free.get(sku, 0.0):.4f} {sku}, needs {qty:.4f}"
            )
        a.capacity_free[sku] -= qty
        a.capacity_locked[sku] = a.capacity_locked.get(sku, 0.0) + qty

    def release_capacity(self, account_id: str, sku: str, qty: float) -> None:
        a = self.get_account(account_id)
        a.capacity_locked[sku] = a.capacity_locked.get(sku, 0.0) - qty
        a.capacity_free[sku] = a.capacity_free.get(sku, 0.0) + qty

    def move_locked_capacity(self, from_id: str, to_id: str, sku: str, qty: float) -> None:
        """Settle a fill: reserved capacity leaves the seller and lands free
        with the buyer."""
        a = self.get_account(from_id)
        b = self.get_account(to_id)
        a.capacity_locked[sku] = a.capacity_locked.get(sku, 0.0) - qty
        b.capacity_free[sku] = b.capacity_free.get(sku, 0.0) + qty


class InMemoryStore(Store):
    """Everything lives in dicts/lists and resets on restart. Perfect for a
    demo; replace with a durable backend by subclassing Store."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._orders: dict[str, Order] = {}
        self._trades: list[Trade] = []
        self._mints: list[Mint] = []
        self._redemptions: list[Redemption] = []
        self._payouts: list[Payout] = []
        self._seq = itertools.count(1)

    def add_account(self, account: Account) -> Account:
        self._accounts[account.id] = account
        return account

    def get_account(self, account_id: str) -> Account:
        a = self._accounts.get(account_id)
        if a is None:
            raise NotFound(f"account {account_id} not found")
        return a

    def list_accounts(self) -> list[Account]:
        return list(self._accounts.values())

    def add_order(self, order: Order) -> Order:
        self._orders[order.id] = order
        return order

    def get_order(self, order_id: str) -> Order:
        o = self._orders.get(order_id)
        if o is None:
            raise NotFound(f"order {order_id} not found")
        return o

    def list_orders(self) -> list[Order]:
        return list(self._orders.values())

    def open_orders(self, sku: str, side: Side) -> list[Order]:
        return [
            o
            for o in self._orders.values()
            if o.status == OrderStatus.open and o.sku == sku and o.side == side
        ]

    def next_seq(self) -> int:
        return next(self._seq)

    def append_trade(self, t: Trade) -> Trade:
        self._trades.append(t)
        return t

    def list_trades(self) -> list[Trade]:
        return list(self._trades)

    def append_mint(self, m: Mint) -> Mint:
        self._mints.append(m)
        return m

    def list_mints(self) -> list[Mint]:
        return list(self._mints)

    def append_redemption(self, r: Redemption) -> Redemption:
        self._redemptions.append(r)
        return r

    def list_redemptions(self) -> list[Redemption]:
        return list(self._redemptions)

    def append_payout(self, p: Payout) -> Payout:
        self._payouts.append(p)
        return p

    def list_payouts(self) -> list[Payout]:
        return list(self._payouts)

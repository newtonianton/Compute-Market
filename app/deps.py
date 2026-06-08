"""
Store wiring.

Routers depend on `get_store` rather than importing a global, so tests can swap
in a fresh store and a future backend can be dropped in from one place.
"""

from .store import InMemoryStore, Store

_store: Store = InMemoryStore()


def get_store() -> Store:
    return _store


def set_store(store: Store) -> None:
    """Replace the active store (used by tests; also handy if you add a durable
    backend and want to select it at startup)."""
    global _store
    _store = store

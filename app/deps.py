"""FastAPI dependencies. Tests swap the store by reassigning `store.store`
or calling reset_store()."""

from . import store as store_module
from .store import Store


def get_store() -> Store:
    return store_module.store


def reset_store() -> Store:
    """Fresh market state (used by tests and the demo reset endpoint)."""
    store_module.store = Store()
    return store_module.store

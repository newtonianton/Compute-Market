"""
End-to-end tests. These double as living documentation of the market flow and
as your verification harness: run `pytest` after any change to confirm the
mint -> list -> buy -> redeem -> settle path and the accounting invariants still
hold.

    pytest -q
"""

from fastapi.testclient import TestClient

from app.deps import set_store
from app.main import app
from app.store import InMemoryStore

client = TestClient(app)


def setup_function() -> None:
    # Fresh, isolated state for every test.
    set_store(InMemoryStore())


def test_full_flow_mint_trade_redeem_settle() -> None:
    # Provider registers and mints 100 H100-hours.
    provider = client.post("/providers", json={"label": "Acme GPU"}).json()
    client.post("/capacity/mint", json={"provider_id": provider["id"], "sku": "H100-HOUR", "qty": 100})

    # Provider offers 50 units at 2.50.
    sell = client.post(
        "/orders",
        json={"account_id": provider["id"], "side": "sell", "sku": "H100-HOUR", "qty": 50, "price": 2.50},
    ).json()
    assert sell["order"]["status"] == "open"
    assert sell["trades"] == []

    # Buyer registers, funds 1000, and lifts 20 units at the offer.
    buyer = client.post("/accounts", json={"label": "AI Lab", "purchaser": True}).json()
    client.post(f"/accounts/{buyer['id']}/deposit", json={"amount": 1000})
    res = client.post(
        "/orders",
        json={"account_id": buyer["id"], "side": "buy", "sku": "H100-HOUR", "qty": 20, "price": 2.50},
    ).json()
    assert res["order"]["status"] == "filled"
    assert len(res["trades"]) == 1
    assert res["trades"][0]["price"] == 2.50

    # Balances settled atomically.
    b = client.get(f"/accounts/{buyer['id']}").json()
    assert abs(b["capacity_free"]["H100-HOUR"] - 20) < 1e-9
    assert abs(b["quote_free"] - (1000 - 20 * 2.50)) < 1e-9
    p = client.get(f"/accounts/{provider['id']}").json()
    assert abs(p["quote_free"] - 20 * 2.50) < 1e-9
    assert abs(p["capacity_locked"]["H100-HOUR"] - 30) < 1e-9  # 30 still resting on the book

    # Buyer redeems 5 for delivery; tokens are burned.
    r = client.post("/capacity/redeem", json={"account_id": buyer["id"], "sku": "H100-HOUR", "qty": 5}).json()
    assert r["status"] == "delivered"
    b = client.get(f"/accounts/{buyer['id']}").json()
    assert abs(b["capacity_free"]["H100-HOUR"] - 15) < 1e-9

    # Seller settles 50 of quote out to a wallet.
    pay = client.post(f"/accounts/{provider['id']}/withdraw", json={"amount": 50}).json()
    assert pay["status"] == "settled"
    p = client.get(f"/accounts/{provider['id']}").json()
    assert abs(p["quote_free"] - 0) < 1e-9


def test_mint_requires_whitelisted_provider() -> None:
    # A plain account (no provider role) cannot mint.
    acct = client.post("/accounts", json={"label": "random"}).json()
    resp = client.post("/capacity/mint", json={"provider_id": acct["id"], "sku": "H100-HOUR", "qty": 10})
    assert resp.status_code == 403


def test_taker_buy_gets_price_improvement_refund() -> None:
    provider = client.post("/providers", json={"label": "Acme"}).json()
    client.post("/capacity/mint", json={"provider_id": provider["id"], "sku": "A100-HOUR", "qty": 100})
    client.post(
        "/orders",
        json={"account_id": provider["id"], "side": "sell", "sku": "A100-HOUR", "qty": 10, "price": 2.00},
    )
    buyer = client.post("/accounts", json={"label": "buyer"}).json()
    client.post(f"/accounts/{buyer['id']}/deposit", json={"amount": 100})
    # Buyer bids 2.50 but the resting ask is 2.00 -> trade at 2.00, 0.50 refunded.
    res = client.post(
        "/orders",
        json={"account_id": buyer["id"], "side": "buy", "sku": "A100-HOUR", "qty": 10, "price": 2.50},
    ).json()
    assert res["trades"][0]["price"] == 2.00
    b = client.get(f"/accounts/{buyer['id']}").json()
    assert abs(b["quote_free"] - (100 - 10 * 2.00)) < 1e-9  # only paid 2.00, not 2.50


def test_oversell_is_rejected() -> None:
    provider = client.post("/providers", json={"label": "Acme"}).json()
    client.post("/capacity/mint", json={"provider_id": provider["id"], "sku": "H100-HOUR", "qty": 5})
    resp = client.post(
        "/orders",
        json={"account_id": provider["id"], "side": "sell", "sku": "H100-HOUR", "qty": 10, "price": 1.0},
    )
    assert resp.status_code == 409  # InsufficientCapacity


def test_cancel_releases_escrow() -> None:
    buyer = client.post("/accounts", json={"label": "buyer"}).json()
    client.post(f"/accounts/{buyer['id']}/deposit", json={"amount": 100})
    res = client.post(
        "/orders",
        json={"account_id": buyer["id"], "side": "buy", "sku": "H100-HOUR", "qty": 10, "price": 3.0},
    ).json()
    b = client.get(f"/accounts/{buyer['id']}").json()
    assert abs(b["quote_locked"] - 30) < 1e-9
    client.post(f"/orders/{res['order']['id']}/cancel")
    b = client.get(f"/accounts/{buyer['id']}").json()
    assert abs(b["quote_locked"] - 0) < 1e-9
    assert abs(b["quote_free"] - 100) < 1e-9

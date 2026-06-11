"""
End-to-end tests against the HTTP API.

The centrepiece is the whitepaper's worked example (Nordfjord / Tessellate),
asserted number-for-number: clearing at $2.00 on 60 hours, the $12 escrow
refund, the $20 + $4 + $6 failure branch, and the "-$6 per cycle" anti-fraud
arithmetic.

Run: pytest -q
"""

import pytest
from fastapi.testclient import TestClient

from app import deps
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_market():
    """Every test starts from an empty market."""
    deps.reset_store()
    yield


# ---------------------------------------------------------------- helpers ----

GOOD_BENCH = {"gpu_model": "H100-SXM", "vram_gb": 80,
              "interconnect_tbps": 3.2, "region": "EU-WEST"}


def first_contract() -> str:
    """The nearest EU-H100 window — the demo's 'Week 30'."""
    contracts = client.get("/contracts").json()
    return next(c["id"] for c in contracts if c["grade_id"] == "EU-H100.v1")


def make_account(label: str, deposit: float = 0.0) -> str:
    acct = client.post("/accounts", json={"label": label}).json()
    if deposit:
        client.post(f"/accounts/{acct['id']}/deposit", json={"amount": deposit})
    return acct["id"]


def make_provider(label: str, deposit: float, bond: float) -> str:
    pid = make_account(label, deposit)
    r = client.post(f"/accounts/{pid}/attest", json={"grade_id": "EU-H100.v1", **GOOD_BENCH})
    assert r.status_code == 200, r.text
    r = client.post(f"/accounts/{pid}/bond", json={"amount": bond})
    assert r.status_code == 200, r.text
    return pid


def balances(account_id: str) -> dict:
    return client.get(f"/accounts/{account_id}").json()


def total_quote(account_id: str) -> float:
    a = balances(account_id)
    return a["quote_free"] + a["quote_locked"] + a["bond"]


# ----------------------------------------------------------- layer 1 & 2 ----

def test_grades_have_stable_fingerprints_and_windows_exist():
    grades = client.get("/grades").json()
    assert {g["id"] for g in grades} == {"EU-H100.v1", "US-A100.v1"}
    eu = next(g for g in grades if g["id"] == "EU-H100.v1")
    assert len(eu["fingerprint"]) == 64  # sha256 of the checklist text

    contracts = client.get("/contracts").json()
    # 2 grades x 4 upcoming weekly windows = 8 books
    assert len(contracts) == 8
    assert all("@" in c["id"] for c in contracts)


# --------------------------------------------------------------- layer 4 ----

def test_attestation_rejects_hardware_that_fails_the_checklist():
    pid = make_account("shady", 1000)
    bad = {**GOOD_BENCH, "vram_gb": 40, "region": "US-EAST"}
    r = client.post(f"/accounts/{pid}/attest", json={"grade_id": "EU-H100.v1", **bad})
    assert r.status_code == 400
    assert "vram" in r.json()["detail"] and "region" in r.json()["detail"]


def test_mint_requires_attestation_and_bond_coverage():
    cid = first_contract()
    pid = make_account("unattested", 1000)
    r = client.post("/mint", json={"provider_id": pid, "contract_id": cid, "qty": 10})
    assert r.status_code == 403  # no attestation

    client.post(f"/accounts/{pid}/attest", json={"grade_id": "EU-H100.v1", **GOOD_BENCH})
    r = client.post("/mint", json={"provider_id": pid, "contract_id": cid, "qty": 10})
    assert r.status_code == 409  # attested, but no bond posted

    # Newcomer rate is 150%: 10 hours x $2 ref price -> $30 required.
    client.post(f"/accounts/{pid}/bond", json={"amount": 30})
    r = client.post("/mint", json={"provider_id": pid, "contract_id": cid, "qty": 10})
    assert r.status_code == 200, r.text

    # The reserve rule: cannot mint more against the same bond.
    r = client.post("/mint", json={"provider_id": pid, "contract_id": cid, "qty": 100})
    assert r.status_code == 409


# ------------------------------------------------- layer 3: the auction ----

def setup_worked_example():
    """The whitepaper's cast, exactly: Nordfjord 40h >= $1.50, B 20h >= $1.80,
    C 15h >= $2.10; Tessellate 30h <= $2.40, Y 30h <= $2.00, Z 10h <= $1.70."""
    cid = first_contract()
    nordfjord = make_provider("Nordfjord Compute", deposit=120, bond=120)
    b = make_provider("Provider B", deposit=80, bond=60)
    c = make_provider("Provider C", deposit=80, bond=45)
    for pid, qty in [(nordfjord, 40), (b, 20), (c, 15)]:
        r = client.post("/mint", json={"provider_id": pid, "contract_id": cid, "qty": qty})
        assert r.status_code == 200, r.text
    for pid, qty, floor in [(nordfjord, 40, 1.50), (b, 20, 1.80), (c, 15, 2.10)]:
        r = client.post("/floors", json={"account_id": pid, "contract_id": cid,
                                         "qty": qty, "floor_price": floor})
        assert r.status_code == 200, r.text

    tessellate = make_account("Tessellate AI", 100)
    y = make_account("Buyer Y", 100)
    z = make_account("Buyer Z", 100)
    for bid_acct, qty, mx in [(tessellate, 30, 2.40), (y, 30, 2.00), (z, 10, 1.70)]:
        r = client.post("/bids", json={"account_id": bid_acct, "contract_id": cid,
                                       "qty": qty, "max_price": mx})
        assert r.status_code == 200, r.text
    return cid, nordfjord, b, c, tessellate, y, z


def test_uniform_price_auction_clears_the_worked_example():
    cid, nordfjord, b, c, tessellate, y, z = setup_worked_example()

    result = client.post(f"/auctions/{cid}/clear").json()
    assert result["clearing_price"] == pytest.approx(2.00)
    assert result["volume"] == pytest.approx(60)

    # Tessellate: bought 30 @ $2.00, escrowed $72 -> $12 headroom refunded.
    t = balances(tessellate)
    assert t["capacity_free"][cid] == pytest.approx(30)
    assert t["quote_free"] == pytest.approx(100 - 60)
    assert t["quote_locked"] == pytest.approx(0)

    # Nordfjord sold all 40 (floor $1.50, paid $2.00 — never had to guess);
    # money sits in escrow, not its wallet, until delivery confirms.
    n = balances(nordfjord)
    assert n["capacity_locked"].get(cid, 0) == pytest.approx(0)
    assert n["quote_free"] == pytest.approx(0)

    # Y got the remaining 30 (10 from Nordfjord, 20 from B); Z's $1.70 missed.
    assert balances(y)["capacity_free"][cid] == pytest.approx(30)
    assert balances(z)["capacity_free"].get(cid, 0) == pytest.approx(0)
    assert balances(z)["quote_locked"] == pytest.approx(17)  # bid still standing

    # C's $2.10 floor was above the clearing price: untouched.
    assert balances(c)["capacity_locked"][cid] == pytest.approx(15)

    # The clearing price became the public index.
    contract = next(x for x in client.get("/contracts").json() if x["id"] == cid)
    assert contract["last_clearing_price"] == pytest.approx(2.00)


def test_reliability_premium_outranks_a_cheaper_flaky_seller():
    """A 10%-flaky seller quoting $2.00 ranks behind a reliable one at $2.05:
    effective 2.00*1.10=2.20 vs 2.05*1.005=2.06."""
    cid = first_contract()
    flaky = make_provider("Flaky", deposit=400, bond=400)
    deps.get_store().accounts[flaky].delivered_qty = 90
    deps.get_store().accounts[flaky].failed_qty = 10
    reliable = make_provider("Reliable", deposit=400, bond=400)
    deps.get_store().accounts[reliable].delivered_qty = 199
    deps.get_store().accounts[reliable].failed_qty = 1

    for pid, floor in [(flaky, 2.00), (reliable, 2.05)]:
        client.post("/mint", json={"provider_id": pid, "contract_id": cid, "qty": 10})
        client.post("/floors", json={"account_id": pid, "contract_id": cid,
                                     "qty": 10, "floor_price": floor})

    buyer = make_account("buyer", 100)
    client.post("/bids", json={"account_id": buyer, "contract_id": cid,
                               "qty": 10, "max_price": 2.50})
    client.post(f"/auctions/{cid}/clear")

    trades = client.get("/trades").json()
    assert len(trades) == 1
    assert trades[0]["seller_id"] == reliable  # cheap-but-flaky couldn't win on price


def test_empty_round_clears_with_no_trade():
    cid = first_contract()
    result = client.post(f"/auctions/{cid}/clear").json()
    assert result["clearing_price"] is None
    assert result["volume"] == 0
    assert result["trades"] == []


# --------------------------------------------- layer 5: delivery branches ----

def test_delivery_releases_escrow_and_improves_reputation():
    cid, nordfjord, *_, tessellate, y, z = setup_worked_example()
    client.post(f"/auctions/{cid}/clear")
    rate_before = client.get(f"/accounts/{nordfjord}/bond-status").json()["bond_rate"]

    deliveries = client.post("/redeem", json={"account_id": tessellate,
                                              "contract_id": cid, "qty": 30}).json()
    assert sum(d["qty"] for d in deliveries) == pytest.approx(30)
    for d in deliveries:
        r = client.post(f"/deliveries/{d['id']}/confirm")
        assert r.status_code == 200

    n = balances(nordfjord)
    assert n["quote_free"] == pytest.approx(60)        # escrow released: 30 x $2.00
    assert n["delivered_qty"] == pytest.approx(30)
    rate_after = client.get(f"/accounts/{nordfjord}/bond-status").json()["bond_rate"]
    assert rate_after < rate_before                     # trust is earned down


def test_noshow_refunds_compensates_and_slashes_to_the_pool():
    """The $20 failure: refund $20 + comp $4 to the buyer, slash $6 to the pool."""
    cid, nordfjord, *_, tessellate, y, z = setup_worked_example()
    client.post(f"/auctions/{cid}/clear")

    # Redeem exactly 10 hours and have them fail (the cooling outage).
    deliveries = client.post("/redeem", json={"account_id": tessellate,
                                              "contract_id": cid, "qty": 10}).json()
    buyer_before = balances(tessellate)["quote_free"]
    bond_before = balances(nordfjord)["bond"]

    for d in deliveries:
        client.post(f"/deliveries/{d['id']}/fail")

    buyer_after = balances(tessellate)["quote_free"]
    assert buyer_after - buyer_before == pytest.approx(20 + 4)   # refund + comp
    assert bond_before - balances(nordfjord)["bond"] == pytest.approx(4 + 6)
    assert client.get("/pool").json()["insurance_pool"] == pytest.approx(6)

    # The failure now taxes Nordfjord's price in every future auction.
    assert balances(nordfjord)["failed_qty"] == pytest.approx(10)


def test_self_dealing_fraud_is_a_guaranteed_net_loss():
    """Attacker runs both sides of a $20 contract and no-shows themself:
    collects $4 comp but forfeits $10 of bond -> -$6, every attempt."""
    cid = first_contract()
    seller = make_provider("attacker-seller", deposit=50, bond=30)
    buyer = make_account("attacker-buyer", 20)
    attacker_total_before = total_quote(seller) + total_quote(buyer)

    client.post("/mint", json={"provider_id": seller, "contract_id": cid, "qty": 10})
    # Floor low enough that even the newcomer premium can't stop the self-match;
    # the round clears at the attacker's own $2.00 bid.
    client.post("/floors", json={"account_id": seller, "contract_id": cid,
                                 "qty": 10, "floor_price": 1.90})
    client.post("/bids", json={"account_id": buyer, "contract_id": cid,
                               "qty": 10, "max_price": 2.00})
    client.post(f"/auctions/{cid}/clear")
    deliveries = client.post("/redeem", json={"account_id": buyer,
                                              "contract_id": cid, "qty": 10}).json()
    for d in deliveries:
        client.post(f"/deliveries/{d['id']}/fail")

    attacker_total_after = total_quote(seller) + total_quote(buyer)
    assert attacker_total_after - attacker_total_before == pytest.approx(-6.0)
    assert client.get("/pool").json()["insurance_pool"] == pytest.approx(6.0)


# ------------------------------------------------------- secondary market ----

def test_capacity_behaves_like_inventory_and_resells():
    """Differentiator #1: Tessellate's project slips; it resells 15 hours
    into a later round at a higher floor."""
    cid, nordfjord, *_rest, tessellate, y, z = setup_worked_example()
    client.post(f"/auctions/{cid}/clear")

    r = client.post("/floors", json={"account_id": tessellate, "contract_id": cid,
                                     "qty": 15, "floor_price": 2.20})
    assert r.status_code == 200

    late_buyer = make_account("late buyer", 100)
    client.post("/bids", json={"account_id": late_buyer, "contract_id": cid,
                               "qty": 15, "max_price": 2.30})
    result = client.post(f"/auctions/{cid}/clear").json()
    assert result["volume"] == pytest.approx(15)
    assert balances(late_buyer)["capacity_free"][cid] == pytest.approx(15)
    assert balances(tessellate)["capacity_free"][cid] == pytest.approx(15)  # kept the rest


# ------------------------------------------------------------------- RFQ ----

def test_rfq_side_door_escrows_and_settles():
    buyer = make_account("bespoke buyer", 500)
    provider = make_account("responsive provider", 0)

    rfq = client.post("/rfqs", json={"buyer_id": buyer, "qty": 32,
                                     "spec": "32x H100 same building 72h"}).json()
    q = client.post(f"/rfqs/{rfq['id']}/quotes",
                    json={"provider_id": provider, "price": 3.00}).json()
    d = client.post(f"/rfqs/{rfq['id']}/accept", json={"quote_id": q["id"]}).json()

    assert balances(buyer)["quote_free"] == pytest.approx(500 - 96)  # escrowed
    client.post(f"/deliveries/{d['id']}/confirm")
    assert balances(provider)["quote_free"] == pytest.approx(96)


# ------------------------------------------------------------ guard rails ----

def test_bids_must_be_fully_collateralized():
    cid = first_contract()
    poor = make_account("underfunded", 10)
    r = client.post("/bids", json={"account_id": poor, "contract_id": cid,
                                   "qty": 100, "max_price": 2.00})
    assert r.status_code == 402


def test_floors_cannot_double_sell_capacity():
    cid = first_contract()
    pid = make_provider("provider", deposit=100, bond=60)
    client.post("/mint", json={"provider_id": pid, "contract_id": cid, "qty": 10})
    assert client.post("/floors", json={"account_id": pid, "contract_id": cid,
                                        "qty": 10, "floor_price": 1.0}).status_code == 200
    r = client.post("/floors", json={"account_id": pid, "contract_id": cid,
                                     "qty": 1, "floor_price": 1.0})
    assert r.status_code == 409  # all capacity already reserved behind the first floor


def test_cancel_returns_collateral():
    cid = first_contract()
    buyer = make_account("buyer", 100)
    bid = client.post("/bids", json={"account_id": buyer, "contract_id": cid,
                                     "qty": 10, "max_price": 2.0}).json()
    assert balances(buyer)["quote_locked"] == pytest.approx(20)
    client.post(f"/bids/{bid['id']}/cancel")
    assert balances(buyer)["quote_free"] == pytest.approx(100)

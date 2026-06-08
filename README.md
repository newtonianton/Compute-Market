# Compute Market

A minimal, **extensible framework for trading GPU compute as a financial asset**. Providers mint standardized capacity units; those units trade on a price-time-priority order book; buyers redeem them for delivery. Built with FastAPI, no database, no chain — so you can stand it up in one command and bend it toward whatever your differentiator turns out to be.

It is deliberately *generic*. It implements the five primitives every compute market needs and nothing opinionated on top, so it's a starting point, not a finished product.

---

## The one thing to understand first

There are **two layers**, and they are separate:

1. **Your Kickstart coin** — the fair-launch token you mint on EasyA Kickstart. That satisfies hackathon eligibility, builds community, and pays you the creator fee. *This repo is not that.*
2. **This framework** — the actual market where compute capacity is represented, priced, traded, and redeemed.

They connect later (e.g. your coin could become the quote currency, or grant fee discounts), but you do **not** need to fuse them to ship. Launch the coin for eligibility; build this in public alongside it.

---

## The five primitives (and where each lives)

| Primitive | What it does | File |
|---|---|---|
| **Capacity unit** | Defines the standardized, fungible thing that trades (e.g. one H100-hour) | `app/config.py` |
| **Registry / whitelist** | Who may supply and who may redeem — the "verified providers/purchasers" gate | `app/registry.py` |
| **Mint / redeem** | Whitelisted providers create supply; holders burn units for delivery | `app/capacity.py` |
| **Price / order flow** | A continuous order book with escrow and partial fills | `app/market.py` |
| **Settlement** | Pays sellers on each fill; lets them withdraw out to a wallet | `app/settlement.py` |

State and all balance accounting (the "ledger") live in `app/store.py`. That file is the single source of truth and the main swap point.

---

## Run it

Requires Python 3.10+.

```bash
cd compute-market
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:app --reload
```

Then open:

- **http://127.0.0.1:8000/** — the demo console (register a provider, mint, trade, watch the book)
- **http://127.0.0.1:8000/docs** — interactive API docs; every endpoint is callable from the browser

Run the tests anytime to confirm nothing broke:

```bash
pytest -q
```

---

## The flow, end to end

The console walks you through this; here it is as raw API calls so you can see the shape.

```bash
# 1. Register a provider (whitelisted to mint by default)
PID=$(curl -s -X POST localhost:8000/providers -H 'content-type: application/json' \
  -d '{"label":"Acme GPU"}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 2. Provider mints 100 H100-hours of supply
curl -s -X POST localhost:8000/capacity/mint -H 'content-type: application/json' \
  -d "{\"provider_id\":\"$PID\",\"sku\":\"H100-HOUR\",\"qty\":100}"

# 3. Provider posts an offer: sell 50 @ 2.50
curl -s -X POST localhost:8000/orders -H 'content-type: application/json' \
  -d "{\"account_id\":\"$PID\",\"side\":\"sell\",\"sku\":\"H100-HOUR\",\"qty\":50,\"price\":2.50}"

# 4. A buyer registers, funds, and lifts 20 of the offer
BID=$(curl -s -X POST localhost:8000/accounts -H 'content-type: application/json' \
  -d '{"label":"AI Lab","purchaser":true}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST localhost:8000/accounts/$BID/deposit -H 'content-type: application/json' -d '{"amount":1000}'
curl -s -X POST localhost:8000/orders -H 'content-type: application/json' \
  -d "{\"account_id\":\"$BID\",\"side\":\"buy\",\"sku\":\"H100-HOUR\",\"qty\":20,\"price\":2.50}"

# 5. Buyer redeems 5 units for actual delivery (burns the tokens)
curl -s -X POST localhost:8000/capacity/redeem -H 'content-type: application/json' \
  -d "{\"account_id\":\"$BID\",\"sku\":\"H100-HOUR\",\"qty\":5}"

# 6. Seller settles earned quote out to a wallet
curl -s -X POST localhost:8000/accounts/$PID/withdraw -H 'content-type: application/json' -d '{"amount":50}'
```

The key property: between mint (3) and redeem (5), a unit can change hands any number of times. A pure speculator can buy at step 4 and resell without ever redeeming — that's the "most traders never take delivery" behaviour the brief is pointing at.

---

## How to modify it — the extension points

Each primitive is isolated so you can replace one without touching the others.

### Change what trades
Edit `DEFAULT_SKUS` in `app/config.py`. Add region, interconnect, or commitment-term fields to the `Sku` model to define capacity more tightly. **Fungibility is the hard part of any compute market** — the more precisely you define the unit, the more credible "any H100-hour is interchangeable" becomes.

### Turn the whitelist into real verification
Right now `app/registry.py` whitelists with a boolean. Replace those endpoints with genuine provider attestation — KYC, a staking deposit, or hardware proof (e.g. a TEE attestation) — and your buyer-side checks. Flip `REQUIRE_WHITELISTED_PURCHASER = True` in config to enforce the "only verified purchasers can redeem" rule.

### Make it persistent or on-chain
`app/store.py` defines an abstract `Store`; `InMemoryStore` is one implementation. Write `SqliteStore` (or `SolanaStore`) implementing the same persistence methods and select it in `app/deps.py`. The accounting rules and every router stay untouched. *(If you go DB-backed, re-save the account after each accounting call — see the note at the top of `store.py`.)* Making capacity an actual SPL token with mint authority gated to whitelisted providers is the natural on-chain version of `mint_capacity`/`burn_capacity`.

### Price differently
`match()` in `app/market.py` is a continuous order book. Swap it for an AMM (constant-product over a capacity/quote pool), a periodic batch auction, or an RFQ/quote model — and keep the reserve/escrow accounting as-is. The rest of the system doesn't care how price is formed.

### Wire up real money
`app/settlement.py` is a stub that debits an internal balance. Replace the body with a real USDC transfer on Solana, an [x402](https://www.x402.org/) micropayment, or a Tempo/MPP streaming payout. Keep the endpoint shape; swap the rails. The funding stub (`/deposit`) becomes an on-chain deposit watcher.

### Connect your Kickstart coin
Once your coin is live, options include: set it as the `QUOTE_CURRENCY`, give holders fee discounts at settlement, or distribute a share of trading fees to holders. This is where the two layers finally meet.

---

## How this maps to the hackathon brief

- **Supply** → providers, onboarded via the registry and creating units via mint.
- **Demand** → buyers and agents placing bids; pure traders providing liquidity.
- **Price** → the order book's cleared price, visible via `/orderbook/{sku}` and the tape at `/trades`.
- **Settlement** → atomic at each fill, with an explicit exit to capacity sellers.
- **Mint/redeem like a stablecoin** → whitelisted mint, gated redeem, free trading in between.

---

## Caveats (read before you demo or extend)

- **In-memory:** all state resets when the server restarts. Fine for a demo; add a `Store` backend for anything durable.
- **Money is `float`:** readable, but floats accumulate rounding error. For real value, switch balances to integer minor-units or `Decimal` (localized to `app/models.py` + `app/store.py`).
- **No authentication:** any caller can act as any `account_id`. Add auth (signed requests / wallet signatures) before this is anything but a local demo.
- **No real delivery:** "redeem" logs a record; it does not provision a GPU. Hooking redemption to an actual cluster lease / API key is real work and a strong differentiator.
- **Single-process, not concurrency-safe:** the matching engine assumes one worker. Don't run multiple uvicorn workers against the in-memory store.

---

## Layout

```
compute-market/
├── app/
│   ├── config.py        # capacity units (SKUs) + market knobs   ← start here
│   ├── models.py        # entities + request/response schemas
│   ├── store.py         # state + accounting (the ledger)        ← swap point
│   ├── deps.py          # store wiring / injection
│   ├── registry.py      # accounts, whitelist, funding
│   ├── capacity.py      # mint / redeem
│   ├── market.py        # order book + matching engine
│   ├── settlement.py    # payouts
│   └── main.py          # app wiring, errors, console, health
├── web/index.html       # single-file demo console
├── tests/test_flow.py   # end-to-end flow + invariant tests
├── requirements.txt
└── README.md
```

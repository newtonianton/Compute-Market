# MWNT — a compute market you can actually demo

Graded, dated, bonded GPU compute that trades like a commodity. Grades are
fingerprinted checklists (Layer 1); contracts add a weekly delivery window
(Layer 2); a **uniform-price batch auction** sets one price per round with
reliability priced in before clearing (Layer 3); **attestation + bonds +
reputation** make strangers safe to trade with (Layer 4); **escrow + slashing +
an insurance pool** make fraud unprofitable by arithmetic (Layer 5).

```
mwnt/
├── app/
│   ├── __init__.py        # version
│   ├── main.py            # FastAPI entrypoint, routers, demo console, /reset
│   ├── config.py          # grade catalogue + every economic constant, with rationale
│   ├── models.py          # Pydantic entities = API schemas (single source of truth)
│   ├── store.py           # in-memory ledger + all balance-moving primitives
│   ├── deps.py            # store dependency injection (swapped in tests)
│   ├── errors.py          # domain errors -> HTTP statuses
│   ├── registry.py        # Layer 4: accounts, attestation, bonding, reputation
│   ├── grades.py          # Layers 1-2: grades, contracts, gated minting
│   ├── auction.py         # Layer 3: floors, bids, uniform-price clearing, the index
│   ├── settlement.py      # Layer 5: redeem, delivery oracle, slashing, pool
│   └── rfq.py             # the bespoke-demand side door
├── web/
│   └── index.html         # zero-build demo console served at /
├── tests/
│   └── test_main.py       # 14 end-to-end tests incl. the worked example, number-for-number
├── conftest.py            # makes `app` importable for bare `pytest`
├── requirements.txt
└── README.md
```

## Quickstart

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

| URL | What |
|---|---|
| http://127.0.0.1:8000/ | Demo console (the thing you show judges) |
| http://127.0.0.1:8000/docs | Swagger UI — every endpoint, interactive |
| http://127.0.0.1:8000/health | Liveness |

Tests:

```bash
pytest -q        # 14 passed
```

## The 3-minute demo script

Everything below happens in the console at `/` (it drives the same public API
that `/docs` exposes — nothing is faked)!

1. **Seed the worked example** (button, top right). This registers the
   whitepaper's cast via the real endpoints: Nordfjord attests its H100s
   against the `EU-H100.v1` checklist, posts a **$120 bond** (150% newcomer
   rate), mints 40 hours, and sets one standing floor of **40h ≥ $1.50** —
   then never touches the market again. Providers B and C, and buyers
   Tessellate ($2.40 max), Y ($2.00) and Z ($1.70) join the same book.
   Point at the order book: asks are shown at their *effective* price —
   each floor bumped by the seller's failure rate.

2. **Clear round.** The banner prints: **60h at $2.00** — the single crossing
   price. Narrate the two punchlines: Nordfjord's floor was $1.50 but it
   *receives* $2.00; Tessellate offered $2.40 but *pays* $2.00 and its unused
   $12 of escrow is already back in its wallet (check the Participants panel).
   The price appears on the **index tape** at the top — the market just built
   its own benchmark. Note Nordfjord's $80 sits in *escrow*, not its wallet:
   sellers get paid on delivery, not on sale.

3. **Happy path.** In *Redeem*, burn 20 of Tessellate's hours, then press
   **deliver** on the tickets. Escrow releases to Nordfjord, its delivery
   record ticks up, and its bond *rate* ticks down — trust being earned down
   in real time (`GET /accounts/{id}/bond-status` shows the curve).

4. **The failure branch** (the credibility moment). Redeem 10 more hours and
   press **no-show**. The activity log shows the exact whitepaper math:
   **refund $20.00, comp $4.00, slashed $6.00 to pool**. The insurance pool
   ticks to $6.00, and Nordfjord's failure rate now bumps its floor in every
   future round — flakiness is priced in automatically.

5. **Fraud is unprofitable by arithmetic.** Tell it over the pool panel:
   an attacker running both sides of that $20 contract collects $4 in
   compensation but forfeits $10 of bond — **−$6 per cycle, every cycle**
   (`test_self_dealing_fraud_is_a_guaranteed_net_loss` asserts exactly this).

6. **Capacity is inventory.** Tessellate's project slips: post a floor of its
   remaining hours at $2.20 from `/docs` (`POST /floors` — any token holder
   may sell), add a late buyer's bid, clear again. The tape prints a second,
   higher index point — a secondary market in 30 seconds.

7. **Empty rounds are not errors.** Switch the contract selector to an empty
   window and clear: *"Round cleared with no trade — a valid outcome."*

8. **The RFQ side door** (if asked): `POST /rfqs` → `/rfqs/{id}/quotes` →
   `/rfqs/{id}/accept` escrows the buyer's funds and opens a delivery ticket
   through the *same* settlement machinery — bespoke deals are bonded too.

## Design choices

**Backend: FastAPI + Pydantic, in-memory store.** One process, zero
infrastructure, instant cold start — ideal for a hackathon booth. Pydantic
models are simultaneously the domain entities and the API schemas, so the
state and the docs can't drift. All value movement goes through named
primitives in `store.py` (`lock_quote`, `slash_bond`, `move_locked_capacity`);
routers compose primitives but never touch balances, which is what makes the
store swappable for Postgres — or for the Solana programs the whitepaper
describes (each contract = one SPL mint; `mint`/`burn_capacity` map to mint
authority and token burns; `Escrow` maps to a PDA) — without touching the
market logic.

**Frontend: a single static HTML file, no build step.** Vanilla JS + `fetch`
against the same public API judges can poke in Swagger. No node_modules to
break five minutes before the demo; the entire UI deploys by existing.

**Auction over order book.** The previous version (attached `market.py`) was a
continuous price-time-priority CLOB. We deliberately replaced it: with thin
hackathon flow, a batch auction aggregates everything into one meaningful
crossing, makes truthful quoting the dominant strategy, and emits one clean
index point per round. The clearing engine is ~80 isolated lines
(`clear_auction`); an AMM or CLOB could be swapped back in without touching
escrow/bond accounting — same modularity bet as before, different mechanism.

**Reliability premium ranks, payment doesn't.** Floors are *ranked* at
`floor × (1 + failure_rate)` (newcomers get a 2% default so "no history" never
beats "good history"), but everyone still trades at the one clearing price.
Risk affects who wins, not what the winner is paid — that keeps the uniform
price honest.

**Clearing-price convention.** When a range of prices clears the same maximum
volume, we take the highest (the demand-side end), matching the whitepaper's
worked example ($1.80–$2.00 range → $2.00).

**Bond economics in one place.** `config.py` holds every constant with its
rationale: 150% newcomer rate stepping down per delivered hour, floored at
50% so a failure (20% comp + 30% slash) is always covered; slash > comp is
the entire anti-fraud argument, so they sit next to each other in the file.

**The delivery oracle is two endpoints, on purpose.** `confirm`/`fail` make
the load-bearing wall *visible and demoable* — you can act out the failure
branch live. The honest framing for judges: in production this is metered
usage, and making it manipulation-resistant is the open research problem.

## Known simplifications (say these before judges find them)

- **Money is floats.** Production needs integer minor-units / Decimal;
  the swap is localized in `models.py`.
- **Resale & the escrow chain.** Deliveries are funded from the *redeemer's
  own* purchase escrows (FIFO). A buyer who resells tokens transfers the
  claim but not the escrow linkage — fine for the demo, a real design task
  for the token model on-chain.
- **In-memory state**: a restart is a market reset (also a feature: `POST /reset`).
- **No auth**: any caller is any account. Wallet signatures replace this on Solana.
- **The scheduler is you**: rounds clear when `POST /auctions/{id}/clear` is
  called; production runs it on a timer.

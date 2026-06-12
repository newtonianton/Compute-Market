# DEMO.md — the ~2-minute demo (with real Token-2022)

Two artefacts: the **run-of-show** (exactly which buttons to press) and the
**voiceover script** (timed to the clicks). The demo has two acts: the
**economics** runs on seeded internal accounts so the headline numbers stay
exact ($2.00 clear, $6 to the pool — no real SOL involved); the **real-chain
coda** acts as your connected Phantom wallet so deposits are verified on devnet
and minted hours land as real **Token-2022** tokens in the wallet.

## Do I need to add a participant first? No.

- **Your wallet auto-registers.** Clicking **Connect Phantom** registers the
  wallet address as a participant, and the deposit endpoint get-or-creates it
  too. The Trade desk's "Acting as" selector defaults to it.
- **Counterparties come from Seed.** **Seed worked example** adds the three
  providers and three buyers, so a round has both sides.
- You only ever click **Add participant** for an *optional* extra local
  counterparty (e.g. the resale beat). The core demo never needs it.

## Before you record (prep)

1. **Run locally with the token layer enabled.** `pip install -r requirements.txt`
   (includes `solders`) and **do not** set `MWNT_ESCROW_ADDRESS` — the app must
   hold the mint-authority keypair. Start: `uvicorn app.main:app --reload`,
   open http://127.0.0.1:8000/.
   - Sanity check: `GET /tokens` must show `"enabled": true`. If it's `false`,
     either `solders` isn't installed or `MWNT_ESCROW_ADDRESS` is set (unset it).
   - Note: the Vercel deploy (which uses `MWNT_ESCROW_ADDRESS`) has Token-2022
     **disabled** by design — record the token act from a local run.
2. **Phantom on Devnet.** Switch Phantom to Devnet (Settings → Developer →
   Testnet/Devnet) and airdrop yourself ~4 devnet SOL
   (`solana airdrop 2 <addr> --url devnet`, twice; faucets rate-limit). You
   need a few SOL because the wallet posts a real bond before it can mint.
3. **Full-screen** the browser, hide the bookmarks bar, zoom ≈ 90% so the three
   panels and the Trade desk fit without scrolling.
4. **Connect Phantom now** (pre-roll). The status chip top-right should show
   `●  ABCD…WXYZ · N.NN SOL · devnet`. This also funds the escrow on your first
   deposit (deposits land at the escrow address, which pays token-mint fees).
5. Press **Reset** so the index tape is empty — the first print lands harder.
   (Reset clears the ledger; deterministic `grade@week` mints persist, so the
   contract's Token-2022 address is stable across resets.)
6. One silent rehearsal of Act 1: Seed → Clear → Redeem 20 → deliver all →
   Redeem 10 → no-show all. Then the coda: Deposit → Attest → Bond → Mint 1.
   Reset, re-connect, re-deposit, and you're ready.
7. Mouse discipline: park the cursor near the next button during each line.

## Run-of-show (what your hands do)

### Act 1 — the economics (seeded accounts, no SOL)

| Time | Action | What appears on screen |
|---|---|---|
| 0:00–0:08 | Nothing — let the empty console breathe | Header, empty index tape, empty book |
| 0:08 | Click **Seed worked example** | Activity log fills: 3 providers attest + bond + mint, 3 buyers escrow bids; book shows 3 green bid levels vs 3 red ask levels |
| 0:08–0:20 | Hover slowly down the order book | Asks shown at *effective* prices (reliability-bumped); depth bars |
| 0:20 | Click **Clear round now** | Banner: "Cleared **60h** at **$2.00**"; **$2.00** prints on the index tape; Tessellate's $12 refund visible in Participants |
| 0:20–0:38 | Point at Nordfjord in Participants | quote_free $0 — its $80 sits in escrow, not its wallet |
| 0:38 | In **Redeem**: pick *Tessellate AI*, qty **20**, **Redeem**; then **deliver** the pending ticket(s) | Ticket flips green `delivered`; Nordfjord's free balance jumps; its fail-rate pill stays clean |
| 0:50 | Redeem **10** more as Tessellate, click **no-show** | Log: `refund 20.00, comp 4.00, slashed 6.00 to pool`; **Insurance pool ticks to $6.00**; Nordfjord's pill now shows a fail % |
| 0:50–1:05 | Point at the pool figure, then at Nordfjord's pill | |

### Act 2 — the real chain + Token-2022 (your wallet)

| Time | Action | What appears on screen |
|---|---|---|
| 1:05 | In the Trade desk, confirm **Acting as** = your wallet; set the **Contract** to the EU-H100 window shown in the book | "Acting as" shows your truncated address |
| 1:08 | In **Fund & withdraw**, deposit **~3.5** and click **Deposit** → approve the transfer in Phantom | Phantom popup; on confirm the log prints `✓ on-chain deposit confirmed`; the wallet's free balance rises (1 SOL → 1 unit) |
| 1:18 | Provider flow as the wallet: **Attest** (fields are pre-filled from the grade) → **Bond** `3` → **Mint** `1` | Log: attested → bonded → minted. Then, a few seconds later: `⛓ Token-2022 mint created …` and `⛓ 1h … minted to wallet …`; the **mint line** under the book becomes a clickable devnet-explorer link |
| 1:28 | Click the mint-line link / switch to Phantom | Solana Explorer shows the mint; Phantom shows **1.00** of the contract token — a real, transferable Token-2022 balance |
| 1:35–1:50 | Sweep cursor: tape → book → mint line → Phantom | Closing shot: one price printed, money where it should be, real tokens in a real wallet |

If a devnet confirmation lags, hold the current sentence — the UI refreshes
itself ~6 s after a mint to catch the async mirror.

## Voiceover script (~2 minutes)

> **[0:00]** This is MWNT, where small data centres sell idle GPU time to
> strangers. Spare compute is hard to trade, because every GPU differs and every
> hour is perishable. So we turned it into a commodity.
>
> **[0:08]** One click seeds a real round through the public API. Three providers
> attest their hardware against a fingerprinted grade, post collateral, and set a
> single standing floor. Nordfjord asks for anything above a dollar fifty and then
> walks away. Three buyers post their maximums, fully escrowed. Notice that each
> ask is bumped by the seller's failure rate, so reliability is priced in before
> the round even clears.
>
> **[0:20]** One auction settles at one price. Sixty hours clear at two dollars
> flat. Nordfjord asked for one-fifty and receives two, while Tessellate offered
> two-forty, pays two, and has its spare escrow refunded instantly. Truthful
> bidding is simply the best strategy. The seller's money then waits in escrow
> until delivery actually happens.
>
> **[0:38]** Tessellate redeems, and the hours deliver. The escrow releases to
> Nordfjord, its record improves, and its next collateral requirement drops. Trust
> is earned down, not assumed.
>
> **[0:50]** Now comes the part that makes strangers safe. Ten hours no-show. The
> buyer is refunded twenty dollars, compensated four more from the seller's bond,
> and six on top of that are slashed into a shared insurance pool. Run both sides
> of the trade yourself and you lose six dollars every cycle. Fraud isn't detected
> here; it's made unprofitable by arithmetic.
>
> **[1:05]** And none of this is mocked. I'm connected with a real Phantom wallet.
> When I deposit devnet SOL, the server re-reads the transaction on-chain before
> it credits a single cent.
>
> **[1:18]** Then I mint capacity as this wallet, and the line "each contract is
> one token mint" stops being a whitepaper promise. A real Token-2022 mint spins
> up on devnet, and the hours land straight in Phantom, real and transferable. The
> holder-signed burn on redemption is the honest next step.
>
> **[1:35]** This is graded, dated, bonded compute that trades like a commodity and
> settles on real tokens, because the protocol manufactures the trust that makes it
> one.

## Delivery notes

- Pace ≈ 150 words/min. The bolded numbers ($2.00, $4, $6) are Act 1; the word
  "real" (wallet, transaction, Token-2022) is Act 2. Lean on both.
- Intended pauses: after "**receives** two dollars" (let the tape print
  register), after "unprofitable by arithmetic" (let the pool figure sit), and
  after "real and transferable" (let Phantom's balance show).
- The token mint involves two devnet transactions (create mint, then mint-to);
  expect a 3–6 s delay before the ⛓ log lines and the explorer link appear.
  Fill by re-stating what's on screen ("that's the mint being created on
  devnet") — never apologise, never narrate UI mechanics.

## Known constraints (say these before judges find them)

- **Token-2022 needs the local mint-authority key.** On the Vercel deploy
  (`MWNT_ESCROW_ADDRESS` set) the chain layer is deposit-verify only and
  minting is disabled; record the token act locally where the app holds the key.
- **SOL budget.** Minting needs a real bond (`1.5 × qty × ref price`), paid in
  deposited SOL. That's why the coda mints **1 hour**, not forty — keep devnet
  SOL needs inside faucet limits. The escrow pays mint fees and tops itself up
  via airdrop when low, but faucets rate-limit; making one deposit first is the
  reliable way to fund it.
- **Mirror is one-way.** Acquisition (provider mint, auction win) mints real
  tokens to the wallet; redeeming burns the *internal* ledger token. Burning
  the on-chain token needs the holder's signature — stated, not faked
  ([app/tokens.py](app/tokens.py) docstring).
- **1 SOL = 1 quote unit.** A demo convention — there's no SOL/USDC oracle on
  devnet.

## Optional 15-second extension (if the slot allows)

- **Resale**: in the Trade desk, act as Tessellate, post a floor of 10 hours at
  $2.20, **Add participant** for a late buyer bidding $2.30, clear again — a
  second, higher print lands on the tape. Line: *"Capacity behaves like
  inventory — Tessellate's plans slipped, so it resells into the next round."*

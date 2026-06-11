# DEMO.md — the 90-second demo

Two artefacts in this file: the **run-of-show** (exactly which buttons to press,
second by second) and the **voiceover script** (timed to the clicks, ~225 words
at a normal speaking pace). They are written to be performed together — record
the screen while following the run-of-show, then lay the voiceover on top, or
speak it live.

## Before you record (one minute of prep)

1. Start the server: `uvicorn app.main:app --reload`, open http://127.0.0.1:8000/.
2. Full-screen the browser, hide bookmarks bar, set zoom so the three panels
   and the trade desk are visible without scrolling (≈ 90% on a 1080p screen).
3. Press **Reset** so the index tape is empty — the first print lands harder.
4. Do one silent rehearsal: Seed → Clear → Redeem 20 → deliver all → Redeem 10
   → no-show all. Reset again. The whole sequence is 9 clicks; the timings
   below leave slack for the UI to refresh.
5. Mouse discipline: park the cursor near the next button during each line.

## Run-of-show (what your hands do)

| Time | Action | What appears on screen |
|---|---|---|
| 0:00–0:10 | Nothing — let the empty console breathe | Header, empty index tape, empty book |
| 0:10 | Click **Seed worked example** | Activity log fills: 3 providers attest + bond + mint, 3 buyers escrow bids; book shows 3 green bid levels vs 3 red ask levels |
| 0:10–0:25 | Hover slowly down the order book | Asks shown at *effective* prices (reliability-bumped); depth bars |
| 0:25 | Click **Clear round now** | Banner: "Cleared **60h** at **$2.00**"; **$2.00** prints on the index tape; Tessellate's $12 refund visible in Participants |
| 0:25–0:45 | Point at Nordfjord in Participants | quote_free $0 — its $80 sits in escrow, not its wallet |
| 0:45 | In **Redeem**: pick *Tessellate AI*, qty **20**, click **Redeem**; then click **deliver** on the pending ticket(s) | Ticket flips to green `delivered`; Nordfjord's free balance jumps; its fail-rate pill stays clean |
| 0:45–1:00 | (talk over the green tickets) | |
| 1:00 | Redeem **10** more as Tessellate, click **no-show** | Log prints: `refund 20.00, comp 4.00, slashed 6.00 to pool`; **Insurance pool ticks to $6.00**; Nordfjord's pill now shows a fail % |
| 1:00–1:20 | Point at the pool figure, then at Nordfjord's pill | |
| 1:20–1:30 | Sweep cursor across: tape → book → pool | Closing shot: one price printed, money where it should be |

Total: 9 clicks. If a refresh lags, hold the current sentence — the script has
~10 seconds of slack built in.

## Voiceover script (~225 words ≈ 90 seconds)

> **[0:00]** This is MWNT — a marketplace where small data centres sell idle
> GPU time to buyers who've never heard of them. Spare compute is hard to
> trade: every GPU is different, and every hour is perishable. So we made it
> a commodity.
>
> **[0:10]** One click seeds a real scenario through the public API. Three
> providers attest their hardware against a fingerprinted grade checklist,
> post collateral, and set one standing floor — Nordfjord says "anything above
> a dollar fifty" and never touches the market again. Three buyers post
> maximums, fully escrowed. Notice the asks: each floor is bumped by the
> seller's failure rate. Reliability is priced in *before* clearing.
>
> **[0:25]** One auction, one price. Sixty hours clear at two dollars flat.
> Nordfjord asked one-fifty and *receives* two dollars; Tessellate offered
> two-forty, *pays* two dollars, and its spare escrow is already refunded.
> Truthful bidding is simply the best strategy. And the seller's money? Held
> in escrow until delivery actually happens.
>
> **[0:45]** Tessellate redeems and the hours deliver: escrow releases,
> Nordfjord's record improves, and its future collateral requirement drops.
> Trust is earned down, not assumed.
>
> **[1:00]** Now the part that makes strangers safe. Ten hours no-show.
> Refund: twenty dollars. Compensation: four — from the seller's bond. And
> six more slashed into a shared insurance pool. Run both sides of that trade
> yourself and you lose six dollars every cycle. Fraud isn't detected here —
> it's unprofitable by arithmetic.
>
> **[1:20]** Graded, dated, bonded compute — trading like a commodity, because
> the protocol manufactures the trust that makes it one.

## Delivery notes for the voiceover

- Pace ≈ 150 words/min — conversational, not rushed. The bolded numbers
  ($2.00, $4, $6) are the demo; lean on them.
- The two intended pauses: after "**receives** two dollars" (let the tape
  print register) and after "unprofitable by arithmetic" (let the pool figure
  sit on screen).
- If recording live and something lags, the safe filler is to re-state what's
  on screen ("that's the clearing price printing on the index") — never
  apologise, never narrate the UI mechanics.

## Optional 15-second extensions (if the slot is 105s+)

- **Resale**: in the Trade desk, act as Tessellate and post a floor of 10
  hours at $2.20, add a bid from a new participant at $2.30, clear again — a
  second, higher print lands on the tape. Line: *"Capacity behaves like
  inventory — Tessellate's plans slipped, so it resells into the next round."*
- **Real chain**: click Connect Phantom, deposit devnet SOL, show the credit.
  Line: *"And the wallet string isn't decorative — deposits are verified
  against a real Solana devnet transaction before a cent is credited."*

"""
Configuration — the economic constants and the grade catalogue.

Everything a judge might ask "why this number?" about lives here, with the
reasoning next to it. Changing market behaviour should mean editing this file,
not hunting through the engine.
"""

from datetime import date, timedelta

QUOTE_CURRENCY = "USDC"

# --- Layer 2: delivery windows ------------------------------------------------
# Coarse weekly windows keep the book count small (grades x windows = books).
# v1 lists the next N ISO weeks. Finer granularity is roadmap, not demo.
UPCOMING_WINDOWS = 4


def upcoming_windows(n: int = UPCOMING_WINDOWS, today: date | None = None) -> list[str]:
    """ISO-week window ids, e.g. '2026-W30', starting next week (you cannot
    buy a window that is already spoiling)."""
    today = today or date.today()
    out = []
    d = today + timedelta(weeks=1)
    for _ in range(n):
        y, w, _ = d.isocalendar()
        out.append(f"{y}-W{w:02d}")
        d += timedelta(weeks=1)
    return out


# --- Layer 1: grade catalogue ---------------------------------------------------
# Each grade is a checklist. The fingerprint (sha256 of the checklist text) is
# computed at startup in grades.py; the id can never quietly change meaning.
GRADE_CATALOGUE = [
    {
        "code": "EU-H100",
        "version": 1,
        "checklist": (
            "GPU model: NVIDIA H100 SXM. Memory: >= 80 GB HBM. "
            "Multi-GPU interconnect: >= 3.2 Tbps. Region: Western or Central Europe. "
            "Provider delivery record: >= 99% or bonded as newcomer."
        ),
        # Machine-checkable form of the same checklist, used by attestation.
        "requirements": {
            "gpu_model": "H100-SXM",
            "min_vram_gb": 80,
            "min_interconnect_tbps": 3.2,
            "regions": ["EU-WEST", "EU-CENTRAL"],
        },
        "reference_price": 2.00,  # seeds bond sizing until the market prints its own index
    },
    {
        "code": "US-A100",
        "version": 1,
        "checklist": (
            "GPU model: NVIDIA A100. Memory: >= 40 GB HBM. "
            "Multi-GPU interconnect: >= 0.6 Tbps. Region: United States. "
            "Provider delivery record: >= 99% or bonded as newcomer."
        ),
        "requirements": {
            "gpu_model": "A100",
            "min_vram_gb": 40,
            "min_interconnect_tbps": 0.6,
            "regions": ["US-EAST", "US-WEST"],
        },
        "reference_price": 1.20,
    },
]

# --- Layer 3: auction -----------------------------------------------------------
# Reliability premium: a seller's floor is ranked at floor * (1 + premium).
# Sellers with history use their measured failure rate; newcomers get a small
# default so "no history" is never ranked better than "good history".
NEWCOMER_FAILURE_RATE = 0.02

# --- Layer 4: bonding -----------------------------------------------------------
# Required bond = rate * outstanding undelivered hours * reference price.
# Newcomers post 150%; every cleanly delivered hour earns the rate down,
# floored so the bond never drops below what a failure actually costs a buyer
# (refund 100% is escrowed already; comp + slash = 50% must stay covered).
BOND_RATE_NEW = 1.50
BOND_RATE_FLOOR = 0.50
BOND_RATE_STEP = 0.01  # rate reduction per delivered hour

# --- Layer 5: settlement --------------------------------------------------------
# On a no-show: buyer is refunded 100% from escrow, compensated COMP_RATE from
# the seller's bond, and the seller is slashed a further SLASH_RATE into the
# shared insurance pool. slash > comp is the anti-fraud arithmetic: self-dealing
# nets -(SLASH_RATE - 0) ... strictly negative every cycle.
COMP_RATE = 0.20
SLASH_RATE = 0.30

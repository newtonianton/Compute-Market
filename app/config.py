"""
Configuration for the compute market.

This is the first file to edit. Everything that defines *what* trades and *who*
is allowed to do what lives here, so you can reshape the market without touching
the engine.
"""

from pydantic import BaseModel


class Sku(BaseModel):
    """A standardized, fungible unit of compute that can be traded.

    Fungibility is the hard problem of a compute market: a buyer must not care
    *which* provider's H100-hour they receive. Defining the unit tightly (GPU
    class, region, interconnect, etc.) is how you make that true. Start simple,
    tighten later.
    """

    sku: str
    gpu_class: str
    unit: str = "gpu-hour"
    description: str = ""


# --- The tradeable units -----------------------------------------------------
# Add, remove, or refine these. Each one becomes its own order book.
DEFAULT_SKUS: list[Sku] = [
    Sku(
        sku="H100-HOUR",
        gpu_class="NVIDIA H100 80GB SXM",
        unit="gpu-hour",
        description="One hour of one standardized NVIDIA H100 80GB SXM GPU.",
    ),
    Sku(
        sku="A100-HOUR",
        gpu_class="NVIDIA A100 80GB",
        unit="gpu-hour",
        description="One hour of one standardized NVIDIA A100 80GB GPU.",
    ),
    Sku(
        sku="B200-HOUR",
        gpu_class="NVIDIA B200",
        unit="gpu-hour",
        description="One hour of one standardized NVIDIA B200 GPU.",
    ),
]

# The currency that orders are priced and settled in. Conceptually a USD
# stablecoin (USDC). In this framework it is just an internal credit balance;
# wiring it to real USDC/SOL is a settlement-layer change (see settlement.py).
QUOTE_CURRENCY = "USDC"


# --- Market knobs ------------------------------------------------------------
# These two flags implement the "stablecoin-style whitelisted mint/redeem" idea.

# If True, a provider is approved to mint the moment it registers. Set to False
# to require an explicit POST /accounts/{id}/whitelist?role=provider step before
# minting is allowed — useful for demoing that the gate is real.
AUTO_WHITELIST_PROVIDERS = True

# If True, only accounts whitelisted as purchasers may redeem capacity for
# delivery. If False (default), anyone holding capacity tokens may redeem, which
# keeps the demo flow short. The brief's "only verified purchasers can redeem"
# corresponds to setting this True.
REQUIRE_WHITELISTED_PURCHASER = False

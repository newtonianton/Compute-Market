"""
Capacity — minting supply and redeeming it for delivery.

This is the "mint / redeem like a stablecoin" core:
  * mint   — only a whitelisted provider can create capacity tokens, the same
             way only a verified issuer can mint a stablecoin.
  * redeem — burns tokens to take delivery. Gated to whitelisted purchasers
             only when REQUIRE_WHITELISTED_PURCHASER is True.

Between mint and redeem the tokens trade freely on the order book (see
market.py), so a speculator can buy and resell capacity without ever redeeming
— exactly the "most traders never take delivery" property.
"""

from fastapi import APIRouter, Depends

from . import config
from .deps import get_store
from .errors import BadRequest, NotWhitelisted
from .models import Account, Mint, MintRequest, RedeemRequest, Redemption
from .store import Store, new_id

router = APIRouter(tags=["capacity"])


def _check_sku(sku: str) -> None:
    if sku not in {s.sku for s in config.DEFAULT_SKUS}:
        raise BadRequest(f"unknown sku {sku!r}; see GET /skus")


@router.get("/skus", response_model=list[config.Sku], summary="List tradeable capacity units")
def list_skus() -> list[config.Sku]:
    return config.DEFAULT_SKUS


@router.post("/capacity/mint", response_model=Account, summary="Mint capacity (whitelisted providers only)")
def mint(req: MintRequest, store: Store = Depends(get_store)) -> Account:
    provider = store.get_account(req.provider_id)
    if not (provider.is_provider and provider.provider_whitelisted):
        raise NotWhitelisted(f"account {req.provider_id} is not a whitelisted provider")
    _check_sku(req.sku)
    store.mint_capacity(req.provider_id, req.sku, req.qty)
    store.append_mint(Mint(id=new_id("mint"), provider_id=req.provider_id, sku=req.sku, qty=req.qty))
    return store.get_account(req.provider_id)


@router.post("/capacity/redeem", response_model=Redemption, summary="Redeem capacity for delivery")
def redeem(req: RedeemRequest, store: Store = Depends(get_store)) -> Redemption:
    acct = store.get_account(req.account_id)
    if config.REQUIRE_WHITELISTED_PURCHASER and not acct.purchaser_whitelisted:
        raise NotWhitelisted(f"account {req.account_id} is not a whitelisted purchaser")
    _check_sku(req.sku)
    store.burn_capacity(req.account_id, req.sku, req.qty)  # raises if insufficient
    record = Redemption(
        id=new_id("redeem"),
        account_id=req.account_id,
        sku=req.sku,
        qty=req.qty,
        note=req.note,
    )
    return store.append_redemption(record)


@router.get("/capacity/mints", response_model=list[Mint], summary="Mint history")
def mints(store: Store = Depends(get_store)) -> list[Mint]:
    return store.list_mints()


@router.get("/capacity/redemptions", response_model=list[Redemption], summary="Redemption history")
def redemptions(store: Store = Depends(get_store)) -> list[Redemption]:
    return store.list_redemptions()

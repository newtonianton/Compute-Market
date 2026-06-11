"""
Grades & capacity — the predicate SKU (Layer 1) and dated windows (Layer 2).

A grade is a checklist with a sha256 fingerprint: anything passing the
checklist is interchangeable by definition, and the id can never quietly mean
something different. A contract = grade x ISO week, e.g. "EU-H100.v1@2026-W30";
on Solana each contract is one SPL token mint.

Minting is the only privileged action: it requires (a) attestation for the
grade and (b) bond coverage for everything the provider will have outstanding —
the reserve rule that stops overselling one real H100.
"""

from fastapi import APIRouter, Depends

from .deps import get_store
from .errors import Forbidden, InsufficientBond
from .models import Contract, Grade, Mint, MintRequest
from .store import EPS, Store, new_id

router = APIRouter(tags=["grades & capacity"])


@router.get("/grades", response_model=list[Grade], summary="The grade catalogue")
def list_grades(store: Store = Depends(get_store)) -> list[Grade]:
    return list(store.grades.values())


@router.get("/contracts", response_model=list[Contract],
            summary="Tradeable books (grade x delivery window)")
def list_contracts(store: Store = Depends(get_store)) -> list[Contract]:
    return list(store.contracts.values())


@router.post("/mint", response_model=Mint, summary="Mint capacity tokens (providers only)")
def mint(req: MintRequest, store: Store = Depends(get_store)) -> Mint:
    acct = store.get_account(req.provider_id)
    contract = store.get_contract(req.contract_id)
    grade = store.get_grade(contract.grade_id)

    if grade.id not in acct.attested_grades:
        raise Forbidden(
            f"{acct.id} is not attested for grade {grade.id}; "
            f"POST /accounts/{acct.id}/attest first"
        )

    ref = contract.last_clearing_price or grade.reference_price
    required = store.required_bond(acct, req.qty, ref)
    if acct.bond + EPS < required:
        raise InsufficientBond(
            f"bond {acct.bond:.2f} < required {required:.2f} "
            f"(rate {store.bond_rate(acct):.2f} x outstanding "
            f"{acct.outstanding_qty + req.qty:g} hours x ref price {ref:.2f}); "
            f"POST /accounts/{acct.id}/bond to top up"
        )

    store.credit_capacity(acct.id, contract.id, req.qty)
    acct.minted_qty += req.qty
    m = Mint(id=new_id("mint"), provider_id=acct.id, contract_id=contract.id,
             qty=req.qty, bond_rate=store.bond_rate(acct))
    store.mints.append(m)
    return m


@router.get("/mints", response_model=list[Mint], summary="Mint history")
def list_mints(store: Store = Depends(get_store)) -> list[Mint]:
    return store.mints

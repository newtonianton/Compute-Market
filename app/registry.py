"""
Registry — making strangers trustworthy (Layer 4).

Three components replace the naive "approved" flag:
  1. Attestation: a benchmark result checked against the grade checklist
     authorises minting (roadmap: TEE attestation).
  2. Bonding: collateral that refunds and compensates buyers on failure.
  3. Reputation: a delivery record that slides the bond rate down and feeds
     the auction's reliability premium.
"""

from fastapi import APIRouter, Depends

from .deps import get_store
from .errors import BadRequest
from .models import Account, AttestRequest, BondRequest, CreateAccount, DepositRequest
from .store import Store, new_id

router = APIRouter(tags=["registry"])


@router.post("/accounts", response_model=Account, summary="Register an account")
def create_account(req: CreateAccount, store: Store = Depends(get_store)) -> Account:
    """Any participant — buyer, provider, or pure trader. No role is needed to
    trade or hold tokens; only minting is gated (by attestation + bond)."""
    acct = Account(id=req.wallet or new_id("acct"), label=req.label)
    return store.add_account(acct)


@router.get("/accounts", response_model=list[Account], summary="List accounts")
def list_accounts(store: Store = Depends(get_store)) -> list[Account]:
    return list(store.accounts.values())


@router.get("/accounts/{account_id}", response_model=Account, summary="Account detail")
def get_account(account_id: str, store: Store = Depends(get_store)) -> Account:
    return store.get_account(account_id)


@router.post("/accounts/{account_id}/deposit", response_model=Account, summary="Fund quote balance")
def deposit(account_id: str, req: DepositRequest, store: Store = Depends(get_store)) -> Account:
    """Funding stub — swap for an on-chain deposit watcher in production."""
    store.get_account(account_id)
    store.credit_quote(account_id, req.amount)
    return store.get_account(account_id)


@router.post("/accounts/{account_id}/bond", response_model=Account, summary="Post collateral")
def post_bond(account_id: str, req: BondRequest, store: Store = Depends(get_store)) -> Account:
    """Moves quote_free into the bond. The bond is what makes a day-one
    stranger safe to buy from: failures are paid from it, not promised."""
    store.post_bond(account_id, req.amount)
    return store.get_account(account_id)


@router.post("/accounts/{account_id}/attest", response_model=Account,
             summary="Run attestation against a grade checklist")
def attest(account_id: str, req: AttestRequest, store: Store = Depends(get_store)) -> Account:
    """Hackathon oracle: the submitted benchmark must satisfy every line of the
    grade's machine-checkable requirements. Passing authorises minting hours
    of that grade. Failing returns exactly which check failed."""
    acct = store.get_account(account_id)
    grade = store.get_grade(req.grade_id)
    r = grade.requirements

    checks = [
        (req.gpu_model == r["gpu_model"],
         f"gpu_model {req.gpu_model!r} != required {r['gpu_model']!r}"),
        (req.vram_gb >= r["min_vram_gb"],
         f"vram {req.vram_gb}GB < required {r['min_vram_gb']}GB"),
        (req.interconnect_tbps >= r["min_interconnect_tbps"],
         f"interconnect {req.interconnect_tbps}Tbps < required {r['min_interconnect_tbps']}Tbps"),
        (req.region in r["regions"],
         f"region {req.region!r} not in {r['regions']}"),
    ]
    failures = [msg for ok, msg in checks if not ok]
    if failures:
        raise BadRequest("attestation failed: " + "; ".join(failures))

    if grade.id not in acct.attested_grades:
        acct.attested_grades.append(grade.id)
    return acct


@router.get("/accounts/{account_id}/bond-status", summary="Bond requirement vs posted")
def bond_status(account_id: str, store: Store = Depends(get_store)) -> dict:
    acct = store.get_account(account_id)
    # Use the max reference price across attested grades as the conservative basis.
    ref = max((store.grades[g].reference_price for g in acct.attested_grades), default=0.0)
    return {
        "account_id": acct.id,
        "bond_posted": acct.bond,
        "bond_rate": store.bond_rate(acct),
        "outstanding_qty": acct.outstanding_qty,
        "required_bond": store.required_bond(acct, 0.0, ref),
        "failure_rate": acct.failure_rate,
    }

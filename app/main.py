"""
Application entrypoint.

Run it:
    uvicorn app.main:app --reload

Then open:
    http://127.0.0.1:8000/        -> the demo console
    http://127.0.0.1:8000/docs    -> interactive API docs (Swagger UI)
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import (
    __version__,
    auction,
    config,
    deps,
    grades,
    onchain,
    registry,
    rfq,
    settlement,
)
from .errors import MarketError

app = FastAPI(
    title="MWNT Compute Market",
    version=__version__,
    description=(
        "Graded, dated, bonded compute that trades like a commodity. "
        "Grades are fingerprinted checklists; contracts add a weekly delivery "
        "window; a uniform-price batch auction sets one price per round; "
        "attestation + bonds + escrow make strangers safe to trade with. "
        f"Prices are quoted in {config.QUOTE_CURRENCY}."
    ),
)

# Permissive CORS for hackathon development. Tighten for prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(MarketError)
async def market_error_handler(_: Request, exc: MarketError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(registry.router)
app.include_router(grades.router)
app.include_router(auction.router)
app.include_router(settlement.router)
app.include_router(rfq.router)
app.include_router(onchain.router)


WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@app.get("/", include_in_schema=False)
def console() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health", tags=["meta"], summary="Liveness check")
def health() -> dict:
    return {"status": "ok", "version": __version__,
            "quote_currency": config.QUOTE_CURRENCY}


@app.post("/reset", tags=["meta"], summary="Wipe market state (demo convenience)")
def reset() -> dict:
    deps.reset_store()
    return {"status": "reset"}

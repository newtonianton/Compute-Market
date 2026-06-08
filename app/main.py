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

from . import __version__, capacity, config, market, registry, settlement
from .errors import MarketError

app = FastAPI(
    title="Compute Market",
    version=__version__,
    description=(
        "A minimal, extensible market for trading GPU compute capacity. "
        "Providers mint standardized capacity units; those units trade on a "
        "price-time-priority order book; buyers redeem them for delivery. "
        f"Prices are quoted in {config.QUOTE_CURRENCY}."
    ),
)

# Permissive CORS so a separately-hosted front-end (or the bundled console
# opened from a file) can call the API during development. Tighten for prod.
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
app.include_router(capacity.router)
app.include_router(market.router)
app.include_router(settlement.router)


WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@app.get("/", include_in_schema=False)
def console() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health", tags=["meta"], summary="Liveness check")
def health() -> dict:
    return {"status": "ok", "version": __version__, "quote_currency": config.QUOTE_CURRENCY}

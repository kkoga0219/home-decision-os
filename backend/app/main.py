"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    cashflow,
    comparison,
    connectors,
    exit_scores,
    loan_scenarios,
    properties,
    rental_scenarios,
)
from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Housing purchase decision engine for the Japanese market",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- routers ---
app.include_router(properties.router)
app.include_router(loan_scenarios.router)
app.include_router(rental_scenarios.router)
app.include_router(exit_scores.router)
app.include_router(comparison.router)
app.include_router(connectors.router)
app.include_router(cashflow.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}

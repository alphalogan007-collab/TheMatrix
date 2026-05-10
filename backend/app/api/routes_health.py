"""
Health and readiness check routes.
These are the only public (unauthenticated) endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    """Check database connectivity."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ready" if db_ok else "not_ready",
        "db": "ok" if db_ok else "error",
    }

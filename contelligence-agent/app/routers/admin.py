"""Admin router — operational endpoints (health deep-check, cache clear, etc.).

Mounted at ``/api/admin`` with appropriate auth guards added in WS-9.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.dependencies import get_settings
from app.settings import AppSettings

logger = logging.getLogger(f"contelligence-agent.{__name__}")

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/cache/stats")
async def cache_stats(settings: AppSettings = Depends(get_settings)) -> dict:
    """Return extraction cache statistics."""
    from app.startup import _extraction_cache

    if _extraction_cache is None:
        return {"enabled": False}

    return _extraction_cache.get_stats()


@router.post("/cache/clear")
async def cache_clear(settings: AppSettings = Depends(get_settings)) -> dict:
    """Clear the extraction cache."""
    from app.startup import _extraction_cache

    if _extraction_cache is None:
        return {"cleared": False, "reason": "cache not enabled"}

    await _extraction_cache.clear()
    logger.info("Extraction cache cleared by admin request.")
    return {"cleared": True}


@router.get("/rate-limits")
async def rate_limit_status() -> dict:
    """Return current rate limiter status."""
    from app.rate_limiting import rate_limiter

    return rate_limiter.get_status()

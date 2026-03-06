"""Token-bucket rate limiter for Azure service calls.

Each configured service gets an independent token bucket.  The bucket
refills at ``requests_per_minute / 60`` tokens per second up to the
``burst`` ceiling.  ``acquire()`` blocks the caller until tokens are
available, preventing Azure API 429 errors.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from .models import RateLimit

if TYPE_CHECKING:
    from app.settings import AppSettings

logger = logging.getLogger(f"contelligence-agent.{__name__}")

class RateLimiter:
    """Token-bucket rate limiter for Azure service calls."""

    def __init__(self) -> None:
        self.limits: dict[str, RateLimit] = {}
        self._tokens: dict[str, float] = {}
        self._last_refill: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def configure(
        self,
        service: str,
        requests_per_minute: int,
        burst: int | None = None,
    ) -> None:
        """Configure rate limits for a service."""
        effective_burst = burst or requests_per_minute
        self.limits[service] = RateLimit(
            requests_per_minute=requests_per_minute,
            burst=effective_burst,
        )
        self._tokens[service] = float(effective_burst)
        self._last_refill[service] = time.monotonic()

    async def acquire(self, service: str, tokens: int = 1) -> None:
        """Wait until the rate limit allows the operation.

        If the service is not configured, returns immediately.
        """
        if service not in self.limits:
            return  # No limit configured — allow immediately

        async with self._lock:
            while True:
                self._refill(service)
                if self._tokens[service] >= tokens:
                    self._tokens[service] -= tokens
                    return
                limit = self.limits[service]
                refill_rate = limit.requests_per_minute / 60.0
                wait_time = (tokens - self._tokens[service]) / refill_rate
                # Release lock while waiting so other callers can proceed
                self._lock.release()
                await asyncio.sleep(min(wait_time, 1.0))
                await self._lock.acquire()

    def _refill(self, service: str) -> None:
        """Refill tokens based on elapsed wall-clock time."""
        now = time.monotonic()
        elapsed = now - self._last_refill[service]
        limit = self.limits[service]
        refill_rate = limit.requests_per_minute / 60.0
        self._tokens[service] = min(
            self._tokens[service] + elapsed * refill_rate,
            float(limit.burst),
        )
        self._last_refill[service] = now

    def get_available_tokens(self, service: str) -> float | None:
        """Return current available tokens for monitoring."""
        if service not in self.limits:
            return None
        self._refill(service)
        return self._tokens[service]

    def get_configured_services(self) -> list[str]:
        """List all services with configured rate limits."""
        return list(self.limits.keys())

    def get_status(self) -> dict:
        """Return status summary of all configured limiters."""
        status: dict[str, dict] = {}
        for service in self.limits:
            self._refill(service)
            limit = self.limits[service]
            status[service] = {
                "requests_per_minute": limit.requests_per_minute,
                "burst": limit.burst,
                "available_tokens": round(self._tokens[service], 2),
            }
        return {"services": status}


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

rate_limiter = RateLimiter()


def configure_default_rate_limits(settings: "AppSettings") -> None:
    """Configure rate limits from application settings."""
    rate_limiter.configure(
        "azure-openai",
        requests_per_minute=settings.RATE_LIMIT_OPENAI_RPM,
        burst=10,
    )
    rate_limiter.configure(
        "azure-doc-intel",
        requests_per_minute=settings.RATE_LIMIT_DOC_INTEL_RPM,
        burst=5,
    )
    rate_limiter.configure(
        "azure-search-query",
        requests_per_minute=300,
        burst=50,
    )
    rate_limiter.configure(
        "azure-search-index",
        requests_per_minute=60,
        burst=10,
    )
    rate_limiter.configure(
        "azure-cosmos",
        requests_per_minute=500,
        burst=100,
    )
    logger.info(
        "Rate limits configured for: %s",
        ", ".join(rate_limiter.get_configured_services()),
    )

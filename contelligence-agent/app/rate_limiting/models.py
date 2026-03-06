"""Rate limiting models."""

from __future__ import annotations

from pydantic import BaseModel


class RateLimit(BaseModel):
    """Configuration for a single service's rate limit."""

    requests_per_minute: int
    burst: int

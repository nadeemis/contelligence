"""Per-session resource quota enforcement.

Each active session gets its own ``SessionQuotaManager`` instance that
tracks consumption of tool calls, documents, tokens, and duration.
When a limit is exceeded a ``QuotaExceededError`` is raised, which is
mapped to HTTP 429 by the FastAPI exception handler.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from app.models.exceptions import QuotaExceededError


class SessionQuotaConfig(BaseModel):
    """Configurable per-session quota limits."""

    max_tool_calls: int = 200
    max_documents: int = 100
    max_tokens: int = 500_000
    max_duration_minutes: int = 60


class SessionQuotaManager:
    """Per-session resource quota enforcement."""

    DEFAULT_QUOTAS = SessionQuotaConfig()

    def __init__(
        self,
        session_id: str,
        quotas: SessionQuotaConfig | None = None,
    ) -> None:
        self.session_id = session_id
        self.quotas = quotas or self.DEFAULT_QUOTAS
        self.usage: dict[str, int] = defaultdict(int)

    def check_quota(self, resource: str, amount: int = 1) -> bool:
        """Return ``True`` if the operation would stay within quota."""
        limit = getattr(self.quotas, f"max_{resource}", None)
        if limit is None:
            return True
        return (self.usage[resource] + amount) <= limit

    def consume(self, resource: str, amount: int = 1) -> None:
        """Record resource consumption.

        Raises ``QuotaExceededError`` if the limit would be exceeded.
        """
        if not self.check_quota(resource, amount):
            raise QuotaExceededError(
                self.session_id, resource, self.get_remaining(resource),
            )
        self.usage[resource] += amount

    def get_remaining(self, resource: str) -> int | None:
        """Return remaining quota for *resource*, or ``None`` if unlimited."""
        limit = getattr(self.quotas, f"max_{resource}", None)
        if limit is None:
            return None
        return max(0, limit - self.usage[resource])

    def get_usage_report(self) -> dict[str, dict[str, int | None]]:
        """Return a summary of resource usage vs limits."""
        report: dict[str, dict[str, int | None]] = {}
        for field in self.quotas.model_fields:
            resource = field.removeprefix("max_")
            limit = getattr(self.quotas, field)
            report[resource] = {
                "used": self.usage.get(resource, 0),
                "limit": limit,
                "remaining": self.get_remaining(resource),
            }
        return report

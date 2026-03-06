"""Unit tests for Phase 4 — Rate Limiting (token-bucket algorithm)."""

from __future__ import annotations

import asyncio

import pytest

from app.rate_limiting.rate_limiter import RateLimiter
from app.rate_limiting.session_quota import SessionQuotaConfig, SessionQuotaManager
from app.models.exceptions import QuotaExceededError


# ---------------------------------------------------------------------------
# RateLimiter tests
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Test the token-bucket rate limiter."""

    def test_configure_creates_bucket(self) -> None:
        rl = RateLimiter()
        rl.configure("test-svc", requests_per_minute=60, burst=10)
        assert "test-svc" in rl.get_configured_services()
        assert rl.get_available_tokens("test-svc") == 10.0

    def test_unconfigured_service_returns_none(self) -> None:
        rl = RateLimiter()
        assert rl.get_available_tokens("unknown") is None

    @pytest.mark.asyncio
    async def test_acquire_decrements_tokens(self) -> None:
        rl = RateLimiter()
        rl.configure("svc", requests_per_minute=600, burst=10)
        await rl.acquire("svc", tokens=3)
        remaining = rl.get_available_tokens("svc")
        assert remaining is not None
        assert remaining < 10.0

    @pytest.mark.asyncio
    async def test_acquire_unconfigured_returns_immediately(self) -> None:
        rl = RateLimiter()
        # Should not raise or block
        await rl.acquire("no-such-service")

    def test_get_status(self) -> None:
        rl = RateLimiter()
        rl.configure("a", requests_per_minute=60, burst=5)
        rl.configure("b", requests_per_minute=120, burst=20)
        status = rl.get_status()
        assert "a" in status["services"]
        assert "b" in status["services"]
        assert status["services"]["a"]["burst"] == 5


# ---------------------------------------------------------------------------
# SessionQuotaManager tests
# ---------------------------------------------------------------------------


class TestSessionQuotaManager:
    """Test per-session quota enforcement."""

    def test_check_quota_passes_initially(self) -> None:
        config = SessionQuotaConfig(max_tool_calls=10)
        mgr = SessionQuotaManager(config)
        # Should not raise
        mgr.check_quota("s1", "tool_calls")

    def test_check_quota_raises_on_exceed(self) -> None:
        config = SessionQuotaConfig(max_tool_calls=2)
        mgr = SessionQuotaManager(config)
        mgr.consume("s1", "tool_calls", 2)
        with pytest.raises(QuotaExceededError):
            mgr.check_quota("s1", "tool_calls")

    def test_consume_and_get_remaining(self) -> None:
        config = SessionQuotaConfig(max_tool_calls=10)
        mgr = SessionQuotaManager(config)
        mgr.consume("s1", "tool_calls", 4)
        assert mgr.get_remaining("s1", "tool_calls") == 6

    def test_get_remaining_unknown_returns_max(self) -> None:
        config = SessionQuotaConfig(max_tool_calls=100)
        mgr = SessionQuotaManager(config)
        assert mgr.get_remaining("new-session", "tool_calls") == 100

    def test_usage_report(self) -> None:
        config = SessionQuotaConfig(max_tool_calls=10, max_documents=5)
        mgr = SessionQuotaManager(config)
        mgr.consume("s1", "tool_calls", 3)
        report = mgr.get_usage_report("s1")
        assert report["tool_calls"]["used"] == 3
        assert report["tool_calls"]["max"] == 10
        assert report["documents"]["used"] == 0

    def test_unknown_resource_raises_value_error(self) -> None:
        config = SessionQuotaConfig()
        mgr = SessionQuotaManager(config)
        with pytest.raises(ValueError):
            mgr.check_quota("s1", "nonexistent_resource")

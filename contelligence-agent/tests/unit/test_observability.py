"""Unit tests for Phase 4 — Observability (metrics, tracing, logging)."""

from __future__ import annotations

import logging

import pytest

from app.observability.logging import (
    SessionContextFilter,
    clear_session_context,
    configure_logging,
    set_instance_context,
    set_session_context,
)
from app.observability.metrics import (
    cache_hit_counter,
    error_counter,
    session_counter,
    tool_call_counter,
)
from app.observability.tracing import trace_tool_call


class TestSessionContextFilter:
    """Test the logging context filter."""

    def test_filter_adds_defaults(self) -> None:
        filt = SessionContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None,
        )
        result = filt.filter(record)
        assert result is True
        assert record.session_id == "none"  # type: ignore[attr-defined]
        assert record.instance_id == "unknown"  # type: ignore[attr-defined]

    def test_context_vars_propagate(self) -> None:
        set_session_context("test-session-123")
        set_instance_context("instance-abc")

        filt = SessionContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None,
        )
        filt.filter(record)
        assert record.session_id == "test-session-123"  # type: ignore[attr-defined]
        assert record.instance_id == "instance-abc"  # type: ignore[attr-defined]

        # Clean up
        clear_session_context()

    def test_configure_logging_sets_level(self) -> None:
        configure_logging("DEBUG")
        hf_logger = logging.getLogger("contelligence")
        assert hf_logger.level == logging.DEBUG
        # Reset
        configure_logging("INFO")


class TestMetrics:
    """Ensure custom metrics are created and accessible."""

    def test_counters_exist(self) -> None:
        # Just assert they're not None (OpenTelemetry NoOp is fine)
        assert session_counter is not None
        assert tool_call_counter is not None
        assert error_counter is not None
        assert cache_hit_counter is not None


class TestTracing:
    """Test tracing decorators."""

    @pytest.mark.asyncio
    async def test_trace_tool_call_decorator(self) -> None:
        call_count = 0

        @trace_tool_call("test-tool")
        async def my_tool(x: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"result": x * 2}

        result = await my_tool(5)
        assert result == {"result": 10}
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_trace_tool_call_propagates_exception(self) -> None:
        @trace_tool_call("failing-tool")
        async def bad_tool() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await bad_tool()

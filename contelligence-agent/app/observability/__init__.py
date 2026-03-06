"""Observability package for the HikmaForge agent.

Provides Application Insights integration via OpenTelemetry, custom
metrics, distributed tracing decorators, and structured logging.
"""

from .logging import (
    SessionContextFilter,
    clear_session_context,
    configure_logging,
    set_instance_context,
    set_session_context,
)
from .metrics import (
    cache_hit_counter,
    cache_miss_counter,
    document_counter,
    error_counter,
    rate_limit_wait_counter,
    rate_limit_wait_histogram,
    session_counter,
    session_duration_histogram,
    tool_call_counter,
    tool_duration_histogram,
)
from .setup import initialize_observability
from .tracing import trace_session, trace_tool_call, tracer

__all__ = [
    # Setup
    "initialize_observability",
    # Metrics
    "session_counter",
    "tool_call_counter",
    "error_counter",
    "document_counter",
    "cache_hit_counter",
    "cache_miss_counter",
    "rate_limit_wait_counter",
    "tool_duration_histogram",
    "session_duration_histogram",
    "rate_limit_wait_histogram",
    # Tracing
    "tracer",
    "trace_session",
    "trace_tool_call",
    # Logging
    "configure_logging",
    "set_session_context",
    "clear_session_context",
    "set_instance_context",
    "SessionContextFilter",
]

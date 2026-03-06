"""Distributed tracing decorators for sessions and tool calls.

Provides ``@trace_session`` and ``@trace_tool_call(name)`` decorators
that wrap async functions with OpenTelemetry spans and automatically
record custom metrics.
"""

from __future__ import annotations

import functools
import json
import time
from typing import Any, Callable, Coroutine

from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode

from .metrics import (
    error_counter,
    session_counter,
    tool_call_counter,
    tool_duration_histogram,
)

tracer = trace.get_tracer("contelligence.agent")


def trace_session(
    func: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Decorator to wrap session creation in a trace span."""

    @functools.wraps(func)
    async def wrapper(self: Any, instruction: str, options: Any, **kwargs: Any) -> Any:
        model = getattr(options, "model", "unknown")
        require_approval = getattr(options, "require_approval", False)

        with tracer.start_as_current_span(
            "agent.session",
            kind=SpanKind.SERVER,
            attributes={
                "session.instruction": instruction[:200],
                "session.model": model,
                "session.require_approval": str(require_approval),
            },
        ) as span:
            try:
                result = await func(self, instruction, options, **kwargs)
                span.set_attribute("session.id", str(result))
                span.set_status(StatusCode.OK)
                session_counter.add(1, {"model": model})
                return result
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                error_counter.add(1, {"type": type(exc).__name__})
                raise

    return wrapper


def trace_tool_call(tool_name: str) -> Callable:
    """Decorator factory for tracing individual tool executions."""

    def decorator(
        func: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(
                f"tool.{tool_name}",
                kind=SpanKind.INTERNAL,
                attributes={"tool.name": tool_name},
            ) as span:
                start = time.monotonic()
                try:
                    result = await func(*args, **kwargs)
                    duration_ms = (time.monotonic() - start) * 1000
                    span.set_attribute("tool.duration_ms", duration_ms)
                    try:
                        span.set_attribute(
                            "tool.result_size",
                            len(json.dumps(result, default=str)),
                        )
                    except (TypeError, ValueError):
                        pass
                    tool_call_counter.add(
                        1, {"tool": tool_name, "status": "success"},
                    )
                    tool_duration_histogram.record(
                        duration_ms, {"tool": tool_name},
                    )
                    return result
                except Exception as exc:
                    duration_ms = (time.monotonic() - start) * 1000
                    span.set_status(StatusCode.ERROR, str(exc))
                    span.record_exception(exc)
                    tool_call_counter.add(
                        1, {"tool": tool_name, "status": "error"},
                    )
                    tool_duration_histogram.record(
                        duration_ms, {"tool": tool_name},
                    )
                    error_counter.add(
                        1, {"tool": tool_name, "type": type(exc).__name__},
                    )
                    raise

        return wrapper

    return decorator

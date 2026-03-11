"""Structured logging with session and instance context.

Uses ``contextvars`` so context is automatically propagated across
``await`` boundaries within the same async task.  Application Insights
picks up the custom dimensions from the structured log records.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

_session_id_var: ContextVar[str | None] = ContextVar(
    "session_id", default=None,
)
_instance_id_var: ContextVar[str | None] = ContextVar(
    "instance_id", default=None,
)

class CustomConsoleColoredFormatter(logging.Formatter):
    
    grey = '\x1b[38;21m'
    blue = '\x1b[38;5;39m'
    green = '\x1b[38;5;35m'
    yellow = '\x1b[38;5;226m'
    red = '\x1b[38;5;196m'
    bold_red = '\x1b[31;1m'
    reset = '\x1b[0m'

    format_str = "%(asctime)s [%(levelname)s] [%(instance_id)s] [%(session_id)s] %(name)s: %(message)s (%(filename)s:%(lineno)d)"
    
    FORMATS = {
        logging.DEBUG: blue + format_str + reset,
        logging.INFO: grey + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class SessionContextFilter(logging.Filter):
    """Logging filter that attaches session and instance context."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = _session_id_var.get() or "none"  # type: ignore[attr-defined]
        record.instance_id = _instance_id_var.get() or "unknown"  # type: ignore[attr-defined]
        return True


def set_session_context(session_id: str) -> None:
    """Set the session ID for the current async context."""
    _session_id_var.set(session_id)


def clear_session_context() -> None:
    """Clear the session ID context."""
    _session_id_var.set(None)


def set_instance_context(instance_id: str) -> None:
    """Set the instance ID at startup (once per replica)."""
    _instance_id_var.set(instance_id)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structured logging with session context.

    Applies the ``SessionContextFilter`` to the root ``contelligence-agent``
    logger so all child loggers inherit the formatting.  Also configures
    the root logger so that uvicorn and third-party log messages are visible.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # --- root logger: catches uvicorn, third-party, etc. ---
    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        root_handler = logging.StreamHandler()
        root_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            )
        )
        root.addHandler(root_handler)

    # --- contelligence-agent logger: colored + session context ---
    hf_logger = logging.getLogger("contelligence-agent")
    hf_logger.setLevel(level)
    hf_logger.propagate = False  # don't duplicate into the root handler

    if not hf_logger.handlers:
        hf_handler = logging.StreamHandler()
        hf_handler.setFormatter(CustomConsoleColoredFormatter())
        hf_handler.addFilter(SessionContextFilter())
        hf_logger.addHandler(hf_handler)

    logging.getLogger('azure.core').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)
    logging.getLogger('azure.identity').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('agent_framework').setLevel(logging.INFO)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    logging.getLogger('azure.cosmos').setLevel(logging.WARNING)
    logging.getLogger('sse_starlette.sse').setLevel(logging.INFO)
    logging.getLogger('aiosqlite').setLevel(logging.INFO)
    # The GlobalEndpointManager runs a background health-check timer that
    # floods logs with ERROR-level tracebacks on transient DNS / network
    # failures.  These are retried automatically by the SDK so we only
    # surface genuinely critical messages.
    logging.getLogger(
        'azure.cosmos.aio._GlobalEndpointManager'
    ).setLevel(logging.CRITICAL)
    logging.getLogger(
        'azure.cosmos.aio._global_endpoint_manager_async'
    ).setLevel(logging.CRITICAL)
    logging.getLogger('msal.token_cache').setLevel(logging.WARNING)
    logging.getLogger('azure.monitor.opentelemetry').setLevel(logging.ERROR)
    logging.getLogger('opentelemetry').setLevel(logging.ERROR)
    logging.getLogger('asyncio').setLevel(logging.ERROR)

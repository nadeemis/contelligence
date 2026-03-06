"""Application Insights / OpenTelemetry startup configuration.

Initialises the Azure Monitor OpenTelemetry distro which automatically
instruments FastAPI, ``httpx``, logging, and asyncio.  Must be called
**before** any other initialisation to capture startup-time spans.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import trace, metrics  # noqa: F401 — re-exported for convenience

logger = logging.getLogger(f"contelligence-agent.{__name__}")

def initialize_observability() -> None:
    """Configure Azure Monitor OpenTelemetry at application startup.

    Reads ``APPLICATIONINSIGHTS_CONNECTION_STRING`` from the environment.
    If the variable is not set, telemetry is disabled gracefully.
    """
    conn_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn_string:
        logger.warning(
            "APPLICATIONINSIGHTS_CONNECTION_STRING not set — "
            "Application Insights telemetry disabled."
        )
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            connection_string=conn_string,
            enable_live_metrics=True,
        )
        logger.info("Application Insights telemetry initialized.")
    except Exception:
        logger.exception(
            "Failed to initialise Application Insights — "
            "continuing without telemetry."
        )

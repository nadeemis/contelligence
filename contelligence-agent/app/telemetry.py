"""Telemetry configuration for the Contelligence agent and MCP servers.

The Azure MCP Server reads ``APPLICATIONINSIGHTS_CONNECTION_STRING``
directly from the environment — no additional SDK setup is required.
This module centralises the small amount of startup-time validation
and logging.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(f"contelligence-agent.{__name__}")


def configure_mcp_telemetry() -> None:
    """Validate and configure MCP server telemetry routing.

    * Checks ``APPLICATIONINSIGHTS_CONNECTION_STRING`` — if set, MCP
      traces will automatically be routed to Application Insights.
    * Ensures ``AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT`` defaults to
      ``false`` (opt-out of Microsoft-collected telemetry).
    """
    ai_connection = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if ai_connection:
        logger.info(
            "MCP telemetry routed to Application Insights "
            "(connection string detected)."
        )
    else:
        logger.info(
            "APPLICATIONINSIGHTS_CONNECTION_STRING not set — "
            "MCP telemetry will not be routed to Application Insights."
        )

    # Opt out of Microsoft-collected telemetry by default
    os.environ.setdefault("AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT", "false")

    telemetry_flag = os.environ["AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT"]
    logger.info(
        "AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT=%s", telemetry_flag,
    )

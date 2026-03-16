"""MCP server configuration for Contelligence.

Defines connection settings for:
- **Azure MCP Server** (unified — 42+ Azure services via stdio or HTTP)
- **GitHub MCP Server** (repository access via HTTP)

Transport modes:
- **stdio** (development): The MCP server runs as a subprocess inside the
  agent container.  No ``AZURE_MCP_SERVER_URL`` env var is needed.
- **HTTP** (production): The MCP server runs as a sidecar Container App or
  standalone service.  Set ``AZURE_MCP_SERVER_URL`` to the server's URL.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")

def get_mcp_servers_config() -> dict[str, dict[str, Any]]:
    """Return MCP server configurations based on the current environment.

    Returns a *mutable* dict so callers (e.g. ``startup.py``) can inject
    resolved tokens at runtime.
    """
    azure_mcp_url = os.getenv("AZURE_MCP_SERVER_URL", "").strip()

    servers: dict[str, dict[str, Any]] = {
        "azure": (
            # HTTP mode for remote / production deployment
            {
                "type": "http",
                "url": azure_mcp_url,
            }
            if azure_mcp_url
            else
            # stdio mode for local / development — runs as subprocess
            {
                "type": "stdio",
                "command": ["azmcp", "server", "start"],
            }
        ),
        "github": {
            "type": "http",
            "url": "https://api.githubcopilot.com/mcp/",
            "auth": {
                "type": "token",
                "token_source": "keyvault",
                "secret_name": "github-copilot-token",
                # Resolved at startup — see ``resolve_github_token``
                "token": "",
            },
        },
        "powerbi-remote": {
                "type": "http",
                "url": "https://api.fabric.microsoft.com/v1/mcp/powerbi"
            }
        }
    
    

    mode = "http" if azure_mcp_url else "stdio"
    logger.info("Azure MCP Server configured in %s mode", mode)
    return servers


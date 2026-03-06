"""MCP (Model Context Protocol) server configuration and health checking.

Provides configuration for the unified Azure MCP Server (42+ Azure services)
and the GitHub MCP server (repository access).
"""

from __future__ import annotations

from .config import get_mcp_servers_config, resolve_github_token
from .health import verify_mcp_servers

__all__ = [
    "get_mcp_servers_config",
    "resolve_github_token",
    "verify_mcp_servers",
]

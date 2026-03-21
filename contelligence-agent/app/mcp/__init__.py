"""MCP (Model Context Protocol) server configuration and health checking.

All servers are loaded from file-based config (``~/.contelligence/mcp-config.json``
and ``~/.copilot/mcp-config.json``).  Default servers are scaffolded on first launch.
"""

from __future__ import annotations

from .config import get_mcp_servers_config
from .file_config import ensure_default_config, load_file_based_servers, save_app_config
from .sdk_adapters import mcp_config_to_sdk_config
from .health import verify_mcp_servers

__all__ = [
    "ensure_default_config",
    "get_mcp_servers_config",
    "load_file_based_servers",
    "save_app_config",
    "verify_mcp_servers",
    "mcp_config_to_sdk_config",
]

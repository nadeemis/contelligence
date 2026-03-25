"""MCP server configuration for Contelligence.

All MCP servers are loaded from file-based configuration:
- ``~/.contelligence/mcp-config.json`` (app-specific, highest priority)
- ``~/.copilot/mcp-config.json``  (shared ecosystem, imported by default)

A default config with common servers (Azure, GitHub, Power BI) is
scaffolded on first launch by the Cowork Electron shell.

See ``docs/gitignore/MCP_CONFIG_LAYERED_LOADING.md`` for the full design.
"""

from __future__ import annotations

import logging
from typing import Any

from app.mcp.file_config import load_file_based_servers

logger = logging.getLogger(f"contelligence-agent.{__name__}")


def get_mcp_servers_config() -> dict[str, dict[str, Any]]:
    """Return MCP server configurations loaded from config files.

    Layers (lowest → highest priority):
    1. Shared ecosystem servers from ``~/.copilot/mcp-config.json``.
    2. App-specific servers from ``~/.contelligence/mcp-config.json``.

    Same-name entries in a higher layer replace the lower one entirely.
    The app config may also specify an ``exclude`` list to remove servers.

    Returns a *mutable* dict so callers (e.g. ``startup.py``) can inject
    resolved tokens at runtime.
    """
    servers, exclude, imported_shared = load_file_based_servers()

    for name in exclude:
        removed = servers.pop(name, None)
        if removed:
            logger.info("Excluded MCP server '%s' per app config", name)

    logger.info(f"Final MCP server list: {list(servers.keys())}")
    return servers


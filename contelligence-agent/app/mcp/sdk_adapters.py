
import logging
from typing import Any

from copilot import MCPLocalServerConfig, MCPRemoteServerConfig, MCPServerConfig

# ------------------------------------------------------------------
# MCP config normalization
# ------------------------------------------------------------------

logger = logging.getLogger(f"contelligence-agent.{__name__}")

def mcp_config_to_sdk_config(
    mcp_servers: dict[str, Any],
) -> list[MCPServerConfig]:
    """Ensure each MCP server config is SDK-ready.
    The Copilot SDK requires a ``tools`` field on each server entry
    to declare which MCP tools the session may use.  When the field
    is absent we default to ``["*"]`` (all tools) so that servers
    added via the management UI work out of the box.
    """
    normalized: list[MCPServerConfig] = []
    for name, cfg in mcp_servers.items():
        entry = dict(cfg)  # shallow copy — don't mutate the original
        entry = {**entry, **{"tools": ["*"]}} # default tools if missing
        
        if entry.get("type") in ["stdio", "local"]:
            # The SDK expects a slightly different config shape for local vs remote servers
            entry = MCPLocalServerConfig(**entry)
        elif entry.get("type") in ["http", "sse"]:
            entry = MCPRemoteServerConfig(**entry)
        else:
            # log error and skip invalid server configs
            logger.error(
                f"MCP server '{name}' has unknown type '{entry.get('type')}' and will be skipped"
            )
            continue
        
        normalized.append(entry)
    return normalized
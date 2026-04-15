
import logging
from typing import Any

from copilot.session import MCPLocalServerConfig, MCPRemoteServerConfig, MCPServerConfig

from app.utils.azure_token_provider import resolve_header_tokens

# ------------------------------------------------------------------
# MCP config normalization
# ------------------------------------------------------------------

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# SDK timeout (milliseconds) for auth-proxy MCP servers that need extra
# time to complete OAuth/Entra ID flows before the first JSON-RPC response.
_AUTH_PROXY_SDK_TIMEOUT_MS: int = 60_000  # 60 seconds

# Command names known to proxy to remote MCP endpoints with auth.
_AUTH_PROXY_COMMANDS: frozenset[str] = frozenset({"agency"})


def _needs_auth_proxy_timeout(entry: dict[str, Any]) -> bool:
    """Return ``True`` if the server config looks like an auth-proxy.

    Detects patterns like ``agency mcp remote --url ...`` where the
    server needs to resolve a 401 WWW-Authenticate challenge and acquire
    an Entra ID token before returning the first JSON-RPC response.
    """
    command = entry.get("command", "")
    cmd_name = command if isinstance(command, str) else (command[0] if isinstance(command, list) and command else "")
    if cmd_name not in _AUTH_PROXY_COMMANDS:
        return False
    args = entry.get("args", [])
    return isinstance(args, list) and "remote" in args


async def mcp_config_to_sdk_config(
    mcp_servers: dict[str, Any],
) -> list[MCPServerConfig]:
    """Ensure each MCP server config is SDK-ready.

    The Copilot SDK requires a ``tools`` field on each server entry
    to declare which MCP tools the session may use.  When the field
    is absent we default to ``["*"]`` (all tools) so that servers
    added via the management UI work out of the box.

    If a server config contains a ``headers`` dict whose values include
    ``${token}`` placeholders, they are resolved to a real Azure access
    token via ``DefaultAzureCredential`` before the config is passed to
    the SDK.

    For auth-proxy servers (e.g. ``agency mcp remote``) that need extra
    time to resolve OAuth challenges, a generous SDK ``timeout`` is set
    automatically unless the user already specified one.
    """
    normalized: list[MCPServerConfig] = []
    for name, cfg in mcp_servers.items():
        entry = dict(cfg)  # shallow copy — don't mutate the original
        entry = {**entry, **{"tools": ["*"]}} # default tools if missing

        # Resolve ${token} placeholders in headers
        if isinstance(entry.get("headers"), dict):
            entry["headers"] = await resolve_header_tokens(entry["headers"], name)

        if entry.get("type") in ["stdio", "local"]:
            # Auto-set a generous timeout for auth-proxy servers so the
            # SDK doesn't kill the process before the OAuth flow completes.
            if "timeout" not in entry and _needs_auth_proxy_timeout(entry):
                entry["timeout"] = _AUTH_PROXY_SDK_TIMEOUT_MS
                logger.info(
                    "MCP server '%s' detected as auth-proxy — "
                    "setting SDK timeout to %dms",
                    name,
                    _AUTH_PROXY_SDK_TIMEOUT_MS,
                )

            # Strip non-SDK keys before constructing the typed config.
            # MCPLocalServerConfig only accepts: tools, type, timeout,
            # command, args, env, cwd.
            sdk_keys = {"tools", "type", "timeout", "command", "args", "env", "cwd"}
            entry = MCPLocalServerConfig(**{k: v for k, v in entry.items() if k in sdk_keys})
        elif entry.get("type") in ["http", "sse"]:
            # Strip non-SDK keys for remote configs too.
            sdk_keys = {"tools", "type", "timeout", "url", "headers"}
            entry = MCPRemoteServerConfig(**{k: v for k, v in entry.items() if k in sdk_keys})
        else:
            # log error and skip invalid server configs
            logger.error(
                f"MCP server '{name}' has unknown type '{entry.get('type')}' and will be skipped"
            )
            continue
        
        normalized.append(entry)
    return normalized
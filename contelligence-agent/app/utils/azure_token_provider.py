"""Acquire Azure access tokens via DefaultAzureCredential for MCP header injection.

Used by ``app.mcp.sdk_adapters`` and ``app.mcp.health`` to replace
``${token}`` placeholders in MCP server header values with a real
Bearer token.

The token is cached and refreshed automatically when near expiry.
Falls back to the ``AzCliCredential`` helper when DefaultAzureCredential
cannot resolve a suitable credential (e.g. local dev without managed identity).
"""

from __future__ import annotations

import logging
import re
import time

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# Matches ${token} or ${token:<scope>} placeholders in header values.
TOKEN_PATTERN = re.compile(r"\$\{token(?::([^}]+))?\}")

# Default scope when no explicit scope is provided in the placeholder.
DEFAULT_SCOPE = "https://management.azure.com/.default"

# Refresh 2 minutes before expiry
_REFRESH_MARGIN_S = 120

# Simple in-memory cache keyed by scope
_token_cache: dict[str, tuple[str, float]] = {}


async def get_azure_token(scope: str) -> str:
    """Return a cached or freshly-acquired Azure access token for *scope*.

    Parameters
    ----------
    scope:
        The OAuth2 scope to request, e.g.
        ``"https://graph.microsoft.com/.default"`` or
        ``"https://management.azure.com/.default"``.

    Returns
    -------
    str
        The raw access token string.

    Raises
    ------
    RuntimeError
        If no credential chain can produce a token.
    """
    cached = _token_cache.get(scope)
    if cached:
        token, expires_on = cached
        if (expires_on - time.time()) > _REFRESH_MARGIN_S:
            return token

    # Try DefaultAzureCredential first
    try:
        from azure.identity.aio import DefaultAzureCredential

        credential = DefaultAzureCredential()
        try:
            token_resp = await credential.get_token(scope)
            _token_cache[scope] = (token_resp.token, token_resp.expires_on)
            return token_resp.token
        finally:
            await credential.close()
    except Exception:
        logger.debug(
            "DefaultAzureCredential failed for scope %s, falling back to az CLI",
            scope,
        )

    # Fallback: Azure CLI credential
    from app.utils.az_cli_credential import AzCliCredential

    async with AzCliCredential(scope=scope) as cred:
        token_resp = await cred.get_token(scope)
        _token_cache[scope] = (token_resp.token, token_resp.expires_on)
        return token_resp.token


async def resolve_header_tokens(
    headers: dict[str, str],
    server_name: str,
) -> dict[str, str]:
    """Replace ``${token}`` / ``${token:<scope>}`` placeholders in *headers*.

    Uses :func:`get_azure_token` to fetch a token from
    ``DefaultAzureCredential`` (with az-CLI fallback).

    Examples of supported placeholder forms::

        "Authorization": "Bearer ${token}"                     # uses default scope
        "Authorization": "Bearer ${token:https://graph.microsoft.com/.default}"  # explicit scope
    """
    resolved: dict[str, str] = {}
    for key, value in headers.items():
        match = TOKEN_PATTERN.search(value)
        if match:
            scope = match.group(1) or DEFAULT_SCOPE
            try:
                token = await get_azure_token(scope)
                value = TOKEN_PATTERN.sub(token, value)
            except Exception:
                logger.error(
                    "Failed to resolve token for MCP server '%s' header '%s' (scope=%s)",
                    server_name,
                    key,
                    scope,
                    exc_info=True,
                )
        resolved[key] = value
    return resolved


def has_token_placeholders(headers: dict[str, str]) -> bool:
    """Return *True* if any header value contains a ``${token}`` placeholder."""
    return any(TOKEN_PATTERN.search(v) for v in headers.values())

"""Shared HTTP client helpers for Microsoft Graph API calls.

Authentication (in priority order):
1. Pre-supplied delegated token via ``MSGRAPH_ACCESS_TOKEN``.
2. Client-credentials (app-only) via ``MSGRAPH_CLIENT_ID`` /
   ``MSGRAPH_CLIENT_SECRET`` / ``MSGRAPH_TENANT_ID``.
3. ``DefaultAzureCredential`` as a managed-identity / dev fallback.

For initial setup of delegated tokens, use ``acquire_token_device_code``
to run the one-time device-code flow and store the resulting token in
``MSGRAPH_ACCESS_TOKEN``.

**Recommended for server-side usage:** configure client credentials
(``MSGRAPH_CLIENT_ID``, ``MSGRAPH_CLIENT_SECRET``, ``MSGRAPH_TENANT_ID``)
with ``MSGRAPH_USER_ID``, then grant **application** permissions + admin
consent in the Azure portal.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urlencode

import httpx
import msal
from azure.identity.aio import (
    ClientSecretCredential,
    DefaultAzureCredential,
)

logger = logging.getLogger(f"contelligence-agent.{__name__}")

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"

# Delegated permission scopes used by the device-code flow.
_DELEGATED_SCOPES = [
    "User.Read",
    "Chat.Read",
    "Chat.ReadWrite",
    "Team.ReadBasic.All",
    "Channel.ReadBasic.All",
    "ChannelMessage.Read.All",
    "ChannelMessage.Send",
    "TeamMember.Read.All",
    "Calendars.Read",
]


# ── Admin consent URL helper ──────────────────────────────────────────

def get_admin_consent_url(tenant_id: str, client_id: str) -> str:
    """Return the Entra ID admin-consent URL for the app registration.

    A tenant admin must visit this URL once to grant the required
    permissions for all users in the organisation.
    """
    params = urlencode({
        "client_id": client_id,
        "scope": " ".join(_DELEGATED_SCOPES),
        "redirect_uri": "https://login.microsoftonline.com/common/oauth2/nativeclient",
        "response_type": "code",
        "prompt": "admin_consent",
    }, quote_via=quote)
    return (
        f"https://login.microsoftonline.com/{tenant_id}/adminconsent?{params}"
    )


# ── Device-code flow (one-time delegated token acquisition) ───────────

def acquire_token_device_code(
    tenant_id: str,
    client_id: str,
) -> str:
    """Run the device-code flow interactively and return an access token.

    This is a **one-time CLI utility** — not called during normal
    request handling.  Store the returned token in
    ``MSGRAPH_ACCESS_TOKEN`` for subsequent API calls.
    """
    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )

    # Try the token cache first.
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(_DELEGATED_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]

    flow = app.initiate_device_flow(scopes=_DELEGATED_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device-code flow initiation failed: {flow}")

    logger.info(flow["message"])
    print(flow["message"])  # noqa: T201  — intentional for CLI usage

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        error = result.get("error_description") or result.get("error", "unknown")
        raise RuntimeError(f"Device-code authentication failed: {error}")

    return result["access_token"]

def _get_graph_settings(
    context: dict,
) -> tuple[str, str, str, str, str]:
    """Extract Microsoft Graph settings from the tool context.

    Returns (tenant_id, client_id, client_secret, access_token, user_id).
    """
    settings = context.get("settings")
    tenant_id: str = getattr(settings, "MSGRAPH_TENANT_ID", "") or ""
    client_id: str = getattr(settings, "MSGRAPH_CLIENT_ID", "") or ""
    client_secret: str = getattr(settings, "MSGRAPH_CLIENT_SECRET", "") or ""
    access_token: str = getattr(settings, "MSGRAPH_ACCESS_TOKEN", "") or ""
    user_id: str = getattr(settings, "MSGRAPH_USER_ID", "") or ""
    return tenant_id, client_id, client_secret, access_token, user_id


async def _get_auth_header(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    access_token: str,
) -> str:
    """Return a Bearer Authorization header value.

    Priority:
    1. Pre-supplied *access_token* (delegated / on-behalf-of flow).
    2. Service-principal client credentials when all three IDs are set.
    3. ``DefaultAzureCredential`` as the last-resort fallback.
    """
    if access_token:
        return f"Bearer {access_token}"

    if client_id and client_secret and tenant_id:
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    else:
        credential = DefaultAzureCredential()

    try:
        token_resp = await credential.get_token(_GRAPH_SCOPE)
        return f"Bearer {token_resp.token}"
    finally:
        await credential.close()


def _resolve_path(path: str, access_token: str, user_id: str) -> str:
    """Replace ``me/`` with ``users/{user_id}/`` for app-only auth.

    The ``/me`` alias requires a delegated (user-context) token.
    When using client-credentials (no *access_token*) and a
    *user_id* is configured, rewrite the path so Graph can resolve
    the target user.
    """
    if access_token:
        # Delegated token — "me" works as-is.
        return path
    if not user_id:
        return path
    stripped = path.lstrip("/")
    if stripped == "me" or stripped.startswith("me/"):
        return f"users/{user_id}{stripped[2:]}"
    return path


async def graph_request(
    context: dict,
    path: str,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Perform an authenticated request against Microsoft Graph API.

    *path* is relative to ``https://graph.microsoft.com/v1.0/``
    (e.g. ``"me/chats"``).

    When using client-credentials auth (no delegated token) and
    ``MSGRAPH_USER_ID`` is configured, ``me/`` is automatically
    rewritten to ``users/{user_id}/``.
    """
    
    
    tenant_id, client_id, client_secret, access_token, user_id = _get_graph_settings(context)

    url = get_admin_consent_url(tenant_id=tenant_id, client_id=client_id)
    print(url)  # noqa: T201  — intentional for visibility when auth issues arise
    
    resolved = _resolve_path(path, access_token, user_id)
    url = f"{_GRAPH_BASE}/{resolved.lstrip('/')}"

    headers = {
        "Authorization": await _get_auth_header(
            tenant_id, client_id, client_secret, access_token,
        ),
        "Accept": "application/json",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            method,
            url,
            json=json_body,
            params=params or {},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

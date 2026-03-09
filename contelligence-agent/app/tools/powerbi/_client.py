"""Shared HTTP client helpers for Power BI REST API calls.

Uses the Power BI REST API for cross-system compatibility.  DAX queries
are executed via the "Execute Queries" endpoint which leverages the XMLA
read path under the hood.

Authentication: Entra ID (DefaultAzureCredential) by default, or a
service-principal client-secret flow when POWERBI_CLIENT_ID /
POWERBI_CLIENT_SECRET are configured.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from azure.identity.aio import (
    ClientSecretCredential,
    DefaultAzureCredential,
)

logger = logging.getLogger(__name__)

_POWERBI_BASE = "https://api.powerbi.com/v1.0/myorg"
_POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"


def _get_powerbi_settings(
    context: dict,
) -> tuple[str, str, str, str]:
    """Extract Power BI settings from the tool context.

    Returns (workspace_id, tenant_id, client_id, client_secret).
    """
    settings = context.get("settings")
    workspace_id: str = getattr(settings, "POWERBI_WORKSPACE_ID", "") or ""
    tenant_id: str = getattr(settings, "POWERBI_TENANT_ID", "") or ""
    client_id: str = getattr(settings, "POWERBI_CLIENT_ID", "") or ""
    client_secret: str = getattr(settings, "POWERBI_CLIENT_SECRET", "") or ""
    return workspace_id, tenant_id, client_id, client_secret


async def _get_auth_header(
    tenant_id: str, client_id: str, client_secret: str,
) -> str:
    """Return a Bearer Authorization header value.

    Uses service-principal credentials when *client_id* and *client_secret*
    are both set; otherwise falls back to ``DefaultAzureCredential``.
    """
    if client_id and client_secret and tenant_id:
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    else:
        credential = DefaultAzureCredential()

    try:
        token_resp = await credential.get_token(_POWERBI_SCOPE)
        return f"Bearer {token_resp.token}"
    finally:
        await credential.close()


async def powerbi_request(
    context: dict,
    path: str,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """Perform an authenticated request against the Power BI REST API.

    *path* is relative (e.g. ``"datasets"``).
    When *workspace_id* is provided (or configured in settings), the request
    is scoped to that workspace (group).
    """
    (
        default_workspace,
        tenant_id,
        client_id,
        client_secret,
    ) = _get_powerbi_settings(context)

    effective_workspace = workspace_id or default_workspace

    if effective_workspace:
        url = f"{_POWERBI_BASE}/groups/{effective_workspace}/{path}"
    else:
        url = f"{_POWERBI_BASE}/{path}"

    headers = {
        "Authorization": await _get_auth_header(
            tenant_id, client_id, client_secret,
        ),
        "Accept": "application/json",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.request(
            method, url, json=json_body, params=params or {}, headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

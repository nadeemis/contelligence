"""Shared HTTP client helpers for SharePoint REST API v1 calls.

Authentication (in priority order):
1. Pre-supplied delegated token via ``SHAREPOINT_ACCESS_TOKEN``.
2. Client-credentials (app-only) via ``MSGRAPH_CLIENT_ID`` /
   ``MSGRAPH_CLIENT_SECRET`` / ``MSGRAPH_TENANT_ID`` — acquires a token
   scoped to the target SharePoint site.
3. ``DefaultAzureCredential`` as a managed-identity / dev fallback.

All endpoints target the SharePoint REST API v1 at
``https://{site_url}/_api/...``.

Required settings:
- ``SHAREPOINT_SITE_URL`` — e.g. ``https://contoso.sharepoint.com/sites/team``
  (no trailing slash).

Optional settings (reuses MS Graph app registration):
- ``SHAREPOINT_ACCESS_TOKEN`` — pre-supplied delegated token.
- ``MSGRAPH_TENANT_ID``, ``MSGRAPH_CLIENT_ID``, ``MSGRAPH_CLIENT_SECRET``
  — used to acquire an app-only token scoped to the SharePoint site.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from azure.identity.aio import (
    ClientSecretCredential,
    DefaultAzureCredential,
)

logger = logging.getLogger(f"contelligence-agent.{__name__}")


def _get_sharepoint_settings(
    context: dict,
) -> tuple[str, str, str, str, str]:
    """Extract SharePoint / Graph settings from the tool context.

    Returns (site_url, tenant_id, client_id, client_secret, access_token).
    """
    settings = context.get("settings")
    site_url: str = (getattr(settings, "SHAREPOINT_SITE_URL", "") or "").rstrip("/")
    access_token: str = getattr(settings, "SHAREPOINT_ACCESS_TOKEN", "") or ""
    tenant_id: str = getattr(settings, "MSGRAPH_TENANT_ID", "") or ""
    client_id: str = getattr(settings, "MSGRAPH_CLIENT_ID", "") or ""
    client_secret: str = getattr(settings, "MSGRAPH_CLIENT_SECRET", "") or ""
    return site_url, tenant_id, client_id, client_secret, access_token


def _sharepoint_scope(site_url: str) -> str:
    """Derive the OAuth2 resource scope from the site URL.

    For a site like ``https://contoso.sharepoint.com/sites/team``,
    the scope is ``https://contoso.sharepoint.com/.default``.
    """
    # Extract scheme + host (e.g. "https://contoso.sharepoint.com")
    from urllib.parse import urlparse

    parsed = urlparse(site_url)
    return f"{parsed.scheme}://{parsed.hostname}/.default"


async def _get_auth_header(
    site_url: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    access_token: str,
) -> str:
    """Return a ``Bearer`` Authorization header value.

    Priority:
    1. Pre-supplied *access_token*.
    2. Service-principal client credentials when all three IDs are set.
    3. ``DefaultAzureCredential`` as the last-resort fallback.
    """
    if access_token:
        return f"Bearer {access_token}"

    scope = _sharepoint_scope(site_url)

    if client_id and client_secret and tenant_id:
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        try:
            token_resp = await credential.get_token(scope)
            return f"Bearer {token_resp.token}"
        finally:
            await credential.close()

    # Try DefaultAzureCredential first, fall back to az CLI
    try:
        credential = DefaultAzureCredential()
        try:
            token_resp = await credential.get_token(scope)
            return f"Bearer {token_resp.token}"
        finally:
            await credential.close()
    except Exception:
        logger.debug("DefaultAzureCredential failed, falling back to az CLI")
        from app.utils.az_cli_credential import AzCliCredential

        async with AzCliCredential(scope=scope) as cred:
            token_resp = await cred.get_token(scope)
            return f"Bearer {token_resp.token}"


async def sharepoint_request(
    context: dict,
    path: str,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    site_url: str | None = None,
    accept: str = "application/json;odata=nometadata",
) -> dict[str, Any]:
    """Perform an authenticated request against the SharePoint REST API v1.

    *path* is relative to ``{site_url}/_api/``
    (e.g. ``"web/lists"``).

    Optionally override the *site_url* per-call; otherwise the value
    from ``SHAREPOINT_SITE_URL`` settings is used.
    """
    (
        settings_site_url,
        tenant_id,
        client_id,
        client_secret,
        access_token,
    ) = _get_sharepoint_settings(context)

    effective_site_url = (site_url or settings_site_url).rstrip("/")
    if not effective_site_url:
        raise ValueError(
            "SHAREPOINT_SITE_URL is not configured and no site_url was "
            "provided. Set SHAREPOINT_SITE_URL in your environment."
        )

    url = f"{effective_site_url}/_api/{path.lstrip('/')}"

    headers = {
        "Authorization": await _get_auth_header(
            effective_site_url,
            tenant_id,
            client_id,
            client_secret,
            access_token,
        ),
        "Accept": accept,
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.request(
            method,
            url,
            json=json_body,
            params=params or {},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def sharepoint_download(
    context: dict,
    path: str,
    *,
    site_url: str | None = None,
) -> bytes:
    """Download binary content from a SharePoint REST API v1 endpoint.

    Returns raw bytes of the response body.
    """
    (
        settings_site_url,
        tenant_id,
        client_id,
        client_secret,
        access_token,
    ) = _get_sharepoint_settings(context)

    effective_site_url = (site_url or settings_site_url).rstrip("/")
    if not effective_site_url:
        raise ValueError(
            "SHAREPOINT_SITE_URL is not configured and no site_url was "
            "provided. Set SHAREPOINT_SITE_URL in your environment."
        )

    url = f"{effective_site_url}/_api/{path.lstrip('/')}"

    headers = {
        "Authorization": await _get_auth_header(
            effective_site_url,
            tenant_id,
            client_id,
            client_secret,
            access_token,
        ),
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content

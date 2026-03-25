"""Shared HTTP client helpers for Azure DevOps REST API calls."""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx
from azure.identity.aio import DefaultAzureCredential

logger = logging.getLogger(__name__)

_API_VERSION = "7.2-preview"
# Azure DevOps resource ID used as the OAuth2 scope.
_DEVOPS_SCOPE = "499b84ac-1321-427f-aa17-267ca6975798/.default"


def _get_devops_settings(context: dict) -> tuple[str, str, str]:
    """Extract Azure DevOps settings from the tool context.

    Returns (organization, default_project, pat).
    Raises ``ValueError`` when the organization is not configured.
    """
    settings = context.get("settings")
    org: str = getattr(settings, "AZURE_DEVOPS_DEFAULT_ORG", "") or ""
    project: str = getattr(settings, "AZURE_DEVOPS_DEFAULT_PROJECT", "") or ""
    pat: str = getattr(settings, "AZURE_DEVOPS_PAT", "") or ""

    # if not org:
    #     raise ValueError("AZURE_DEVOPS_ORG is not configured")
    return org, project, pat


async def _get_auth_header(pat: str = None) -> str:
    """Return an Authorization header value.

    Uses PAT (Basic auth) when *pat* is provided, otherwise falls back
    to DefaultAzureCredential (Bearer token).
    """
    if pat:
        token = base64.b64encode(f":{pat}".encode()).decode()
        return f"Basic {token}"

    credential = DefaultAzureCredential()
    try:
        token_resp = await credential.get_token(_DEVOPS_SCOPE)
        return f"Bearer {token_resp.token}"
    finally:
        await credential.close()


def _base_url(org: str) -> str:
    """Return the Azure DevOps base URL for an organization."""
    return f"https://dev.azure.com/{org}"


async def devops_request(
    context: dict,
    path: str,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    organization: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """Perform an authenticated request against the Azure DevOps REST API.

    *path* is relative (e.g. ``"_apis/wit/workitems/123"``).
    If *project* is given, it is injected between the org base and the path.
    *method* defaults to ``"GET"``; pass ``"POST"`` for write / query endpoints.
    """
    default_org, default_project, pat = _get_devops_settings(context)
    effective_project = project or default_project
    effective_org = organization or default_org
    
    base = _base_url(effective_org)
    if effective_project:
        url = f"{base}/{effective_project}/{path}"
    else:
        url = f"{base}/{path}"

    query_params = params or {}
    query_params.setdefault("api-version", _API_VERSION)

    headers = {
        "Authorization": await _get_auth_header(pat),
        "Accept": "application/json",
        "X-TFS-FedAuthRedirect": "Suppress",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            method, url, json=json_body, params=query_params, headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

"""Tool to download a file from SharePoint via an authenticated browser session.

Instead of using service-principal or delegated tokens directly, this tool
launches a Playwright-managed Edge browser with a persistent profile.  All
SharePoint REST API calls are executed *inside the browser* via
``page.evaluate(fetch(...))``, so they carry the user's real SSO cookies
and headers automatically — no token management required.
"""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._browser_session import SharePointSession

logger = logging.getLogger(__name__)


class BrowserDownloadFileParams(BaseModel):
    """Parameters for the sharepoint_browser_download_file tool."""

    server_relative_url: str = Field(
        ...,
        description=(
            "Server-relative URL of the file to download "
            "(e.g. '/sites/team/Shared Documents/Report.pdf'). "
            "Obtain this from sharepoint_list_items results."
        ),
    )
    site_url: str = Field(
        ...,
        description=(
            "Full URL of the SharePoint site "
            "(e.g. 'https://contoso.sharepoint.com/sites/team'). "
            "Required to establish the browser session."
        ),
    )
    include_content: bool = Field(
        True,
        description=(
            "If true, include the file content as a base64-encoded string "
            "in the response. Set to false to retrieve metadata only."
        ),
    )
    headless: bool = Field(
        True,
        description=(
            "If true (default), launch the browser in headless mode. "
            "Falls back to headed mode automatically if authentication "
            "requires interactive login (MFA). Set to false to always "
            "open a visible browser window."
        ),
    )


@define_tool(
    name="sharepoint_browser_download_file",
    description=(
        "Download a file from a SharePoint document library using an "
        "authenticated browser session (Playwright + Edge). The browser "
        "carries the user's real SSO cookies, so no service-principal or "
        "delegated tokens are needed. Returns file metadata (name, size, "
        "version) and optionally the file content as a base64-encoded string."
    ),
    parameters_model=BrowserDownloadFileParams,
)
async def browser_download_file(
    params: BrowserDownloadFileParams, context: dict,
) -> dict[str, Any]:
    """Download a file from SharePoint via browser session."""
    try:
        encoded_url = quote(params.server_relative_url, safe="/")

        async with SharePointSession(params.site_url, headless=params.headless) as session:
            # Fetch file metadata
            metadata = await session.fetch(
                "GET",
                f"_api/web/GetFileByServerRelativeUrl('{encoded_url}')"
                f"?$select=Name,ServerRelativeUrl,Length,TimeCreated,"
                f"TimeLastModified,MajorVersion,MinorVersion,"
                f"CheckOutType,UIVersionLabel",
            )

            result: dict[str, Any] = {
                "name": metadata.get("Name"),
                "serverRelativeUrl": metadata.get("ServerRelativeUrl"),
                "sizeBytes": int(metadata.get("Length", 0)),
                "created": metadata.get("TimeCreated"),
                "lastModified": metadata.get("TimeLastModified"),
                "version": metadata.get("UIVersionLabel", ""),
            }

            if params.include_content:
                content = await session.fetch_bytes(
                    "GET",
                    f"_api/web/GetFileByServerRelativeUrl('{encoded_url}')/$value",
                )
                result["contentBase64"] = base64.b64encode(content).decode("ascii")
                result["downloadedBytes"] = len(content)

        return result

    except Exception as exc:
        logger.exception("sharepoint_browser_download_file failed")
        return {"error": str(exc)}

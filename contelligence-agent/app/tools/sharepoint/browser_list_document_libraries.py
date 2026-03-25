"""Tool to list document libraries in a SharePoint site via browser session.

Uses Playwright + Edge to execute SharePoint REST API calls inside an
authenticated browser context — no service-principal or delegated tokens needed.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._browser_session import SharePointSession

logger = logging.getLogger(__name__)


class BrowserListDocumentLibrariesParams(BaseModel):
    """Parameters for the sharepoint_browser_list_document_libraries tool."""

    site_url: str = Field(
        ...,
        description=(
            "Full URL of the SharePoint site "
            "(e.g. 'https://contoso.sharepoint.com/sites/team'). "
            "Required to establish the browser session."
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
    name="sharepoint_browser_list_document_libraries",
    description=(
        "List all document libraries in a SharePoint site using an "
        "authenticated browser session (Playwright + Edge). The browser "
        "carries the user's real SSO cookies, so no service-principal or "
        "delegated tokens are needed. Returns library IDs, titles, item "
        "counts, and URLs. Use the library title with "
        "sharepoint_browser_list_items to browse folders and files."
    ),
    parameters_model=BrowserListDocumentLibrariesParams,
)
async def browser_list_document_libraries(
    params: BrowserListDocumentLibrariesParams, context: dict,
) -> dict[str, Any]:
    """Retrieve document libraries from the SharePoint site via browser session."""
    try:
        async with SharePointSession(params.site_url, headless=params.headless) as session:
            data = await session.fetch(
                "GET",
                "_api/web/lists"
                "?$filter=BaseTemplate eq 101"
                "&$select=Id,Title,ItemCount,Created,LastItemModifiedDate,"
                "RootFolder/ServerRelativeUrl"
                "&$expand=RootFolder",
            )

            libraries = [
                {
                    "id": lib.get("Id"),
                    "title": lib.get("Title"),
                    "itemCount": lib.get("ItemCount"),
                    "created": lib.get("Created"),
                    "lastModified": lib.get("LastItemModifiedDate"),
                    "serverRelativeUrl": (lib.get("RootFolder") or {}).get(
                        "ServerRelativeUrl"
                    ),
                }
                for lib in data.get("value", [])
            ]
            return {"count": len(libraries), "libraries": libraries}

    except Exception as exc:
        logger.exception("sharepoint_browser_list_document_libraries failed")
        return {"error": str(exc)}

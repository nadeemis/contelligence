"""Tool to list document libraries in a SharePoint site."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import sharepoint_request

logger = logging.getLogger(__name__)


class ListDocumentLibrariesParams(BaseModel):
    """Parameters for the sharepoint_list_document_libraries tool."""

    site_url: str | None = Field(
        None,
        description=(
            "Full URL of the SharePoint site "
            "(e.g. 'https://contoso.sharepoint.com/sites/team'). "
            "Overrides the default SHAREPOINT_SITE_URL setting."
        ),
    )


@define_tool(
    name="sharepoint_list_document_libraries",
    description=(
        "List all document libraries in a SharePoint site. "
        "Returns library IDs, titles, item counts, and URLs. "
        "Use the library title with sharepoint_list_items to browse "
        "folders and files inside a library."
    ),
    parameters_model=ListDocumentLibrariesParams,
)
async def list_document_libraries(
    params: ListDocumentLibrariesParams, context: dict,
) -> dict[str, Any]:
    """Retrieve document libraries from the SharePoint site."""
    try:
        # Filter to document libraries only (BaseTemplate 101)
        data = await sharepoint_request(
            context,
            "web/lists",
            params={
                "$filter": "BaseTemplate eq 101",
                "$select": "Id,Title,ItemCount,Created,LastItemModifiedDate,RootFolder/ServerRelativeUrl",
                "$expand": "RootFolder",
            },
            site_url=params.site_url,
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
        logger.exception("sharepoint_list_document_libraries failed")
        return {"error": str(exc)}

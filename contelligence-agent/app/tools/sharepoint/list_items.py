"""Tool to list folders and files in a SharePoint document library."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import sharepoint_request

logger = logging.getLogger(__name__)


class ListItemsParams(BaseModel):
    """Parameters for the sharepoint_list_items tool."""

    library_title: str = Field(
        ...,
        description=(
            "Title of the document library to browse "
            "(e.g. 'Documents', 'Shared Documents')."
        ),
    )
    folder_path: str | None = Field(
        None,
        description=(
            "Server-relative path of a subfolder within the library to list. "
            "Omit to list the root of the library. "
            "Example: '/sites/team/Shared Documents/Reports'."
        ),
    )
    site_url: str | None = Field(
        None,
        description=(
            "Full URL of the SharePoint site. "
            "Overrides the default SHAREPOINT_SITE_URL setting."
        ),
    )


@define_tool(
    name="sharepoint_list_items",
    description=(
        "List folders and files inside a SharePoint document library. "
        "Optionally navigate into a subfolder by providing folder_path. "
        "Returns file names, sizes, modification dates, and server-relative URLs. "
        "Use the server-relative URL with sharepoint_download_file to "
        "download a specific file."
    ),
    parameters_model=ListItemsParams,
)
async def list_items(
    params: ListItemsParams, context: dict,
) -> dict[str, Any]:
    """List folders and files in a document library or subfolder."""
    try:
        from urllib.parse import quote

        if params.folder_path:
            encoded = quote(params.folder_path, safe="/")
            base = f"web/GetFolderByServerRelativeUrl('{encoded}')"
        else:
            encoded_title = quote(params.library_title, safe="")
            base = f"web/lists/getByTitle('{encoded_title}')/RootFolder"

        # Fetch subfolders
        folders_data = await sharepoint_request(
            context,
            f"{base}/Folders",
            params={
                "$select": "Name,ServerRelativeUrl,ItemCount,TimeCreated,TimeLastModified",
            },
            site_url=params.site_url,
        )

        folders = [
            {
                "type": "folder",
                "name": f.get("Name"),
                "serverRelativeUrl": f.get("ServerRelativeUrl"),
                "itemCount": f.get("ItemCount"),
                "created": f.get("TimeCreated"),
                "lastModified": f.get("TimeLastModified"),
            }
            for f in folders_data.get("value", [])
            # Skip hidden system folders (e.g. "Forms")
            if f.get("Name") not in ("Forms",)
        ]

        # Fetch files
        files_data = await sharepoint_request(
            context,
            f"{base}/Files",
            params={
                "$select": "Name,ServerRelativeUrl,Length,TimeCreated,TimeLastModified,MajorVersion,MinorVersion",
            },
            site_url=params.site_url,
        )

        files = [
            {
                "type": "file",
                "name": f.get("Name"),
                "serverRelativeUrl": f.get("ServerRelativeUrl"),
                "sizeBytes": int(f.get("Length", 0)),
                "created": f.get("TimeCreated"),
                "lastModified": f.get("TimeLastModified"),
                "version": f"{f.get('MajorVersion', 0)}.{f.get('MinorVersion', 0)}",
            }
            for f in files_data.get("value", [])
        ]

        items = folders + files
        return {
            "folderCount": len(folders),
            "fileCount": len(files),
            "items": items,
        }

    except Exception as exc:
        logger.exception("sharepoint_list_items failed")
        return {"error": str(exc)}

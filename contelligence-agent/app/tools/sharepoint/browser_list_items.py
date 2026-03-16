"""Tool to list folders and files in a SharePoint document library via browser session.

Uses Playwright + Edge to execute SharePoint REST API calls inside an
authenticated browser context.  Supports recursive listing up to a
configurable depth.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._browser_session import SharePointSession

logger = logging.getLogger(__name__)


class BrowserListItemsParams(BaseModel):
    """Parameters for the sharepoint_browser_list_items tool."""

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
    site_url: str = Field(
        ...,
        description=(
            "Full URL of the SharePoint site "
            "(e.g. 'https://contoso.sharepoint.com/sites/team'). "
            "Required to establish the browser session."
        ),
    )
    recursive: bool = Field(
        False,
        description=(
            "If true, recursively list subfolders up to max_depth levels. "
            "Each subfolder's contents are nested under a 'children' key."
        ),
    )
    max_depth: int = Field(
        3,
        ge=1,
        le=10,
        description=(
            "Maximum folder depth to recurse into when recursive is true. "
            "Defaults to 3. Range: 1-10."
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


async def _list_folder(
    session: SharePointSession,
    base_api_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch folders and files for a single folder via the browser session.

    Returns (folders, files) where each is a list of dicts.
    """
    folders_data = await session.fetch(
        "GET",
        f"_api/{base_api_path}/Folders"
        f"?$select=Name,ServerRelativeUrl,ItemCount,TimeCreated,TimeLastModified",
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
        if f.get("Name") not in ("Forms",)
    ]

    files_data = await session.fetch(
        "GET",
        f"_api/{base_api_path}/Files"
        f"?$select=Name,ServerRelativeUrl,Length,TimeCreated,TimeLastModified,"
        f"MajorVersion,MinorVersion",
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

    return folders, files


async def _list_recursive(
    session: SharePointSession,
    folder_server_relative_url: str,
    current_depth: int,
    max_depth: int,
) -> list[dict[str, Any]]:
    """Recursively list folder contents up to *max_depth*."""
    encoded = quote(folder_server_relative_url, safe="/")
    base = f"web/GetFolderByServerRelativeUrl('{encoded}')"

    folders, files = await _list_folder(session, base)

    if current_depth < max_depth:
        for folder in folders:
            url = folder.get("serverRelativeUrl", "")
            if url:
                folder["children"] = await _list_recursive(
                    session, url, current_depth + 1, max_depth,
                )

    return folders + files


@define_tool(
    name="sharepoint_browser_list_items",
    description=(
        "List folders and files inside a SharePoint document library using "
        "an authenticated browser session (Playwright + Edge). Optionally "
        "navigate into a subfolder by providing folder_path. Supports "
        "recursive listing up to a configurable depth (max_depth). Returns "
        "file names, sizes, modification dates, and server-relative URLs. "
        "Use the server-relative URL with sharepoint_browser_download_file "
        "to download a specific file."
    ),
    parameters_model=BrowserListItemsParams,
)
async def browser_list_items(
    params: BrowserListItemsParams, context: dict,
) -> dict[str, Any]:
    """List folders and files in a document library or subfolder via browser."""
    try:
        async with SharePointSession(params.site_url, headless=params.headless) as session:
            # Build the base API path for the root query
            if params.folder_path:
                encoded = quote(params.folder_path, safe="/")
                base = f"web/GetFolderByServerRelativeUrl('{encoded}')"
            else:
                encoded_title = quote(params.library_title, safe="")
                base = f"web/lists/getByTitle('{encoded_title}')/RootFolder"

            folders, files = await _list_folder(session, base)

            # Recurse into subfolders if requested
            if params.recursive:
                for folder in folders:
                    url = folder.get("serverRelativeUrl", "")
                    if url:
                        folder["children"] = await _list_recursive(
                            session, url, 1, params.max_depth,
                        )

            items = folders + files
            return {
                "folderCount": len(folders),
                "fileCount": len(files),
                "recursive": params.recursive,
                "maxDepth": params.max_depth if params.recursive else None,
                "items": items,
            }

    except Exception as exc:
        logger.exception("sharepoint_browser_list_items failed")
        return {"error": str(exc)}

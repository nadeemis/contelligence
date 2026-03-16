"""Tool to download a file from a SharePoint document library."""

from __future__ import annotations

import base64
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import sharepoint_download, sharepoint_request

logger = logging.getLogger(__name__)


class DownloadFileParams(BaseModel):
    """Parameters for the sharepoint_download_file tool."""

    server_relative_url: str = Field(
        ...,
        description=(
            "Server-relative URL of the file to download "
            "(e.g. '/sites/team/Shared Documents/Report.pdf'). "
            "Obtain this from sharepoint_list_items results."
        ),
    )
    site_url: str | None = Field(
        None,
        description=(
            "Full URL of the SharePoint site. "
            "Overrides the default SHAREPOINT_SITE_URL setting."
        ),
    )
    include_content: bool = Field(
        True,
        description=(
            "If true, include the file content as a base64-encoded string "
            "in the response. Set to false to retrieve metadata only."
        ),
    )


@define_tool(
    name="sharepoint_download_file",
    description=(
        "Download a file from a SharePoint document library by its "
        "server-relative URL. Returns file metadata (name, size, "
        "content type) and optionally the file content as a "
        "base64-encoded string."
    ),
    parameters_model=DownloadFileParams,
)
async def download_file(
    params: DownloadFileParams, context: dict,
) -> dict[str, Any]:
    """Download a file from SharePoint."""
    try:
        from urllib.parse import quote

        encoded_url = quote(params.server_relative_url, safe="/")

        # Fetch file metadata first
        metadata = await sharepoint_request(
            context,
            f"web/GetFileByServerRelativeUrl('{encoded_url}')",
            params={
                "$select": "Name,ServerRelativeUrl,Length,TimeCreated,TimeLastModified,MajorVersion,MinorVersion,CheckOutType,UIVersionLabel",
            },
            site_url=params.site_url,
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
            content = await sharepoint_download(
                context,
                f"web/GetFileByServerRelativeUrl('{encoded_url}')/$value",
                site_url=params.site_url,
            )
            result["contentBase64"] = base64.b64encode(content).decode("ascii")
            result["downloadedBytes"] = len(content)

        return result

    except Exception as exc:
        logger.exception("sharepoint_download_file failed")
        return {"error": str(exc)}

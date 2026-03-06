"""Tool for reading from Azure Blob Storage."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.connectors.blob_connector import BlobConnectorAdapter
from app.core.tool_registry import define_tool, ToolDefinition

logger = logging.getLogger(__name__)


class ReadBlobParams(BaseModel):
    """Parameters for the read_blob tool."""

    storage_account: str | None = Field(
        default=None,
        description=(
            "Azure Storage account name to connect to. "
            "When omitted the default account configured for the agent is used. "
            "Provide this to read from a different storage account "
            "(authentication uses DefaultAzureCredential)."
        ),
    )
    container: str = Field(
        description="Name of the Azure Blob Storage container."
    )
    action: Literal["list", "read", "metadata"] = Field(
        description=(
            "Action to perform: 'list' to enumerate blobs, "
            "'read' to download content as text, "
            "'metadata' to retrieve blob properties."
        )
    )
    path: str | None = Field(
        default=None,
        description="Blob path within the container. Required for 'read' and 'metadata' actions.",
    )
    prefix: str | None = Field(
        default=None,
        description="Filter prefix for the 'list' action (e.g. 'documents/').",
    )
    max_results: int = Field(
        default=100,
        description="Maximum number of blobs to return when listing.",
    )


@define_tool(
    name="read_blob",
    description=(
        "Read from Azure Blob Storage. Use action='list' to list blobs in a "
        "container (with optional prefix filter), action='read' to download "
        "file content as text, or action='metadata' to get blob properties. "
        "Use 'list' to discover what files exist before processing them."
    ),
    parameters_model=ReadBlobParams,
)
async def read_blob(params: ReadBlobParams, context: dict) -> dict:
    """Handle read_blob tool invocations."""
    # Use a per-request connector when the caller specifies a different
    # storage account; fall back to the default connector otherwise.
    default_connector: BlobConnectorAdapter = context["blob"]
    ad_hoc_connector: BlobConnectorAdapter | None = None

    if (
        params.storage_account
        and params.storage_account != default_connector._account_name
    ):
        ad_hoc_connector = BlobConnectorAdapter(
            account_name=params.storage_account,
            credential_type="default_azure_credential",
        )
        connector = ad_hoc_connector
        logger.info(
            "read_blob using ad-hoc connector for storage account '%s'",
            params.storage_account,
        )
    else:
        connector = default_connector

    try:
        return await _execute(params, connector)
    finally:
        if ad_hoc_connector is not None:
            await ad_hoc_connector.close()


async def _execute(params: ReadBlobParams, connector: BlobConnectorAdapter) -> dict:
    """Run the requested blob action against *connector*."""
    if params.action == "list":
        blobs = await connector.list_blobs(
            container=params.container,
            prefix=params.prefix,
            max_results=params.max_results,
        )
        logger.debug(
            "read_blob list container=%s prefix=%s returned %d blobs",
            params.container,
            params.prefix,
            len(blobs),
        )
        return {
            "count": len(blobs),
            "blobs": [
                {"name": b.name, "size": b.size, "type": b.content_type}
                for b in blobs
            ],
        }

    if params.action == "read":
        if not params.path:
            return {"error": "The 'path' parameter is required for action='read'."}
        raw = await connector.download_blob(
            container=params.container, path=params.path
        )
        content = raw.decode("utf-8", errors="replace")
        logger.debug(
            "read_blob read container=%s path=%s size=%d",
            params.container,
            params.path,
            len(raw),
        )
        return {
            "path": params.path,
            "content": content,
            "size": len(raw),
        }

    if params.action == "metadata":
        if not params.path:
            return {"error": "The 'path' parameter is required for action='metadata'."}
        props = await connector.get_blob_properties(
            container=params.container, path=params.path
        )
        logger.debug(
            "read_blob metadata container=%s path=%s",
            params.container,
            params.path,
        )
        return {
            "path": props.name,
            "size": props.size,
            "content_type": props.content_type,
            "metadata": props.metadata,
        }

    return {"error": f"Unknown action: {params.action}"}

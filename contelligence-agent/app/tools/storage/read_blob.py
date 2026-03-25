"""Tool for reading from Azure Blob Storage."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool, ToolDefinition
from app.connectors.blob_connector import BlobConnectorAdapter

logger = logging.getLogger(f"contelligence-agent.{__name__}")


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
    container: str | None = Field(
        default=None,
        description=(
            "Name of the Azure Blob Storage container. If not present, the tool will attempt to list containers "
            "(if action='list' and storage_account is specified) or return an error (for other actions)."
        )
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
        "Read from Azure Blob Storage. Use action='list' to list containers "
        "in a storage account or blobs in a container (with optional prefix filter), "
        "action='read' to download file content as text, or action='metadata' to get blob properties. "
        "Use 'list' to discover what files exist before processing them."
    ),
    parameters_model=ReadBlobParams,
)
async def read_blob(params: ReadBlobParams, context: dict) -> dict:
    """Handle read_blob tool invocations."""

    connector = BlobConnectorAdapter(
            account_name=params.storage_account,
            credential_type="default_azure_credential",
        )
    logger.info(
        f"read_blob using connector for storage account '{params.storage_account}'"
    )

    try:
        return await _execute(params, connector)
    finally:
        if connector is not None:
            await connector.close()


async def _execute(params: ReadBlobParams, connector: BlobConnectorAdapter) -> dict:
    """Run the requested blob action against *connector*."""
    if params.action == "list":
        # If no container is specified, list containers instead of blobs
        if not params.container:
            containers = await connector.list_containers()
            logger.debug(
                f"read_blob list containers returned {len(containers)} containers"
            )
            return {
                "count": len(containers),
                "containers": [
                    c["name"] if isinstance(c, dict) else c.name
                    for c in containers
                ],
            }
        
        blobs = await connector.list_blobs(
            container=params.container,
            prefix=params.prefix,
            max_results=params.max_results,
        )
        logger.debug(
            f"read_blob list container={params.container} prefix={params.prefix} returned {len(blobs)} blobs"
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
            f"read_blob read container={params.container} path={params.path} size={len(raw)}"
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
            f"read_blob metadata container={params.container} path={params.path}"
        )
        return {
            "path": props.name,
            "size": props.size,
            "content_type": props.content_type,
            "metadata": props.metadata,
        }

    return {"error": f"Unknown action: {params.action}"}

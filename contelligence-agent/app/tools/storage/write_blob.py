"""Tool for writing content to Azure Blob Storage."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool, ToolDefinition

logger = logging.getLogger(__name__)


class WriteBlobParams(BaseModel):
    """Parameters for the write_blob tool."""

    storage_account: str | None = Field(
        default=None,
        description=(
            "Azure Storage account name to connect to. "
            "When omitted the default account configured for the agent is used. "
            "Provide this to write to a different storage account "
            "(authentication uses DefaultAzureCredential)."
        ),
    )
    container: str = Field(
        description="Name of the Azure Blob Storage container."
    )
    path: str = Field(
        description="Destination blob path within the container."
    )
    content: str = Field(
        description=(
            "Text content to write. Use base64 encoding for binary data."
        )
    )
    content_type: str = Field(
        default="application/json",
        description="MIME type of the content being uploaded.",
    )


@define_tool(
    name="write_blob",
    description=(
        "Write content to Azure Blob Storage. The content should be a text "
        "string (use base64 encoding for binary data). Specify content_type "
        "for the MIME type of the content."
    ),
    parameters_model=WriteBlobParams,
)
async def write_blob(params: WriteBlobParams, context: dict) -> dict:
    """Handle write_blob tool invocations."""
    default_connector = context["blob"]
    ad_hoc_connector = None

    # Ad-hoc Azure connector only applies when running against Azure Blob
    # Storage (the connector exposes _account_name). In local mode the
    # LocalBlobConnectorAdapter has no _account_name.
    default_account = getattr(default_connector, "_account_name", None)
    if (
        params.storage_account
        and default_account
        and params.storage_account != default_account
    ):
        from app.connectors.blob_connector import BlobConnectorAdapter

        ad_hoc_connector = BlobConnectorAdapter(
            account_name=params.storage_account,
            credential_type="default_azure_credential",
        )
        connector = ad_hoc_connector
        logger.info(
            "write_blob using ad-hoc connector for storage account '%s'",
            params.storage_account,
        )
    else:
        connector = default_connector

    try:
        data = params.content.encode("utf-8")

        await connector.upload_blob(
            container=params.container,
            path=params.path,
            data=data,
            content_type=params.content_type,
        )
        logger.info(
            "write_blob container=%s path=%s size=%d content_type=%s",
            params.container,
            params.path,
            len(data),
            params.content_type,
        )
        return {
            "status": "written",
            "path": f"{params.container}/{params.path}",
        }
    finally:
        if ad_hoc_connector is not None:
            await ad_hoc_connector.close()

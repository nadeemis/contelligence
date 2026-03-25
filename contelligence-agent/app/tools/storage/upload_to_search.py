"""Tool for uploading documents to an Azure AI Search index."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool, ToolDefinition

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class UploadToSearchParams(BaseModel):
    """Parameters for the upload_to_search tool."""

    index: str = Field(
        description="Name of the Azure AI Search index to upload to."
    )
    documents: list[dict[str, Any]] = Field(
        description=(
            "List of documents to upload. Each document must be a dict "
            "with a unique 'id' field plus fields matching the target index schema."
        )
    )


@define_tool(
    name="upload_to_search",
    description=(
        "Upload documents to an Azure AI Search index. Each document must be "
        "a dict with a unique 'id' field plus fields matching the target "
        "index schema. Use this to make extracted and transformed data searchable."
    ),
    parameters_model=UploadToSearchParams,
)
async def upload_to_search(params: UploadToSearchParams, context: dict) -> dict:
    """Handle upload_to_search tool invocations."""
    connector = context["search"]

    # Validate that every document has an "id" field.
    errors: list[str] = []
    for idx, doc in enumerate(params.documents):
        if "id" not in doc:
            errors.append(f"Document at index {idx} is missing required 'id' field.")

    if errors:
        logger.warning(
            "upload_to_search validation failed: %s", "; ".join(errors)
        )
        return {
            "index": params.index,
            "uploaded": 0,
            "failed": len(params.documents),
            "errors": errors,
        }

    result = await connector.upload_documents(
        index=params.index, documents=params.documents
    )
    logger.info(
        "upload_to_search index=%s succeeded=%d failed=%d",
        params.index,
        result["succeeded"],
        result["failed"],
    )
    return {
        "index": params.index,
        "uploaded": result["succeeded"],
        "failed": result["failed"],
        "errors": [],
    }

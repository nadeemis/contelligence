"""Tool for upserting documents into Azure Cosmos DB."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool, ToolDefinition

logger = logging.getLogger(__name__)


class UpsertCosmosParams(BaseModel):
    """Parameters for the upsert_cosmos tool."""

    database: str = Field(
        description="Name of the Cosmos DB database."
    )
    container: str = Field(
        description="Name of the Cosmos DB container."
    )
    document: dict[str, Any] = Field(
        description=(
            "The document to upsert. Must include an 'id' field."
        )
    )
    partition_key: str = Field(
        description="Partition key value for the target container."
    )


@define_tool(
    name="upsert_cosmos",
    description=(
        "Insert or update a document in Azure Cosmos DB. The document must "
        "have an 'id' field. If a document with the same id exists, it will "
        "be replaced. Specify the partition_key value for the target container."
    ),
    parameters_model=UpsertCosmosParams,
)
async def upsert_cosmos(params: UpsertCosmosParams, context: dict) -> dict:
    """Handle upsert_cosmos tool invocations."""
    connector = context["cosmos"]

    if "id" not in params.document:
        logger.warning("upsert_cosmos called without 'id' in document")
        return {"error": "Document must contain an 'id' field."}

    result = await connector.upsert(
        container=params.container,
        document=params.document,
        database=params.database,
        partition_key=params.partition_key,
    )
    logger.info(
        "upsert_cosmos database=%s container=%s id=%s",
        params.database,
        params.container,
        params.document.get("id"),
    )
    return {
        "status": "upserted",
        "id": result.get("id"),
        "etag": result.get("_etag"),
    }

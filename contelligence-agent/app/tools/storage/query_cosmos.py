"""Tool for querying documents from Azure Cosmos DB."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool, ToolDefinition

logger = logging.getLogger(__name__)


class QueryCosmosParams(BaseModel):
    """Parameters for the query_cosmos tool."""

    database: str = Field(
        description="Name of the Cosmos DB database."
    )
    container: str = Field(
        description="Name of the Cosmos DB container."
    )
    query: str = Field(
        description=(
            "SQL query string. Example: "
            "'SELECT * FROM c WHERE c.status = @status'."
        )
    )
    parameters: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Query parameters as a list of {name, value} dicts. "
            "Example: [{'name': '@status', 'value': 'active'}]."
        ),
    )


@define_tool(
    name="query_cosmos",
    description=(
        "Query documents from Azure Cosmos DB using SQL syntax. "
        "Example: 'SELECT * FROM c WHERE c.status = @status'. "
        "Pass query parameters as a list of {name, value} dicts."
    ),
    parameters_model=QueryCosmosParams,
)
async def query_cosmos(params: QueryCosmosParams, context: dict) -> dict:
    """Handle query_cosmos tool invocations."""
    connector = context["cosmos"]

    documents: list[dict[str, Any]] = await connector.query(
        container=params.container,
        query_str=params.query,
        parameters=params.parameters,
        database=params.database,
    )
    logger.info(
        "query_cosmos database=%s container=%s returned %d documents",
        params.database,
        params.container,
        len(documents),
    )
    return {
        "count": len(documents),
        "documents": documents,
    }

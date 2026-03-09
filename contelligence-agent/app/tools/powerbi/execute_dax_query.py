"""Tool for executing DAX queries against a Power BI dataset.

Uses the Power BI REST API *Execute Queries* endpoint which leverages the
XMLA read path, making it cross-system compatible without requiring a
direct XMLA client library.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import powerbi_request

logger = logging.getLogger(__name__)


class ExecuteDaxQueryParams(BaseModel):
    """Parameters for the execute_dax_query tool."""

    dataset_id: str = Field(
        ...,
        description="The Power BI dataset (semantic model) ID to query.",
    )
    dax_query: str = Field(
        ...,
        description=(
            "A DAX query string to execute. Must begin with EVALUATE. "
            "Example: \"EVALUATE TOPN(10, 'Sales', 'Sales'[Amount], DESC)\""
        ),
    )
    workspace_id: str | None = Field(
        None,
        description=(
            "Power BI workspace (group) ID. Uses the configured default "
            "when omitted."
        ),
    )
    impersonated_user: str | None = Field(
        None,
        description=(
            "UPN of the user to impersonate for row-level security. "
            "Optional — omit to query without RLS."
        ),
    )


@define_tool(
    name="powerbi_execute_dax_query",
    description=(
        "Execute a DAX query against a Power BI dataset (semantic model) "
        "via the XMLA-backed REST API. Returns tabular results as rows. "
        "The query must start with EVALUATE. Use this to retrieve "
        "report data, aggregations, measures, or ad-hoc analyses."
    ),
    parameters_model=ExecuteDaxQueryParams,
)
async def execute_dax_query(
    params: ExecuteDaxQueryParams, context: dict,
) -> dict[str, Any]:
    """Execute a DAX query and return structured results."""
    try:
        body: dict[str, Any] = {
            "queries": [{"query": params.dax_query}],
            "serializerSettings": {"includeNulls": True},
        }
        if params.impersonated_user:
            body["impersonatedUserName"] = params.impersonated_user

        data = await powerbi_request(
            context,
            f"datasets/{params.dataset_id}/executeQueries",
            method="POST",
            json_body=body,
            workspace_id=params.workspace_id,
        )

        # Parse the response into a clean structure
        results: list[dict[str, Any]] = []
        for table in data.get("results", []):
            rows = table.get("tables", [{}])[0].get("rows", [])
            results.extend(rows)

        return {
            "dataset_id": params.dataset_id,
            "row_count": len(results),
            "rows": results,
        }

    except Exception as exc:
        logger.exception("DAX query execution failed for dataset %s", params.dataset_id)
        return {
            "error": str(exc),
            "dataset_id": params.dataset_id,
        }

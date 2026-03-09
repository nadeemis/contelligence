"""Tool for retrieving table and column metadata from a Power BI dataset."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import powerbi_request

logger = logging.getLogger(__name__)

# DAX query that returns all tables and columns via INFO functions.
_SCHEMA_DAX = (
    "EVALUATE "
    "SELECTCOLUMNS("
    "    FILTER("
    "        INFO.COLUMNS(),"
    "        NOT(LEFT([ExplicitName], 1) = \"_\")"
    "    ),"
    '    "Table", [TableName],'
    '    "Column", [ExplicitName],'
    '    "DataType", [DataType],'
    '    "IsHidden", [IsHidden]'
    ")"
)


class GetDatasetTablesParams(BaseModel):
    """Parameters for the get_dataset_tables tool."""

    dataset_id: str = Field(
        ...,
        description="The Power BI dataset (semantic model) ID.",
    )
    workspace_id: str | None = Field(
        None,
        description=(
            "Power BI workspace (group) ID. Uses the configured default "
            "when omitted."
        ),
    )


@define_tool(
    name="powerbi_get_dataset_tables",
    description=(
        "Retrieve the schema (tables and columns) of a Power BI dataset. "
        "Returns table names, column names, data types, and visibility. "
        "Use this to understand a dataset's structure before writing "
        "DAX queries."
    ),
    parameters_model=GetDatasetTablesParams,
)
async def get_dataset_tables(
    params: GetDatasetTablesParams, context: dict,
) -> dict[str, Any]:
    """Retrieve table/column metadata for a Power BI dataset."""
    try:
        body = {
            "queries": [{"query": _SCHEMA_DAX}],
            "serializerSettings": {"includeNulls": True},
        }

        data = await powerbi_request(
            context,
            f"datasets/{params.dataset_id}/executeQueries",
            method="POST",
            json_body=body,
            workspace_id=params.workspace_id,
        )

        # Parse into a grouped-by-table structure
        rows = data.get("results", [{}])[0].get("tables", [{}])[0].get("rows", [])

        tables: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            table_name = row.get("Table", row.get("[Table]", ""))
            column_info = {
                "name": row.get("Column", row.get("[Column]", "")),
                "data_type": row.get("DataType", row.get("[DataType]", "")),
                "is_hidden": row.get("IsHidden", row.get("[IsHidden]", False)),
            }
            tables.setdefault(table_name, []).append(column_info)

        return {
            "dataset_id": params.dataset_id,
            "table_count": len(tables),
            "tables": {
                name: {"column_count": len(cols), "columns": cols}
                for name, cols in tables.items()
            },
        }

    except Exception as exc:
        logger.exception(
            "Failed to retrieve tables for dataset %s", params.dataset_id,
        )
        return {
            "error": str(exc),
            "dataset_id": params.dataset_id,
        }

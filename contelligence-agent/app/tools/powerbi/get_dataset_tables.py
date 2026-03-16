"""Tool for retrieving table and column metadata from a Power BI dataset.

Uses a multi-strategy approach to discover schema:
1. REST API ``GET datasets/{id}/tables`` — works for push datasets
2. Admin Scanning API — works for all dataset types (requires admin perms)
3. DAX ``INFO.COLUMNS()`` — requires XMLA endpoint access (often blocked)

Each strategy is tried in order; the first success wins.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import powerbi_request

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# DAX fallback — requires XMLA endpoint access which many tenants block.
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


# ------------------------------------------------------------------
# Strategy 1: REST API GET /datasets/{id}/tables  (push datasets)
# ------------------------------------------------------------------

async def _try_rest_tables(
    params: GetDatasetTablesParams, context: dict,
) -> dict[str, Any] | None:
    """Attempt to fetch tables via the standard REST endpoint."""
    try:
        data = await powerbi_request(
            context,
            f"datasets/{params.dataset_id}/tables",
            workspace_id=params.workspace_id,
        )
        raw_tables = data.get("value", [])
        if not raw_tables:
            return None

        tables: dict[str, Any] = {}
        for tbl in raw_tables:
            table_name = tbl.get("name", "")
            columns = [
                {
                    "name": col.get("name", ""),
                    "data_type": col.get("dataType", ""),
                    "is_hidden": col.get("isHidden", False),
                }
                for col in tbl.get("columns", [])
            ]
            tables[table_name] = {
                "column_count": len(columns),
                "columns": columns,
            }

        logger.info("Retrieved tables via REST API for dataset %s", params.dataset_id)
        return {
            "dataset_id": params.dataset_id,
            "table_count": len(tables),
            "tables": tables,
            "source": "rest_api",
        }
    except httpx.HTTPStatusError as exc:
        logger.debug(
            "REST tables endpoint returned %s for dataset %s — trying next strategy",
            exc.response.status_code,
            params.dataset_id,
        )
        return None
    except Exception:
        logger.debug(
            "REST tables endpoint failed for dataset %s — trying next strategy",
            params.dataset_id,
            exc_info=True,
        )
        return None


# ------------------------------------------------------------------
# Strategy 2: Admin Scanning API  (all dataset types, admin required)
# ------------------------------------------------------------------

_SCAN_POLL_INTERVAL = 2.0  # seconds
_SCAN_MAX_WAIT = 30.0  # seconds

async def _try_admin_scan(
    params: GetDatasetTablesParams, context: dict,
) -> dict[str, Any] | None:
    """Attempt to discover tables via the Admin workspace-info scan."""
    try:
        ws_id = params.workspace_id
        if not ws_id:
            settings = context.get("settings")
            ws_id = getattr(settings, "POWERBI_WORKSPACE_ID", "") or ""
        if not ws_id:
            logger.debug("No workspace ID available for admin scan")
            return None

        # Step 1 — trigger the scan
        scan_resp = await powerbi_request(
            context,
            "admin/workspaces/getInfo",
            method="POST",
            json_body={"workspaces": [ws_id]},
            params={"datasetSchema": "true", "datasetExpressions": "true"},
            # admin endpoint is not workspace-scoped
            workspace_id=None,
        )
        scan_id = scan_resp.get("id")
        if not scan_id:
            return None

        # Step 2 — poll until the scan completes
        elapsed = 0.0
        scan_status: str = scan_resp.get("status", "")
        while scan_status not in ("Succeeded", "Failed") and elapsed < _SCAN_MAX_WAIT:
            await asyncio.sleep(_SCAN_POLL_INTERVAL)
            elapsed += _SCAN_POLL_INTERVAL
            status_resp = await powerbi_request(
                context,
                f"admin/workspaces/scanStatus/{scan_id}",
                workspace_id=None,
            )
            scan_status = status_resp.get("status", "")

        if scan_status != "Succeeded":
            logger.debug("Admin scan %s did not succeed (status=%s)", scan_id, scan_status)
            return None

        # Step 3 — retrieve the scan result
        result = await powerbi_request(
            context,
            f"admin/workspaces/scanResult/{scan_id}",
            workspace_id=None,
        )

        # Find the target dataset within the scan result
        tables: dict[str, Any] = {}
        for workspace in result.get("workspaces", []):
            for ds in workspace.get("datasets", []):
                if ds.get("id") != params.dataset_id:
                    continue
                for tbl in ds.get("tables", []):
                    table_name = tbl.get("name", "")
                    columns = [
                        {
                            "name": col.get("name", ""),
                            "data_type": col.get("dataType", ""),
                            "is_hidden": col.get("isHidden", False),
                        }
                        for col in tbl.get("columns", [])
                    ]
                    tables[table_name] = {
                        "column_count": len(columns),
                        "columns": columns,
                    }

        if not tables:
            return None

        logger.info("Retrieved tables via admin scan for dataset %s", params.dataset_id)
        return {
            "dataset_id": params.dataset_id,
            "table_count": len(tables),
            "tables": tables,
            "source": "admin_scan_api",
        }
    except httpx.HTTPStatusError as exc:
        logger.debug(
            "Admin scan returned %s for dataset %s — trying next strategy",
            exc.response.status_code,
            params.dataset_id,
        )
        return None
    except Exception:
        logger.debug(
            "Admin scan failed for dataset %s — trying next strategy",
            params.dataset_id,
            exc_info=True,
        )
        return None


# ------------------------------------------------------------------
# Strategy 3: DAX INFO.COLUMNS()  (requires XMLA endpoint access)
# ------------------------------------------------------------------

async def _try_dax_info(
    params: GetDatasetTablesParams, context: dict,
) -> dict[str, Any] | None:
    """Attempt to fetch schema via DAX INFO.COLUMNS() (needs XMLA)."""
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

        rows = data.get("results", [{}])[0].get("tables", [{}])[0].get("rows", [])
        if not rows:
            return None

        tables: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            table_name = row.get("Table", row.get("[Table]", ""))
            column_info = {
                "name": row.get("Column", row.get("[Column]", "")),
                "data_type": row.get("DataType", row.get("[DataType]", "")),
                "is_hidden": row.get("IsHidden", row.get("[IsHidden]", False)),
            }
            tables.setdefault(table_name, []).append(column_info)

        logger.info("Retrieved tables via DAX INFO.COLUMNS() for dataset %s", params.dataset_id)
        return {
            "dataset_id": params.dataset_id,
            "table_count": len(tables),
            "tables": {
                name: {"column_count": len(cols), "columns": cols}
                for name, cols in tables.items()
            },
            "source": "dax_info_columns",
        }
    except Exception:
        logger.debug(
            "DAX INFO.COLUMNS() failed for dataset %s",
            params.dataset_id,
            exc_info=True,
        )
        return None


# ------------------------------------------------------------------
# Orchestrator
# ------------------------------------------------------------------

@define_tool(
    name="powerbi_get_dataset_tables",
    description=(
        "Retrieve the schema (tables and columns) of a Power BI dataset. "
        "Returns table names, column names, data types, and visibility. "
        "Tries multiple discovery strategies automatically: REST API tables "
        "endpoint, Admin scanning API, and DAX INFO.COLUMNS(). "
        "Use this to understand a dataset's structure before writing "
        "DAX queries."
    ),
    parameters_model=GetDatasetTablesParams,
)
async def get_dataset_tables(
    params: GetDatasetTablesParams, context: dict,
) -> dict[str, Any]:
    """Retrieve table/column metadata using a multi-strategy fallback chain."""
    strategies = [
        ("REST API tables", _try_rest_tables),
        ("Admin scanning API", _try_admin_scan),
        ("DAX INFO.COLUMNS()", _try_dax_info),
    ]
    errors: list[str] = []

    for name, strategy in strategies:
        logger.debug("Trying strategy '%s' for dataset %s", name, params.dataset_id)
        result = await strategy(params, context)
        if result is not None:
            return result
        errors.append(name)

    logger.warning(
        "All table-discovery strategies failed for dataset %s: %s",
        params.dataset_id,
        ", ".join(errors),
    )
    return {
        "dataset_id": params.dataset_id,
        "error": (
            "Could not retrieve table metadata. All strategies failed: "
            f"{', '.join(errors)}. "
            "This usually means the dataset is not a push dataset (REST API) "
            "and admin permissions are not available (Admin Scan). "
            "If you know specific table names, use powerbi_execute_dax_query "
            "with EVALUATE TOPN(1, 'TableName') to probe individual tables."
        ),
        "strategies_attempted": errors,
    }

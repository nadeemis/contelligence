"""Tool for listing Power BI datasets in a workspace."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import powerbi_request

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class ListDatasetsParams(BaseModel):
    """Parameters for the list_datasets tool."""

    workspace_id: str | None = Field(
        None,
        description=(
            "Power BI workspace (group) ID. Uses the configured default "
            "when omitted."
        ),
    )


@define_tool(
    name="powerbi_list_datasets",
    description=(
        "List all datasets (semantic models) in a Power BI workspace. "
        "Returns dataset IDs, names, and configuration details. "
        "Use this to discover available datasets before running DAX queries."
    ),
    parameters_model=ListDatasetsParams,
)
async def list_datasets(
    params: ListDatasetsParams, context: dict,
) -> dict[str, Any]:
    """List Power BI datasets in a workspace."""
    try:
        data = await powerbi_request(
            context,
            "datasets",
            workspace_id=params.workspace_id,
        )

        datasets = [
            {
                "id": ds.get("id"),
                "name": ds.get("name"),
                "configured_by": ds.get("configuredBy"),
                "is_refreshable": ds.get("isRefreshable"),
                "is_effective_identity_required": ds.get(
                    "isEffectiveIdentityRequired",
                ),
                "target_storage_mode": ds.get("targetStorageMode"),
                "created_date": ds.get("createdDate"),
            }
            for ds in data.get("value", [])
        ]

        return {
            "workspace_id": params.workspace_id or "(default)",
            "count": len(datasets),
            "datasets": datasets,
        }

    except Exception as exc:
        logger.exception("Failed to list datasets")
        raise exc

"""Tool for retrieving multiple Azure DevOps work items by IDs."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import devops_request

logger = logging.getLogger(__name__)

_MAX_IDS = 200  # Azure DevOps API limit


class ListWorkItemsParams(BaseModel):
    """Parameters for the list_work_items tool."""

    ids: list[int] = Field(
        ...,
        description=(
            "List of work item IDs to retrieve (maximum 200). "
            "Example: [101, 102, 103]."
        ),
        max_length=_MAX_IDS,
    )
    project: str | None = Field(
        None,
        description=(
            "Azure DevOps project name or ID. "
            "Uses the configured default project when omitted."
        ),
    )
    fields: str | None = Field(
        None,
        description=(
            "Comma-separated list of field reference names to return, "
            "e.g. 'System.Id,System.Title,System.State'. "
            "Omit to return all fields."
        ),
    )
    expand: str | None = Field(
        None,
        description=(
            "Expand parameters for work item attributes. "
            "Options: 'None', 'Relations', 'Fields', 'Links', 'All'."
        ),
    )


@define_tool(
    name="devops_list_work_items",
    description=(
        "Retrieve multiple Azure DevOps work items by their IDs in a single batch "
        "(maximum 200). Returns each work item's fields. Use this after a WIQL query "
        "to hydrate the returned work item IDs with full field data, or when you "
        "already know the specific IDs you need."
    ),
    parameters_model=ListWorkItemsParams,
)
async def list_work_items(
    params: ListWorkItemsParams, context: dict,
) -> dict[str, Any]:
    """Fetch multiple work items from Azure DevOps in one call."""
    try:
        if not params.ids:
            return {"error": "ids list must not be empty"}

        query_params: dict[str, Any] = {
            "ids": ",".join(str(i) for i in params.ids),
        }
        if params.fields:
            query_params["fields"] = params.fields
        if params.expand:
            query_params["$expand"] = params.expand

        data = await devops_request(
            context,
            "_apis/wit/workitems",
            params=query_params,
            project=params.project,
        )

        items = data.get("value", [])
        return {
            "count": data.get("count", len(items)),
            "work_items": [
                {
                    "id": wi.get("id"),
                    "rev": wi.get("rev"),
                    "url": wi.get("url"),
                    "fields": wi.get("fields", {}),
                    "relations": wi.get("relations"),
                }
                for wi in items
            ],
        }

    except Exception as exc:
        logger.exception("devops_list_work_items failed for ids=%s", params.ids)
        return {"error": str(exc), "ids": params.ids}

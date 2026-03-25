"""Tool for retrieving a single Azure DevOps work item by ID."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import devops_request

logger = logging.getLogger(__name__)


class GetWorkItemParams(BaseModel):
    """Parameters for the get_work_item tool."""
    
    organization: str | None = Field(
        None,
        description=(
            "Azure DevOps organization name or ID. "
            "Uses the configured default organization when omitted."
        ),
    )
    project: str | None = Field(
        None,
        description=(
            "Azure DevOps project name or ID. "
            "Uses the configured default project when omitted."
        ),
    )
    work_item_id: int = Field(..., description="The ID of the work item to retrieve.")
    fields: str | None = Field(
        None,
        description=(
            "Comma-separated list of field reference names to return, "
            "e.g. 'System.Title,System.State,System.AssignedTo'. "
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
    name="devops_get_work_item",
    description=(
        "Retrieve a single Azure DevOps work item by ID. Returns the work item's "
        "fields (title, state, assigned to, description, etc.), and optionally "
        "its relations and links. Use this when you need details about a specific "
        "work item such as a bug, task, user story, or feature."
    ),
    parameters_model=GetWorkItemParams,
)
async def get_work_item(
    params: GetWorkItemParams, context: dict,
) -> dict[str, Any]:
    """Fetch a single work item from Azure DevOps."""
    try:
        settings = context.get("settings")
        org_name = params.organization or getattr(settings, "AZURE_DEVOPS_DEFAULT_ORG", "")
        if not org_name:
            return {"error": "No organization specified and AZURE_DEVOPS_DEFAULT_ORG is not set"}
        
        project_name = params.project or getattr(settings, "AZURE_DEVOPS_DEFAULT_PROJECT", "")
        if not project_name:
            return {"error": "No project specified and AZURE_DEVOPS_DEFAULT_PROJECT is not set"}
        
        query_params: dict[str, Any] = {}
        if params.fields:
            query_params["fields"] = params.fields
        if params.expand:
            query_params["$expand"] = params.expand

        data = await devops_request(
            context,
            f"_apis/wit/workitems/{params.work_item_id}",
            params=query_params,
            organization=org_name,
            project=project_name,
        )

        fields = data.get("fields", {})
        return {
            "id": data.get("id"),
            "rev": data.get("rev"),
            "url": data.get("url"),
            "fields": fields,
            "relations": data.get("relations"),
        }

    except Exception as exc:
        logger.exception(
            "devops_get_work_item failed for id=%s", params.work_item_id,
        )
        return {"error": str(exc), "work_item_id": params.work_item_id}

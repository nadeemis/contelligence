"""Tool for querying Azure DevOps work items using WIQL."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import devops_request

logger = logging.getLogger(__name__)


class QueryWorkItemsParams(BaseModel):
    """Parameters for the query_work_items tool."""
    
    query: str = Field(
        ...,
        description=(
            "A WIQL (Work Item Query Language) query string. Example: "
            "\"Select [System.Id], [System.Title], [System.State] "
            "From WorkItems Where [System.WorkItemType] = 'Task' "
            "AND [System.State] <> 'Closed' "
            "order by [System.CreatedDate] desc\""
        ),
    )
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
    team: str | None = Field(
        None,
        description="Team name or ID to scope the query to. Optional.",
    )
    top: int | None = Field(
        None,
        description="Maximum number of results to return. Omit for API default.",
        gt=0,
    )


@define_tool(
    name="devops_query_work_items",
    description=(
        "Query Azure DevOps work items using WIQL (Work Item Query Language). "
        "Returns matching work item IDs and columns. For flat queries this returns "
        "work item references; for tree/one-hop queries it returns link references. "
        "Use devops_list_work_items afterward to fetch full field data for the "
        "returned IDs."
    ),
    parameters_model=QueryWorkItemsParams,
)
async def query_work_items(
    params: QueryWorkItemsParams, context: dict,
) -> dict[str, Any]:
    """Execute a WIQL query against Azure DevOps."""
    try:
        settings = context.get("settings")
        org_name = params.organization or getattr(settings, "AZURE_DEVOPS_DEFAULT_ORG", "")
        if not org_name:
            return {"error": "No organization specified and AZURE_DEVOPS_DEFAULT_ORG is not set"}
        
        project_name = params.project or getattr(settings, "AZURE_DEVOPS_DEFAULT_PROJECT", "")
        if not project_name:
            return {"error": "No project specified and AZURE_DEVOPS_DEFAULT_PROJECT is not set"}
        
        query_params: dict[str, Any] = {}
        if params.top is not None:
            query_params["$top"] = params.top

        # Build the path, optionally including team segment
        path = "_apis/wit/wiql"
        project = project_name
        if params.team:
            # For team-scoped WIQL the URL is /{project}/{team}/_apis/wit/wiql
            # We inject the team by extending the project segment.
            effective_project = project
            if effective_project:
                project = f"{effective_project}/{params.team}"
            else:
                project = params.team

        data = await devops_request(
            context,
            path,
            method="POST",
            json_body={"query": params.query},
            params=query_params,
            organization=org_name,
            project=project,
        )

        # Flat queries return "workItems"; tree/one-hop return "workItemRelations"
        work_items = data.get("workItems", [])
        relations = data.get("workItemRelations", [])

        result: dict[str, Any] = {
            "query_type": data.get("queryType"),
            "as_of": data.get("asOf"),
            "columns": [
                {"name": c.get("name"), "reference_name": c.get("referenceName")}
                for c in data.get("columns", [])
            ],
        }

        if work_items:
            result["work_items"] = [
                {"id": wi.get("id"), "url": wi.get("url")} for wi in work_items
            ]
            result["count"] = len(work_items)
        elif relations:
            result["work_item_relations"] = [
                {
                    "rel": r.get("rel"),
                    "source": r.get("source"),
                    "target": r.get("target"),
                }
                for r in relations
            ]
            result["count"] = len(relations)
        else:
            result["work_items"] = []
            result["count"] = 0

        return result

    except Exception as exc:
        logger.exception("devops_query_work_items failed", exc_info=exc)
        return {"error": str(exc)}

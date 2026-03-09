"""Tool for retrieving Azure DevOps project information."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import devops_request

logger = logging.getLogger(__name__)


class GetProjectParams(BaseModel):
    """Parameters for the get_project tool."""

    project: str | None = Field(
        None,
        description=(
            "Project name or ID to retrieve. "
            "Uses the configured default project when omitted. "
            "Pass '*' to list all projects in the organization."
        ),
    )


@define_tool(
    name="devops_get_project",
    description=(
        "Retrieve Azure DevOps project information. Returns the project's name, "
        "description, state, visibility, and default team. Pass '*' as the project "
        "parameter to list all projects in the organization."
    ),
    parameters_model=GetProjectParams,
)
async def get_project(
    params: GetProjectParams, context: dict,
) -> dict[str, Any]:
    """Fetch project details from Azure DevOps."""
    try:
        if params.project == "*":
            # List all projects (org-level, no project segment)
            data = await devops_request(
                context,
                "_apis/projects",
                project="",  # force no project segment
            )
            projects = data.get("value", [])
            return {
                "count": data.get("count", len(projects)),
                "projects": [
                    {
                        "id": p.get("id"),
                        "name": p.get("name"),
                        "description": p.get("description"),
                        "state": p.get("state"),
                        "visibility": p.get("visibility"),
                        "url": p.get("url"),
                    }
                    for p in projects
                ],
            }

        # Single project
        settings = context.get("settings")
        project_name = params.project or getattr(
            settings, "AZURE_DEVOPS_DEFAULT_PROJECT", "",
        )
        if not project_name:
            return {"error": "No project specified and AZURE_DEVOPS_DEFAULT_PROJECT is not set"}

        data = await devops_request(
            context,
            f"_apis/projects/{project_name}",
            project="",  # project already in the path
        )

        default_team = data.get("defaultTeam", {})
        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "description": data.get("description"),
            "state": data.get("state"),
            "visibility": data.get("visibility"),
            "default_team": {
                "id": default_team.get("id"),
                "name": default_team.get("name"),
            } if default_team else None,
            "url": data.get("url"),
        }

    except Exception as exc:
        logger.exception("devops_get_project failed")
        return {"error": str(exc)}

"""Tool for retrieving Azure DevOps iteration paths (sprints)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import devops_request

logger = logging.getLogger(__name__)


class GetIterationsParams(BaseModel):
    """Parameters for the get_iterations tool."""

    project: str | None = Field(
        None,
        description=(
            "Azure DevOps project name or ID. "
            "Uses the configured default project when omitted."
        ),
    )
    team: str | None = Field(
        None,
        description=(
            "Team name or ID. When provided, returns only the iterations "
            "selected for that team."
        ),
    )
    timeframe: str | None = Field(
        None,
        description=(
            "Filter iterations by timeframe. "
            "Options: 'current', 'past', 'future'. Omit for all."
        ),
    )


@define_tool(
    name="devops_get_iterations",
    description=(
        "List iteration paths (sprints) for an Azure DevOps project or team. "
        "Returns iteration names, paths, start/end dates, and timeframe. "
        "Use this to discover sprint boundaries, check the current iteration, "
        "or list past/future sprints."
    ),
    parameters_model=GetIterationsParams,
)
async def get_iterations(
    params: GetIterationsParams, context: dict,
) -> dict[str, Any]:
    """Fetch iteration paths from Azure DevOps."""
    try:
        query_params: dict[str, Any] = {}
        if params.timeframe:
            query_params["$timeframe"] = params.timeframe

        # Team iterations endpoint:
        #   GET {org}/{project}/{team}/_apis/work/teamsettings/iterations
        # Project classification nodes (all iterations):
        #   GET {org}/{project}/_apis/wit/classificationnodes/iterations?$depth=10
        if params.team:
            settings = context.get("settings")
            effective_project = params.project or getattr(
                settings, "AZURE_DEVOPS_DEFAULT_PROJECT", "",
            )
            project_with_team = (
                f"{effective_project}/{params.team}" if effective_project else params.team
            )
            data = await devops_request(
                context,
                "_apis/work/teamsettings/iterations",
                params=query_params,
                project=project_with_team,
            )
        else:
            query_params["$depth"] = 10
            data = await devops_request(
                context,
                "_apis/wit/classificationnodes/iterations",
                params=query_params,
                project=params.project,
            )

        # Team iterations API returns a "value" array; classification node API
        # returns a tree with "children".
        iterations: list[dict[str, Any]] = []

        if "value" in data:
            # Team-scoped response
            for it in data["value"]:
                attrs = it.get("attributes", {})
                iterations.append({
                    "id": it.get("id"),
                    "name": it.get("name"),
                    "path": it.get("path"),
                    "start_date": attrs.get("startDate"),
                    "finish_date": attrs.get("finishDate"),
                    "timeframe": attrs.get("timeFrame"),
                    "url": it.get("url"),
                })
        else:
            # Classification-node tree — flatten children
            _flatten_iteration_tree(data, iterations)

        return {"count": len(iterations), "iterations": iterations}

    except Exception as exc:
        logger.exception("devops_get_iterations failed")
        return {"error": str(exc)}


def _flatten_iteration_tree(
    node: dict[str, Any],
    result: list[dict[str, Any]],
) -> None:
    """Recursively flatten a classification-node tree into a list."""
    attrs = node.get("attributes", {})
    result.append({
        "id": node.get("id"),
        "name": node.get("name"),
        "path": node.get("path"),
        "start_date": attrs.get("startDate"),
        "finish_date": attrs.get("finishDate"),
        "url": node.get("url"),
    })
    for child in node.get("children", []):
        _flatten_iteration_tree(child, result)

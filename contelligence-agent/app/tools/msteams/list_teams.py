"""Tool to list the Microsoft Teams that the signed-in user has joined."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import graph_request

logger = logging.getLogger(__name__)


class ListTeamsParams(BaseModel):
    """Parameters for the teams_list_teams tool."""

    top: int | None = Field(
        None,
        description="Maximum number of teams to return.",
        gt=0,
    )


@define_tool(
    name="teams_list_teams",
    description=(
        "List the Microsoft Teams that the signed-in user has joined. "
        "Returns team IDs, display names, and descriptions. "
        "Use the team ID with teams_list_channels to explore channels."
    ),
    parameters_model=ListTeamsParams,
)
async def list_teams(
    params: ListTeamsParams, context: dict,
) -> dict[str, Any]:
    """Retrieve the user's joined Teams."""
    try:
        query: dict[str, Any] = {}
        if params.top:
            query["$top"] = params.top

        data = await graph_request(context, "me/joinedTeams", params=query)

        teams = [
            {
                "id": t.get("id"),
                "displayName": t.get("displayName"),
                "description": t.get("description"),
            }
            for t in data.get("value", [])
        ]
        return {"count": len(teams), "teams": teams}

    except Exception as exc:
        logger.exception("teams_list_teams failed")
        return {"error": str(exc)}

"""Tool to list members of a Microsoft Teams team."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import graph_request

logger = logging.getLogger(__name__)


class ListTeamMembersParams(BaseModel):
    """Parameters for the teams_list_team_members tool."""

    team_id: str = Field(
        ...,
        description="The ID of the team whose members to list.",
    )


@define_tool(
    name="teams_list_team_members",
    description=(
        "List all members of a Microsoft Teams team. "
        "Returns display names, email addresses, and roles "
        "(owner, member, guest)."
    ),
    parameters_model=ListTeamMembersParams,
)
async def list_team_members(
    params: ListTeamMembersParams, context: dict,
) -> dict[str, Any]:
    """Retrieve members for a given team."""
    try:
        data = await graph_request(
            context, f"teams/{params.team_id}/members",
        )

        members = [
            {
                "id": m.get("id"),
                "displayName": m.get("displayName"),
                "email": m.get("email"),
                "roles": m.get("roles", []),
            }
            for m in data.get("value", [])
        ]
        return {"count": len(members), "members": members}

    except Exception as exc:
        logger.exception("teams_list_team_members failed")
        return {"error": str(exc)}

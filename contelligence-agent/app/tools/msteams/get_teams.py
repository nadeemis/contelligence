"""Tool to list the current user's joined Microsoft Teams."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool
from ._graph_session import get_session

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class GetTeamsParams(BaseModel):
    """Parameters for the msteams_get_teams tool."""

    headless: bool = Field(
        True,
        description="Launch the browser in headless mode.",
    )


@define_tool(
    name="msteams_get_teams",
    description=(
        "List all Microsoft Teams the current user has joined via the "
        "MS Graph API (/me/joinedTeams). Returns team IDs, display names, "
        "and descriptions. Use msteams_get_channels to list channels "
        "within a specific team."
    ),
    parameters_model=GetTeamsParams,
)
async def get_teams(params: GetTeamsParams, context: dict) -> dict[str, Any]:
    """Retrieve the user's joined Teams."""
    try:
        session = await get_session(headless=params.headless)

        data = await session.graph_get("/me/joinedTeams")

        teams = [
            {
                "id": t.get("id"),
                "displayName": t.get("displayName"),
                "description": t.get("description"),
                "isArchived": t.get("isArchived"),
                "visibility": t.get("visibility"),
                "webUrl": t.get("webUrl"),
            }
            for t in data.get("value", [])
        ]

        return {"count": len(teams), "teams": teams}

    except Exception as exc:
        logger.exception("msteams_get_teams failed")
        return {"error": str(exc)}

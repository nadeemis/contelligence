"""Tool to list channels in a Microsoft Teams team."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool
from ._graph_session import get_session

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class GetChannelsParams(BaseModel):
    """Parameters for the msteams_get_channels tool."""

    team_id: str = Field(
        ...,
        description=(
            "The ID of the team to list channels for. "
            "Obtain this from msteams_get_teams."
        ),
    )
    headless: bool = Field(
        True,
        description="Launch the browser in headless mode.",
    )


@define_tool(
    name="msteams_get_channels",
    description=(
        "List all channels in a Microsoft Teams team via the MS Graph API "
        "(/teams/{team_id}/channels). Returns channel IDs, display names, "
        "and membership types. Requires a team_id from msteams_get_teams. "
        "Use msteams_get_channel_messages to read messages from a channel."
    ),
    parameters_model=GetChannelsParams,
)
async def get_channels(
    params: GetChannelsParams, context: dict,
) -> dict[str, Any]:
    """Retrieve channels for a Teams team."""
    try:
        session = await get_session(headless=params.headless)

        data = await session.graph_get(f"/teams/{params.team_id}/channels")

        channels = [
            {
                "id": ch.get("id"),
                "displayName": ch.get("displayName"),
                "description": ch.get("description"),
                "membershipType": ch.get("membershipType"),
                "webUrl": ch.get("webUrl"),
                "isArchived": ch.get("isArchived"),
            }
            for ch in data.get("value", [])
        ]

        return {
            "teamId": params.team_id,
            "count": len(channels),
            "channels": channels,
        }

    except Exception as exc:
        logger.exception("msteams_get_channels failed")
        return {"error": str(exc)}

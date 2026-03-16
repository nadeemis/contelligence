"""Tool to list channels in a Microsoft Teams team."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import graph_request

logger = logging.getLogger(__name__)


class ListChannelsParams(BaseModel):
    """Parameters for the teams_list_channels tool."""

    team_id: str = Field(
        ...,
        description="The ID of the team whose channels to list.",
    )


@define_tool(
    name="teams_list_channels",
    description=(
        "List all channels in a Microsoft Teams team. "
        "Returns channel IDs, display names, descriptions, and membership type "
        "(standard, private, shared). Use the channel ID with "
        "teams_get_channel_messages to fetch messages."
    ),
    parameters_model=ListChannelsParams,
)
async def list_channels(
    params: ListChannelsParams, context: dict,
) -> dict[str, Any]:
    """Retrieve channels for a given team."""
    try:
        data = await graph_request(
            context, f"teams/{params.team_id}/channels",
        )

        channels = [
            {
                "id": ch.get("id"),
                "displayName": ch.get("displayName"),
                "description": ch.get("description"),
                "membershipType": ch.get("membershipType"),
            }
            for ch in data.get("value", [])
        ]
        return {"count": len(channels), "channels": channels}

    except Exception as exc:
        logger.exception("teams_list_channels failed")
        return {"error": str(exc)}

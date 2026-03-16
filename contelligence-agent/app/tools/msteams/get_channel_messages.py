"""Tool to retrieve messages from a Microsoft Teams channel."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import graph_request

logger = logging.getLogger(__name__)


class GetChannelMessagesParams(BaseModel):
    """Parameters for the teams_get_channel_messages tool."""

    team_id: str = Field(
        ...,
        description="The ID of the team containing the channel.",
    )
    channel_id: str = Field(
        ...,
        description="The ID of the channel to fetch messages from.",
    )
    top: int | None = Field(
        None,
        description="Maximum number of messages to return (default 50, max 50).",
        gt=0,
        le=50,
    )


@define_tool(
    name="teams_get_channel_messages",
    description=(
        "Retrieve messages from a Microsoft Teams channel. "
        "Requires team ID and channel ID. Returns message bodies, senders, "
        "timestamps, and reply counts."
    ),
    parameters_model=GetChannelMessagesParams,
)
async def get_channel_messages(
    params: GetChannelMessagesParams, context: dict,
) -> dict[str, Any]:
    """Fetch messages for a specific Teams channel."""
    try:
        query: dict[str, Any] = {}
        if params.top:
            query["$top"] = params.top

        data = await graph_request(
            context,
            f"teams/{params.team_id}/channels/{params.channel_id}/messages",
            params=query,
        )

        messages = [
            {
                "id": m.get("id"),
                "messageType": m.get("messageType"),
                "createdDateTime": m.get("createdDateTime"),
                "from": (
                    m.get("from", {}).get("user", {}).get("displayName")
                    if m.get("from")
                    else None
                ),
                "body": m.get("body", {}).get("content"),
                "contentType": m.get("body", {}).get("contentType"),
                "replyCount": len(m.get("replies", [])),
            }
            for m in data.get("value", [])
        ]
        return {"count": len(messages), "messages": messages}

    except Exception as exc:
        logger.exception("teams_get_channel_messages failed")
        return {"error": str(exc)}

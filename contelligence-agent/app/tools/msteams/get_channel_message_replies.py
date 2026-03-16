"""Tool to retrieve replies to a specific channel message."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import graph_request

logger = logging.getLogger(__name__)


class GetChannelMessageRepliesParams(BaseModel):
    """Parameters for the teams_get_channel_message_replies tool."""

    team_id: str = Field(
        ...,
        description="The ID of the team containing the channel.",
    )
    channel_id: str = Field(
        ...,
        description="The ID of the channel containing the message.",
    )
    message_id: str = Field(
        ...,
        description="The ID of the parent message to get replies for.",
    )
    top: int | None = Field(
        None,
        description="Maximum number of replies to return (default 50, max 50).",
        gt=0,
        le=50,
    )


@define_tool(
    name="teams_get_channel_message_replies",
    description=(
        "Retrieve replies to a specific message in a Microsoft Teams channel. "
        "Requires team ID, channel ID, and the parent message ID. "
        "Returns reply bodies, senders, and timestamps."
    ),
    parameters_model=GetChannelMessageRepliesParams,
)
async def get_channel_message_replies(
    params: GetChannelMessageRepliesParams, context: dict,
) -> dict[str, Any]:
    """Fetch replies for a channel message."""
    try:
        query: dict[str, Any] = {}
        if params.top:
            query["$top"] = params.top

        path = (
            f"teams/{params.team_id}/channels/{params.channel_id}"
            f"/messages/{params.message_id}/replies"
        )
        data = await graph_request(context, path, params=query)

        replies = [
            {
                "id": r.get("id"),
                "createdDateTime": r.get("createdDateTime"),
                "from": (
                    r.get("from", {}).get("user", {}).get("displayName")
                    if r.get("from")
                    else None
                ),
                "body": r.get("body", {}).get("content"),
                "contentType": r.get("body", {}).get("contentType"),
            }
            for r in data.get("value", [])
        ]
        return {"count": len(replies), "replies": replies}

    except Exception as exc:
        logger.exception("teams_get_channel_message_replies failed")
        return {"error": str(exc)}

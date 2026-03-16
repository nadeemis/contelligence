"""Tool to send a message to a Microsoft Teams channel."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import graph_request

logger = logging.getLogger(__name__)


class SendChannelMessageParams(BaseModel):
    """Parameters for the teams_send_channel_message tool."""

    team_id: str = Field(
        ...,
        description="The ID of the team containing the channel.",
    )
    channel_id: str = Field(
        ...,
        description="The ID of the channel to post the message to.",
    )
    content: str = Field(
        ...,
        description="The message body content to send.",
    )
    content_type: str = Field(
        "text",
        description="Content type: 'text' for plain text or 'html' for rich HTML.",
    )


@define_tool(
    name="teams_send_channel_message",
    description=(
        "Send a message to a Microsoft Teams channel. "
        "Requires team ID and channel ID. "
        "Supports plain text and HTML content."
    ),
    parameters_model=SendChannelMessageParams,
)
async def send_channel_message(
    params: SendChannelMessageParams, context: dict,
) -> dict[str, Any]:
    """Post a message to a Teams channel."""
    try:
        body = {
            "body": {
                "contentType": params.content_type,
                "content": params.content,
            },
        }

        data = await graph_request(
            context,
            f"teams/{params.team_id}/channels/{params.channel_id}/messages",
            method="POST",
            json_body=body,
        )

        return {
            "id": data.get("id"),
            "createdDateTime": data.get("createdDateTime"),
            "teamId": params.team_id,
            "channelId": params.channel_id,
            "status": "sent",
        }

    except Exception as exc:
        logger.exception("teams_send_channel_message failed")
        return {"error": str(exc)}

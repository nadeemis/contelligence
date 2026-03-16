"""Tool to send a message to a Microsoft Teams chat."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import graph_request

logger = logging.getLogger(__name__)


class SendChatMessageParams(BaseModel):
    """Parameters for the teams_send_chat_message tool."""

    chat_id: str = Field(
        ...,
        description="The ID of the chat to send the message to.",
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
    name="teams_send_chat_message",
    description=(
        "Send a message to a Microsoft Teams chat. "
        "Requires the chat ID (obtainable via teams_list_chats). "
        "Supports plain text and HTML content."
    ),
    parameters_model=SendChatMessageParams,
)
async def send_chat_message(
    params: SendChatMessageParams, context: dict,
) -> dict[str, Any]:
    """Send a message to a Teams chat."""
    try:
        body = {
            "body": {
                "contentType": params.content_type,
                "content": params.content,
            },
        }

        data = await graph_request(
            context,
            f"me/chats/{params.chat_id}/messages",
            method="POST",
            json_body=body,
        )

        return {
            "id": data.get("id"),
            "createdDateTime": data.get("createdDateTime"),
            "chatId": params.chat_id,
            "status": "sent",
        }

    except Exception as exc:
        logger.exception("teams_send_chat_message failed")
        return {"error": str(exc)}

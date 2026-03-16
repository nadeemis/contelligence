"""Tool to retrieve messages from a specific Microsoft Teams chat."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import graph_request

logger = logging.getLogger(__name__)


class GetChatMessagesParams(BaseModel):
    """Parameters for the teams_get_chat_messages tool."""

    chat_id: str = Field(
        ...,
        description="The ID of the chat to fetch messages from.",
    )
    top: int | None = Field(
        None,
        description="Maximum number of messages to return (default 50, max 50).",
        gt=0,
        le=50,
    )


@define_tool(
    name="teams_get_chat_messages",
    description=(
        "Retrieve messages from a Microsoft Teams chat. "
        "Requires the chat ID (obtainable via teams_list_chats). "
        "Returns message bodies, senders, timestamps, and message type."
    ),
    parameters_model=GetChatMessagesParams,
)
async def get_chat_messages(
    params: GetChatMessagesParams, context: dict,
) -> dict[str, Any]:
    """Fetch messages for a specific Teams chat."""
    try:
        query: dict[str, Any] = {"$orderby": "createdDateTime desc"}
        if params.top:
            query["$top"] = params.top

        data = await graph_request(
            context, f"me/chats/{params.chat_id}/messages", params=query,
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
            }
            for m in data.get("value", [])
        ]
        return {"count": len(messages), "messages": messages}

    except Exception as exc:
        logger.exception("teams_get_chat_messages failed")
        return {"error": str(exc)}

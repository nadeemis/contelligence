"""Tool to retrieve messages from a specific Microsoft Teams chat."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool
from ._graph_session import get_session

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class GetChatMessagesParams(BaseModel):
    """Parameters for the msteams_get_chat_messages tool."""

    chat_id: str = Field(
        ...,
        description=(
            "The ID of the chat to retrieve messages from. "
            "Obtain this from msteams_get_chats."
        ),
    )
    top: int = Field(
        50,
        description="Maximum number of messages to return (1–50).",
        ge=1,
        le=50,
    )
    headless: bool = Field(
        True,
        description="Launch the browser in headless mode.",
    )


@define_tool(
    name="msteams_get_chat_messages",
    description=(
        "Retrieve messages from a specific Microsoft Teams chat via the "
        "MS Graph API (/me/chats/{chat_id}/messages). Returns message "
        "bodies, senders, timestamps, and attachment metadata. Requires "
        "a chat_id obtained from msteams_get_chats."
    ),
    parameters_model=GetChatMessagesParams,
)
async def get_chat_messages(
    params: GetChatMessagesParams, context: dict,
) -> dict[str, Any]:
    """Retrieve messages from a Teams chat."""
    try:
        session = await get_session(headless=params.headless)

        data = await session.graph_get(
            f"/me/chats/{params.chat_id}/messages",
            params={"$top": str(params.top)},
        )

        messages = [
            {
                "id": m.get("id"),
                "messageType": m.get("messageType"),
                "createdDateTime": m.get("createdDateTime"),
                "lastModifiedDateTime": m.get("lastModifiedDateTime"),
                "from": (
                    (m.get("from") or {}).get("user", {}).get("displayName")
                ),
                "body": (m.get("body") or {}).get("content", ""),
                "contentType": (m.get("body") or {}).get("contentType"),
                "importance": m.get("importance"),
                "attachments": [
                    {
                        "id": a.get("id"),
                        "name": a.get("name"),
                        "contentType": a.get("contentType"),
                        "contentUrl": a.get("contentUrl"),
                    }
                    for a in (m.get("attachments") or [])
                ],
                "mentions": [
                    {
                        "id": mn.get("id"),
                        "mentionText": mn.get("mentionText"),
                    }
                    for mn in (m.get("mentions") or [])
                ],
            }
            for m in data.get("value", [])
        ]

        return {
            "chatId": params.chat_id,
            "count": len(messages),
            "messages": messages,
        }

    except Exception as exc:
        logger.exception("msteams_get_chat_messages failed")
        return {"error": str(exc)}

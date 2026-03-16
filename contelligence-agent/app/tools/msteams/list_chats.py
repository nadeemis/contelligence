"""Tool to list the signed-in user's Microsoft Teams chats."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import graph_request

logger = logging.getLogger(__name__)


class ListChatsParams(BaseModel):
    """Parameters for the teams_list_chats tool."""

    top: int | None = Field(
        None,
        description="Maximum number of chats to return (default 50, max 50).",
        gt=0,
        le=50,
    )
    chat_type: str | None = Field(
        None,
        description=(
            "Filter by chat type: 'oneOnOne', 'group', or 'meeting'. "
            "Omit to return all types."
        ),
    )


@define_tool(
    name="teams_list_chats",
    description=(
        "List the signed-in user's Microsoft Teams chats. "
        "Returns chat IDs, topics, chat type (oneOnOne, group, meeting), "
        "and last-updated timestamps. Use the returned chat ID with "
        "teams_get_chat_messages to fetch messages."
    ),
    parameters_model=ListChatsParams,
)
async def list_chats(
    params: ListChatsParams, context: dict,
) -> dict[str, Any]:
    """Retrieve the user's Teams chats via Microsoft Graph."""
    try:
        query: dict[str, Any] = {}
        if params.top:
            query["$top"] = params.top

        filter_parts: list[str] = []
        if params.chat_type:
            filter_parts.append(f"chatType eq '{params.chat_type}'")
        if filter_parts:
            query["$filter"] = " and ".join(filter_parts)

        data = await graph_request(context, "me/chats", params=query)

        chats = [
            {
                "id": c.get("id"),
                "topic": c.get("topic"),
                "chatType": c.get("chatType"),
                "createdDateTime": c.get("createdDateTime"),
                "lastUpdatedDateTime": c.get("lastUpdatedDateTime"),
            }
            for c in data.get("value", [])
        ]
        return {"count": len(chats), "chats": chats}

    except Exception as exc:
        logger.exception("teams_list_chats failed")
        return {"error": str(exc)}

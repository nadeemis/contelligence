"""Tool to list the current user's Microsoft Teams chats via MS Graph."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool
from ._graph_session import get_session, close_session

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class GetChatsParams(BaseModel):
    """Parameters for the msteams_get_chats tool."""

    top: int = Field(
        50,
        description="Maximum number of chats to return (1–50).",
        ge=1,
        le=50,
    )
    filter: str | None = Field(
        None,
        description=(
            "OData $filter expression. Example: "
            "\"chatType eq 'oneOnOne'\" to get only 1:1 chats."
        ),
    )
    expand_members: bool = Field(
        False,
        description="If true, expand the members navigation property.",
    )
    headless: bool = Field(
        True,
        description=(
            "Launch the browser in headless mode. Set to false if "
            "interactive login is required."
        ),
    )


@define_tool(
    name="msteams_get_chats",
    description=(
        "List the current user's Microsoft Teams chats via the MS Graph API "
        "(/me/chats). Returns chat IDs, topics, chat types, and the last "
        "message preview. Uses the authenticated Edge browser session — no "
        "app registration or tokens needed. Use msteams_get_chat_messages "
        "to read messages from a specific chat."
    ),
    parameters_model=GetChatsParams,
)
async def get_chats(params: GetChatsParams, context: dict) -> dict[str, Any]:
    """Retrieve the user's Teams chats."""
    try:
        session = await get_session(headless=params.headless)

        query: dict[str, str] = {
            "$top": str(params.top),
            "$orderby": "lastMessagePreview/createdDateTime desc",
        }
        if params.filter:
            query["$filter"] = params.filter
        if params.expand_members:
            query["$expand"] = "members"

        data = await session.graph_get("/me/chats", params=query)

        chats = [
            {
                "id": c.get("id"),
                "topic": c.get("topic"),
                "chatType": c.get("chatType"),
                "createdDateTime": c.get("createdDateTime"),
                "lastUpdatedDateTime": c.get("lastUpdatedDateTime"),
                "lastMessagePreview": (
                    {
                        "body": (c.get("lastMessagePreview") or {}).get("body", {}).get("content", ""),
                        "createdDateTime": (c.get("lastMessagePreview") or {}).get("createdDateTime"),
                        "from": (
                            ((c.get("lastMessagePreview") or {}).get("from") or {})
                            .get("user", {})
                            .get("displayName")
                        ),
                    }
                    if c.get("lastMessagePreview")
                    else None
                ),
                "members": (
                    [
                        {
                            "displayName": m.get("displayName"),
                            "email": m.get("email"),
                        }
                        for m in c.get("members", [])
                    ]
                    if params.expand_members
                    else None
                ),
            }
            for c in data.get("value", [])
        ]

        return {"count": len(chats), "chats": chats}

    except Exception as exc:
        logger.exception("msteams_get_chats failed")
        return {"error": str(exc)}

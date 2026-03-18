"""Tool to retrieve messages from a Microsoft Teams channel."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool
from ._graph_session import get_session

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# Regex to extract hosted-content image URLs from HTML bodies.
_HOSTED_CONTENT_RE = re.compile(
    r'src="(https://graph\.microsoft\.com/[^"]*hostedContents[^"]*)"',
)


class GetChannelMessagesParams(BaseModel):
    """Parameters for the msteams_get_channel_messages tool."""

    team_id: str = Field(
        ...,
        description="The ID of the team containing the channel.",
    )
    channel_id: str = Field(
        ...,
        description=(
            "The ID of the channel to retrieve messages from. "
            "Obtain this from msteams_get_channels."
        ),
    )
    channel_name: str = Field(
        "",
        description=(
            "The display name of the channel (e.g. 'General'). Used when "
            "navigating to the channel page in the browser to capture "
            "the correct token scopes."
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


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_sender(msg: dict[str, Any]) -> str | None:
    """Extract the display name of the sender from a message object."""
    from_obj = msg.get("from") or {}
    user_obj = from_obj.get("user") or {}
    app_obj = from_obj.get("application") or {}
    return user_obj.get("displayName") or app_obj.get("displayName")


def _parse_attachments(raw: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Parse attachments, including adaptive-card content."""
    attachments: list[dict[str, Any]] = []
    for a in raw or []:
        parsed: dict[str, Any] = {
            "id": a.get("id"),
            "name": a.get("name"),
            "contentType": a.get("contentType"),
            "contentUrl": a.get("contentUrl"),
        }
        # Adaptive cards carry their payload in a JSON string ``content`` field.
        if a.get("contentType") == "application/vnd.microsoft.card.adaptive":
            try:
                parsed["content"] = json.loads(a["content"])
            except (json.JSONDecodeError, KeyError, TypeError):
                parsed["content"] = a.get("content")
        attachments.append(parsed)
    return attachments


def _parse_mentions(raw: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Parse @mentions with richer target info."""
    mentions: list[dict[str, Any]] = []
    for mn in raw or []:
        mentioned = mn.get("mentioned") or {}
        # Resolve the mentioned entity — user, conversation/team, tag, or app
        mentioned_user = mentioned.get("user") or {}
        mentioned_conv = mentioned.get("conversation") or {}
        target: dict[str, Any] = {}
        if mentioned_user.get("displayName"):
            target = {
                "type": "user",
                "id": mentioned_user.get("id"),
                "displayName": mentioned_user.get("displayName"),
            }
        elif mentioned_conv.get("displayName"):
            target = {
                "type": mentioned_conv.get("conversationIdentityType", "conversation"),
                "id": mentioned_conv.get("id"),
                "displayName": mentioned_conv.get("displayName"),
            }
        mentions.append({
            "id": mn.get("id"),
            "mentionText": mn.get("mentionText"),
            "mentioned": target or None,
        })
    return mentions


def _parse_reactions(raw: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Parse reactions with emoji name and user."""
    return [
        {
            "reactionType": r.get("reactionType"),
            "displayName": r.get("displayName"),
            "user": (
                (r.get("user") or {}).get("user") or {}
            ).get("displayName"),
            "createdDateTime": r.get("createdDateTime"),
        }
        for r in (raw or [])
    ]


def _extract_hosted_content_urls(html: str) -> list[str]:
    """Pull Graph-hosted image URLs out of an HTML body."""
    return _HOSTED_CONTENT_RE.findall(html)


def _parse_event_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalise an eventDetail into a compact representation."""
    if not detail:
        return None
    event_type = detail.get("@odata.type", "")
    parsed: dict[str, Any] = {"type": event_type}

    # Teams app installed / removed
    if "teamsApp" in event_type.lower():
        parsed["teamsAppId"] = detail.get("teamsAppId")
        parsed["teamsAppDisplayName"] = detail.get("teamsAppDisplayName")

    # Members added / deleted / joined / left
    if "members" in event_type.lower():
        parsed["members"] = [
            {
                "id": mem.get("id"),
                "displayName": mem.get("displayName"),
            }
            for mem in (detail.get("members") or [])
        ]

    # Initiator (present on most event types)
    initiator = detail.get("initiator") or {}
    initiator_user = initiator.get("user") or {}
    initiator_app = initiator.get("application") or {}
    parsed["initiator"] = (
        initiator_user.get("displayName")
        or initiator_app.get("displayName")
    )

    return parsed


def _parse_message(m: dict[str, Any], *, include_replies: bool = True) -> dict[str, Any]:
    """Parse a single Graph chatMessage into our normalised shape."""
    body_obj = m.get("body") or {}
    body_html = body_obj.get("content", "")

    parsed: dict[str, Any] = {
        "id": m.get("id"),
        "replyToId": m.get("replyToId"),
        "messageType": m.get("messageType"),
        "createdDateTime": m.get("createdDateTime"),
        "lastModifiedDateTime": m.get("lastModifiedDateTime"),
        "lastEditedDateTime": m.get("lastEditedDateTime"),
        "deletedDateTime": m.get("deletedDateTime"),
        "from": _parse_sender(m),
        "subject": m.get("subject"),
        "body": body_html,
        "contentType": body_obj.get("contentType"),
        "importance": m.get("importance"),
        "locale": m.get("locale"),
        "webUrl": m.get("webUrl"),
        "attachments": _parse_attachments(m.get("attachments")),
        "mentions": _parse_mentions(m.get("mentions")),
        "reactions": _parse_reactions(m.get("reactions")),
        "hostedContentUrls": _extract_hosted_content_urls(body_html),
        "eventDetail": _parse_event_detail(m.get("eventDetail")),
    }

    if include_replies:
        raw_replies = m.get("replies") or []
        parsed["replyCount"] = m.get("replies@odata.count", len(raw_replies))
        parsed["replies"] = [
            _parse_message(r, include_replies=False)
            for r in raw_replies
        ]

    return parsed


# ------------------------------------------------------------------
# Tool definition
# ------------------------------------------------------------------

@define_tool(
    name="msteams_get_channel_messages",
    description=(
        "Retrieve messages from a Microsoft Teams channel via the MS Graph "
        "API (/teams/{team_id}/channels/{channel_id}/messages). Returns "
        "full message bodies, senders, timestamps, replies, attachments "
        "(including adaptive cards), @mentions, reactions, inline images, "
        "and system events (app installs, member changes). "
        "Requires team_id and channel_id from msteams_get_teams and "
        "msteams_get_channels."
    ),
    parameters_model=GetChannelMessagesParams,
)
async def get_channel_messages(
    params: GetChannelMessagesParams, context: dict,
) -> dict[str, Any]:
    """Retrieve messages from a Teams channel."""
    try:
        session = await get_session(headless=params.headless)

        data = await session.graph_get(
            f"/teams/{params.team_id}/channels/{params.channel_id}/messages",
            params={"$expand": "replies", "$top": str(params.top)},
        )

        messages = [
            _parse_message(m) for m in data.get("value", [])
        ]

        result: dict[str, Any] = {
            "teamId": params.team_id,
            "channelId": params.channel_id,
            "count": len(messages),
            "messages": messages,
        }

        # Pagination metadata
        if data.get("@odata.count") is not None:
            result["totalCount"] = data["@odata.count"]
        if data.get("@odata.nextLink"):
            result["nextLink"] = data["@odata.nextLink"]

        return result

    except Exception as exc:
        logger.exception("msteams_get_channel_messages failed")
        return {"error": str(exc)}

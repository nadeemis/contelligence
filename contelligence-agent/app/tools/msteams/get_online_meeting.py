"""Tool to retrieve details of a Microsoft Teams online meeting."""

from __future__ import annotations

import logging
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool
from ._graph_session import get_session

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class GetOnlineMeetingParams(BaseModel):
    """Parameters for the msteams_get_online_meeting tool."""

    meeting_id: str | None = Field(
        None,
        description=(
            "The online-meeting ID. Obtain from the onlineMeeting "
            "property of a calendar event or from the meeting URL."
        ),
    )
    join_web_url: str | None = Field(
        None,
        description=(
            "The joinWebUrl of the meeting (the Teams 'Join' link). "
            "Use this when you have the meeting URL but not the ID."
        ),
    )
    join_meeting_id: str | None = Field(
        None,
        description=(
            "The joinMeetingId (numeric meeting code). "
            "Use this when you have the dial-in meeting ID."
        ),
    )
    headless: bool = Field(
        True,
        description="Launch the browser in headless mode.",
    )


@define_tool(
    name="msteams_get_online_meeting",
    description=(
        "Retrieve details of a Microsoft Teams online meeting via the "
        "MS Graph API. Supports lookup by meeting_id "
        "(/me/onlineMeetings/{id}), join_web_url, or join_meeting_id. "
        "Returns subject, start/end times, participants, lobby settings, "
        "join information, and audio conferencing details. Provide exactly "
        "one of meeting_id, join_web_url, or join_meeting_id."
    ),
    parameters_model=GetOnlineMeetingParams,
)
async def get_online_meeting(
    params: GetOnlineMeetingParams, context: dict,
) -> dict[str, Any]:
    """Retrieve an online meeting by ID, joinWebUrl, or joinMeetingId."""
    try:
        session = await get_session(headless=params.headless)

        if params.meeting_id:
            data = await session.graph_get(
                f"/me/onlineMeetings/{params.meeting_id}",
            )
        elif params.join_web_url:
            encoded_url = quote(params.join_web_url, safe="")
            data = await session.graph_get(
                "/me/onlineMeetings",
                params={"$filter": f"JoinWebUrl eq '{encoded_url}'"},
            )
            # Filter returns a collection — unwrap the first value
            values = data.get("value", [])
            if not values:
                return {"error": "No meeting found for the provided joinWebUrl."}
            data = values[0]
        elif params.join_meeting_id:
            data = await session.graph_get(
                "/me/onlineMeetings",
                params={
                    "$filter": (
                        f"joinMeetingIdSettings/joinMeetingId eq "
                        f"'{params.join_meeting_id}'"
                    ),
                },
            )
            values = data.get("value", [])
            if not values:
                return {"error": "No meeting found for the provided joinMeetingId."}
            data = values[0]
        else:
            return {
                "error": (
                    "Provide exactly one of: meeting_id, join_web_url, "
                    "or join_meeting_id."
                ),
            }

        participants = data.get("participants") or {}
        organizer_identity = (
            (participants.get("organizer") or {})
            .get("identity", {})
            .get("user", {})
        )

        return {
            "id": data.get("id"),
            "subject": data.get("subject"),
            "startDateTime": data.get("startDateTime"),
            "endDateTime": data.get("endDateTime"),
            "creationDateTime": data.get("creationDateTime"),
            "joinWebUrl": data.get("joinWebUrl"),
            "organizer": {
                "displayName": organizer_identity.get("displayName"),
                "id": organizer_identity.get("id"),
                "upn": (participants.get("organizer") or {}).get("upn"),
            },
            "attendees": [
                {
                    "displayName": (
                        (a.get("identity") or {}).get("user", {}).get("displayName")
                    ),
                    "upn": a.get("upn"),
                    "role": a.get("role"),
                }
                for a in participants.get("attendees", [])
            ],
            "audioConferencing": data.get("audioConferencing"),
            "lobbyBypassSettings": data.get("lobbyBypassSettings"),
            "joinMeetingIdSettings": data.get("joinMeetingIdSettings"),
            "allowedPresenters": data.get("allowedPresenters"),
            "isEntryExitAnnounced": data.get("isEntryExitAnnounced"),
            "autoAdmittedUsers": data.get("autoAdmittedUsers"),
            "videoTeleconferenceId": data.get("videoTeleconferenceId"),
            "chatInfo": data.get("chatInfo"),
        }

    except Exception as exc:
        logger.exception("msteams_get_online_meeting failed")
        return {"error": str(exc)}

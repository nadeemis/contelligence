"""Tool to retrieve details of a specific calendar event."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool
from ._graph_session import get_session

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class GetCalendarEventParams(BaseModel):
    """Parameters for the msteams_get_calendar_event tool."""

    event_id: str = Field(
        ...,
        description=(
            "The ID of the calendar event to retrieve. "
            "Obtain this from msteams_get_calendar."
        ),
    )
    headless: bool = Field(
        True,
        description="Launch the browser in headless mode.",
    )


@define_tool(
    name="msteams_get_calendar_event",
    description=(
        "Retrieve full details of a specific calendar event via the MS Graph "
        "API (/me/events/{event_id}). Returns the subject, body, start/end "
        "times, location, organizer, attendees with RSVP status, online "
        "meeting join URL, recurrence pattern, and attachments. Requires an "
        "event_id obtained from msteams_get_calendar."
    ),
    parameters_model=GetCalendarEventParams,
)
async def get_calendar_event(
    params: GetCalendarEventParams, context: dict,
) -> dict[str, Any]:
    """Retrieve details of a single calendar event."""
    try:
        session = await get_session(headless=params.headless)

        ev = await session.graph_get(
            f"/me/events/{params.event_id}",
            headers={"Prefer": 'outlook.timezone="UTC"'},
        )

        return {
            "id": ev.get("id"),
            "subject": ev.get("subject"),
            "body": (ev.get("body") or {}).get("content", ""),
            "bodyContentType": (ev.get("body") or {}).get("contentType"),
            "start": (
                ev.get("start", {}).get("dateTime")
                if isinstance(ev.get("start"), dict)
                else ev.get("start")
            ),
            "end": (
                ev.get("end", {}).get("dateTime")
                if isinstance(ev.get("end"), dict)
                else ev.get("end")
            ),
            "timeZone": (
                ev.get("start", {}).get("timeZone")
                if isinstance(ev.get("start"), dict)
                else None
            ),
            "location": (
                ev.get("location", {}).get("displayName")
                if isinstance(ev.get("location"), dict)
                else ev.get("location")
            ),
            "isOnlineMeeting": ev.get("isOnlineMeeting"),
            "onlineMeetingUrl": ev.get("onlineMeetingUrl"),
            "onlineMeeting": (
                {
                    "joinUrl": (ev.get("onlineMeeting") or {}).get("joinUrl"),
                    "conferenceId": (ev.get("onlineMeeting") or {}).get("conferenceId"),
                    "tollNumber": (ev.get("onlineMeeting") or {}).get("tollNumber"),
                }
                if ev.get("onlineMeeting")
                else None
            ),
            "organizer": (
                {
                    "name": ev.get("organizer", {}).get("emailAddress", {}).get("name"),
                    "email": ev.get("organizer", {}).get("emailAddress", {}).get("address"),
                }
                if isinstance(ev.get("organizer"), dict)
                else None
            ),
            "attendees": [
                {
                    "name": (a.get("emailAddress") or {}).get("name"),
                    "email": (a.get("emailAddress") or {}).get("address"),
                    "type": a.get("type"),
                    "status": (a.get("status") or {}).get("response"),
                }
                for a in (ev.get("attendees") or [])
            ],
            "recurrence": ev.get("recurrence"),
            "importance": ev.get("importance"),
            "sensitivity": ev.get("sensitivity"),
            "isAllDay": ev.get("isAllDay"),
            "isCancelled": ev.get("isCancelled"),
            "hasAttachments": ev.get("hasAttachments"),
            "categories": ev.get("categories"),
            "createdDateTime": ev.get("createdDateTime"),
            "lastModifiedDateTime": ev.get("lastModifiedDateTime"),
            "webLink": ev.get("webLink"),
        }

    except Exception as exc:
        logger.exception("msteams_get_calendar_event failed")
        return {"error": str(exc)}

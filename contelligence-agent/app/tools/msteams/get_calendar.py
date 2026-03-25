"""Tool to retrieve the current user's calendar events from Microsoft Teams."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool
from ._graph_session import get_session

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class GetCalendarParams(BaseModel):
    """Parameters for the msteams_get_calendar tool."""

    start_date: str | None = Field(
        None,
        description=(
            "Start of the date range in ISO 8601 format "
            "(e.g. '2026-03-17T00:00:00Z'). Defaults to today."
        ),
    )
    end_date: str | None = Field(
        None,
        description=(
            "End of the date range in ISO 8601 format "
            "(e.g. '2026-03-24T23:59:59Z'). Defaults to 7 days from start."
        ),
    )
    top: int = Field(
        50,
        description="Maximum number of events to return (1-100).",
        ge=1,
        le=100,
    )
    headless: bool = Field(
        True,
        description="Launch the browser in headless mode.",
    )


@define_tool(
    name="msteams_get_calendar",
    description=(
        "Retrieve calendar events for the current user via the MS Graph API "
        "(/me/calendarView). Returns event subjects, start/end times, "
        "organizer, online meeting URLs, and attendees. Defaults to the "
        "next 7 days if no date range is specified."
    ),
    parameters_model=GetCalendarParams,
)
async def get_calendar(
    params: GetCalendarParams, context: dict,
) -> dict[str, Any]:
    """Retrieve calendar events."""
    try:
        session = await get_session(headless=params.headless)

        now = datetime.now(timezone.utc)

        start = params.start_date or now.strftime("%Y-%m-%dT00:00:00Z")
        if params.end_date:
            end = params.end_date
        else:
            # Parse start to compute end = start + 7 days
            try:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            except ValueError:
                start_dt = now
            end = (start_dt + timedelta(days=7)).strftime("%Y-%m-%dT23:59:59Z")

        data = await session.graph_get(
            "/me/calendarView",
            params={
                "startDateTime": start,
                "endDateTime": end,
                "$top": str(params.top),
            },
            headers={"Prefer": 'outlook.timezone="UTC"'},
        )

        events = [
            {
                "id": ev.get("id"),
                "subject": ev.get("subject"),
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
                "location": (
                    ev.get("location", {}).get("displayName")
                    if isinstance(ev.get("location"), dict)
                    else ev.get("location")
                ),
                "isOnlineMeeting": ev.get("isOnlineMeeting"),
                "onlineMeetingUrl": ev.get("onlineMeetingUrl"),
                "organizer": (
                    ev.get("organizer", {})
                    .get("emailAddress", {})
                    .get("name")
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
                "importance": ev.get("importance"),
                "isAllDay": ev.get("isAllDay"),
                "isCancelled": ev.get("isCancelled"),
            }
            for ev in data.get("value", [])
        ]

        return {
            "startDateTime": start,
            "endDateTime": end,
            "count": len(events),
            "events": events,
        }

    except Exception as exc:
        logger.exception("msteams_get_calendar failed")
        return {"error": str(exc)}

"""Tool to list calendar events for the signed-in user."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import graph_request

logger = logging.getLogger(__name__)


class ListCalendarEventsParams(BaseModel):
    """Parameters for the teams_list_calendar_events tool."""

    start_datetime: str | None = Field(
        None,
        description=(
            "ISO 8601 start of the time range (e.g. '2025-01-01T00:00:00Z'). "
            "Required when end_datetime is provided."
        ),
    )
    end_datetime: str | None = Field(
        None,
        description=(
            "ISO 8601 end of the time range (e.g. '2025-01-31T23:59:59Z'). "
            "Required when start_datetime is provided."
        ),
    )
    top: int | None = Field(
        None,
        description="Maximum number of events to return (default 25).",
        gt=0,
    )


@define_tool(
    name="teams_list_calendar_events",
    description=(
        "List calendar events for the signed-in user from Microsoft 365. "
        "Supports optional date range filtering via calendarView. "
        "Returns event subjects, organizers, start/end times, locations, "
        "and online meeting URLs (Teams meeting links)."
    ),
    parameters_model=ListCalendarEventsParams,
)
async def list_calendar_events(
    params: ListCalendarEventsParams, context: dict,
) -> dict[str, Any]:
    """Retrieve user calendar events."""
    try:
        query: dict[str, Any] = {
            "$orderby": "start/dateTime",
        }
        if params.top:
            query["$top"] = params.top

        # Use calendarView for date-range queries, otherwise /events
        if params.start_datetime and params.end_datetime:
            path = "me/calendarView"
            query["startDateTime"] = params.start_datetime
            query["endDateTime"] = params.end_datetime
        else:
            path = "me/events"

        data = await graph_request(context, path, params=query)

        events = [
            {
                "id": e.get("id"),
                "subject": e.get("subject"),
                "organizer": (
                    e.get("organizer", {})
                    .get("emailAddress", {})
                    .get("name")
                ),
                "start": e.get("start"),
                "end": e.get("end"),
                "location": e.get("location", {}).get("displayName"),
                "isOnlineMeeting": e.get("isOnlineMeeting"),
                "onlineMeetingUrl": e.get("onlineMeetingUrl"),
                "bodyPreview": e.get("bodyPreview"),
            }
            for e in data.get("value", [])
        ]
        return {"count": len(events), "events": events}

    except Exception as exc:
        logger.exception("teams_list_calendar_events failed")
        return {"error": str(exc)}

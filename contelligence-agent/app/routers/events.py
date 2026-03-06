"""Events Router — Azure Event Grid webhook receiver.

Accepts Event Grid subscription validation handshakes and event
notifications.  Matched events are dispatched to the scheduling engine
which fires any schedules with matching ``event`` triggers.

Mount at ``/api/events``:

    app.include_router(events_router, prefix="/api/events")
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.auth.middleware import get_current_user
from app.auth.models import User

logger = logging.getLogger(f"contelligence-agent.{__name__}")

router = APIRouter(prefix="/events", tags=["Events"])


@router.post("")
async def handle_event_grid(
    request: Request,
    user: User = Depends(get_current_user),
) -> JSONResponse:
    """Handle Azure Event Grid subscription validation and event delivery.

    Event Grid sends a validation handshake on subscription creation
    (``SubscriptionValidation`` event type).  On success, this endpoint
    echoes the ``validationCode`` back.

    All other events are forwarded to the scheduling engine for
    matching against registered event-triggered schedules.
    """
    body = await request.json()

    # Event Grid sends an array of events
    events: list[dict[str, Any]] = body if isinstance(body, list) else [body]

    # ------------------------------------------------------------------
    # Subscription Validation Handshake
    # ------------------------------------------------------------------
    for event in events:
        event_type = event.get("eventType", "")
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            validation_code = (
                event.get("data", {}).get("validationCode", "")
            )
            logger.info("Event Grid subscription validation received.")
            return JSONResponse(
                content={"validationResponse": validation_code},
            )

    # ------------------------------------------------------------------
    # Event Dispatch
    # ------------------------------------------------------------------
    scheduling_engine = getattr(request.app.state, "scheduling_engine", None)
    if scheduling_engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduling engine not available",
        )

    session_ids: list[str] = []
    for event in events:
        event_type = event.get("eventType", "unknown")
        subject = event.get("subject", "")
        source = event.get("source", "")

        # Build a normalised event_source for matching
        # e.g., "blob:vendor-inbox" from an Azure Blob event
        event_source = _normalise_event_source(source, event_type, subject)

        logger.info(
            "Received event: type=%s, subject=%s, source=%s → %s",
            event_type,
            subject,
            source,
            event_source,
        )

        fired = await scheduling_engine.handle_event(
            event_source=event_source,
            event_data=event,
        )
        session_ids.extend(fired)

    return JSONResponse(
        content={
            "accepted": True,
            "events_processed": len(events),
            "sessions_created": session_ids,
        },
    )


def _normalise_event_source(
    source: str, event_type: str, subject: str,
) -> str:
    """Normalise an Event Grid event into a simple source string.

    Maps Azure resource events into the ``<type>:<container>`` format
    used by schedule trigger configurations.

    Examples:
    - Blob: ``/blobServices/.../vendor-inbox`` → ``blob:vendor-inbox``
    - Queue: ``Microsoft.Storage.QueueCreated`` → ``queue:<subject>``
    """
    # Azure Blob Storage events
    if "BlobCreated" in event_type or "Blob" in event_type:
        container = _extract_blob_container(subject)
        return f"blob:{container}" if container else f"blob:{subject}"

    # Azure Queue Storage events
    if "Queue" in event_type:
        return f"queue:{subject}"

    # Generic — use the raw source
    return source


def _extract_blob_container(subject: str) -> str:
    """Extract the container name from a blob event subject.

    Subjects look like: ``/blobServices/default/containers/vendor-inbox/blobs/file.pdf``
    """
    parts = subject.split("/")
    try:
        idx = parts.index("containers")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""

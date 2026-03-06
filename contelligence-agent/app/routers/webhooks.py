"""Webhooks Router — inbound HTTP trigger endpoint.

Receives POST requests at ``/api/webhooks/{webhook_id}`` and fires
the matching schedule.  Optionally validates HMAC signatures.

Mount at ``/api/webhooks``:

    app.include_router(webhooks_router, prefix="/api/webhooks")
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.utils.hmac_validation import validate_signature

logger = logging.getLogger(f"contelligence-agent.{__name__}")

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/{webhook_id}")
async def handle_webhook(
    webhook_id: str,
    request: Request,
) -> JSONResponse:
    """Receive and validate an inbound webhook trigger.

    The endpoint is **unauthenticated by design** (the HMAC signature
    serves as the authentication mechanism).  The ``webhook_id`` maps
    to a specific schedule's ``webhook_id`` field.

    Steps:
    1. Read raw body and extract ``X-Webhook-Signature`` header
    2. Look up the schedule by ``webhook_id``
    3. Validate HMAC if a secret is configured
    4. Fire the schedule via the scheduling engine
    """
    body = await request.body()
    signature_header = request.headers.get("X-Webhook-Signature")

    # Get scheduling engine
    scheduling_engine = getattr(request.app.state, "scheduling_engine", None)
    if scheduling_engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduling engine not available",
        )

    # Look up the schedule to get the webhook secret
    schedule_store = getattr(request.app.state, "schedule_store", None)
    if schedule_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Schedule store not available",
        )

    # Find schedule by webhook_id
    from app.models.schedule_models import TriggerType

    schedules = await schedule_store.get_schedules_by_trigger_type(
        TriggerType.WEBHOOK.value,
    )
    matching = [s for s in schedules if s.webhook_id == webhook_id]

    if not matching:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No schedule found for webhook ID: {webhook_id}",
        )

    schedule = matching[0]

    # Validate HMAC signature
    secret = schedule.trigger.webhook_secret or ""
    if not validate_signature(body, secret, signature_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # Parse payload
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    # Fire the schedule
    session_id = await scheduling_engine.handle_webhook(
        webhook_id=webhook_id,
        payload=payload,
    )

    if session_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fire schedule",
        )

    logger.info(
        "Webhook %s fired schedule %s → session %s",
        webhook_id,
        schedule.id,
        session_id,
    )

    return JSONResponse(
        content={
            "accepted": True,
            "schedule_id": schedule.id,
            "session_id": session_id,
        },
    )

"""Schedules Router — CRUD endpoints for managing scheduled agent jobs.

Mount at ``/api/schedules``:

    app.include_router(schedules_router, prefix="/api/schedules")

All endpoints require at least the ``operator`` role.

Endpoints:
- ``POST   /``              — Create a new schedule
- ``GET    /``              — List schedules (with filters)
- ``GET    /{schedule_id}`` — Get a specific schedule
- ``PATCH  /{schedule_id}`` — Update a schedule
- ``DELETE /{schedule_id}`` — Delete a schedule
- ``POST   /{schedule_id}/pause``   — Pause a schedule
- ``POST   /{schedule_id}/resume``  — Resume a paused schedule
- ``POST   /{schedule_id}/trigger`` — Fire a schedule immediately
- ``GET    /{schedule_id}/runs``    — List run history
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.auth.middleware import get_current_user, require_role
from app.auth.models import Role, User
from app.models.exceptions import ScheduleNotFoundError
from app.models.schedule_models import (
    CreateScheduleRequest,
    ScheduleRecord,
    ScheduleRunRecord,
    UpdateScheduleRequest,
)

logger = logging.getLogger(f"contelligence-agent.{__name__}")

router = APIRouter(prefix="/schedules", tags=["Schedules"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_schedule_service(request: Request):
    """Extract the ``ScheduleService`` from ``app.state``."""
    svc = getattr(request.app.state, "schedule_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Schedule service not available",
        )
    return svc


def _get_schedule_store(request: Request):
    """Extract the ``ScheduleStore`` from ``app.state``."""
    store = getattr(request.app.state, "schedule_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Schedule store not available",
        )
    return store


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ScheduleRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new schedule",
)
async def create_schedule(
    body: CreateScheduleRequest,
    request: Request,
    user: User = Depends(require_role(Role.OPERATOR)),
) -> ScheduleRecord:
    """Create a new scheduled agent job."""
    svc = _get_schedule_service(request)
    try:
        return await svc.create_schedule(body, created_by=user.oid)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=list[ScheduleRecord],
    summary="List schedules",
)
async def list_schedules(
    request: Request,
    user: User = Depends(get_current_user),
    status_filter: str | None = Query(None, alias="status"),
    trigger_type: str | None = Query(None, alias="trigger_type"),
    tag: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ScheduleRecord]:
    """List all schedules with optional filters."""
    store = _get_schedule_store(request)
    return await store.list_schedules(
        status=status_filter,
        trigger_type=trigger_type,
        tag=tag,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{schedule_id}",
    response_model=ScheduleRecord,
    summary="Get a schedule",
)
async def get_schedule(
    schedule_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> ScheduleRecord:
    """Get a specific schedule by ID."""
    store = _get_schedule_store(request)
    try:
        return await store.get_schedule(schedule_id)
    except ScheduleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule not found: {schedule_id}",
        )


@router.patch(
    "/{schedule_id}",
    response_model=ScheduleRecord,
    summary="Update a schedule",
)
async def update_schedule(
    schedule_id: str,
    body: UpdateScheduleRequest,
    request: Request,
    user: User = Depends(require_role(Role.OPERATOR)),
) -> ScheduleRecord:
    """Update an existing schedule (partial update)."""
    svc = _get_schedule_service(request)
    try:
        return await svc.update_schedule(schedule_id, body)
    except ScheduleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule not found: {schedule_id}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a schedule",
)
async def delete_schedule(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_role(Role.ADMIN)),
) -> None:
    """Soft-delete a schedule."""
    svc = _get_schedule_service(request)
    try:
        await svc.delete_schedule(schedule_id)
    except ScheduleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule not found: {schedule_id}",
        )


# ---------------------------------------------------------------------------
# Lifecycle Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{schedule_id}/pause",
    response_model=ScheduleRecord,
    summary="Pause a schedule",
)
async def pause_schedule(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_role(Role.OPERATOR)),
) -> ScheduleRecord:
    """Pause a running schedule."""
    svc = _get_schedule_service(request)
    try:
        return await svc.pause_schedule(schedule_id)
    except ScheduleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule not found: {schedule_id}",
        )


@router.post(
    "/{schedule_id}/resume",
    response_model=ScheduleRecord,
    summary="Resume a schedule",
)
async def resume_schedule(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_role(Role.OPERATOR)),
) -> ScheduleRecord:
    """Resume a paused schedule."""
    svc = _get_schedule_service(request)
    try:
        return await svc.resume_schedule(schedule_id)
    except ScheduleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule not found: {schedule_id}",
        )


@router.post(
    "/{schedule_id}/trigger",
    summary="Trigger a schedule manually",
)
async def trigger_schedule_now(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_role(Role.OPERATOR)),
) -> JSONResponse:
    """Fire a schedule immediately (manual trigger)."""
    svc = _get_schedule_service(request)
    try:
        session_id = await svc.trigger_now(schedule_id)
    except ScheduleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule not found: {schedule_id}",
        )

    if session_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger schedule",
        )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "schedule_id": schedule_id,
            "session_id": session_id,
            "trigger_reason": "manual",
        },
    )


# ---------------------------------------------------------------------------
# Run History
# ---------------------------------------------------------------------------


@router.get(
    "/{schedule_id}/runs",
    response_model=list[ScheduleRunRecord],
    summary="List run history for a schedule",
)
async def list_schedule_runs(
    schedule_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
) -> list[ScheduleRunRecord]:
    """List recent run history for a specific schedule."""
    store = _get_schedule_store(request)

    # Verify schedule exists
    try:
        await store.get_schedule(schedule_id)
    except ScheduleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule not found: {schedule_id}",
        )

    return await store.list_runs(
        schedule_id,
        limit=limit,
        status=status_filter,
    )

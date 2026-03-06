"""Dashboard Router — aggregated metrics, activity feed, and upcoming runs.

Mount at ``/api/dashboard``:

    app.include_router(dashboard_router, prefix="/api/dashboard")

Provides three endpoints:
- ``GET /metrics``  — Aggregated session and schedule counts
- ``GET /activity`` — Recent activity feed
- ``GET /upcoming`` — Upcoming scheduled runs
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.middleware import get_current_user
from app.auth.models import User
from app.models.schedule_models import ActivityEvent, DashboardMetrics
from app.models.session_models import SessionStatus

logger = logging.getLogger(f"contelligence-agent.{__name__}")

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# ---------------------------------------------------------------------------
# Helper — access state
# ---------------------------------------------------------------------------


def _get_session_store(request: Request):
    store = getattr(request.app.state, "session_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session store not available",
        )
    return store


def _get_schedule_store(request: Request):
    store = getattr(request.app.state, "schedule_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Schedule store not available",
        )
    return store


def _get_scheduling_engine(request: Request):
    return getattr(request.app.state, "scheduling_engine", None)


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------


@router.get(
    "/metrics",
    response_model=DashboardMetrics,
    summary="Dashboard metrics",
)
async def get_dashboard_metrics(
    request: Request,
    user: User = Depends(get_current_user),
    days: int = Query(7, ge=1, le=90, description="Number of lookback days"),
) -> DashboardMetrics:
    """Return aggregated metrics for the dashboard.

    Queries sessions and schedule runs over the specified lookback
    period and computes totals, rates, and breakdowns.
    """
    session_store = _get_session_store(request)
    schedule_store = _get_schedule_store(request)

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Fetch all sessions in the window
    all_sessions = await session_store.list_sessions(since=since, limit=1000)

    total = len(all_sessions)
    active = sum(1 for s in all_sessions if s.status == SessionStatus.ACTIVE)
    completed = sum(1 for s in all_sessions if s.status == SessionStatus.COMPLETED)
    failed = sum(1 for s in all_sessions if s.status == SessionStatus.FAILED)

    # Aggregate metrics
    total_tool_calls = 0
    total_docs = 0
    total_duration = 0.0
    durations: list[float] = []

    for session in all_sessions:
        if session.metrics:
            total_tool_calls += session.metrics.total_tool_calls
            total_docs += session.metrics.documents_processed
            if session.metrics.total_duration_seconds > 0:
                total_duration += session.metrics.total_duration_seconds
                durations.append(session.metrics.total_duration_seconds)

    avg_duration = (sum(durations) / len(durations)) if durations else 0.0
    error_rate = (failed / total) if total > 0 else 0.0

    # Schedule counts
    active_schedules = await schedule_store.count_schedules(status="active")

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    schedules_fired_today = await schedule_store.count_runs_since(since=today_start)

    # Sessions by day
    sessions_by_day = _aggregate_sessions_by_day(all_sessions, days)

    # Top tools (from across sessions — best effort from metrics)
    # Note: detailed per-tool breakdown requires conversation store queries
    # For MVP, we return tool_calls total only
    top_tools: list[dict[str, Any]] = []

    return DashboardMetrics(
        total_sessions=total,
        active_sessions=active,
        completed_sessions=completed,
        failed_sessions=failed,
        total_tool_calls=total_tool_calls,
        total_documents_processed=total_docs,
        avg_session_duration_seconds=round(avg_duration, 2),
        error_rate=round(error_rate, 4),
        active_schedules=active_schedules,
        schedules_fired_today=schedules_fired_today,
        sessions_by_day=sessions_by_day,
        top_tools=top_tools,
    )


# ---------------------------------------------------------------------------
# GET /activity
# ---------------------------------------------------------------------------


@router.get(
    "/activity",
    response_model=list[ActivityEvent],
    summary="Recent activity feed",
)
async def get_activity_feed(
    request: Request,
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
) -> list[ActivityEvent]:
    """Return recent activity events for the dashboard feed.

    Combines recent session completions/failures and schedule fires
    into a unified, chronologically sorted feed.
    """
    session_store = _get_session_store(request)
    schedule_store = _get_schedule_store(request)

    events: list[ActivityEvent] = []

    # Recent sessions (completed + failed)
    since = datetime.now(timezone.utc) - timedelta(days=7)
    sessions = await session_store.list_sessions(since=since, limit=limit)

    for session in sessions:
        if session.status in (SessionStatus.COMPLETED, SessionStatus.FAILED):
            event_type = (
                "session_completed"
                if session.status == SessionStatus.COMPLETED
                else "session_failed"
            )
            events.append(
                ActivityEvent(
                    timestamp=session.updated_at,
                    type=event_type,
                    session_id=session.id,
                    schedule_id=session.schedule_id,
                    summary=session.summary or f"Session {session.id[:8]}... {session.status.value}",
                ),
            )

    # Recent schedule runs
    recent_runs = await schedule_store.get_recent_runs(limit=limit)
    for run in recent_runs:
        events.append(
            ActivityEvent(
                timestamp=run.triggered_at,
                type="schedule_fired",
                session_id=run.session_id,
                schedule_id=run.schedule_id,
                summary=f"Schedule {run.schedule_id[:8]}... fired ({run.trigger_reason})",
            ),
        )

    # Sort by timestamp descending and limit
    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events[:limit]


# ---------------------------------------------------------------------------
# GET /upcoming
# ---------------------------------------------------------------------------


@router.get(
    "/upcoming",
    summary="Upcoming scheduled runs",
)
async def get_upcoming_runs(
    request: Request,
    user: User = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, Any]]:
    """Return upcoming scheduled job runs from the APScheduler.

    Only available when this instance is the scheduler leader.
    """
    engine = _get_scheduling_engine(request)
    if engine is None:
        return []

    return engine.get_upcoming_runs(limit=limit)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _aggregate_sessions_by_day(
    sessions: list[Any],
    days: int,
) -> list[dict[str, Any]]:
    """Aggregate sessions into daily counts for the last N days."""
    from collections import Counter

    day_counts: Counter[str] = Counter()
    for session in sessions:
        day_key = session.created_at.strftime("%Y-%m-%d")
        day_counts[day_key] += 1

    # Fill in missing days
    today = datetime.now(timezone.utc).date()
    result: list[dict[str, Any]] = []
    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.isoformat()
        result.append({"date": date_str, "count": day_counts.get(date_str, 0)})

    result.reverse()  # Oldest first
    return result

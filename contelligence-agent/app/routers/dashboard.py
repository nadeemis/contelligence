"""Dashboard Router — aggregated metrics, activity feed, and upcoming runs.

Mount at ``/api/dashboard``:

    app.include_router(dashboard_router, prefix="/api/dashboard")

Provides five endpoints:
- ``GET /metrics``          — Aggregated session and schedule counts
- ``GET /metrics/detailed`` — Detailed metrics with tables for sessions, tools, schedules
- ``GET /metrics/daily``    — Drill-down metrics for a specific day
- ``GET /activity``         — Recent activity feed
- ``GET /upcoming``         — Upcoming scheduled runs
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.middleware import get_current_user
from app.auth.models import User
from app.models.schedule_models import (
    ActivityEvent,
    DailyDetailMetrics,
    DashboardMetrics,
    DetailedMetrics,
    ScheduleMetricsDetail,
    SessionMetricsDetail,
    ToolCallMetricsDetail,
)
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
# GET /metrics/detailed
# ---------------------------------------------------------------------------


@router.get(
    "/metrics/detailed",
    response_model=DetailedMetrics,
    summary="Detailed metrics by category",
)
async def get_detailed_metrics(
    request: Request,
    user: User = Depends(get_current_user),
    days: int = Query(30, ge=1, le=90, description="Number of lookback days"),
) -> DetailedMetrics:
    """Return detailed metrics broken into sessions, tool calls, and schedules.

    Each category contains multiple table datasets plus trend data.
    """
    session_store = _get_session_store(request)
    schedule_store = _get_schedule_store(request)

    since = datetime.now(timezone.utc) - timedelta(days=days)
    today = datetime.now(timezone.utc).date()

    # Fetch sessions in window
    all_sessions = await session_store.list_sessions(since=since, limit=1000)

    # ── Session Metrics ──────────────────────────────────────────────
    sessions_detail = _build_session_metrics(all_sessions, days, today)

    # ── Tool Call Metrics ────────────────────────────────────────────
    tool_calls_detail = await _build_tool_call_metrics(
        session_store, all_sessions, days, today,
    )

    # ── Schedule Metrics ─────────────────────────────────────────────
    schedules_detail = await _build_schedule_metrics(
        schedule_store, days, today, since,
    )

    return DetailedMetrics(
        sessions=sessions_detail,
        tool_calls=tool_calls_detail,
        schedules=schedules_detail,
    )


# ---------------------------------------------------------------------------
# GET /metrics/daily
# ---------------------------------------------------------------------------


@router.get(
    "/metrics/daily",
    response_model=DailyDetailMetrics,
    summary="Daily drill-down metrics",
)
async def get_daily_metrics(
    request: Request,
    user: User = Depends(get_current_user),
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
) -> DailyDetailMetrics:
    """Return detailed metrics for a single day.

    Shows individual sessions, tool calls, and schedule runs
    that occurred on the specified date.
    """
    session_store = _get_session_store(request)
    schedule_store = _get_schedule_store(request)

    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD.",
        )

    day_start = target_date
    day_end = target_date + timedelta(days=1)

    # Fetch sessions for that day
    all_sessions = await session_store.list_sessions(since=day_start, limit=500)
    day_sessions = [
        s for s in all_sessions
        if s.created_at < day_end
    ]

    # Build session rows
    session_rows: list[dict[str, Any]] = []
    durations: list[float] = []
    total_input = 0
    total_output = 0
    total_tokens = 0
    total_cost = 0.0
    completed = 0
    failed = 0

    for s in day_sessions:
        status_str = s.status.value if hasattr(s.status, "value") else str(s.status)
        if status_str == "completed":
            completed += 1
        elif status_str == "failed":
            failed += 1

        m = s.metrics
        dur = m.total_duration_seconds if m else 0.0
        inp = (m.input_tokens or 0) if m else 0
        out = (m.output_tokens or 0) if m else 0
        tok = (m.total_tokens_used or 0) if m else 0
        cost = (m.cost or 0.0) if m else 0.0
        tc = (m.total_tool_calls or 0) if m else 0

        total_input += inp
        total_output += out
        total_tokens += tok
        total_cost += cost
        if dur > 0:
            durations.append(dur)

        session_rows.append({
            "id": s.id,
            "instruction": (s.instruction or "")[:120],
            "status": status_str,
            "duration": round(dur, 2),
            "tool_calls": tc,
            "tokens": tok,
            "cost": round(cost, 4),
            "created_at": s.created_at.isoformat(),
        })

    # Build tool call rows from conversation turns
    tool_rows: list[dict[str, Any]] = []
    total_tool_calls = 0
    total_tool_errors = 0

    for s in day_sessions[:100]:
        try:
            turns = await session_store.get_turns(s.id)
        except Exception:
            continue
        for turn in turns:
            if turn.role == "tool" and turn.tool_call:
                tc = turn.tool_call
                total_tool_calls += 1
                is_error = tc.status == "error"
                if is_error:
                    total_tool_errors += 1
                tool_rows.append({
                    "tool_name": tc.tool_name,
                    "status": tc.status or "unknown",
                    "duration_ms": tc.duration_ms or 0,
                    "session_id": s.id,
                    "error": tc.error if is_error else None,
                })

    # Build schedule run rows
    run_rows: list[dict[str, Any]] = []
    # Fetch schedules for name mapping
    all_schedules = await schedule_store.list_schedules(limit=200)
    sched_names = {s.id: s.name for s in all_schedules}

    recent_runs = await schedule_store.get_recent_runs(limit=500)
    for run in recent_runs:
        run_day = run.triggered_at.strftime("%Y-%m-%d")
        if run_day == date:
            run_rows.append({
                "schedule_id": run.schedule_id,
                "name": sched_names.get(run.schedule_id, run.schedule_id[:8]),
                "session_id": run.session_id,
                "status": run.status,
                "duration": round(run.duration_seconds, 2) if run.duration_seconds else None,
                "trigger_reason": run.trigger_reason,
            })

    avg_dur = round(sum(durations) / len(durations), 2) if durations else 0.0
    min_dur = round(min(durations), 2) if durations else 0.0
    max_dur = round(max(durations), 2) if durations else 0.0

    return DailyDetailMetrics(
        date=date,
        sessions=session_rows,
        session_count=len(day_sessions),
        completed_count=completed,
        failed_count=failed,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_tokens,
        total_cost=round(total_cost, 4),
        avg_duration=avg_dur,
        min_duration=min_dur,
        max_duration=max_dur,
        tool_calls=tool_rows,
        total_tool_calls=total_tool_calls,
        total_tool_errors=total_tool_errors,
        schedule_runs=run_rows,
        total_schedule_runs=len(run_rows),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fill_days(
    day_data: dict[str, dict[str, Any]],
    days: int,
    today: Any,
    template: dict[str, Any],
) -> list[dict[str, Any]]:
    """Fill missing days with a template dict, returning oldest-first list."""
    result: list[dict[str, Any]] = []
    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.isoformat()
        if date_str in day_data:
            entry = {"date": date_str, **day_data[date_str]}
        else:
            entry = {"date": date_str, **template}
        result.append(entry)
    result.reverse()
    return result


def _build_session_metrics(
    sessions: list[Any],
    days: int,
    today: Any,
) -> SessionMetricsDetail:
    """Aggregate session-level metrics into daily tables."""

    # Per-day accumulators
    token_days: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"input_tokens": 0, "output_tokens": 0, "cache_tokens": 0, "total_tokens": 0, "cost": 0.0},
    )
    duration_days: dict[str, dict[str, list]] = defaultdict(
        lambda: {"durations": [], "session_count": 0},
    )
    status_days: dict[str, dict[str, int]] = defaultdict(
        lambda: {"active": 0, "completed": 0, "failed": 0, "cancelled": 0},
    )
    docs_days: dict[str, dict[str, int]] = defaultdict(
        lambda: {"documents_processed": 0, "outputs_produced": 0, "errors": 0},
    )

    total_input = 0
    total_output = 0
    total_cache = 0
    total_cost = 0.0
    all_durations: list[float] = []

    for session in sessions:
        day_key = session.created_at.strftime("%Y-%m-%d")

        # Status
        status_str = session.status.value if hasattr(session.status, "value") else str(session.status)
        if status_str in status_days[day_key]:
            status_days[day_key][status_str] += 1

        if session.metrics:
            m = session.metrics
            # Tokens
            inp = m.input_tokens or 0
            out = m.output_tokens or 0
            cache = (m.cache_read_tokens or 0) + (m.cache_write_tokens or 0)
            cost = m.cost or 0.0

            token_days[day_key]["input_tokens"] += inp
            token_days[day_key]["output_tokens"] += out
            token_days[day_key]["cache_tokens"] += cache
            token_days[day_key]["total_tokens"] += m.total_tokens_used or 0
            token_days[day_key]["cost"] += cost

            total_input += inp
            total_output += out
            total_cache += cache
            total_cost += cost

            # Duration
            if m.total_duration_seconds > 0:
                duration_days[day_key]["durations"].append(m.total_duration_seconds)
                all_durations.append(m.total_duration_seconds)
            duration_days[day_key]["session_count"] += 1

            # Documents
            docs_days[day_key]["documents_processed"] += m.documents_processed or 0
            docs_days[day_key]["outputs_produced"] += m.outputs_produced or 0
            docs_days[day_key]["errors"] += m.errors_encountered or 0

    # Build token_usage_by_day
    token_template = {"input_tokens": 0, "output_tokens": 0, "cache_tokens": 0, "total_tokens": 0, "cost": 0.0}
    token_usage_by_day = _fill_days(token_days, days, today, token_template)

    # Build duration_by_day
    duration_by_day_raw: dict[str, dict[str, Any]] = {}
    for day_key, data in duration_days.items():
        durations = data["durations"]
        duration_by_day_raw[day_key] = {
            "avg_duration": round(sum(durations) / len(durations), 2) if durations else 0.0,
            "min_duration": round(min(durations), 2) if durations else 0.0,
            "max_duration": round(max(durations), 2) if durations else 0.0,
            "session_count": data["session_count"],
        }
    duration_template = {"avg_duration": 0.0, "min_duration": 0.0, "max_duration": 0.0, "session_count": 0}
    duration_by_day = _fill_days(duration_by_day_raw, days, today, duration_template)

    # Build status_by_day
    status_template = {"active": 0, "completed": 0, "failed": 0, "cancelled": 0}
    status_by_day = _fill_days(status_days, days, today, status_template)

    # Build documents_by_day
    docs_template = {"documents_processed": 0, "outputs_produced": 0, "errors": 0}
    documents_by_day = _fill_days(docs_days, days, today, docs_template)

    avg_duration = round(sum(all_durations) / len(all_durations), 2) if all_durations else 0.0

    return SessionMetricsDetail(
        token_usage_by_day=token_usage_by_day,
        duration_by_day=duration_by_day,
        status_by_day=status_by_day,
        documents_by_day=documents_by_day,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cache_tokens=total_cache,
        total_cost=round(total_cost, 4),
        avg_duration=avg_duration,
    )


async def _build_tool_call_metrics(
    session_store: Any,
    sessions: list[Any],
    days: int,
    today: Any,
) -> ToolCallMetricsDetail:
    """Aggregate tool call metrics from conversation turns."""

    tool_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "success": 0, "error": 0, "durations": [], "last_error": None},
    )
    calls_by_day: Counter[str] = Counter()
    total_calls = 0
    total_errors = 0

    # Query tool turns from recent sessions (limit to avoid heavy queries)
    for session in sessions[:200]:
        try:
            turns = await session_store.get_turns(session.id)
        except Exception:
            continue

        for turn in turns:
            if turn.role == "tool" and turn.tool_call:
                tc = turn.tool_call
                tool_name = tc.tool_name
                tool_stats[tool_name]["total"] += 1
                total_calls += 1

                day_key = turn.timestamp.strftime("%Y-%m-%d") if hasattr(turn.timestamp, "strftime") else str(turn.timestamp)[:10]
                calls_by_day[day_key] += 1

                if tc.status == "success":
                    tool_stats[tool_name]["success"] += 1
                elif tc.status == "error":
                    tool_stats[tool_name]["error"] += 1
                    total_errors += 1
                    tool_stats[tool_name]["last_error"] = tc.error

                if tc.duration_ms is not None and tc.duration_ms > 0:
                    tool_stats[tool_name]["durations"].append(tc.duration_ms)

    # Build tool_usage table (sorted by total calls)
    tool_usage = sorted(
        [
            {
                "tool_name": name,
                "total_calls": stats["total"],
                "success_count": stats["success"],
                "error_count": stats["error"],
                "avg_duration_ms": round(sum(stats["durations"]) / len(stats["durations"])) if stats["durations"] else 0,
            }
            for name, stats in tool_stats.items()
        ],
        key=lambda x: x["total_calls"],
        reverse=True,
    )

    # Build tool_calls_by_day
    day_data = {day: {"count": count} for day, count in calls_by_day.items()}
    tool_calls_by_day = _fill_days(day_data, days, today, {"count": 0})

    # Build tool_errors table (only tools with errors)
    tool_errors = sorted(
        [
            {
                "tool_name": name,
                "error_count": stats["error"],
                "last_error": stats["last_error"],
            }
            for name, stats in tool_stats.items()
            if stats["error"] > 0
        ],
        key=lambda x: x["error_count"],
        reverse=True,
    )

    # Build tool_duration table
    tool_duration = sorted(
        [
            {
                "tool_name": name,
                "avg_duration_ms": round(sum(stats["durations"]) / len(stats["durations"])) if stats["durations"] else 0,
                "min_duration_ms": min(stats["durations"]) if stats["durations"] else 0,
                "max_duration_ms": max(stats["durations"]) if stats["durations"] else 0,
            }
            for name, stats in tool_stats.items()
            if stats["durations"]
        ],
        key=lambda x: x["avg_duration_ms"],
        reverse=True,
    )

    return ToolCallMetricsDetail(
        tool_usage=tool_usage,
        tool_calls_by_day=tool_calls_by_day,
        tool_errors=tool_errors,
        tool_duration=tool_duration,
        total_tool_calls=total_calls,
        total_tool_errors=total_errors,
    )


async def _build_schedule_metrics(
    schedule_store: Any,
    days: int,
    today: Any,
    since: datetime,
) -> ScheduleMetricsDetail:
    """Aggregate schedule-level metrics."""

    all_schedules = await schedule_store.list_schedules(limit=100)
    recent_runs = await schedule_store.get_recent_runs(limit=500)

    # Schedule overview
    schedule_overview = [
        {
            "name": s.name,
            "status": s.status,
            "total_runs": s.total_runs,
            "success_rate": round(
                ((s.total_runs - s.consecutive_failures) / s.total_runs) * 100, 1,
            ) if s.total_runs > 0 else 0.0,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
        }
        for s in all_schedules
    ]

    # Runs by day
    runs_day: dict[str, dict[str, int]] = defaultdict(
        lambda: {"runs": 0, "successes": 0, "failures": 0},
    )
    total_runs = 0
    total_successes = 0
    total_failures = 0

    for run in recent_runs:
        day_key = run.triggered_at.strftime("%Y-%m-%d")
        runs_day[day_key]["runs"] += 1
        total_runs += 1
        if run.status == "completed":
            runs_day[day_key]["successes"] += 1
            total_successes += 1
        elif run.status == "failed":
            runs_day[day_key]["failures"] += 1
            total_failures += 1

    runs_template = {"runs": 0, "successes": 0, "failures": 0}
    runs_by_day = _fill_days(runs_day, days, today, runs_template)

    # Schedule duration (from recent runs)
    sched_durations: dict[str, list[float]] = defaultdict(list)
    for run in recent_runs:
        if run.duration_seconds and run.duration_seconds > 0:
            sched_durations[run.schedule_id].append(run.duration_seconds)

    # Map schedule_id to name
    sched_names = {s.id: s.name for s in all_schedules}

    schedule_duration = sorted(
        [
            {
                "name": sched_names.get(sid, sid[:8]),
                "avg_duration": round(sum(durs) / len(durs), 2),
                "min_duration": round(min(durs), 2),
                "max_duration": round(max(durs), 2),
            }
            for sid, durs in sched_durations.items()
            if durs
        ],
        key=lambda x: x["avg_duration"],
        reverse=True,
    )

    # Schedule reliability
    schedule_reliability = [
        {
            "name": s.name,
            "consecutive_failures": s.consecutive_failures,
            "success_rate": round(
                ((s.total_runs - s.consecutive_failures) / s.total_runs) * 100, 1,
            ) if s.total_runs > 0 else 0.0,
            "total_runs": s.total_runs,
        }
        for s in all_schedules
        if s.total_runs > 0
    ]

    return ScheduleMetricsDetail(
        schedule_overview=schedule_overview,
        runs_by_day=runs_by_day,
        schedule_duration=schedule_duration,
        schedule_reliability=schedule_reliability,
        total_runs=total_runs,
        total_successes=total_successes,
        total_failures=total_failures,
    )


def _aggregate_sessions_by_day(
    sessions: list[Any],
    days: int,
) -> list[dict[str, Any]]:
    """Aggregate sessions into daily counts for the last N days."""

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

"""Unit tests for Phase 5 — Schedule Run Tracker (schedule_run_tracker.py).

Tests the fire-and-track callback, session completion polling logic,
and cleanup.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schedule_models import (
    ScheduleRecord,
    ScheduleRunRecord,
    TriggerConfig,
    TriggerType,
)
from app.models.session_models import SessionMetrics, SessionRecord, SessionStatus
from app.services.schedule_run_tracker import ScheduleRunTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_schedule(
    *,
    schedule_id: str = "sched-001",
    name: str = "Test Schedule",
) -> ScheduleRecord:
    return ScheduleRecord(
        id=schedule_id,
        name=name,
        instruction="Process documents",
        trigger=TriggerConfig(type=TriggerType.CRON, cron="0 6 * * *"),
        status="active",
    )


def _make_session(
    *,
    session_id: str = "sess-001",
    status: SessionStatus = SessionStatus.COMPLETED,
    summary: str | None = "Done",
) -> SessionRecord:
    now = datetime.now(timezone.utc)
    return SessionRecord(
        id=session_id,
        created_at=now,
        updated_at=now,
        status=status,
        model="gpt-4.1",
        instruction="Process documents",
        summary=summary,
        metrics=SessionMetrics(
            total_tool_calls=5,
            documents_processed=3,
            total_duration_seconds=60.0,
        ),
    )


def _make_run(
    *,
    run_id: str = "run-001",
    schedule_id: str = "sched-001",
    session_id: str = "sess-001",
) -> ScheduleRunRecord:
    return ScheduleRunRecord(
        id=run_id,
        schedule_id=schedule_id,
        session_id=session_id,
        triggered_at=datetime.now(timezone.utc),
        trigger_reason="cron",
        status="running",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_agent_service() -> AsyncMock:
    svc = AsyncMock()
    svc.create_and_run.return_value = "sess-001"
    return svc


@pytest.fixture()
def mock_schedule_store() -> AsyncMock:
    store = AsyncMock()
    store.list_runs.return_value = [_make_run()]
    store.complete_run.return_value = None
    store.reset_consecutive_failures.return_value = None
    store.increment_consecutive_failures.return_value = _make_schedule()
    store.get_schedule.return_value = _make_schedule()
    store.save_schedule.return_value = None
    return store


@pytest.fixture()
def mock_session_store() -> AsyncMock:
    store = AsyncMock()
    store.get_session.return_value = _make_session()
    return store


@pytest.fixture()
def tracker(
    mock_agent_service: AsyncMock,
    mock_schedule_store: AsyncMock,
    mock_session_store: AsyncMock,
) -> ScheduleRunTracker:
    return ScheduleRunTracker(
        agent_service=mock_agent_service,
        schedule_store=mock_schedule_store,
        session_store=mock_session_store,
    )


# ---------------------------------------------------------------------------
# Tests — fire_and_track
# ---------------------------------------------------------------------------


class TestFireAndTrack:
    """Tests for the fire_and_track callback."""

    @pytest.mark.asyncio
    async def test_creates_session_and_returns_id(
        self,
        tracker: ScheduleRunTracker,
        mock_agent_service: AsyncMock,
    ) -> None:
        schedule = _make_schedule()
        session_id = await tracker.fire_and_track(schedule, "cron")

        assert session_id == "sess-001"
        mock_agent_service.create_and_run.assert_awaited_once()

        # Should have a metadata arg with schedule_id
        call_kwargs = mock_agent_service.create_and_run.call_args.kwargs
        metadata = call_kwargs.get("metadata", {})
        assert metadata["schedule_id"] == "sched-001"
        assert metadata["trigger_reason"] == "cron"

    @pytest.mark.asyncio
    async def test_starts_poll_task(
        self,
        tracker: ScheduleRunTracker,
    ) -> None:
        schedule = _make_schedule()
        await tracker.fire_and_track(schedule, "cron")

        # A poll task should have been created
        assert len(tracker._poll_tasks) == 1
        assert "sess-001" in tracker._poll_tasks

        # Clean up
        await tracker.cancel_all_tracking()

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(
        self,
        tracker: ScheduleRunTracker,
        mock_agent_service: AsyncMock,
    ) -> None:
        mock_agent_service.create_and_run.side_effect = RuntimeError("Boom")

        schedule = _make_schedule()
        result = await tracker.fire_and_track(schedule, "cron")
        assert result is None


# ---------------------------------------------------------------------------
# Tests — Session Completion Handling
# ---------------------------------------------------------------------------


class TestOnSessionComplete:
    """Tests for _on_session_complete method."""

    @pytest.mark.asyncio
    async def test_successful_completion(
        self,
        tracker: ScheduleRunTracker,
        mock_schedule_store: AsyncMock,
    ) -> None:
        metrics = SimpleNamespace(
            total_duration_seconds=60.0,
            total_tool_calls=5,
            documents_processed=3,
            errors_encountered=0,
        )

        await tracker._on_session_complete(
            session_id="sess-001",
            schedule_id="sched-001",
            status=SessionStatus.COMPLETED,
            summary="Done",
            metrics=metrics,
        )

        mock_schedule_store.complete_run.assert_awaited_once()
        mock_schedule_store.reset_consecutive_failures.assert_awaited_once_with(
            "sched-001",
        )

    @pytest.mark.asyncio
    async def test_failed_completion(
        self,
        tracker: ScheduleRunTracker,
        mock_schedule_store: AsyncMock,
    ) -> None:
        await tracker._on_session_complete(
            session_id="sess-001",
            schedule_id="sched-001",
            status=SessionStatus.FAILED,
            summary="Error occurred",
            metrics=None,
        )

        mock_schedule_store.increment_consecutive_failures.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_matching_run(
        self,
        tracker: ScheduleRunTracker,
        mock_schedule_store: AsyncMock,
    ) -> None:
        """If no run record matches, should not crash."""
        mock_schedule_store.list_runs.return_value = []

        await tracker._on_session_complete(
            session_id="sess-999",
            schedule_id="sched-001",
            status=SessionStatus.COMPLETED,
            summary="Done",
            metrics=None,
        )
        # complete_run should NOT be called
        mock_schedule_store.complete_run.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests — Cleanup
# ---------------------------------------------------------------------------


class TestTrackerCleanup:
    """Tests for cancel_all_tracking."""

    @pytest.mark.asyncio
    async def test_cancel_clears_tasks(
        self,
        tracker: ScheduleRunTracker,
    ) -> None:
        schedule = _make_schedule()
        await tracker.fire_and_track(schedule, "cron")
        assert len(tracker._poll_tasks) == 1

        await tracker.cancel_all_tracking()
        assert len(tracker._poll_tasks) == 0

    @pytest.mark.asyncio
    async def test_cancel_empty_is_noop(
        self,
        tracker: ScheduleRunTracker,
    ) -> None:
        await tracker.cancel_all_tracking()
        assert len(tracker._poll_tasks) == 0

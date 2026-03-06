"""Unit tests for Phase 5 — Scheduling Engine (scheduling_engine.py).

Tests APScheduler integration, job registration, fire dispatch,
event/webhook handling, and schedule lifecycle management.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schedule_models import (
    ScheduleRecord,
    ScheduleRunRecord,
    TriggerConfig,
    TriggerType,
)
from app.services.scheduling_engine import SchedulingEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_schedule(
    *,
    schedule_id: str = "sched-001",
    name: str = "Test",
    trigger_type: TriggerType = TriggerType.CRON,
    cron: str = "0 6 * * *",
    interval_minutes: int | None = None,
    status: str = "active",
    webhook_id: str | None = None,
    event_source: str | None = None,
) -> ScheduleRecord:
    trigger_kwargs: dict = {"type": trigger_type}
    if trigger_type == TriggerType.CRON:
        trigger_kwargs["cron"] = cron
    elif trigger_type == TriggerType.INTERVAL:
        trigger_kwargs["interval_minutes"] = interval_minutes or 60
    elif trigger_type == TriggerType.EVENT:
        trigger_kwargs["event_source"] = event_source or "blob:vendor-inbox"
    return ScheduleRecord(
        id=schedule_id,
        name=name,
        instruction="Do something",
        trigger=TriggerConfig(**trigger_kwargs),
        status=status,
        webhook_id=webhook_id,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_store() -> AsyncMock:
    """Mock ScheduleStore."""
    store = AsyncMock()
    store.get_active_schedules.return_value = []
    store.save_schedule.return_value = None
    store.save_run.return_value = None
    store.update_schedule_last_run.return_value = None
    store.increment_consecutive_failures.return_value = _make_schedule()
    return store


@pytest.fixture()
def mock_fire_callback() -> AsyncMock:
    """Mock fire callback that returns a session ID."""
    callback = AsyncMock()
    callback.return_value = "sess-001"
    return callback


@pytest.fixture()
def engine(mock_store: AsyncMock, mock_fire_callback: AsyncMock) -> SchedulingEngine:
    return SchedulingEngine(
        schedule_store=mock_store,
        fire_callback=mock_fire_callback,
        misfire_grace_time=60,
    )


# ---------------------------------------------------------------------------
# Tests — Lifecycle
# ---------------------------------------------------------------------------


class TestSchedulingEngineLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_scheduler(
        self, engine: SchedulingEngine,
    ) -> None:
        assert not engine.is_running
        await engine.start()
        assert engine.is_running
        assert engine._scheduler is not None
        await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_scheduler(
        self, engine: SchedulingEngine,
    ) -> None:
        await engine.start()
        await engine.stop()
        assert not engine.is_running
        assert engine._scheduler is None

    @pytest.mark.asyncio
    async def test_double_start_warns(
        self, engine: SchedulingEngine,
    ) -> None:
        await engine.start()
        await engine.start()  # Should not crash
        assert engine.is_running
        await engine.stop()

    @pytest.mark.asyncio
    async def test_start_loads_active_schedules(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        schedule = _make_schedule()
        mock_store.get_active_schedules.return_value = [schedule]

        await engine.start()
        mock_store.get_active_schedules.assert_awaited_once()

        # Should have registered one APScheduler job
        jobs = engine._scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "schedule:sched-001"

        await engine.stop()

    @pytest.mark.asyncio
    async def test_start_registers_interval_schedules(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        schedule = _make_schedule(
            schedule_id="int-001",
            trigger_type=TriggerType.INTERVAL,
            interval_minutes=30,
        )
        mock_store.get_active_schedules.return_value = [schedule]

        await engine.start()
        jobs = engine._scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "schedule:int-001"

        await engine.stop()

    @pytest.mark.asyncio
    async def test_start_skips_event_webhook_schedules(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        """Event/webhook triggers should NOT be registered with APScheduler."""
        event_sched = _make_schedule(
            schedule_id="evt-001",
            trigger_type=TriggerType.EVENT,
            event_source="blob:inbox",
        )
        webhook_sched = _make_schedule(
            schedule_id="wh-001",
            trigger_type=TriggerType.WEBHOOK,
        )
        mock_store.get_active_schedules.return_value = [event_sched, webhook_sched]

        await engine.start()
        jobs = engine._scheduler.get_jobs()
        assert len(jobs) == 0  # Neither should be registered

        await engine.stop()


# ---------------------------------------------------------------------------
# Tests — Fire Schedule
# ---------------------------------------------------------------------------


class TestFireSchedule:
    """Tests for fire_schedule (unified trigger entry point)."""

    @pytest.mark.asyncio
    async def test_fire_creates_run_and_calls_callback(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
        mock_fire_callback: AsyncMock,
    ) -> None:
        schedule = _make_schedule()
        mock_store.get_schedule.return_value = schedule

        session_id = await engine.fire_schedule("sched-001", "cron")
        assert session_id == "sess-001"

        mock_fire_callback.assert_awaited_once_with(schedule, "cron")
        mock_store.save_run.assert_awaited_once()
        mock_store.update_schedule_last_run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fire_skips_paused_schedule(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
        mock_fire_callback: AsyncMock,
    ) -> None:
        schedule = _make_schedule(status="paused")
        mock_store.get_schedule.return_value = schedule

        result = await engine.fire_schedule("sched-001", "manual")
        assert result is None
        mock_fire_callback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fire_callback_failure_records_failed_run(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
        mock_fire_callback: AsyncMock,
    ) -> None:
        schedule = _make_schedule()
        mock_store.get_schedule.return_value = schedule
        mock_fire_callback.side_effect = RuntimeError("Agent failed")

        result = await engine.fire_schedule("sched-001", "cron")
        assert result is None

        # Should still save a failed run record
        mock_store.save_run.assert_awaited_once()
        run_arg = mock_store.save_run.call_args[0][0]
        assert run_arg.status == "failed"
        mock_store.increment_consecutive_failures.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fire_callback_returns_none(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
        mock_fire_callback: AsyncMock,
    ) -> None:
        schedule = _make_schedule()
        mock_store.get_schedule.return_value = schedule
        mock_fire_callback.return_value = None

        result = await engine.fire_schedule("sched-001", "cron")
        assert result is None

    @pytest.mark.asyncio
    async def test_fire_schedule_not_found(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        from app.models.exceptions import ScheduleNotFoundError

        mock_store.get_schedule.side_effect = ScheduleNotFoundError("missing")
        result = await engine.fire_schedule("missing", "cron")
        assert result is None


# ---------------------------------------------------------------------------
# Tests — Schedule Management
# ---------------------------------------------------------------------------


class TestScheduleManagement:
    """Tests for add, update, pause, resume, delete schedule."""

    @pytest.mark.asyncio
    async def test_add_cron_schedule(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        await engine.start()
        schedule = _make_schedule()

        await engine.add_schedule(schedule)

        assert engine._scheduler.get_job("schedule:sched-001") is not None
        await engine.stop()

    @pytest.mark.asyncio
    async def test_add_event_schedule_no_apscheduler_job(
        self,
        engine: SchedulingEngine,
    ) -> None:
        await engine.start()
        schedule = _make_schedule(
            trigger_type=TriggerType.EVENT,
            event_source="blob:inbox",
        )

        await engine.add_schedule(schedule)

        # Event triggers are not added to APScheduler
        assert engine._scheduler.get_job("schedule:sched-001") is None
        await engine.stop()

    @pytest.mark.asyncio
    async def test_pause_schedule(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        await engine.start()

        paused = _make_schedule(status="paused")
        mock_store.update_schedule_status.return_value = paused

        result = await engine.pause_schedule("sched-001")
        assert result.status == "paused"
        mock_store.update_schedule_status.assert_awaited_once_with(
            "sched-001", "paused",
        )
        await engine.stop()

    @pytest.mark.asyncio
    async def test_resume_schedule(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        await engine.start()

        active = _make_schedule(status="active")
        mock_store.update_schedule_status.return_value = active

        result = await engine.resume_schedule("sched-001")
        assert result.status == "active"

        # Should re-register with APScheduler
        assert engine._scheduler.get_job("schedule:sched-001") is not None
        await engine.stop()

    @pytest.mark.asyncio
    async def test_delete_schedule(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        await engine.start()
        await engine.delete_schedule("sched-001")
        mock_store.delete_schedule.assert_awaited_once_with("sched-001")
        await engine.stop()


# ---------------------------------------------------------------------------
# Tests — Event Handling
# ---------------------------------------------------------------------------


class TestEventHandling:
    """Tests for handle_event (Event Grid dispatch)."""

    @pytest.mark.asyncio
    async def test_handle_event_matches_source(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
        mock_fire_callback: AsyncMock,
    ) -> None:
        # Setup: event-type schedule matching "blob:vendor-inbox"
        schedule = _make_schedule(
            schedule_id="evt-001",
            trigger_type=TriggerType.EVENT,
            event_source="blob:vendor-inbox",
        )
        mock_store.get_schedules_by_trigger_type.return_value = [schedule]
        mock_store.get_schedule.return_value = schedule

        results = await engine.handle_event(
            event_source="blob:vendor-inbox/file.pdf",
            event_data={"subject": "blob:vendor-inbox/file.pdf"},
        )
        assert len(results) == 1
        assert results[0] == "sess-001"

    @pytest.mark.asyncio
    async def test_handle_event_no_match(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        schedule = _make_schedule(
            trigger_type=TriggerType.EVENT,
            event_source="blob:other-container",
        )
        mock_store.get_schedules_by_trigger_type.return_value = [schedule]

        results = await engine.handle_event(
            event_source="blob:vendor-inbox/file.pdf",
            event_data={},
        )
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Tests — Webhook Handling
# ---------------------------------------------------------------------------


class TestWebhookHandling:
    """Tests for handle_webhook."""

    @pytest.mark.asyncio
    async def test_handle_webhook_fires_matching(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
        mock_fire_callback: AsyncMock,
    ) -> None:
        schedule = _make_schedule(
            trigger_type=TriggerType.WEBHOOK,
            webhook_id="wh_abc123",
        )
        mock_store.get_schedules_by_trigger_type.return_value = [schedule]
        mock_store.get_schedule.return_value = schedule

        result = await engine.handle_webhook("wh_abc123", {"data": "test"})
        assert result == "sess-001"

    @pytest.mark.asyncio
    async def test_handle_webhook_no_match(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        mock_store.get_schedules_by_trigger_type.return_value = []

        result = await engine.handle_webhook("wh_nonexistent", {})
        assert result is None


# ---------------------------------------------------------------------------
# Tests — Upcoming Runs
# ---------------------------------------------------------------------------


class TestUpcomingRuns:
    """Tests for get_upcoming_runs."""

    @pytest.mark.asyncio
    async def test_upcoming_runs_empty(
        self, engine: SchedulingEngine,
    ) -> None:
        """No scheduler -> empty list."""
        result = engine.get_upcoming_runs()
        assert result == []

    @pytest.mark.asyncio
    async def test_upcoming_runs_with_jobs(
        self,
        engine: SchedulingEngine,
        mock_store: AsyncMock,
    ) -> None:
        schedule = _make_schedule()
        mock_store.get_active_schedules.return_value = [schedule]

        await engine.start()
        result = engine.get_upcoming_runs()
        assert len(result) >= 1
        assert result[0]["schedule_id"] == "sched-001"
        assert "next_run_at" in result[0]
        await engine.stop()


# ---------------------------------------------------------------------------
# Tests — Event Matching
# ---------------------------------------------------------------------------


class TestEventMatching:
    """Tests for _event_matches static method."""

    def test_exact_match(self) -> None:
        assert SchedulingEngine._event_matches(
            "blob:vendor-inbox", None, "blob:vendor-inbox", {},
        ) is True

    def test_prefix_match(self) -> None:
        assert SchedulingEngine._event_matches(
            "blob:vendor-inbox", None, "blob:vendor-inbox/file.pdf", {},
        ) is True

    def test_no_match(self) -> None:
        assert SchedulingEngine._event_matches(
            "blob:other", None, "blob:vendor-inbox", {},
        ) is False

    def test_filter_match(self) -> None:
        assert SchedulingEngine._event_matches(
            "blob:inbox", "*.pdf",
            "blob:inbox/file.pdf",
            {"subject": "blob:inbox/file.pdf"},
        ) is True

    def test_filter_no_match(self) -> None:
        assert SchedulingEngine._event_matches(
            "blob:inbox", "*.pdf",
            "blob:inbox/file.csv",
            {"subject": "blob:inbox/file.csv"},
        ) is False

"""Unit tests for Phase 5 — Schedule Models (schedule_models.py).

Tests TriggerConfig validation, ScheduleRecord serialization,
CreateScheduleRequest/UpdateScheduleRequest validation, and
DashboardMetrics/ActivityEvent models.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.schedule_models import (
    ActivityEvent,
    CreateScheduleRequest,
    DashboardMetrics,
    ScheduleRecord,
    ScheduleRunRecord,
    TriggerConfig,
    TriggerType,
    UpdateScheduleRequest,
)


# -----------------------------------------------------------------------
# TriggerType Enum
# -----------------------------------------------------------------------


class TestTriggerType:
    """Tests for the TriggerType enum."""

    def test_cron_value(self) -> None:
        assert TriggerType.CRON == "cron"
        assert TriggerType.CRON.value == "cron"

    def test_interval_value(self) -> None:
        assert TriggerType.INTERVAL == "interval"

    def test_event_value(self) -> None:
        assert TriggerType.EVENT == "event"

    def test_webhook_value(self) -> None:
        assert TriggerType.WEBHOOK == "webhook"

    def test_string_coercion(self) -> None:
        assert str(TriggerType.CRON) == "TriggerType.CRON" or TriggerType.CRON == "cron"


# -----------------------------------------------------------------------
# TriggerConfig Validation
# -----------------------------------------------------------------------


class TestTriggerConfig:
    """Tests for TriggerConfig model validation."""

    def test_valid_cron_trigger(self) -> None:
        cfg = TriggerConfig(type=TriggerType.CRON, cron="0 6 * * 1-5")
        assert cfg.type == TriggerType.CRON
        assert cfg.cron == "0 6 * * 1-5"
        assert cfg.timezone == "UTC"

    def test_cron_trigger_with_timezone(self) -> None:
        cfg = TriggerConfig(
            type=TriggerType.CRON,
            cron="0 6 * * *",
            timezone="America/New_York",
        )
        assert cfg.timezone == "America/New_York"

    def test_cron_trigger_missing_expression(self) -> None:
        with pytest.raises(ValidationError, match="cron"):
            TriggerConfig(type=TriggerType.CRON)

    def test_cron_trigger_empty_expression(self) -> None:
        with pytest.raises(ValidationError, match="cron"):
            TriggerConfig(type=TriggerType.CRON, cron="")

    def test_cron_trigger_invalid_expression(self) -> None:
        """croniter should reject invalid cron expressions."""
        with pytest.raises(ValidationError, match="[Ii]nvalid cron"):
            TriggerConfig(type=TriggerType.CRON, cron="not-a-cron")

    def test_valid_interval_trigger(self) -> None:
        cfg = TriggerConfig(type=TriggerType.INTERVAL, interval_minutes=30)
        assert cfg.interval_minutes == 30

    def test_interval_trigger_missing_minutes(self) -> None:
        with pytest.raises(ValidationError, match="interval_minutes"):
            TriggerConfig(type=TriggerType.INTERVAL)

    def test_interval_trigger_zero_minutes(self) -> None:
        with pytest.raises(ValidationError, match="interval_minutes"):
            TriggerConfig(type=TriggerType.INTERVAL, interval_minutes=0)

    def test_interval_trigger_negative_minutes(self) -> None:
        with pytest.raises(ValidationError, match="interval_minutes"):
            TriggerConfig(type=TriggerType.INTERVAL, interval_minutes=-5)

    def test_valid_event_trigger(self) -> None:
        cfg = TriggerConfig(
            type=TriggerType.EVENT,
            event_source="blob:vendor-inbox",
        )
        assert cfg.event_source == "blob:vendor-inbox"

    def test_event_trigger_with_filter(self) -> None:
        cfg = TriggerConfig(
            type=TriggerType.EVENT,
            event_source="blob:vendor-inbox",
            event_filter="*.pdf",
        )
        assert cfg.event_filter == "*.pdf"

    def test_event_trigger_missing_source(self) -> None:
        with pytest.raises(ValidationError, match="event_source"):
            TriggerConfig(type=TriggerType.EVENT)

    def test_valid_webhook_trigger(self) -> None:
        """Webhook trigger has no required fields beyond type."""
        cfg = TriggerConfig(type=TriggerType.WEBHOOK)
        assert cfg.type == TriggerType.WEBHOOK

    def test_webhook_trigger_with_secret(self) -> None:
        cfg = TriggerConfig(
            type=TriggerType.WEBHOOK,
            webhook_secret="my-secret-key",
        )
        assert cfg.webhook_secret == "my-secret-key"

    def test_json_roundtrip(self) -> None:
        cfg = TriggerConfig(type=TriggerType.CRON, cron="*/5 * * * *")
        data = cfg.model_dump(mode="json")
        assert data["type"] == "cron"
        loaded = TriggerConfig.model_validate(data)
        assert loaded == cfg


# -----------------------------------------------------------------------
# ScheduleRecord
# -----------------------------------------------------------------------


class TestScheduleRecord:
    """Tests for ScheduleRecord creation and serialization."""

    @pytest.fixture()
    def sample_record(self) -> ScheduleRecord:
        return ScheduleRecord(
            id="sched-001",
            name="Daily Vendor Inbox",
            instruction="Process all new PDFs in vendor-inbox",
            trigger=TriggerConfig(type=TriggerType.CRON, cron="0 6 * * *"),
            tags=["vendor", "pdf"],
            created_by="user-abc",
        )

    def test_default_status(self, sample_record: ScheduleRecord) -> None:
        assert sample_record.status == "active"

    def test_default_run_counts(self, sample_record: ScheduleRecord) -> None:
        assert sample_record.total_runs == 0
        assert sample_record.consecutive_failures == 0

    def test_created_at_auto_set(self, sample_record: ScheduleRecord) -> None:
        assert sample_record.created_at is not None
        assert isinstance(sample_record.created_at, datetime)

    def test_tags_stored(self, sample_record: ScheduleRecord) -> None:
        assert sample_record.tags == ["vendor", "pdf"]

    def test_json_safe_dump(self, sample_record: ScheduleRecord) -> None:
        data = sample_record.model_dump_json_safe()
        assert isinstance(data, dict)
        assert data["id"] == "sched-001"
        assert data["trigger"]["type"] == "cron"
        # datetimes should be ISO strings
        assert isinstance(data["created_at"], str)

    def test_webhook_fields_default_none(self, sample_record: ScheduleRecord) -> None:
        assert sample_record.webhook_id is None
        assert sample_record.webhook_url is None

    def test_webhook_fields_populated(self) -> None:
        rec = ScheduleRecord(
            id="sched-wh-001",
            name="Webhook Schedule",
            instruction="Process webhook data",
            trigger=TriggerConfig(type=TriggerType.WEBHOOK),
            webhook_id="wh_abc123",
            webhook_url="http://localhost/api/webhooks/wh_abc123",
        )
        assert rec.webhook_id == "wh_abc123"
        assert "wh_abc123" in rec.webhook_url


# -----------------------------------------------------------------------
# ScheduleRunRecord
# -----------------------------------------------------------------------


class TestScheduleRunRecord:
    """Tests for ScheduleRunRecord."""

    def test_default_status_running(self) -> None:
        now = datetime.now(timezone.utc)
        run = ScheduleRunRecord(
            id="run-001",
            schedule_id="sched-001",
            session_id="sess-001",
            triggered_at=now,
            trigger_reason="cron",
        )
        assert run.status == "running"
        assert run.completed_at is None

    def test_completed_run(self) -> None:
        now = datetime.now(timezone.utc)
        run = ScheduleRunRecord(
            id="run-002",
            schedule_id="sched-001",
            session_id="sess-002",
            triggered_at=now,
            trigger_reason="manual",
            status="completed",
            completed_at=now,
            duration_seconds=45.2,
            tool_calls=3,
        )
        assert run.status == "completed"
        assert run.duration_seconds == 45.2
        assert run.tool_calls == 3

    def test_json_roundtrip(self) -> None:
        now = datetime.now(timezone.utc)
        run = ScheduleRunRecord(
            id="run-003",
            schedule_id="sched-001",
            session_id="sess-003",
            triggered_at=now,
            trigger_reason="webhook:wh_123",
        )
        data = run.model_dump(mode="json")
        loaded = ScheduleRunRecord.model_validate(data)
        assert loaded.id == run.id
        assert loaded.trigger_reason == "webhook:wh_123"


# -----------------------------------------------------------------------
# CreateScheduleRequest Validation
# -----------------------------------------------------------------------


class TestCreateScheduleRequest:
    """Tests for CreateScheduleRequest validation."""

    def test_valid_minimal(self) -> None:
        req = CreateScheduleRequest(
            name="Test Schedule",
            instruction="Process documents",
            trigger=TriggerConfig(type=TriggerType.CRON, cron="0 * * * *"),
        )
        assert req.name == "Test Schedule"
        assert req.enabled is True

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="name"):
            CreateScheduleRequest(
                name="",
                instruction="Process documents",
                trigger=TriggerConfig(type=TriggerType.CRON, cron="0 * * * *"),
            )

    def test_empty_instruction_rejected(self) -> None:
        with pytest.raises(ValidationError, match="instruction"):
            CreateScheduleRequest(
                name="Test",
                instruction="",
                trigger=TriggerConfig(type=TriggerType.CRON, cron="0 * * * *"),
            )

    def test_disabled_schedule(self) -> None:
        req = CreateScheduleRequest(
            name="Paused",
            instruction="Do something",
            trigger=TriggerConfig(type=TriggerType.INTERVAL, interval_minutes=60),
            enabled=False,
        )
        assert req.enabled is False

    def test_tags_validation_max_count(self) -> None:
        with pytest.raises(ValidationError, match="20"):
            CreateScheduleRequest(
                name="Too Many Tags",
                instruction="Do something",
                trigger=TriggerConfig(type=TriggerType.CRON, cron="0 * * * *"),
                tags=[f"tag-{i}" for i in range(21)],
            )

    def test_tags_validation_max_length(self) -> None:
        with pytest.raises(ValidationError, match="50"):
            CreateScheduleRequest(
                name="Long Tag",
                instruction="Do something",
                trigger=TriggerConfig(type=TriggerType.CRON, cron="0 * * * *"),
                tags=["x" * 51],
            )

    def test_valid_tags(self) -> None:
        req = CreateScheduleRequest(
            name="Tagged",
            instruction="Do something",
            trigger=TriggerConfig(type=TriggerType.CRON, cron="0 * * * *"),
            tags=["vendor", "pdf", "daily"],
        )
        assert len(req.tags) == 3


# -----------------------------------------------------------------------
# UpdateScheduleRequest Validation
# -----------------------------------------------------------------------


class TestUpdateScheduleRequest:
    """Tests for UpdateScheduleRequest validation."""

    def test_all_none_valid(self) -> None:
        req = UpdateScheduleRequest()
        assert req.name is None
        assert req.trigger is None

    def test_partial_update(self) -> None:
        req = UpdateScheduleRequest(
            name="Updated Name",
            instruction="New instruction",
        )
        assert req.name == "Updated Name"
        assert req.trigger is None  # unchanged

    def test_tags_validation_on_update(self) -> None:
        with pytest.raises(ValidationError, match="20"):
            UpdateScheduleRequest(tags=[f"t-{i}" for i in range(21)])


# -----------------------------------------------------------------------
# DashboardMetrics
# -----------------------------------------------------------------------


class TestDashboardMetrics:
    """Tests for DashboardMetrics model."""

    def test_defaults_to_zero(self) -> None:
        metrics = DashboardMetrics()
        assert metrics.total_sessions == 0
        assert metrics.active_sessions == 0
        assert metrics.error_rate == 0.0
        assert metrics.sessions_by_day == []
        assert metrics.top_tools == []

    def test_with_values(self) -> None:
        metrics = DashboardMetrics(
            total_sessions=100,
            completed_sessions=90,
            failed_sessions=10,
            error_rate=0.1,
            active_schedules=5,
        )
        assert metrics.total_sessions == 100
        assert metrics.error_rate == 0.1


# -----------------------------------------------------------------------
# ActivityEvent
# -----------------------------------------------------------------------


class TestActivityEvent:
    """Tests for ActivityEvent model."""

    def test_basic_event(self) -> None:
        now = datetime.now(timezone.utc)
        event = ActivityEvent(
            timestamp=now,
            type="session_completed",
            session_id="sess-001",
            summary="Processed 3 documents",
        )
        assert event.type == "session_completed"
        assert event.schedule_id is None

    def test_summary_truncation(self) -> None:
        """Summary should be truncated to 200 characters."""
        now = datetime.now(timezone.utc)
        long_summary = "x" * 250
        event = ActivityEvent(
            timestamp=now,
            type="session_completed",
            summary=long_summary,
        )
        assert len(event.summary) <= 200
        assert event.summary.endswith("...")

    def test_schedule_event(self) -> None:
        now = datetime.now(timezone.utc)
        event = ActivityEvent(
            timestamp=now,
            type="schedule_fired",
            schedule_id="sched-001",
            session_id="sess-001",
            summary="Schedule fired (cron)",
        )
        assert event.schedule_id == "sched-001"

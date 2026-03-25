"""Pydantic models for Phase 5 — Scheduling Engine.

Defines all data models for schedule definitions, trigger configurations,
run records, dashboard metrics, and API request/response payloads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.agent_models import InstructOptions


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TriggerType(str, Enum):
    """Supported trigger types for scheduled jobs."""

    CRON = "cron"           # Standard cron expression
    INTERVAL = "interval"   # Every N minutes/hours/days
    EVENT = "event"         # Azure Event Grid subscription
    WEBHOOK = "webhook"     # Inbound HTTP POST


# ---------------------------------------------------------------------------
# Trigger Configuration
# ---------------------------------------------------------------------------


class TriggerConfig(BaseModel):
    """Trigger configuration supporting all four trigger types.

    Uses optional fields per type with a model validator to ensure
    the required fields for each trigger type are present.
    """

    type: TriggerType

    # Cron-specific
    cron: str | None = None                     # "0 6 * * 1-5" (weekdays at 6 AM)
    timezone: str | None = "UTC"                # IANA timezone name

    # Interval-specific
    interval_minutes: int | None = None         # 360 = every 6 hours

    # Event-specific
    event_source: str | None = None             # "blob:vendor-inbox" or "queue:processing"
    event_filter: str | None = None             # Glob or regex for event matching

    # Webhook-specific
    webhook_secret: str | None = None           # HMAC secret for webhook validation

    @model_validator(mode="after")
    def _validate_trigger_fields(self) -> TriggerConfig:
        """Validate that the required fields for the selected trigger type are present."""
        if self.type == TriggerType.CRON:
            if not self.cron:
                raise ValueError("Cron trigger requires a 'cron' expression")
            # Validate cron expression format
            try:
                from croniter import croniter
                if not croniter.is_valid(self.cron):
                    raise ValueError(
                        f"Invalid cron expression: '{self.cron}'"
                    )
            except ImportError:
                pass  # croniter not installed — skip validation

        elif self.type == TriggerType.INTERVAL:
            if self.interval_minutes is None or self.interval_minutes <= 0:
                raise ValueError(
                    "Interval trigger requires 'interval_minutes' > 0"
                )

        elif self.type == TriggerType.EVENT:
            if not self.event_source:
                raise ValueError(
                    "Event trigger requires an 'event_source' "
                    "(e.g., 'blob:vendor-inbox')"
                )

        # Webhook has no strictly required fields (secret is optional)
        return self


# ---------------------------------------------------------------------------
# Schedule Record (Cosmos container: schedules, partition key: /id)
# ---------------------------------------------------------------------------


class ScheduleRecord(BaseModel):
    """Full schedule record stored in Cosmos DB ``schedules`` container.

    Partitioned by ``/id`` — each schedule is its own logical partition.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str                                         # Schedule ID (UUID)
    name: str                                       # Human-readable name
    description: str | None = None                  # Optional description
    instruction: str                                # Natural language instruction to run
    trigger: TriggerConfig                          # Trigger definition
    options: InstructOptions = Field(
        default_factory=InstructOptions,
    )                                               # Session options (model, timeout, etc.)
    tags: list[str] = Field(default_factory=list)   # For filtering and organization

    # State
    status: str = "active"                          # "active", "paused", "error", "deleted"
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    created_by: str | None = None                   # User who created the schedule

    # Run tracking
    last_run_at: datetime | None = None
    last_run_session_id: str | None = None
    last_run_status: str | None = None              # "running", "completed", "failed"
    next_run_at: datetime | None = None             # Computed from trigger
    total_runs: int = 0
    consecutive_failures: int = 0                   # For auto-pause on repeated failures

    # Webhook-specific fields
    webhook_id: str | None = None                   # Generated ID for webhook URL
    webhook_url: str | None = None                  # Full URL: /api/webhooks/{webhook_id}

    def model_dump_json_safe(self) -> dict[str, Any]:
        """Serialise to a dict with datetimes as ISO format strings for Cosmos DB."""
        data = self.model_dump(mode="json")
        return data


# ---------------------------------------------------------------------------
# Schedule Run Record (Cosmos container: schedule-runs, pk: /schedule_id)
# ---------------------------------------------------------------------------


class ScheduleRunRecord(BaseModel):
    """One document per trigger fire, linked to the agent session it created.

    Stored in the ``schedule-runs`` Cosmos container, partitioned by
    ``schedule_id`` for efficient per-schedule history queries.
    """

    id: str                                         # Run ID (UUID)
    schedule_id: str                                # Parent schedule (partition key)
    session_id: str                                 # The agent session created
    triggered_at: datetime                          # When the trigger fired
    trigger_reason: str                             # "cron", "interval", "manual",
                                                    # "webhook:wh_abc", "event:blob_created"

    # Completion tracking
    completed_at: datetime | None = None
    status: str = "running"                         # "running", "completed", "failed", "cancelled"
    summary: str | None = None                      # Agent-generated session summary

    # Metrics (copied from session on completion)
    duration_seconds: float | None = None
    tool_calls: int | None = None
    documents_processed: int | None = None
    errors: int | None = None


# ---------------------------------------------------------------------------
# API Request Models
# ---------------------------------------------------------------------------


class CreateScheduleRequest(BaseModel):
    """API request body for creating a new schedule."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable schedule name",
    )
    description: str | None = Field(
        None,
        max_length=1000,
        description="Optional description of what this schedule does",
    )
    instruction: str = Field(
        ...,
        min_length=1,
        description="Natural language instruction the agent will execute",
    )
    trigger: TriggerConfig = Field(
        ...,
        description="Trigger configuration (cron, interval, event, or webhook)",
    )
    options: InstructOptions | None = Field(
        None,
        description="Session options — model, timeout, approval, etc.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for filtering and organisation",
    )
    enabled: bool = Field(
        True,
        description="If False, schedule is created in 'paused' state",
    )

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str]) -> list[str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 tags allowed")
        for tag in v:
            if len(tag) > 50:
                raise ValueError(f"Tag '{tag[:50]}...' exceeds 50 characters")
        return v


class UpdateScheduleRequest(BaseModel):
    """API request body for updating an existing schedule.

    Only non-``None`` fields are applied to the existing record.
    """

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    instruction: str | None = Field(None, min_length=1)
    trigger: TriggerConfig | None = None
    options: InstructOptions | None = None
    tags: list[str] | None = None

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if len(v) > 20:
                raise ValueError("Maximum 20 tags allowed")
            for tag in v:
                if len(tag) > 50:
                    raise ValueError(
                        f"Tag '{tag[:50]}...' exceeds 50 characters"
                    )
        return v


# ---------------------------------------------------------------------------
# Dashboard / Activity Models
# ---------------------------------------------------------------------------


class DashboardMetrics(BaseModel):
    """Aggregated metrics for the dashboard endpoint."""

    total_sessions: int = 0
    active_sessions: int = 0
    completed_sessions: int = 0
    failed_sessions: int = 0
    total_tool_calls: int = 0
    total_documents_processed: int = 0
    avg_session_duration_seconds: float = 0.0
    error_rate: float = 0.0                         # 0.0 to 1.0
    active_schedules: int = 0
    schedules_fired_today: int = 0
    sessions_by_day: list[dict[str, Any]] = Field(
        default_factory=list,
        description='[{"date": "2026-03-01", "count": 12}, ...]',
    )
    top_tools: list[dict[str, Any]] = Field(
        default_factory=list,
        description='[{"tool": "extract_pdf", "calls": 45}, ...]',
    )


class ActivityEvent(BaseModel):
    """A single event in the dashboard activity feed."""

    timestamp: datetime
    type: str                                       # "session_completed", "session_failed",
                                                    # "schedule_fired", "schedule_paused"
    session_id: str | None = None
    schedule_id: str | None = None
    summary: str = ""

    @field_validator("summary")
    @classmethod
    def _truncate_summary(cls, v: str) -> str:
        """Truncate summary to 200 characters for display."""
        if len(v) > 200:
            return v[:197] + "..."
        return v


# ---------------------------------------------------------------------------
# Detailed Metrics Models (Metrics Page)
# ---------------------------------------------------------------------------


class SessionMetricsDetail(BaseModel):
    """Detailed session metrics broken into tables."""

    token_usage_by_day: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Daily token usage: date, input_tokens, output_tokens, cache_tokens, total_tokens, cost",
    )
    duration_by_day: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Daily duration stats: date, avg_duration, min_duration, max_duration, session_count",
    )
    status_by_day: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Daily status counts: date, active, completed, failed, cancelled",
    )
    documents_by_day: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Daily document processing: date, documents_processed, outputs_produced, errors",
    )
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_tokens: int = 0
    total_cost: float = 0.0
    avg_duration: float = 0.0


class ToolCallMetricsDetail(BaseModel):
    """Detailed tool call metrics broken into tables."""

    tool_usage: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-tool breakdown: tool_name, total_calls, success_count, error_count, avg_duration_ms",
    )
    tool_calls_by_day: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Daily tool call counts: date, count",
    )
    tool_errors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Tool errors: tool_name, error_count, last_error",
    )
    tool_duration: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Tool duration: tool_name, avg_duration_ms, min_duration_ms, max_duration_ms",
    )
    total_tool_calls: int = 0
    total_tool_errors: int = 0


class ScheduleMetricsDetail(BaseModel):
    """Detailed schedule metrics broken into tables."""

    schedule_overview: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-schedule: name, status, total_runs, success_rate, last_run_at, next_run_at",
    )
    runs_by_day: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Daily run counts: date, runs, successes, failures",
    )
    schedule_duration: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-schedule duration: name, avg_duration, min_duration, max_duration",
    )
    schedule_reliability: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-schedule reliability: name, consecutive_failures, success_rate, total_runs",
    )
    total_runs: int = 0
    total_successes: int = 0
    total_failures: int = 0


class DetailedMetrics(BaseModel):
    """Combined detailed metrics for all three categories."""

    sessions: SessionMetricsDetail = Field(default_factory=SessionMetricsDetail)
    tool_calls: ToolCallMetricsDetail = Field(default_factory=ToolCallMetricsDetail)
    schedules: ScheduleMetricsDetail = Field(default_factory=ScheduleMetricsDetail)


class DailyDetailMetrics(BaseModel):
    """Detailed metrics for a single day, shown in drill-down view."""

    date: str

    # Sessions
    sessions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Sessions on this day: id, instruction, status, duration, tool_calls, tokens, cost",
    )
    session_count: int = 0
    completed_count: int = 0
    failed_count: int = 0

    # Token summary for the day
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0

    # Duration summary
    avg_duration: float = 0.0
    min_duration: float = 0.0
    max_duration: float = 0.0

    # Tool calls
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Tool calls on this day: tool_name, status, duration_ms, session_id, error",
    )
    total_tool_calls: int = 0
    total_tool_errors: int = 0

    # Schedule runs
    schedule_runs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Schedule runs on this day: schedule_id, name, session_id, status, duration, trigger_reason",
    )
    total_schedule_runs: int = 0

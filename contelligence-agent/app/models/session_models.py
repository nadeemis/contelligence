"""Pydantic models for Phase 2 — Persistent Sessions.

Defines all data models stored in Cosmos DB for session persistence:
session records, conversation turns, tool call records, output artifacts,
and supporting enums/metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SessionStatus(str, Enum):
    """Lifecycle states for an agent session."""

    ACTIVE = "active"                       # Agent is processing
    WAITING_FOR_INPUT = "waiting_for_input"  # Agent paused, awaiting user reply
    COMPLETED = "completed"                 # Agent finished successfully
    FAILED = "failed"                       # Unrecoverable error
    CANCELLED = "cancelled"                 # User cancelled the session


class SessionEventType(str, Enum):
    """SDK event types understood by the persistence handler.

    Maps 1:1 with Copilot SDK event types and is used in
    ``PersistentAgentService._persist_event()`` for event routing.
    """

    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_EXECUTION_START = "tool_execution_start"
    TOOL_EXECUTION_COMPLETE = "tool_execution_complete"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    SESSION_COMPLETE = "session_complete"
    SESSION_ERROR = "session_error"
    WAITING_FOR_INPUT = "waiting_for_input"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class SessionMetrics(BaseModel):
    """Aggregate metrics computed incrementally as the session runs.

    All fields default to ``0`` so the model can be instantiated at session
    creation. Fields are updated incrementally via
    ``SessionStore.update_session_metrics()`` which adds delta values.
    ``total_duration_seconds`` is computed absolutely at session completion.
    """

    total_duration_seconds: float = 0.0     # Wall clock time from start to end
    total_tool_calls: int = 0               # Number of tool invocations
    input_tokens: int = 0                   # LLM input tokens
    output_tokens: int = 0                  # LLM output tokens
    cache_read_tokens: int = 0              # Tokens read from cache (not billed)
    cache_write_tokens: int = 0             # Tokens written to cache (not billed)
    total_tokens_used: int = 0              # LLM token consumption (input + output)
    model: str | None = None                # LLM model used (e.g., "claude-sonnet-4.6")
    cost: float | None = 0.0                # Estimated cost in USD
    documents_processed: int = 0            # Files handled by extraction tools
    errors_encountered: int = 0             # Errors (may be recovered from)
    outputs_produced: int = 0               # Artifacts written to storage


# ---------------------------------------------------------------------------
# Tool Call Record (embedded within ConversationTurn)
# ---------------------------------------------------------------------------


class ToolCallRecord(BaseModel):
    """Complete record of a single tool invocation.

    Embedded within a ``ConversationTurn`` with ``role == "tool"``.
    ``status`` starts as ``"running"`` when the tool turn is created, then
    transitions to ``"success"`` or ``"error"`` when the tool completes.
    """

    tool_name: str                                  # e.g., "extract_pdf", "read_blob"
    parameters: dict[str, Any] = Field(default_factory=dict)  # Input parameters
    result: dict[str, Any] | None = None            # Output (may be truncated if large)
    started_at: datetime                            # When the tool call began
    completed_at: datetime | None = None            # When the tool call finished
    duration_ms: int | None = None                  # Execution time in milliseconds
    status: str = "running"                         # "running", "success", "error"
    error: str | None = None                        # Error message if status == "error"


# ---------------------------------------------------------------------------
# Delegation Record (Phase 3 — embedded within SessionRecord)
# ---------------------------------------------------------------------------


class DelegationRecord(BaseModel):
    """Record of a sub-agent delegation originating from this session.

    Stored as a list within the parent ``SessionRecord.delegations`` field
    and updated as the sub-session progresses.
    """

    sub_session_id: str                             # Sub-session identifier
    agent_name: str                                 # Custom agent name (e.g., "doc-processor")
    instruction: str                                # Task instruction sent to the sub-agent
    started_at: str                                 # ISO timestamp
    completed_at: str | None = None                 # ISO timestamp when finished
    status: Literal["running", "completed", "failed", "timed_out"] = "running"
    result_summary: str | None = None               # Brief summary of the sub-agent's result


# ---------------------------------------------------------------------------
# Session Record (Cosmos container: sessions, partition key: /id)
# ---------------------------------------------------------------------------


class SessionRecord(BaseModel):
    """Top-level session record stored in the ``sessions`` Cosmos container.

    Partitioned by ``/id`` — i.e. each session is its own logical partition.
    """

    id: str                                         # Session ID (partition key, UUID)
    created_at: datetime                            # When the session was created
    updated_at: datetime                            # Last activity timestamp
    status: SessionStatus                           # Current session state
    model: str                                      # LLM model used (e.g., "gpt-4.1")

    # The original instruction
    instruction: str                                # Natural language instruction

    # User / caller identity
    user_id: str | None = None                      # Identity of the caller (RBAC Phase 4)

    # Configuration used
    options: dict[str, Any] = Field(default_factory=dict)  # InstructOptions serialized

    # Scheduling linkage (populated if created by a schedule — Phase 5)
    schedule_id: str | None = None                  # ID of the triggering schedule
    trigger_reason: str | None = None               # "cron", "event:blob_created", etc.

    # Summary of what was accomplished
    summary: str | None = None                      # Agent-generated summary at completion

    # Aggregate metrics
    metrics: SessionMetrics = Field(default_factory=SessionMetrics)

    # Custom Agent Management — agent selection for this session
    allowed_agents: list[str] = Field(
        default_factory=list,
        description=(
            "Agent IDs allowed in this session. "
            "Empty list means all active agents are available (backward compatible)."
        ),
    )

    # Skills Integration — skills active in this session
    active_skill_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Skill IDs activated for this session. "
            "Skills listed here had their instructions loaded at session start."
        ),
    )

    # Phase 3 — delegations to custom agents
    delegations: list[DelegationRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Conversation Turn (Cosmos container: conversation, partition key: /session_id)
# ---------------------------------------------------------------------------


class ConversationTurn(BaseModel):
    """A single turn in the conversation.

    Stored in the ``conversation`` Cosmos container, partitioned by
    ``session_id``, ordered by ``sequence`` (0-based).

    • For **user** turns: ``prompt`` is populated.
    • For **assistant** turns: ``content`` is populated, optionally ``reasoning``.
    • For **tool** turns: ``tool_call`` is populated with a ``ToolCallRecord``.
    """

    id: str                                         # Turn ID (UUID)
    session_id: str                                 # Parent session (partition key)
    sequence: int                                   # Order in conversation (0-based)
    timestamp: datetime                             # When this turn occurred
    role: str                                       # "user", "assistant", or "tool"

    # User turns
    prompt: str | None = None                       # User's message text

    # Assistant turns
    content: str | None = None                      # Agent's message/response text
    reasoning: str | None = None                    # Internal reasoning (if exposed)

    # Tool turns
    tool_call: ToolCallRecord | None = None         # Tool invocation record


# ---------------------------------------------------------------------------
# Output Artifact (Cosmos container: outputs, partition key: /session_id)
# ---------------------------------------------------------------------------


class SessionEvent(BaseModel):
    """A generic event record persisted to the ``events`` Cosmos container.

    Partitioned by ``session_id``.  All SDK/hook events are stored here,
    grouped by ``event_group`` for easy querying.

    Event groups:
    - ``"tool"``      — tool_call_start/complete/error, tool_execution_*
    - ``"assistant"``  — message, assistant_intent, reasoning, streaming, usage
    - ``"session"``    — session_start/complete/error, lifecycle events
    - ``"turn"``       — user_message, turn_start/end, usage_info
    - ``"agent"``      — subagent_* and delegation_* events
    - ``"meta"``       — hook_*, skill_*, approval, abort, unknown
    """

    id: str                                         # Event ID (UUID)
    session_id: str                                 # Parent session (partition key)
    event_type: str                                 # Original AgentEvent type
    event_group: str                                # Grouping category
    data: dict[str, Any] = Field(default_factory=dict)  # Event payload
    timestamp: datetime                             # When the event occurred


# ---------------------------------------------------------------------------
# User Preferences (Cosmos container: user-preferences, partition key: /user_id)
# ---------------------------------------------------------------------------


class UserPreferences(BaseModel):
    """Per-user persistent preferences.

    Stored in the ``user-preferences`` Cosmos container,
    partitioned by ``/user_id``.
    """

    id: str                                         # Same as user_id (Cosmos requires 'id')
    user_id: str                                    # Identity of the user (partition key)
    default_model: str | None = None                # Preferred default model
    default_agent_id: str | None = None             # Preferred default agent
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


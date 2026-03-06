"""Pydantic models for the contelligence-agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


EventType = Literal[
    # ── Assistant events ──
    "reasoning",
    "message",
    "assistant_intent",
    "assistant_streaming_delta",
    "assistant_usage",
    # ── Tool events (from hooks) ──
    "tool_call_start",
    "tool_call_complete",
    "tool_call_error",
    # ── Tool execution events (from SDK) ──
    "tool_execution_start",
    "tool_execution_complete",
    "tool_execution_partial_result",
    "tool_execution_progress",
    "tool_user_requested",
    # ── Session lifecycle ──
    "session_start",
    "session_complete",
    "session_error",
    "session_info",
    "session_warning",
    "session_resume",
    "session_shutdown",
    "session_handoff",
    "session_model_change",
    "session_mode_changed",
    "session_plan_changed",
    "session_title_changed",
    "session_context_changed",
    "session_truncation",
    "session_compaction_start",
    "session_compaction_complete",
    "session_snapshot_rewind",
    "session_task_complete",
    "session_workspace_file_changed",
    # ── Hook events ──
    "hook_start",
    "hook_end",
    # ── User / turn events ──
    "user_message",
    "turn_start",
    "turn_end",
    "usage_info",
    "pending_messages_modified",
    "system_message",
    # ── Approval ──
    "approval_required",
    # ── Delegation events (Phase 3) ──
    "delegation_start",
    "delegation_progress",
    "delegation_complete",
    "delegation_error",
    # ── Subagent events ──
    "subagent_started",
    "subagent_completed",
    "subagent_failed",
    "subagent_selected",
    "subagent_deselected",
    # ── Skill events ──
    "skill_invoked",
    # ── Abort ──
    "abort",
    # ── Unknown / forward compatibility ──
    "unknown_event",
]


class AgentEvent(BaseModel):
    """An event emitted during an agent session."""

    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str = ""


class InstructOptions(BaseModel):
    """Options governing an instruct request."""

    require_approval: bool = True
    model: str = ""
    persist_outputs: bool = True
    timeout_minutes: int = 60
    agents: list[str] = Field(
        default_factory=list,
        description=(
            "Agent IDs to make available in this session. "
            "Empty list means all active agents are available."
        ),
    )
    skill_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Skill IDs to activate for this session. "
            "Empty list means all active skills are discoverable. "
            "Specified skills are pre-loaded at Level 2 (full instructions)."
        ),
    )


class InstructRequest(BaseModel):
    """Payload sent by the client to start an agent session."""

    instruction: str
    session_id: str | None = None
    options: InstructOptions = Field(default_factory=InstructOptions)


class InstructResponse(BaseModel):
    """Acknowledgement returned after accepting an instruct request."""

    session_id: str
    status: str = "processing"


class ReplyRequest(BaseModel):
    """Payload sent by the client to continue an active session."""

    message: str

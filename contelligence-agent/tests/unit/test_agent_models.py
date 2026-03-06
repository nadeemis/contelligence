"""Tests for the agent Pydantic models."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.models.agent_models import (
    AgentEvent,
    EventType,
    InstructOptions,
    InstructRequest,
    InstructResponse,
    ReplyRequest,
)


# ---------------------------------------------------------------------------
# AgentEvent
# ---------------------------------------------------------------------------

class TestAgentEvent:

    def test_defaults(self) -> None:
        event = AgentEvent(type="message")
        assert event.type == "message"
        assert event.data == {}
        assert event.session_id == ""
        assert isinstance(event.timestamp, datetime)

    def test_with_all_fields(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        event = AgentEvent(
            type="tool_call_start",
            data={"tool": "extract_pdf"},
            timestamp=ts,
            session_id="sess-123",
        )
        assert event.type == "tool_call_start"
        assert event.data == {"tool": "extract_pdf"}
        assert event.timestamp == ts
        assert event.session_id == "sess-123"

    def test_all_event_types(self) -> None:
        """All valid event type literals should be accepted."""
        valid_types: list[EventType] = [
            # Assistant events
            "reasoning",
            "message",
            "assistant_intent",
            "assistant_streaming_delta",
            "assistant_usage",
            # Tool events (hooks)
            "tool_call_start",
            "tool_call_complete",
            "tool_call_error",
            # Tool execution events (SDK)
            "tool_execution_start",
            "tool_execution_complete",
            "tool_execution_partial_result",
            "tool_execution_progress",
            "tool_user_requested",
            # Session lifecycle
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
            # Hook events
            "hook_start",
            "hook_end",
            # User / turn events
            "user_message",
            "turn_start",
            "turn_end",
            "usage_info",
            "pending_messages_modified",
            "system_message",
            # Approval
            "approval_required",
            # Delegation (Phase 3)
            "delegation_start",
            "delegation_progress",
            "delegation_complete",
            "delegation_error",
            # Subagent events
            "subagent_started",
            "subagent_completed",
            "subagent_failed",
            "subagent_selected",
            "subagent_deselected",
            # Skill
            "skill_invoked",
            # Abort
            "abort",
            # Unknown
            "unknown_event",
        ]
        for t in valid_types:
            event = AgentEvent(type=t)
            assert event.type == t

    def test_serialization_roundtrip(self) -> None:
        event = AgentEvent(
            type="session_complete",
            data={"response": "Done!"},
            session_id="s1",
        )
        payload = event.model_dump()
        restored = AgentEvent.model_validate(payload)
        assert restored.type == event.type
        assert restored.data == event.data
        assert restored.session_id == event.session_id

    def test_json_serialization(self) -> None:
        event = AgentEvent(type="message", data={"content": "hello"})
        json_str = event.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["type"] == "message"
        assert parsed["data"]["content"] == "hello"


# ---------------------------------------------------------------------------
# InstructOptions
# ---------------------------------------------------------------------------

class TestInstructOptions:

    def test_defaults(self) -> None:
        opts = InstructOptions()
        assert opts.require_approval is True
        assert opts.model == "gpt-4.1"
        assert opts.persist_outputs is True
        assert opts.timeout_minutes == 60

    def test_custom_values(self) -> None:
        opts = InstructOptions(
            require_approval=False,
            model="gpt-4o",
            persist_outputs=False,
            timeout_minutes=30,
        )
        assert opts.require_approval is False
        assert opts.model == "gpt-4o"
        assert opts.persist_outputs is False
        assert opts.timeout_minutes == 30

    def test_serialization(self) -> None:
        opts = InstructOptions(model="gpt-3.5-turbo")
        data = opts.model_dump()
        assert data["model"] == "gpt-3.5-turbo"
        assert data["require_approval"] is True


# ---------------------------------------------------------------------------
# InstructRequest
# ---------------------------------------------------------------------------

class TestInstructRequest:

    def test_required_field(self) -> None:
        req = InstructRequest(instruction="Process the files")
        assert req.instruction == "Process the files"
        assert req.session_id is None
        assert isinstance(req.options, InstructOptions)

    def test_with_session_id(self) -> None:
        req = InstructRequest(instruction="Do X", session_id="s-42")
        assert req.session_id == "s-42"

    def test_with_custom_options(self) -> None:
        req = InstructRequest(
            instruction="Do X",
            options=InstructOptions(model="gpt-4o"),
        )
        assert req.options.model == "gpt-4o"

    def test_json_roundtrip(self) -> None:
        req = InstructRequest(instruction="test")
        json_str = req.model_dump_json()
        restored = InstructRequest.model_validate_json(json_str)
        assert restored.instruction == "test"


# ---------------------------------------------------------------------------
# InstructResponse
# ---------------------------------------------------------------------------

class TestInstructResponse:

    def test_defaults(self) -> None:
        resp = InstructResponse(session_id="sess-1")
        assert resp.session_id == "sess-1"
        assert resp.status == "processing"

    def test_custom_status(self) -> None:
        resp = InstructResponse(session_id="sess-2", status="completed")
        assert resp.status == "completed"


# ---------------------------------------------------------------------------
# ReplyRequest
# ---------------------------------------------------------------------------

class TestReplyRequest:

    def test_message_field(self) -> None:
        req = ReplyRequest(message="Yes, proceed")
        assert req.message == "Yes, proceed"

    def test_serialization(self) -> None:
        req = ReplyRequest(message="ok")
        data = req.model_dump()
        assert data["message"] == "ok"

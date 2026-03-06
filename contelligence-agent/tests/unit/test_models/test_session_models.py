"""Unit tests for Phase 2 session Pydantic models."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.models.session_models import (
    ConversationTurn,
    OutputArtifact,
    SessionEventType,
    SessionMetrics,
    SessionRecord,
    SessionStatus,
    ToolCallRecord,
)
from app.utils.cosmos_helpers import to_cosmos_dict


# ---------------------------------------------------------------------------
# SessionStatus
# ---------------------------------------------------------------------------


class TestSessionStatus:
    def test_enum_values(self) -> None:
        assert SessionStatus.ACTIVE == "active"
        assert SessionStatus.WAITING_FOR_INPUT == "waiting_for_input"
        assert SessionStatus.COMPLETED == "completed"
        assert SessionStatus.FAILED == "failed"
        assert SessionStatus.CANCELLED == "cancelled"

    def test_all_statuses_present(self) -> None:
        assert len(SessionStatus) == 5


# ---------------------------------------------------------------------------
# SessionEventType
# ---------------------------------------------------------------------------


class TestSessionEventType:
    def test_all_event_types(self) -> None:
        assert len(SessionEventType) == 7
        expected = {
            "assistant_message",
            "tool_execution_start",
            "tool_execution_complete",
            "tool_execution_error",
            "session_complete",
            "session_error",
            "waiting_for_input",
        }
        assert {e.value for e in SessionEventType} == expected


# ---------------------------------------------------------------------------
# SessionMetrics
# ---------------------------------------------------------------------------


class TestSessionMetrics:
    def test_defaults(self) -> None:
        m = SessionMetrics()
        assert m.total_duration_seconds == 0.0
        assert m.total_tool_calls == 0
        assert m.total_tokens_used == 0
        assert m.documents_processed == 0
        assert m.errors_encountered == 0
        assert m.outputs_produced == 0

    def test_custom_values(self) -> None:
        m = SessionMetrics(total_tool_calls=5, outputs_produced=3)
        assert m.total_tool_calls == 5
        assert m.outputs_produced == 3


# ---------------------------------------------------------------------------
# ToolCallRecord
# ---------------------------------------------------------------------------


class TestToolCallRecord:
    def test_running_status_default(self) -> None:
        now = datetime.now(timezone.utc)
        tc = ToolCallRecord(tool_name="extract_pdf", started_at=now)
        assert tc.status == "running"
        assert tc.result is None
        assert tc.error is None

    def test_completed_record(self) -> None:
        start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 0, 0, 5, tzinfo=timezone.utc)
        tc = ToolCallRecord(
            tool_name="read_blob",
            parameters={"container": "data", "path": "doc.pdf"},
            result={"content": "extracted text"},
            started_at=start,
            completed_at=end,
            duration_ms=5000,
            status="success",
        )
        assert tc.status == "success"
        assert tc.duration_ms == 5000

    def test_error_record(self) -> None:
        now = datetime.now(timezone.utc)
        tc = ToolCallRecord(
            tool_name="scrape_webpage",
            started_at=now,
            status="error",
            error="Connection refused",
        )
        assert tc.status == "error"
        assert tc.error == "Connection refused"


# ---------------------------------------------------------------------------
# SessionRecord
# ---------------------------------------------------------------------------


class TestSessionRecord:
    def test_minimal_record(self) -> None:
        now = datetime.now(timezone.utc)
        r = SessionRecord(
            id="sess-1",
            created_at=now,
            updated_at=now,
            status=SessionStatus.ACTIVE,
            model="gpt-4.1",
            instruction="Process documents",
        )
        assert r.id == "sess-1"
        assert r.user_id is None
        assert r.schedule_id is None
        assert r.summary is None
        assert r.metrics.total_tool_calls == 0

    def test_serialization_roundtrip(self) -> None:
        now = datetime.now(timezone.utc)
        r = SessionRecord(
            id="sess-2",
            created_at=now,
            updated_at=now,
            status=SessionStatus.COMPLETED,
            model="gpt-4.1",
            instruction="Summarise data",
            summary="Done.",
            metrics=SessionMetrics(total_tool_calls=3, outputs_produced=1),
        )
        data = r.model_dump(mode="json")
        restored = SessionRecord.model_validate(data)
        assert restored.id == r.id
        assert restored.status == SessionStatus.COMPLETED
        assert restored.metrics.total_tool_calls == 3


# ---------------------------------------------------------------------------
# ConversationTurn
# ---------------------------------------------------------------------------


class TestConversationTurn:
    def test_user_turn(self) -> None:
        now = datetime.now(timezone.utc)
        t = ConversationTurn(
            id="turn-1",
            session_id="sess-1",
            sequence=0,
            timestamp=now,
            role="user",
            prompt="Extract documents",
        )
        assert t.role == "user"
        assert t.prompt == "Extract documents"
        assert t.content is None
        assert t.tool_call is None

    def test_assistant_turn(self) -> None:
        now = datetime.now(timezone.utc)
        t = ConversationTurn(
            id="turn-2",
            session_id="sess-1",
            sequence=1,
            timestamp=now,
            role="assistant",
            content="I will process the files.",
        )
        assert t.role == "assistant"
        assert t.content is not None

    def test_tool_turn(self) -> None:
        now = datetime.now(timezone.utc)
        tc = ToolCallRecord(
            tool_name="extract_pdf",
            parameters={"container": "data", "path": "doc.pdf"},
            started_at=now,
        )
        t = ConversationTurn(
            id="turn-3",
            session_id="sess-1",
            sequence=2,
            timestamp=now,
            role="tool",
            tool_call=tc,
        )
        assert t.role == "tool"
        assert t.tool_call is not None
        assert t.tool_call.tool_name == "extract_pdf"


# ---------------------------------------------------------------------------
# OutputArtifact
# ---------------------------------------------------------------------------


class TestOutputArtifact:
    def test_blob_artifact(self) -> None:
        now = datetime.now(timezone.utc)
        a = OutputArtifact(
            id="art-1",
            session_id="sess-1",
            name="results.json",
            description="Extracted results",
            artifact_type="json",
            storage_type="blob",
            storage_location="agent-outputs/sess-1/results.json",
            size_bytes=2048,
            content_type="application/json",
            created_at=now,
        )
        assert a.storage_type == "blob"
        assert a.size_bytes == 2048

    def test_search_index_artifact(self) -> None:
        now = datetime.now(timezone.utc)
        a = OutputArtifact(
            id="art-2",
            session_id="sess-1",
            name="documents index upload",
            description="Uploaded 100 docs",
            artifact_type="search_index",
            storage_type="search_index",
            storage_location="documents-index",
            record_count=100,
            created_at=now,
        )
        assert a.storage_type == "search_index"
        assert a.record_count == 100

    def test_cosmos_artifact(self) -> None:
        now = datetime.now(timezone.utc)
        a = OutputArtifact(
            id="art-3",
            session_id="sess-1",
            name="upsert result",
            description="Upserted to mydb/mycol",
            artifact_type="json",
            storage_type="cosmos",
            storage_location="mydb/mycol",
            created_at=now,
        )
        assert a.storage_type == "cosmos"


# ---------------------------------------------------------------------------
# to_cosmos_dict helper
# ---------------------------------------------------------------------------


class TestToCosmosDict:
    def test_datetime_converted_to_iso(self) -> None:
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        r = SessionRecord(
            id="sess-x",
            created_at=now,
            updated_at=now,
            status=SessionStatus.ACTIVE,
            model="gpt-4.1",
            instruction="Test",
        )
        d = to_cosmos_dict(r)
        assert isinstance(d["created_at"], str)
        assert "2025-06-01" in d["created_at"]

    def test_enum_converted_to_value(self) -> None:
        now = datetime.now(timezone.utc)
        r = SessionRecord(
            id="sess-y",
            created_at=now,
            updated_at=now,
            status=SessionStatus.COMPLETED,
            model="gpt-4.1",
            instruction="Test",
        )
        d = to_cosmos_dict(r)
        assert d["status"] == "completed"

    def test_nested_metrics_serialized(self) -> None:
        now = datetime.now(timezone.utc)
        r = SessionRecord(
            id="sess-z",
            created_at=now,
            updated_at=now,
            status=SessionStatus.ACTIVE,
            model="gpt-4.1",
            instruction="Test",
            metrics=SessionMetrics(total_tool_calls=7),
        )
        d = to_cosmos_dict(r)
        assert d["metrics"]["total_tool_calls"] == 7

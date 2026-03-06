"""AC-3: Tool calls record parameters, results, duration, and status.

Integration test verifying that tool call records are fully populated
after tool execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.session_models import (
    ConversationTurn,
    SessionStatus,
    ToolCallRecord,
)
from tests.conftest import MockSessionStore, create_sample_session


class TestToolCallRecords:
    @pytest.mark.asyncio
    async def test_successful_tool_call_fully_populated(self) -> None:
        """A successful tool call has parameters, result, duration, and status."""
        store = MockSessionStore()
        session = create_sample_session(session_id="s-tc1", status=SessionStatus.ACTIVE)
        await store.save_session(session)

        start = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        tc = ToolCallRecord(
            tool_name="extract_pdf",
            parameters={"container": "data", "path": "doc.pdf"},
            started_at=start,
        )
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            session_id="s-tc1",
            sequence=1,
            timestamp=start,
            role="tool",
            tool_call=tc,
        )
        await store.save_turn(turn)

        # Simulate tool completion
        end = start + timedelta(seconds=2)
        await store.update_tool_call(
            session_id="s-tc1",
            tool_name="extract_pdf",
            result={"text": "Extracted content", "pages": 5},
            result_blob_ref=None,
            completed_at=end,
            status="success",
        )

        turns = await store.get_turns("s-tc1")
        tool_turns = [t for t in turns if t.role == "tool"]
        assert len(tool_turns) == 1

        tc_record = tool_turns[0].tool_call
        assert tc_record.tool_name == "extract_pdf"
        assert tc_record.parameters == {"container": "data", "path": "doc.pdf"}
        assert tc_record.result == {"text": "Extracted content", "pages": 5}
        assert tc_record.status == "success"
        assert tc_record.started_at == start
        assert tc_record.completed_at == end
        assert tc_record.duration_ms == 2000
        assert tc_record.error is None

    @pytest.mark.asyncio
    async def test_failed_tool_call_has_error(self) -> None:
        """A failed tool call records the error message."""
        store = MockSessionStore()

        start = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        tc = ToolCallRecord(
            tool_name="scrape_webpage",
            parameters={"url": "https://example.com"},
            started_at=start,
        )
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            session_id="s-tc2",
            sequence=1,
            timestamp=start,
            role="tool",
            tool_call=tc,
        )
        await store.save_turn(turn)

        end = start + timedelta(seconds=5)
        await store.update_tool_call(
            session_id="s-tc2",
            tool_name="scrape_webpage",
            result=None,
            result_blob_ref=None,
            completed_at=end,
            status="error",
            error="Connection refused",
        )

        turns = await store.get_turns("s-tc2")
        tc_record = turns[0].tool_call
        assert tc_record.status == "error"
        assert tc_record.error == "Connection refused"
        assert tc_record.duration_ms == 5000

    @pytest.mark.asyncio
    async def test_started_at_before_completed_at(self) -> None:
        """Verify started_at < completed_at for completed tool calls."""
        store = MockSessionStore()

        start = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        tc = ToolCallRecord(
            tool_name="read_blob",
            parameters={},
            started_at=start,
        )
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            session_id="s-tc3",
            sequence=0,
            timestamp=start,
            role="tool",
            tool_call=tc,
        )
        await store.save_turn(turn)

        end = start + timedelta(milliseconds=500)
        await store.update_tool_call(
            session_id="s-tc3",
            tool_name="read_blob",
            result={"content": "data"},
            result_blob_ref=None,
            completed_at=end,
            status="success",
        )

        turns = await store.get_turns("s-tc3")
        tc_record = turns[0].tool_call
        assert tc_record.started_at < tc_record.completed_at
        assert tc_record.duration_ms == 500

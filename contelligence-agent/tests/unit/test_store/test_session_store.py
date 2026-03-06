"""Unit tests for SessionStore using MockSessionStore.

Tests verify that all CRUD operations behave correctly, including
error mapping, filtering, incremental metric updates, and tool call updates.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import pytest

from app.models.exceptions import SessionNotFoundError
from app.models.session_models import (
    ConversationTurn,
    OutputArtifact,
    SessionMetrics,
    SessionRecord,
    SessionStatus,
    ToolCallRecord,
)
from tests.conftest import (
    MockSessionStore,
    create_sample_outputs,
    create_sample_session,
    create_sample_turns,
)


@pytest.fixture()
def store() -> MockSessionStore:
    return MockSessionStore()


# ---------------------------------------------------------------------------
# save_session / get_session
# ---------------------------------------------------------------------------


class TestSaveAndGetSession:
    @pytest.mark.asyncio
    async def test_save_and_retrieve(self, store: MockSessionStore) -> None:
        record = create_sample_session(session_id="s-1")
        await store.save_session(record)
        fetched = await store.get_session("s-1")
        assert fetched.id == "s-1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_raises(self, store: MockSessionStore) -> None:
        with pytest.raises(SessionNotFoundError):
            await store.get_session("does-not-exist")

    @pytest.mark.asyncio
    async def test_upsert_overwrites(self, store: MockSessionStore) -> None:
        r1 = create_sample_session(session_id="s-2", instruction="v1")
        await store.save_session(r1)
        r2 = create_sample_session(session_id="s-2", instruction="v2")
        await store.save_session(r2)
        fetched = await store.get_session("s-2")
        assert fetched.instruction == "v2"


# ---------------------------------------------------------------------------
# update_session_status
# ---------------------------------------------------------------------------


class TestUpdateSessionStatus:
    @pytest.mark.asyncio
    async def test_status_transition(self, store: MockSessionStore) -> None:
        record = create_sample_session(session_id="s-3", status=SessionStatus.ACTIVE)
        await store.save_session(record)

        await store.update_session_status("s-3", SessionStatus.COMPLETED, summary="Done")
        fetched = await store.get_session("s-3")
        assert fetched.status == SessionStatus.COMPLETED
        assert fetched.summary == "Done"

    @pytest.mark.asyncio
    async def test_nonexistent_raises(self, store: MockSessionStore) -> None:
        with pytest.raises(SessionNotFoundError):
            await store.update_session_status("missing", SessionStatus.FAILED)


# ---------------------------------------------------------------------------
# update_session_metrics
# ---------------------------------------------------------------------------


class TestUpdateSessionMetrics:
    @pytest.mark.asyncio
    async def test_incremental_add(self, store: MockSessionStore) -> None:
        record = create_sample_session(session_id="s-4", status=SessionStatus.ACTIVE)
        await store.save_session(record)

        await store.update_session_metrics("s-4", total_tool_calls=2, documents_processed=1)
        await store.update_session_metrics("s-4", total_tool_calls=3)

        fetched = await store.get_session("s-4")
        assert fetched.metrics.total_tool_calls == 5
        assert fetched.metrics.documents_processed == 1

    @pytest.mark.asyncio
    async def test_unknown_metric_ignored(self, store: MockSessionStore) -> None:
        record = create_sample_session(session_id="s-5", status=SessionStatus.ACTIVE)
        await store.save_session(record)
        # Should not raise even with unknown key
        await store.update_session_metrics("s-5", nonexistent_field=99)
        fetched = await store.get_session("s-5")
        assert fetched.metrics.total_tool_calls == 0  # unchanged


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    @pytest.mark.asyncio
    async def test_list_all(self, store: MockSessionStore) -> None:
        for i in range(3):
            await store.save_session(
                create_sample_session(session_id=f"s-{i}", status=SessionStatus.COMPLETED)
            )
        results = await store.list_sessions()
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_filter_by_status(self, store: MockSessionStore) -> None:
        await store.save_session(
            create_sample_session(session_id="s-a", status=SessionStatus.ACTIVE)
        )
        await store.save_session(
            create_sample_session(session_id="s-b", status=SessionStatus.COMPLETED)
        )
        results = await store.list_sessions(status=SessionStatus.COMPLETED)
        assert len(results) == 1
        assert results[0].id == "s-b"

    @pytest.mark.asyncio
    async def test_filter_by_user_id(self, store: MockSessionStore) -> None:
        await store.save_session(
            create_sample_session(session_id="s-u1", user_id="alice")
        )
        await store.save_session(
            create_sample_session(session_id="s-u2", user_id="bob")
        )
        results = await store.list_sessions(user_id="alice")
        assert len(results) == 1
        assert results[0].user_id == "alice"

    @pytest.mark.asyncio
    async def test_limit(self, store: MockSessionStore) -> None:
        for i in range(5):
            await store.save_session(create_sample_session(session_id=f"s-lim-{i}"))
        results = await store.list_sessions(limit=2)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_empty_result(self, store: MockSessionStore) -> None:
        results = await store.list_sessions()
        assert results == []


# ---------------------------------------------------------------------------
# save_turn / get_turns
# ---------------------------------------------------------------------------


class TestTurns:
    @pytest.mark.asyncio
    async def test_save_and_get_ordered(self, store: MockSessionStore) -> None:
        turns = create_sample_turns("s-10", count=4)
        for t in turns:
            await store.save_turn(t)
        fetched = await store.get_turns("s-10")
        assert len(fetched) == 4
        for i, t in enumerate(fetched):
            assert t.sequence == i

    @pytest.mark.asyncio
    async def test_empty_turns(self, store: MockSessionStore) -> None:
        turns = await store.get_turns("nonexistent")
        assert turns == []


# ---------------------------------------------------------------------------
# update_tool_call
# ---------------------------------------------------------------------------


class TestUpdateToolCall:
    @pytest.mark.asyncio
    async def test_updates_running_tool(self, store: MockSessionStore) -> None:
        now = datetime.now(timezone.utc)
        tc = ToolCallRecord(tool_name="extract_pdf", started_at=now, parameters={})
        turn = ConversationTurn(
            id="tc-turn-1",
            session_id="s-20",
            sequence=1,
            timestamp=now,
            role="tool",
            tool_call=tc,
        )
        await store.save_turn(turn)

        completed_at = now + timedelta(seconds=3)
        await store.update_tool_call(
            session_id="s-20",
            tool_name="extract_pdf",
            result={"text": "extracted"},
            result_blob_ref=None,
            completed_at=completed_at,
            status="success",
        )

        turns = await store.get_turns("s-20")
        assert turns[0].tool_call.status == "success"
        assert turns[0].tool_call.result == {"text": "extracted"}
        assert turns[0].tool_call.duration_ms == 3000


# ---------------------------------------------------------------------------
# save_output / get_outputs / get_output
# ---------------------------------------------------------------------------


class TestOutputs:
    @pytest.mark.asyncio
    async def test_save_and_list(self, store: MockSessionStore) -> None:
        outputs = create_sample_outputs("s-30", count=3)
        for o in outputs:
            await store.save_output(o)
        fetched = await store.get_outputs("s-30")
        assert len(fetched) == 3

    @pytest.mark.asyncio
    async def test_get_specific_output(self, store: MockSessionStore) -> None:
        outputs = create_sample_outputs("s-31", count=2)
        for o in outputs:
            await store.save_output(o)
        target = outputs[1]
        fetched = await store.get_output("s-31", target.id)
        assert fetched.id == target.id

    @pytest.mark.asyncio
    async def test_get_output_not_found(self, store: MockSessionStore) -> None:
        with pytest.raises(SessionNotFoundError):
            await store.get_output("s-32", "missing-id")

    @pytest.mark.asyncio
    async def test_empty_outputs(self, store: MockSessionStore) -> None:
        outputs = await store.get_outputs("nonexistent")
        assert outputs == []

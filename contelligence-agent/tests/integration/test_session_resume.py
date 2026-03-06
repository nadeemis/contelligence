"""AC-11 / AC-12: Session resume — restores history and continues numbering.

Integration tests for ``PersistentAgentService.resume_session()``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.agent_models import InstructOptions
from app.models.session_models import (
    ConversationTurn,
    SessionRecord,
    SessionStatus,
    SessionMetrics,
    ToolCallRecord,
)
from app.services.persistent_agent_service import (
    PersistentAgentService,
    RESUMABLE_STATUSES,
)
from tests.conftest import MockSessionStore, create_sample_session


def _make_service(store: MockSessionStore) -> PersistentAgentService:
    """Build a PersistentAgentService with mocked session factory."""
    session_factory = MagicMock()

    # Mock both create_session and resume_session to return a mock CopilotSession
    mock_copilot_session = MagicMock()
    mock_copilot_session.status = "active"
    session_factory.create_session = AsyncMock(return_value=mock_copilot_session)
    session_factory.resume_session = AsyncMock(return_value=mock_copilot_session)

    blob = AsyncMock()
    return PersistentAgentService(
        session_factory=session_factory,
        session_store=store,
        system_prompt="You are an agent.",
        blob_connector=blob,
    )


async def _seed_completed_session(
    store: MockSessionStore,
    session_id: str = "s-resume-1",
    turn_count: int = 4,
) -> str:
    """Seed a COMPLETED session with conversation history."""
    now = datetime.now(timezone.utc)
    session = SessionRecord(
        id=session_id,
        created_at=now,
        updated_at=now,
        status=SessionStatus.COMPLETED,
        model="gpt-4.1",
        instruction="Original instruction",
        metrics=SessionMetrics(total_tool_calls=2, documents_processed=1),
    )
    await store.save_session(session)

    # Seed turns: user → tool → assistant → user
    turns = [
        ConversationTurn(
            id=str(uuid.uuid4()), session_id=session_id, sequence=0,
            timestamp=now, role="user", prompt="Original instruction",
        ),
        ConversationTurn(
            id=str(uuid.uuid4()), session_id=session_id, sequence=1,
            timestamp=now, role="tool",
            tool_call=ToolCallRecord(
                tool_name="extract_pdf",
                parameters={"path": "doc.pdf"},
                started_at=now, completed_at=now, duration_ms=500,
                status="success", result={"text": "extracted content"},
            ),
        ),
        ConversationTurn(
            id=str(uuid.uuid4()), session_id=session_id, sequence=2,
            timestamp=now, role="assistant", content="I extracted the PDF.",
        ),
        ConversationTurn(
            id=str(uuid.uuid4()), session_id=session_id, sequence=3,
            timestamp=now, role="user", prompt="Now summarise it",
        ),
    ]
    for t in turns[:turn_count]:
        await store.save_turn(t)

    return session_id


class TestSessionResume:
    """AC-11: Resuming a completed session restores conversation history."""

    @pytest.mark.asyncio
    async def test_resumable_statuses_accepted(self) -> None:
        """Sessions in COMPLETED, FAILED, CANCELLED, WAITING_FOR_INPUT can resume."""
        for status in RESUMABLE_STATUSES:
            store = MockSessionStore()
            sid = f"s-{status.value}"
            session = create_sample_session(session_id=sid, status=status)
            await store.save_session(session)
            await store.save_turn(
                ConversationTurn(
                    id=str(uuid.uuid4()), session_id=sid, sequence=0,
                    timestamp=datetime.now(timezone.utc), role="user",
                    prompt="Initial",
                ),
            )
            service = _make_service(store)

            with patch.object(service, "_run_persistent_loop", new_callable=AsyncMock):
                returned_id = await service.resume_session(
                    sid, "Continue please", InstructOptions(),
                )
            assert returned_id == sid

    @pytest.mark.asyncio
    async def test_active_session_in_memory_delegates_to_send_reply(self) -> None:
        """An ACTIVE session that is running in memory should forward via send_reply."""
        store = MockSessionStore()
        session = create_sample_session(session_id="s-active", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        await store.save_turn(
            ConversationTurn(
                id=str(uuid.uuid4()), session_id="s-active", sequence=0,
                timestamp=datetime.now(timezone.utc), role="user",
                prompt="Initial",
            ),
        )
        service = _make_service(store)

        # Simulate the session being actively running in memory
        mock_sdk_session = MagicMock()
        mock_sdk_session.send_message = AsyncMock()
        service.active_sessions["s-active"] = mock_sdk_session

        with patch.object(service, "send_reply", new_callable=AsyncMock) as mock_reply:
            returned_id = await service.resume_session(
                "s-active", "Follow-up", InstructOptions(),
            )

        assert returned_id == "s-active"
        mock_reply.assert_awaited_once_with("s-active", "Follow-up")

    @pytest.mark.asyncio
    async def test_stale_active_session_can_be_resumed(self) -> None:
        """An ACTIVE session NOT in memory (stale) should resume normally."""
        store = MockSessionStore()
        session = create_sample_session(session_id="s-stale", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        await store.save_turn(
            ConversationTurn(
                id=str(uuid.uuid4()), session_id="s-stale", sequence=0,
                timestamp=datetime.now(timezone.utc), role="user",
                prompt="Initial",
            ),
        )
        service = _make_service(store)

        with patch.object(service, "_run_persistent_loop", new_callable=AsyncMock):
            returned_id = await service.resume_session(
                "s-stale", "Continue", InstructOptions(),
            )
        assert returned_id == "s-stale"

    @pytest.mark.asyncio
    async def test_resume_restores_session_to_active(self) -> None:
        store = MockSessionStore()
        sid = await _seed_completed_session(store)
        service = _make_service(store)

        with patch.object(service, "_run_persistent_loop", new_callable=AsyncMock):
            await service.resume_session(sid, "Continue", InstructOptions())

        record = await store.get_session(sid)
        assert record.status == SessionStatus.ACTIVE


class TestResumeConversationNumbering:
    """AC-12: Resumed session continues turn sequence numbering."""

    @pytest.mark.asyncio
    async def test_new_user_turn_continues_sequence(self) -> None:
        store = MockSessionStore()
        sid = await _seed_completed_session(store, turn_count=4)
        service = _make_service(store)

        with patch.object(service, "_run_persistent_loop", new_callable=AsyncMock):
            await service.resume_session(sid, "New instruction", InstructOptions())

        turns = await store.get_turns(sid)
        # Original 4 turns + 1 new resume instruction
        assert len(turns) == 5
        assert turns[-1].sequence == 4
        assert turns[-1].role == "user"
        assert turns[-1].prompt == "New instruction"

    @pytest.mark.asyncio
    async def test_sdk_resume_session_called(self) -> None:
        """The SDK session should be resumed via resume_session, not create_session."""
        store = MockSessionStore()
        sid = await _seed_completed_session(store, turn_count=4)
        service = _make_service(store)

        with patch.object(service, "_run_persistent_loop", new_callable=AsyncMock):
            await service.resume_session(sid, "Continue", InstructOptions())

        # Verify resume_session was called (not create_session)
        service.session_factory.resume_session.assert_awaited_once()
        call_kwargs = service.session_factory.resume_session.call_args[1]
        assert call_kwargs["session_id"] == sid
        # create_session should NOT have been called for resume
        service.session_factory.create_session.assert_not_awaited()

"""AC-2: Every conversation turn is persisted with correct sequence.

Integration test verifying that conversation turns are persisted with
sequential numbering and correct role assignment.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.session_models import (
    ConversationTurn,
    SessionStatus,
    ToolCallRecord,
)
from tests.conftest import MockSessionStore, create_sample_session


class TestConversationTurnsPersisted:
    @pytest.mark.asyncio
    async def test_turns_sequential_ordering(self) -> None:
        """Turns are persisted with strictly sequential numbering."""
        store = MockSessionStore()
        session = create_sample_session(session_id="s-conv", status=SessionStatus.ACTIVE)
        await store.save_session(session)

        now = datetime.now(timezone.utc)
        roles = ["user", "assistant", "tool", "assistant"]
        for seq, role in enumerate(roles):
            turn = ConversationTurn(
                id=str(uuid.uuid4()),
                session_id="s-conv",
                sequence=seq,
                timestamp=now,
                role=role,
                prompt="Test prompt" if role == "user" else None,
                content="Response" if role == "assistant" else None,
                tool_call=(
                    ToolCallRecord(tool_name="extract_pdf", started_at=now)
                    if role == "tool"
                    else None
                ),
            )
            await store.save_turn(turn)

        turns = await store.get_turns("s-conv")
        assert len(turns) == 4
        assert turns[0].role == "user"
        assert turns[0].sequence == 0
        for i, turn in enumerate(turns):
            assert turn.sequence == i
            assert turn.session_id == "s-conv"

    @pytest.mark.asyncio
    async def test_first_turn_is_user(self) -> None:
        """The first turn should always be the user instruction."""
        store = MockSessionStore()
        session = create_sample_session(session_id="s-first", status=SessionStatus.ACTIVE)
        await store.save_session(session)

        now = datetime.now(timezone.utc)
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            session_id="s-first",
            sequence=0,
            timestamp=now,
            role="user",
            prompt="Extract all PDFs",
        )
        await store.save_turn(turn)

        turns = await store.get_turns("s-first")
        assert turns[0].role == "user"
        assert turns[0].prompt == "Extract all PDFs"

    @pytest.mark.asyncio
    async def test_tool_turn_has_tool_call(self) -> None:
        """Tool turns must have a populated tool_call field."""
        store = MockSessionStore()
        now = datetime.now(timezone.utc)

        tc = ToolCallRecord(
            tool_name="read_blob",
            parameters={"container": "data", "path": "file.txt"},
            started_at=now,
        )
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            session_id="s-tool",
            sequence=2,
            timestamp=now,
            role="tool",
            tool_call=tc,
        )
        await store.save_turn(turn)

        turns = await store.get_turns("s-tool")
        assert len(turns) == 1
        assert turns[0].tool_call is not None
        assert turns[0].tool_call.tool_name == "read_blob"

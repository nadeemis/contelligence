"""AC-1: Every session creates a SessionRecord in Cosmos DB.

Integration test verifying that ``PersistentAgentService.create_and_run()``
persists a ``SessionRecord`` with all required fields.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.agent_models import InstructOptions
from app.models.session_models import SessionRecord, SessionStatus
from app.services.persistent_agent_service import PersistentAgentService
from tests.conftest import MockSessionStore


def _make_service(store: MockSessionStore) -> PersistentAgentService:
    session_factory = MagicMock()
    mock_session = AsyncMock()
    mock_session.session_id = str(uuid.uuid4())
    mock_session.status = "active"
    mock_session.close = AsyncMock()
    mock_session.send_message = AsyncMock()
    session_factory.create_session = AsyncMock(return_value=mock_session)

    blob = AsyncMock()
    return PersistentAgentService(
        session_factory=session_factory,
        session_store=store,
        system_prompt="You are an agent.",
        blob_connector=blob,
    )


class TestSessionCreatesRecord:
    @pytest.mark.asyncio
    async def test_session_record_created(self) -> None:
        """AC-1: create_and_run persists a SessionRecord."""
        store = MockSessionStore()
        service = _make_service(store)

        with patch.object(service, "_run_persistent_loop", new_callable=AsyncMock):
            session_id = await service.create_and_run(
                instruction="Extract text from PDFs",
                options=InstructOptions(),
            )

        record = await store.get_session(session_id)
        assert record.id == session_id
        assert record.status == SessionStatus.ACTIVE
        assert record.instruction == "Extract text from PDFs"
        assert record.model == "gpt-4.1"
        assert record.metrics.total_tool_calls == 0
        assert record.metrics.total_duration_seconds == 0.0

    @pytest.mark.asyncio
    async def test_session_has_timestamps(self) -> None:
        store = MockSessionStore()
        service = _make_service(store)

        with patch.object(service, "_run_persistent_loop", new_callable=AsyncMock):
            session_id = await service.create_and_run(
                instruction="Test timestamps",
                options=InstructOptions(),
            )

        record = await store.get_session(session_id)
        assert record.created_at is not None
        assert record.updated_at is not None
        assert record.created_at <= record.updated_at

    @pytest.mark.asyncio
    async def test_initial_user_turn_persisted(self) -> None:
        """The first turn (user instruction) should be persisted with sequence 0."""
        store = MockSessionStore()
        service = _make_service(store)

        with patch.object(service, "_run_persistent_loop", new_callable=AsyncMock):
            session_id = await service.create_and_run(
                instruction="Process files",
                options=InstructOptions(),
            )

        turns = await store.get_turns(session_id)
        assert len(turns) == 1
        assert turns[0].role == "user"
        assert turns[0].sequence == 0
        assert turns[0].prompt == "Process files"

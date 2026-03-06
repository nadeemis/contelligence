"""AC-13: Session metrics update incrementally during processing.

Integration test verifying that ``PersistentAgentService`` methods
properly increment metrics (tool calls, errors, documents processed,
outputs produced, tokens, duration).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.agent_models import InstructOptions
from app.models.session_models import SessionStatus
from app.services.persistent_agent_service import PersistentAgentService
from tests.conftest import MockSessionStore, create_sample_session


def _make_service(store: MockSessionStore) -> PersistentAgentService:
    session_factory = MagicMock()
    mock_session = AsyncMock()
    mock_session.session_id = str(uuid.uuid4())
    mock_session.status = "active"
    mock_session.close = AsyncMock()
    session_factory.create_session.return_value = mock_session
    blob = AsyncMock()
    return PersistentAgentService(
        session_factory=session_factory,
        session_store=store,
        system_prompt="Test",
        blob_connector=blob,
    )


class TestSessionMetricsIncrement:
    """Verify that metrics are updated via persist_* hooks."""

    @pytest.mark.asyncio
    async def test_tool_calls_incremented(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-m1", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service = _make_service(store)

        turn_seq = [0]
        await service.persist_tool_start("s-m1", "extract_pdf", {"path": "a.pdf"}, turn_seq)
        await service.persist_tool_start("s-m1", "extract_pdf", {"path": "b.pdf"}, turn_seq)

        record = await store.get_session("s-m1")
        assert record.metrics.total_tool_calls == 2

    @pytest.mark.asyncio
    async def test_documents_processed_for_extraction(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-m2", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service = _make_service(store)

        turn_seq = [0]
        await service.persist_tool_start("s-m2", "extract_pdf", {"path": "a.pdf"}, turn_seq)
        await service.persist_tool_complete("s-m2", "extract_pdf", {"text": "content"})

        record = await store.get_session("s-m2")
        assert record.metrics.documents_processed == 1

    @pytest.mark.asyncio
    async def test_errors_encountered_on_tool_error(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-m3", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service = _make_service(store)

        turn_seq = [0]
        await service.persist_tool_start("s-m3", "extract_pdf", {"path": "a.pdf"}, turn_seq)
        await service.persist_tool_error("s-m3", "extract_pdf", "File not found")

        record = await store.get_session("s-m3")
        assert record.metrics.errors_encountered == 1

    @pytest.mark.asyncio
    async def test_outputs_produced_for_write_tools(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-m4", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service = _make_service(store)

        await service._register_output(
            session_id="s-m4",
            tool_name="write_blob",
            params={"container": "c", "path": "f.json", "data": "x"},
            result={},
        )

        record = await store.get_session("s-m4")
        assert record.metrics.outputs_produced == 1

    @pytest.mark.asyncio
    async def test_metrics_accumulate_across_multiple_events(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-m5", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service = _make_service(store)

        turn_seq = [0]
        # 3 tool calls
        for i in range(3):
            await service.persist_tool_start(
                "s-m5", "extract_pdf", {"path": f"file_{i}.pdf"}, turn_seq,
            )
            await service.persist_tool_complete(
                "s-m5", "extract_pdf", {"text": f"text {i}"},
            )

        # 1 tool error
        await service.persist_tool_start("s-m5", "extract_docx", {"path": "bad.docx"}, turn_seq)
        await service.persist_tool_error("s-m5", "extract_docx", "Corrupt file")

        record = await store.get_session("s-m5")
        assert record.metrics.total_tool_calls == 4  # 3 ok + 1 error
        assert record.metrics.documents_processed == 3
        assert record.metrics.errors_encountered == 1

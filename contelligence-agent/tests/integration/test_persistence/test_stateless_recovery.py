"""AC-15: Stateless container restart — no data loss.

Integration test verifying that session data survives a simulated
container restart. Since ``MockSessionStore`` is in-memory, we verify
the invariant that *persisted* data is always written to the store
before the response is returned, so a fresh service instance backed by
the **same** store sees the data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.agent_models import InstructOptions
from app.models.session_models import SessionStatus
from app.services.persistent_agent_service import PersistentAgentService
from tests.conftest import MockSessionStore, create_sample_session, create_sample_turns


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
        system_prompt="Test",
        blob_connector=blob,
    )


class TestStatelessRecovery:
    """Simulate a "container restart" by building a new PersistentAgentService
    while keeping the same underlying ``MockSessionStore``."""

    @pytest.mark.asyncio
    async def test_session_survives_restart(self) -> None:
        """Data written by service-1 is readable by service-2."""
        store = MockSessionStore()
        service_1 = _make_service(store)

        with patch.object(service_1, "_run_persistent_loop", new_callable=AsyncMock):
            session_id = await service_1.create_and_run(
                instruction="Survive restart", options=InstructOptions(),
            )

        # "Restart" = new service instance, same store
        service_2 = _make_service(store)
        status = await service_2.get_session_status(session_id)
        assert status["session_id"] == session_id
        assert status["status"] in ("active", SessionStatus.ACTIVE.value)

    @pytest.mark.asyncio
    async def test_turns_survive_restart(self) -> None:
        store = MockSessionStore()
        service_1 = _make_service(store)

        with patch.object(service_1, "_run_persistent_loop", new_callable=AsyncMock):
            session_id = await service_1.create_and_run(
                instruction="Turn survival test", options=InstructOptions(),
            )

        # Persist extra turns via hooks
        turn_seq = [1]
        await service_1.persist_tool_start(session_id, "extract_pdf", {"path": "a.pdf"}, turn_seq)

        # "Restart"
        turns = await store.get_turns(session_id)
        assert len(turns) == 2  # initial user turn + tool turn

    @pytest.mark.asyncio
    async def test_metrics_survive_restart(self) -> None:
        store = MockSessionStore()
        service_1 = _make_service(store)

        with patch.object(service_1, "_run_persistent_loop", new_callable=AsyncMock):
            session_id = await service_1.create_and_run(
                instruction="Metrics survival", options=InstructOptions(),
            )

        turn_seq = [1]
        await service_1.persist_tool_start(session_id, "extract_pdf", {}, turn_seq)
        await service_1.persist_tool_complete(session_id, "extract_pdf", {"text": "ok"})

        # "Restart"
        service_2 = _make_service(store)
        record = await service_2.store.get_session(session_id)
        assert record.metrics.total_tool_calls == 1
        assert record.metrics.documents_processed == 1

    @pytest.mark.asyncio
    async def test_outputs_survive_restart(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-out-survive", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service_1 = _make_service(store)

        await service_1._register_output(
            session_id="s-out-survive",
            tool_name="write_blob",
            params={"container": "c", "path": "file.json", "data": "{}"},
            result={},
        )

        # "Restart"
        service_2 = _make_service(store)
        outputs = await service_2.store.get_outputs("s-out-survive")
        assert len(outputs) == 1
        assert outputs[0].storage_type == "blob"

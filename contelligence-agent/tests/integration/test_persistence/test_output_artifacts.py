"""AC-5: Output artifacts registered when write tools complete.

Integration test verifying output artifact creation for blob, search,
and Cosmos write tools.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.agent_models import InstructOptions
from app.models.session_models import SessionStatus
from app.services.persistent_agent_service import PersistentAgentService
from tests.conftest import MockSessionStore, create_sample_session


def _make_service(store: MockSessionStore) -> PersistentAgentService:
    blob = AsyncMock()
    session_factory = MagicMock()
    return PersistentAgentService(
        session_factory=session_factory,
        session_store=store,
        system_prompt="Test",
        blob_connector=blob,
    )


class TestOutputArtifactsRegistered:
    @pytest.mark.asyncio
    async def test_write_blob_registers_blob_artifact(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-wba", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service = _make_service(store)

        await service._register_output(
            session_id="s-wba",
            tool_name="write_blob",
            params={
                "container": "results",
                "path": "output.json",
                "data": '{"key": "value"}',
                "content_type": "application/json",
            },
            result={"status": "ok"},
        )

        outputs = await store.get_outputs("s-wba")
        assert len(outputs) == 1
        assert outputs[0].storage_type == "blob"
        assert outputs[0].storage_location == "results/output.json"
        assert outputs[0].content_type == "application/json"
        assert outputs[0].size_bytes > 0

    @pytest.mark.asyncio
    async def test_upload_to_search_registers_index_artifact(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-usa", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service = _make_service(store)

        await service._register_output(
            session_id="s-usa",
            tool_name="upload_to_search",
            params={"index": "my-index"},
            result={"uploaded": 100},
        )

        outputs = await store.get_outputs("s-usa")
        assert len(outputs) == 1
        assert outputs[0].storage_type == "search_index"
        assert outputs[0].storage_location == "my-index"
        assert outputs[0].record_count == 100

    @pytest.mark.asyncio
    async def test_upsert_cosmos_registers_cosmos_artifact(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-uca", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service = _make_service(store)

        await service._register_output(
            session_id="s-uca",
            tool_name="upsert_cosmos",
            params={"database": "db1", "container": "col1"},
            result={"id": "doc-1"},
        )

        outputs = await store.get_outputs("s-uca")
        assert len(outputs) == 1
        assert outputs[0].storage_type == "cosmos"
        assert "db1/col1" in outputs[0].storage_location

    @pytest.mark.asyncio
    async def test_non_write_tool_no_artifact(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-nwa", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service = _make_service(store)

        await service._register_output(
            session_id="s-nwa",
            tool_name="extract_pdf",
            params={"container": "c", "path": "doc.pdf"},
            result={"text": "content"},
        )

        outputs = await store.get_outputs("s-nwa")
        assert len(outputs) == 0

    @pytest.mark.asyncio
    async def test_outputs_produced_metric_incremented(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-metric", status=SessionStatus.ACTIVE)
        await store.save_session(session)
        service = _make_service(store)

        # Register two outputs
        for i in range(2):
            await service._register_output(
                session_id="s-metric",
                tool_name="write_blob",
                params={"container": "c", "path": f"file_{i}.json", "data": "x"},
                result={},
            )

        record = await store.get_session("s-metric")
        assert record.metrics.outputs_produced == 2

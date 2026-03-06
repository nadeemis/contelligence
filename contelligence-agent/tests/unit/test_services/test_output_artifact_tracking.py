"""Unit tests for output artifact tracking (WS-5, AC-5).

Verifies that write tools (write_blob, upload_to_search, upsert_cosmos)
automatically register output artifacts via _register_output.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.session_models import SessionMetrics, SessionRecord, SessionStatus
from app.services.persistent_agent_service import PersistentAgentService, WRITE_TOOLS
from tests.conftest import MockSessionStore, create_sample_session


def _make_service(
    store: MockSessionStore | None = None,
) -> PersistentAgentService:
    """Build a PersistentAgentService with mocked dependencies."""
    if store is None:
        store = MockSessionStore()
    blob = AsyncMock()
    session_factory = MagicMock()
    return PersistentAgentService(
        session_factory=session_factory,
        session_store=store,
        system_prompt="Test prompt",
        blob_connector=blob,
    )


class TestWriteToolsConstant:
    def test_includes_expected_tools(self) -> None:
        assert "write_blob" in WRITE_TOOLS
        assert "upload_to_search" in WRITE_TOOLS
        assert "upsert_cosmos" in WRITE_TOOLS
        assert len(WRITE_TOOLS) == 3


class TestInferType:
    def test_json_type(self) -> None:
        service = _make_service()
        assert service._infer_type("application/json") == "json"

    def test_csv_type(self) -> None:
        service = _make_service()
        assert service._infer_type("text/csv") == "csv"

    def test_pdf_type(self) -> None:
        service = _make_service()
        assert service._infer_type("application/pdf") == "pdf"

    def test_default_type(self) -> None:
        service = _make_service()
        result = service._infer_type("application/octet-stream")
        assert isinstance(result, str)


class TestRegisterOutputWriteBlob:
    @pytest.mark.asyncio
    async def test_write_blob_creates_artifact(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-wb", status=SessionStatus.ACTIVE)
        await store.save_session(session)

        service = _make_service(store=store)

        await service._register_output(
            session_id="s-wb",
            tool_name="write_blob",
            params={
                "container": "output-data",
                "path": "results/report.json",
                "data": '{"key": "value"}',
                "content_type": "application/json",
            },
            result={"status": "uploaded"},
        )

        outputs = await store.get_outputs("s-wb")
        assert len(outputs) == 1
        artifact = outputs[0]
        assert artifact.session_id == "s-wb"
        assert artifact.name == "report.json"
        assert artifact.storage_type == "blob"
        assert "output-data/results/report.json" in artifact.storage_location
        assert artifact.content_type == "application/json"

    @pytest.mark.asyncio
    async def test_write_blob_increments_outputs_metric(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-wb2", status=SessionStatus.ACTIVE)
        await store.save_session(session)

        service = _make_service(store=store)

        await service._register_output(
            session_id="s-wb2",
            tool_name="write_blob",
            params={"container": "c", "path": "p", "data": "x"},
            result={},
        )

        record = await store.get_session("s-wb2")
        assert record.metrics.outputs_produced == 1


class TestRegisterOutputUploadToSearch:
    @pytest.mark.asyncio
    async def test_upload_to_search_creates_artifact(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-us", status=SessionStatus.ACTIVE)
        await store.save_session(session)

        service = _make_service(store=store)

        await service._register_output(
            session_id="s-us",
            tool_name="upload_to_search",
            params={"index": "documents-index"},
            result={"uploaded": 50},
        )

        outputs = await store.get_outputs("s-us")
        assert len(outputs) == 1
        artifact = outputs[0]
        assert artifact.storage_type == "search_index"
        assert artifact.storage_location == "documents-index"
        assert artifact.record_count == 50


class TestRegisterOutputUpsertCosmos:
    @pytest.mark.asyncio
    async def test_upsert_cosmos_creates_artifact(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-uc", status=SessionStatus.ACTIVE)
        await store.save_session(session)

        service = _make_service(store=store)

        await service._register_output(
            session_id="s-uc",
            tool_name="upsert_cosmos",
            params={"database": "mydb", "container": "mycol"},
            result={"id": "doc-1"},
        )

        outputs = await store.get_outputs("s-uc")
        assert len(outputs) == 1
        artifact = outputs[0]
        assert artifact.storage_type == "cosmos"
        assert "mydb/mycol" in artifact.storage_location


class TestRegisterOutputNonWriteTool:
    @pytest.mark.asyncio
    async def test_non_write_tool_skipped(self) -> None:
        store = MockSessionStore()
        session = create_sample_session(session_id="s-nw", status=SessionStatus.ACTIVE)
        await store.save_session(session)

        service = _make_service(store=store)

        await service._register_output(
            session_id="s-nw",
            tool_name="extract_pdf",
            params={"container": "c", "path": "doc.pdf"},
            result={"text": "content"},
        )

        outputs = await store.get_outputs("s-nw")
        assert len(outputs) == 0

"""Unit tests for large result offloading (WS-4, AC-4).

Verifies that tool results exceeding the 50 KB threshold are offloaded
to Blob Storage and replaced with a reference stub.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.session_models import SessionMetrics, SessionRecord, SessionStatus
from app.services.persistent_agent_service import (
    LARGE_RESULT_THRESHOLD_BYTES,
    PersistentAgentService,
)
from tests.conftest import MockSessionStore, create_sample_session


def _make_service(
    store: MockSessionStore | None = None,
    blob_connector: AsyncMock | None = None,
    large_result_threshold: int = LARGE_RESULT_THRESHOLD_BYTES,
) -> PersistentAgentService:
    """Build a PersistentAgentService with mocked dependencies."""
    if store is None:
        store = MockSessionStore()
    if blob_connector is None:
        blob_connector = AsyncMock()
        blob_connector.upload_blob = AsyncMock()
        blob_connector.download_blob = AsyncMock(return_value=b'{"key": "value"}')

    session_factory = MagicMock()
    return PersistentAgentService(
        session_factory=session_factory,
        session_store=store,
        system_prompt="Test prompt",
        blob_connector=blob_connector,
        outputs_container="agent-outputs",
        large_result_threshold=large_result_threshold,
    )


class TestLargeResultThreshold:
    """Verify the threshold constant is 50 KB."""

    def test_constant_value(self) -> None:
        assert LARGE_RESULT_THRESHOLD_BYTES == 50_000


class TestStoreAndFetchLargeResult:
    @pytest.mark.asyncio
    async def test_store_large_result_uploads_to_blob(self) -> None:
        blob = AsyncMock()
        blob.upload_blob = AsyncMock()
        service = _make_service(blob_connector=blob)

        large_result = {"data": "x" * 60_000}
        ref = await service._store_large_result("sess-1", "extract_pdf", large_result)

        blob.upload_blob.assert_awaited_once()
        call_args = blob.upload_blob.call_args
        assert call_args.kwargs["container"] == "agent-outputs"
        assert "sess-1/tool_results/extract_pdf_" in call_args.kwargs["path"]
        assert call_args.kwargs["content_type"] == "application/json"
        assert ref.startswith("agent-outputs/sess-1/tool_results/extract_pdf_")

    @pytest.mark.asyncio
    async def test_fetch_large_result_downloads_from_blob(self) -> None:
        blob = AsyncMock()
        blob.download_blob = AsyncMock(return_value=json.dumps({"restored": True}).encode())
        service = _make_service(blob_connector=blob)

        result = await service.fetch_large_result("agent-outputs/sess-1/tool_results/extract_pdf_2025.json")

        blob.download_blob.assert_awaited_once_with(
            "agent-outputs", "sess-1/tool_results/extract_pdf_2025.json",
        )
        assert result == {"restored": True}

    @pytest.mark.asyncio
    async def test_blob_path_format(self) -> None:
        blob = AsyncMock()
        blob.upload_blob = AsyncMock()
        service = _make_service(blob_connector=blob)

        ref = await service._store_large_result("my-session", "read_blob", {"data": "x"})

        # Format: agent-outputs/{session_id}/tool_results/{tool}_{timestamp}.json
        assert ref.startswith("agent-outputs/my-session/tool_results/read_blob_")
        assert ref.endswith(".json")


class TestResultSizeDecision:
    """Verify that the persist_tool_complete method correctly decides whether to offload."""

    @pytest.mark.asyncio
    async def test_small_result_stored_inline(self) -> None:
        """Results under threshold should be stored directly, not offloaded."""
        store = MockSessionStore()
        blob = AsyncMock()
        blob.upload_blob = AsyncMock()
        service = _make_service(store=store, blob_connector=blob)

        small_result = {"data": "small"}
        # Manually invoke persist_tool_complete to test the decision logic
        session = create_sample_session(session_id="s-small", status=SessionStatus.ACTIVE)
        await store.save_session(session)

        # The service uses persist_tool_complete which checks size
        from app.models.session_models import ConversationTurn, ToolCallRecord

        now = datetime.now(timezone.utc)
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            session_id="s-small",
            sequence=1,
            timestamp=now,
            role="tool",
            tool_call=ToolCallRecord(
                tool_name="read_blob",
                parameters={"container": "data", "path": "file.txt"},
                started_at=now,
            ),
        )
        await store.save_turn(turn)

        await service.persist_tool_complete(
            session_id="s-small",
            tool_name="read_blob",
            result=small_result,
        )

        # Blob upload should NOT have been called since result is small
        blob.upload_blob.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_large_result_offloaded(self) -> None:
        """Results over threshold should be offloaded to blob storage."""
        store = MockSessionStore()
        blob = AsyncMock()
        blob.upload_blob = AsyncMock()
        service = _make_service(store=store, blob_connector=blob)

        large_result = {"data": "x" * 60_000}
        session = create_sample_session(session_id="s-large", status=SessionStatus.ACTIVE)
        await store.save_session(session)

        from app.models.session_models import ConversationTurn, ToolCallRecord

        now = datetime.now(timezone.utc)
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            session_id="s-large",
            sequence=1,
            timestamp=now,
            role="tool",
            tool_call=ToolCallRecord(
                tool_name="extract_pdf",
                parameters={"container": "data", "path": "big.pdf"},
                started_at=now,
            ),
        )
        await store.save_turn(turn)

        await service.persist_tool_complete(
            session_id="s-large",
            tool_name="extract_pdf",
            result=large_result,
        )

        # Blob upload SHOULD have been called
        blob.upload_blob.assert_awaited_once()

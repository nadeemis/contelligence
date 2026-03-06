"""AC-8: GET /sessions/{id}/logs returns ordered conversation turns.

Integration tests using FastAPI TestClient with MockSessionStore.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_agent_service, get_session_store
from app.models.session_models import SessionStatus
from tests.conftest import (
    MockSessionStore,
    create_sample_session,
    create_sample_turns,
)


def _create_test_app(store: MockSessionStore) -> FastAPI:
    from app.routers import agent, health

    app = FastAPI()
    app.include_router(agent.router, prefix="/api/agent")
    app.include_router(health.router)
    app.dependency_overrides[get_session_store] = lambda: store
    svc = MagicMock()
    app.dependency_overrides[get_agent_service] = lambda: svc
    return app


class TestGetSessionLogs:
    @pytest.fixture(autouse=True)
    async def setup(self) -> None:
        self.store = MockSessionStore()
        session = create_sample_session(session_id="s-logs-1")
        await self.store.save_session(session)
        # Seed 5 turns for this session
        turns = create_sample_turns("s-logs-1", count=5)
        for t in turns:
            await self.store.save_turn(t)
        self.app = _create_test_app(self.store)
        self.client = TestClient(self.app)

    def test_returns_turns_in_order(self) -> None:
        resp = self.client.get("/api/agent/sessions/s-logs-1/logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "s-logs-1"
        sequences = [t["sequence"] for t in body["turns"]]
        assert sequences == sorted(sequences)

    def test_returns_correct_turn_count(self) -> None:
        resp = self.client.get("/api/agent/sessions/s-logs-1/logs")
        assert len(resp.json()["turns"]) == 5

    def test_tool_results_truncated_by_default(self) -> None:
        """When include_tool_results=False (default), tool call results are truncated."""
        from app.models.session_models import ConversationTurn, ToolCallRecord
        from datetime import datetime, timezone
        import uuid

        now = datetime.now(timezone.utc)
        tool_turn = ConversationTurn(
            id=str(uuid.uuid4()),
            session_id="s-logs-1",
            sequence=10,
            timestamp=now,
            role="tool",
            tool_call=ToolCallRecord(
                tool_name="extract_pdf",
                parameters={"path": "big.pdf"},
                started_at=now,
                completed_at=now,
                duration_ms=100,
                status="success",
                result={"text": "Very long content..."},
            ),
        )
        # Use sync-compatible approach — the store is async, run in event loop
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.store.save_turn(tool_turn))

        resp = self.client.get("/api/agent/sessions/s-logs-1/logs")
        body = resp.json()
        tool_turns = [t for t in body["turns"] if t.get("tool_call")]
        if tool_turns:
            for tt in tool_turns:
                result = tt["tool_call"].get("result", {})
                assert result.get("_truncated") is True

    def test_tool_results_included_when_requested(self) -> None:
        from app.models.session_models import ConversationTurn, ToolCallRecord
        from datetime import datetime, timezone
        import uuid

        now = datetime.now(timezone.utc)
        tool_turn = ConversationTurn(
            id=str(uuid.uuid4()),
            session_id="s-logs-1",
            sequence=20,
            timestamp=now,
            role="tool",
            tool_call=ToolCallRecord(
                tool_name="extract_pdf",
                parameters={"path": "doc.pdf"},
                started_at=now,
                completed_at=now,
                duration_ms=200,
                status="success",
                result={"text": "Extracted text content"},
            ),
        )
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.store.save_turn(tool_turn))

        resp = self.client.get(
            "/api/agent/sessions/s-logs-1/logs",
            params={"include_tool_results": "true"},
        )
        body = resp.json()
        seq20 = [t for t in body["turns"] if t["sequence"] == 20]
        assert len(seq20) == 1
        assert seq20[0]["tool_call"]["result"]["text"] == "Extracted text content"

    def test_404_for_unknown_session(self) -> None:
        resp = self.client.get("/api/agent/sessions/does-not-exist/logs")
        assert resp.status_code == 404

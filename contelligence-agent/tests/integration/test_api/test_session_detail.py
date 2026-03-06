"""AC-7: GET /sessions/{session_id} returns the full session record.

Integration tests using FastAPI TestClient with MockSessionStore.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_agent_service, get_session_store
from app.models.session_models import SessionStatus
from tests.conftest import MockSessionStore, create_sample_session


def _create_test_app(store: MockSessionStore) -> FastAPI:
    from app.routers import agent, health

    app = FastAPI()
    app.include_router(agent.router, prefix="/api/agent")
    app.include_router(health.router)
    app.dependency_overrides[get_session_store] = lambda: store
    svc = MagicMock()
    svc.get_session_status = AsyncMock(return_value={"session_id": "x", "status": "active"})
    app.dependency_overrides[get_agent_service] = lambda: svc
    return app


class TestGetSessionDetail:
    @pytest.fixture(autouse=True)
    async def setup(self) -> None:
        self.store = MockSessionStore()
        self.session = create_sample_session(session_id="s-detail-1")
        await self.store.save_session(self.session)
        self.app = _create_test_app(self.store)
        self.client = TestClient(self.app)

    def test_returns_full_record(self) -> None:
        resp = self.client.get("/api/agent/sessions/s-detail-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "s-detail-1"
        assert body["instruction"] == "Test instruction"
        assert "metrics" in body
        assert "created_at" in body
        assert "status" in body

    def test_returns_404_for_unknown_session(self) -> None:
        resp = self.client.get("/api/agent/sessions/does-not-exist")
        assert resp.status_code == 404

    def test_includes_summary_when_present(self) -> None:
        self.session.summary = "All done"
        resp = self.client.get("/api/agent/sessions/s-detail-1")
        body = resp.json()
        assert body["summary"] == "All done"

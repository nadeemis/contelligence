"""AC-9: GET /sessions/{id}/outputs lists artifacts produced.

Integration tests using FastAPI TestClient with MockSessionStore.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_agent_service, get_session_store
from tests.conftest import (
    MockSessionStore,
    create_sample_outputs,
    create_sample_session,
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


class TestGetSessionOutputs:
    @pytest.fixture(autouse=True)
    async def setup(self) -> None:
        self.store = MockSessionStore()
        session = create_sample_session(session_id="s-out-1")
        await self.store.save_session(session)
        outputs = create_sample_outputs("s-out-1", count=3)
        for o in outputs:
            await self.store.save_output(o)
        self.app = _create_test_app(self.store)
        self.client = TestClient(self.app)

    def test_returns_outputs(self) -> None:
        resp = self.client.get("/api/agent/sessions/s-out-1/outputs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "s-out-1"
        assert len(body["outputs"]) == 3

    def test_output_shape(self) -> None:
        resp = self.client.get("/api/agent/sessions/s-out-1/outputs")
        output = resp.json()["outputs"][0]
        assert "id" in output
        assert "name" in output
        assert "storage_type" in output
        assert "storage_location" in output
        assert "created_at" in output

    def test_empty_outputs(self) -> None:
        """A session with no outputs should return an empty list."""
        import asyncio

        async def _seed():
            session = create_sample_session(session_id="s-out-empty")
            await self.store.save_session(session)

        asyncio.get_event_loop().run_until_complete(_seed())
        resp = self.client.get("/api/agent/sessions/s-out-empty/outputs")
        assert resp.status_code == 200
        assert resp.json()["outputs"] == []

    def test_404_for_unknown_session(self) -> None:
        resp = self.client.get("/api/agent/sessions/nope/outputs")
        assert resp.status_code == 404

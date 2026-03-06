"""AC-6: GET /sessions returns filtered session list.

Integration tests using FastAPI TestClient with a ``MockSessionStore``
injected via dependency overrides.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_session_store
from app.models.session_models import SessionStatus
from tests.conftest import MockSessionStore, create_sample_session


def _create_test_app(store: MockSessionStore) -> FastAPI:
    from app.dependencies import get_agent_service
    from app.routers import agent, health
    from unittest.mock import AsyncMock, MagicMock

    app = FastAPI()
    app.include_router(agent.router, prefix="/api/agent")
    app.include_router(health.router)

    # Override both dependencies
    app.dependency_overrides[get_session_store] = lambda: store
    # Provide a stub agent service for other routes
    svc = MagicMock()
    svc.create_and_run = AsyncMock(return_value="mock-id")
    app.dependency_overrides[get_agent_service] = lambda: svc
    return app


class TestListSessions:
    @pytest.fixture(autouse=True)
    async def setup(self) -> None:
        self.store = MockSessionStore()
        # Seed sessions
        now = datetime.now(timezone.utc)
        for i in range(5):
            s = create_sample_session(
                session_id=f"s-{i}",
                status=SessionStatus.COMPLETED if i % 2 == 0 else SessionStatus.ACTIVE,
                user_id="user-a" if i < 3 else "user-b",
            )
            s.created_at = now - timedelta(hours=5 - i)
            await self.store.save_session(s)
        self.app = _create_test_app(self.store)
        self.client = TestClient(self.app)

    def test_returns_all_sessions(self) -> None:
        resp = self.client.get("/api/agent/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 5

    def test_filter_by_status(self) -> None:
        resp = self.client.get("/api/agent/sessions", params={"status": "completed"})
        assert resp.status_code == 200
        for item in resp.json():
            assert item["status"] == "completed"

    def test_filter_by_user_id(self) -> None:
        resp = self.client.get("/api/agent/sessions", params={"user_id": "user-a"})
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_limit(self) -> None:
        resp = self.client.get("/api/agent/sessions", params={"limit": 2})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_newest_first(self) -> None:
        resp = self.client.get("/api/agent/sessions")
        items = resp.json()
        timestamps = [item["created_at"] for item in items]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_session_list_item_shape(self) -> None:
        resp = self.client.get("/api/agent/sessions")
        item = resp.json()[0]
        assert "id" in item
        assert "status" in item
        assert "instruction" in item
        assert "model" in item
        assert "metrics" in item
        assert "created_at" in item

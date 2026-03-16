"""Integration tests for DELETE /sessions/{session_id} — permanent session deletion.

Tests cover:
- Successful deletion of session and all related data
- 404 when session does not exist
- RBAC: non-admin users cannot delete other users' sessions
- RBAC: admin users can delete any session
- Deletion of active sessions (cancels first)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.middleware import get_current_user
from app.auth.models import Role, User
from app.dependencies import get_agent_service, get_session_store
from app.models.session_models import SessionStatus
from tests.conftest import (
    MockSessionStore,
    create_sample_outputs,
    create_sample_session,
    create_sample_turns,
)

_ADMIN_USER = User(oid="admin-001", name="Admin", roles=[Role.ADMIN])
_REGULAR_USER = User(oid="user-001", name="Regular User", roles=[Role.VIEWER])
_OTHER_USER = User(oid="user-002", name="Other User", roles=[Role.VIEWER])


def _create_test_app(
    store: MockSessionStore,
    agent_service: MagicMock | None = None,
    user: User = _ADMIN_USER,
) -> FastAPI:
    from app.routers import agent, health

    app = FastAPI()
    app.include_router(agent.router, prefix="/api")
    app.include_router(health.router)

    app.dependency_overrides[get_session_store] = lambda: store

    if agent_service is None:
        agent_service = MagicMock()
        agent_service.store = store
        agent_service.delete_session = AsyncMock(
            return_value={
                "session_id": "placeholder",
                "turns_deleted": 0,
                "outputs_deleted": 0,
                "events_deleted": 0,
                "blobs_deleted": 0,
            },
        )

    app.dependency_overrides[get_agent_service] = lambda: agent_service

    async def _mock_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = _mock_current_user

    return app


class TestDeleteSession:

    @pytest.fixture(autouse=True)
    async def setup(self) -> None:
        self.store = MockSessionStore()
        self.session = create_sample_session(
            session_id="s-del-1", user_id="admin-001",
        )
        await self.store.save_session(self.session)

        # Add related data
        for t in create_sample_turns("s-del-1", count=3):
            await self.store.save_turn(t)
        for o in create_sample_outputs("s-del-1", count=2):
            await self.store.save_output(o)

    def test_successful_deletion(self) -> None:
        """DELETE /sessions/{id} returns 200 with deletion summary."""
        svc = MagicMock()
        svc.store = self.store
        svc.delete_session = AsyncMock(return_value={
            "session_id": "s-del-1",
            "turns_deleted": 3,
            "outputs_deleted": 2,
            "events_deleted": 0,
            "blobs_deleted": 2,
        })
        app = _create_test_app(self.store, agent_service=svc)
        client = TestClient(app)

        resp = client.delete("/api/agent/sessions/s-del-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert body["session_id"] == "s-del-1"
        assert body["turns_deleted"] == 3
        assert body["outputs_deleted"] == 2
        assert body["blobs_deleted"] == 2
        svc.delete_session.assert_awaited_once_with(session_id="s-del-1")

    def test_returns_404_for_unknown_session(self) -> None:
        """DELETE /sessions/{id} returns 404 when session does not exist."""
        svc = MagicMock()
        svc.store = self.store

        from app.models.exceptions import SessionNotFoundError
        svc.delete_session = AsyncMock(
            side_effect=SessionNotFoundError("not-found"),
        )
        app = _create_test_app(self.store, agent_service=svc)
        client = TestClient(app)

        resp = client.delete("/api/agent/sessions/not-found")
        assert resp.status_code == 404

    def test_non_admin_can_delete_own_session(self) -> None:
        """Non-admin user can delete their own session."""
        session = create_sample_session(
            session_id="s-del-own", user_id="user-001",
        )
        # synchronously add to store
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.store.save_session(session))

        svc = MagicMock()
        svc.store = self.store
        svc.delete_session = AsyncMock(return_value={
            "session_id": "s-del-own",
            "turns_deleted": 0,
            "outputs_deleted": 0,
            "events_deleted": 0,
            "blobs_deleted": 0,
        })
        app = _create_test_app(self.store, agent_service=svc, user=_REGULAR_USER)
        client = TestClient(app)

        resp = client.delete("/api/agent/sessions/s-del-own")
        assert resp.status_code == 200
        svc.delete_session.assert_awaited_once()

    def test_non_admin_cannot_delete_other_users_session(self) -> None:
        """Non-admin user gets 403 when trying to delete another user's session."""
        session = create_sample_session(
            session_id="s-del-other", user_id="user-002",
        )
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.store.save_session(session))

        svc = MagicMock()
        svc.store = self.store
        svc.delete_session = AsyncMock()
        app = _create_test_app(self.store, agent_service=svc, user=_REGULAR_USER)
        client = TestClient(app)

        resp = client.delete("/api/agent/sessions/s-del-other")
        assert resp.status_code == 403
        svc.delete_session.assert_not_awaited()

    def test_admin_can_delete_any_session(self) -> None:
        """Admin user can delete sessions belonging to other users."""
        session = create_sample_session(
            session_id="s-del-admin", user_id="user-002",
        )
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.store.save_session(session))

        svc = MagicMock()
        svc.store = self.store
        svc.delete_session = AsyncMock(return_value={
            "session_id": "s-del-admin",
            "turns_deleted": 0,
            "outputs_deleted": 0,
            "events_deleted": 0,
            "blobs_deleted": 0,
        })
        app = _create_test_app(self.store, agent_service=svc, user=_ADMIN_USER)
        client = TestClient(app)

        resp = client.delete("/api/agent/sessions/s-del-admin")
        assert resp.status_code == 200
        svc.delete_session.assert_awaited_once()


class TestDeleteSessionService:
    """Unit tests for PersistentAgentService.delete_session logic."""

    @pytest.mark.asyncio
    async def test_deletes_all_related_data(self) -> None:
        """delete_session removes turns, outputs, events, blobs, and session doc."""
        store = MockSessionStore()
        session = create_sample_session(session_id="s-svc-1")
        await store.save_session(session)
        for t in create_sample_turns("s-svc-1", count=4):
            await store.save_turn(t)
        for o in create_sample_outputs("s-svc-1", count=3):
            await store.save_output(o)

        blob_connector = AsyncMock()
        blob_connector.delete_prefix = AsyncMock(return_value=5)

        from app.services.persistent_agent_service import PersistentAgentService

        svc = PersistentAgentService(
            session_factory=MagicMock(),
            session_store=store,
            system_prompt="test",
            blob_connector=blob_connector,
        )

        summary = await svc.delete_session("s-svc-1")

        assert summary["session_id"] == "s-svc-1"
        assert summary["turns_deleted"] == 4
        assert summary["outputs_deleted"] == 3
        assert summary["blobs_deleted"] == 5

        # Session should be gone from the store
        from app.models.exceptions import SessionNotFoundError
        with pytest.raises(SessionNotFoundError):
            await store.get_session("s-svc-1")

        # Turns and outputs should be empty
        assert await store.get_turns("s-svc-1") == []
        assert await store.get_outputs("s-svc-1") == []

        blob_connector.delete_prefix.assert_awaited_once_with(
            "agent-outputs", "s-svc-1/",
        )

    @pytest.mark.asyncio
    async def test_raises_for_nonexistent_session(self) -> None:
        """delete_session raises SessionNotFoundError for unknown session."""
        store = MockSessionStore()
        blob_connector = AsyncMock()

        from app.services.persistent_agent_service import PersistentAgentService
        from app.models.exceptions import SessionNotFoundError

        svc = PersistentAgentService(
            session_factory=MagicMock(),
            session_store=store,
            system_prompt="test",
            blob_connector=blob_connector,
        )

        with pytest.raises(SessionNotFoundError):
            await svc.delete_session("nonexistent")

    @pytest.mark.asyncio
    async def test_blob_failure_does_not_block_cosmos_cleanup(self) -> None:
        """If blob deletion fails, Cosmos data should still be cleaned up."""
        store = MockSessionStore()
        session = create_sample_session(session_id="s-blob-fail")
        await store.save_session(session)
        for t in create_sample_turns("s-blob-fail", count=2):
            await store.save_turn(t)

        blob_connector = AsyncMock()
        blob_connector.delete_prefix = AsyncMock(side_effect=Exception("Storage unavailable"))

        from app.services.persistent_agent_service import PersistentAgentService
        from app.models.exceptions import SessionNotFoundError

        svc = PersistentAgentService(
            session_factory=MagicMock(),
            session_store=store,
            system_prompt="test",
            blob_connector=blob_connector,
        )

        summary = await svc.delete_session("s-blob-fail")

        assert summary["turns_deleted"] == 2
        assert summary["blobs_deleted"] == 0

        # Session should still be deleted from Cosmos
        with pytest.raises(SessionNotFoundError):
            await store.get_session("s-blob-fail")

    @pytest.mark.asyncio
    async def test_cancels_active_session_before_deleting(self) -> None:
        """If the session is active in memory, it should be cancelled first."""
        store = MockSessionStore()
        session = create_sample_session(
            session_id="s-active", status=SessionStatus.ACTIVE,
        )
        await store.save_session(session)

        blob_connector = AsyncMock()
        blob_connector.delete_prefix = AsyncMock(return_value=0)

        from app.services.persistent_agent_service import PersistentAgentService

        svc = PersistentAgentService(
            session_factory=MagicMock(),
            session_store=store,
            system_prompt="test",
            blob_connector=blob_connector,
        )

        # Simulate an active in-memory session
        mock_sdk_session = AsyncMock()
        mock_sdk_session.close = AsyncMock()
        svc.active_sessions["s-active"] = mock_sdk_session

        summary = await svc.delete_session("s-active")
        assert summary["session_id"] == "s-active"

        # Active session should have been removed from in-memory tracking
        assert "s-active" not in svc.active_sessions

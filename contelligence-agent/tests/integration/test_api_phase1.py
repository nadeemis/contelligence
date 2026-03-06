"""Integration tests for the FastAPI endpoints.

Uses FastAPI TestClient with mocked AgentService to validate routing,
status codes, and response shapes without hitting real Azure services.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.agent_models import InstructResponse
from app.models.exceptions import SessionNotFoundError
from app.services.agent_service import AgentService


# ---------------------------------------------------------------------------
# Build a test app with a mocked AgentService injected via dependency override
# ---------------------------------------------------------------------------

def _create_test_app(mock_agent_service: AgentService) -> FastAPI:
    """Build a FastAPI app with the agent and health routers wired up,
    overriding the agent_service dependency with a mock."""
    from app.routers import agent, health
    from app.dependencies import get_agent_service

    app = FastAPI()
    app.include_router(agent.router, prefix="/api/agent")
    app.include_router(health.router)

    app.dependency_overrides[get_agent_service] = lambda: mock_agent_service
    return app


def _make_mock_agent_service() -> MagicMock:
    """Create a MagicMock that looks like AgentService."""
    svc = MagicMock(spec=AgentService)
    svc.create_and_run = AsyncMock(return_value="mock-session-id")
    svc.send_reply = AsyncMock()
    svc.cancel = AsyncMock()
    svc.get_session_status = AsyncMock(
        return_value={"session_id": "mock-session-id", "status": "active"}
    )

    # stream_events returns an async generator.
    async def _stream(*args, **kwargs):
        yield {"event": "session_complete", "data": '{"response": "done"}'}

    svc.stream_events = _stream
    return svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_agent_service() -> MagicMock:
    return _make_mock_agent_service()


@pytest.fixture()
def client(mock_agent_service: MagicMock) -> TestClient:
    app = _create_test_app(mock_agent_service)
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /api/agent/instruct
# ---------------------------------------------------------------------------

class TestInstructEndpoint:

    def test_returns_200_with_session_id(
        self, client: TestClient, mock_agent_service: MagicMock
    ) -> None:
        response = client.post(
            "/api/agent/instruct",
            json={"instruction": "Extract and process all PDFs"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "session_id" in body
        assert body["session_id"] == "mock-session-id"
        assert body["status"] == "processing"

    def test_instruct_with_options(
        self, client: TestClient, mock_agent_service: MagicMock
    ) -> None:
        response = client.post(
            "/api/agent/instruct",
            json={
                "instruction": "Do something",
                "options": {"model": "gpt-4o", "timeout_minutes": 30},
            },
        )
        assert response.status_code == 200
        mock_agent_service.create_and_run.assert_awaited_once()

    def test_instruct_missing_instruction_returns_422(
        self, client: TestClient
    ) -> None:
        response = client.post("/api/agent/instruct", json={})
        assert response.status_code == 422

    def test_instruct_server_error_returns_500(
        self, client: TestClient, mock_agent_service: MagicMock
    ) -> None:
        mock_agent_service.create_and_run.side_effect = RuntimeError("boom")
        response = client.post(
            "/api/agent/instruct",
            json={"instruction": "fail"},
        )
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"] == "contelligence-agent"

    def test_health_includes_version(self, client: TestClient) -> None:
        response = client.get("/api/health")
        body = response.json()
        assert "version" in body


# ---------------------------------------------------------------------------
# POST /api/agent/sessions/{id}/reply
# ---------------------------------------------------------------------------

class TestReplyEndpoint:

    def test_reply_unknown_session_returns_404(
        self, client: TestClient, mock_agent_service: MagicMock
    ) -> None:
        mock_agent_service.send_reply.side_effect = SessionNotFoundError("unknown-id")
        response = client.post(
            "/api/agent/sessions/unknown-id/reply",
            json={"message": "yes"},
        )
        assert response.status_code == 404

    def test_reply_success(
        self, client: TestClient, mock_agent_service: MagicMock
    ) -> None:
        response = client.post(
            "/api/agent/sessions/mock-session-id/reply",
            json={"message": "proceed"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "sent"

    def test_reply_missing_message_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/agent/sessions/s1/reply",
            json={},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/agent/sessions/{id}
# ---------------------------------------------------------------------------

class TestCancelEndpoint:

    def test_cancel_unknown_session_returns_200(
        self, client: TestClient, mock_agent_service: MagicMock
    ) -> None:
        """DELETE should succeed gracefully even for unknown sessions."""
        response = client.delete("/api/agent/sessions/unknown-id")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "cancelled"

    def test_cancel_known_session(
        self, client: TestClient, mock_agent_service: MagicMock
    ) -> None:
        response = client.delete("/api/agent/sessions/mock-session-id")
        assert response.status_code == 200
        mock_agent_service.cancel.assert_awaited_once_with(session_id="mock-session-id")


# ---------------------------------------------------------------------------
# GET /api/agent/sessions/{id}/status
# ---------------------------------------------------------------------------

class TestStatusEndpoint:

    def test_status_returns_session_info(
        self, client: TestClient, mock_agent_service: MagicMock
    ) -> None:
        response = client.get("/api/agent/sessions/mock-session-id/status")
        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == "mock-session-id"
        assert body["status"] == "active"

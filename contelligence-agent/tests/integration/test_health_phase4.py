"""Integration test for Phase 4 — Health endpoint includes Phase 4 fields."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_returns_phase4_fields() -> None:
    """The /health endpoint should include instance_id and version 4.0.0."""
    with (
        patch("app.routers.health.get_instance_id", return_value="test-instance-id"),
        patch("app.routers.health.get_agent_service") as mock_get_svc,
        patch("app.routers.health.get_scheduler") as mock_get_sched,
        patch("app.routers.health.get_token_manager") as mock_get_tm,
    ):
        # Mock agent service
        agent_svc = MagicMock()
        agent_svc.active_sessions = {}
        mock_get_svc.return_value = agent_svc

        # Mock scheduler
        scheduler = MagicMock()
        scheduler._is_leader = False
        mock_get_sched.return_value = scheduler

        # Mock token manager
        tm = MagicMock()
        tm.health_status.return_value = {"healthy": True}
        mock_get_tm.return_value = tm

        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        data = response.json()
        assert data["version"] == "4.0.0"
        assert data["instance_id"] == "test-instance-id"
        assert "active_sessions" in data

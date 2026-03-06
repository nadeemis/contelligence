"""Integration tests for Phase 5 — Schedule, Events, Webhooks, Dashboard routers.

Uses FastAPI TestClient with mocked services on app.state to validate
routing, status codes, authentication, and response shapes.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.middleware import get_current_user
from app.auth.models import Role, User
from app.dependencies import get_settings
from app.models.exceptions import ScheduleNotFoundError
from app.models.schedule_models import (
    ScheduleRecord,
    ScheduleRunRecord,
    TriggerConfig,
    TriggerType,
)
from app.models.session_models import SessionMetrics, SessionRecord, SessionStatus

# Synthetic admin user returned by overridden dependencies.
_TEST_USER = User(
    oid="test-user",
    name="Test User",
    email="test@example.com",
    roles=[Role.ADMIN],
    tenant_id="test-tenant",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_schedule(
    *,
    schedule_id: str = "sched-001",
    name: str = "Daily Vendor",
    status: str = "active",
    trigger_type: TriggerType = TriggerType.CRON,
    webhook_id: str | None = None,
    webhook_secret: str | None = None,
) -> ScheduleRecord:
    trigger_kwargs: dict = {"type": trigger_type}
    if trigger_type == TriggerType.CRON:
        trigger_kwargs["cron"] = "0 6 * * *"
    elif trigger_type == TriggerType.INTERVAL:
        trigger_kwargs["interval_minutes"] = 60
    elif trigger_type == TriggerType.EVENT:
        trigger_kwargs["event_source"] = "blob:vendor-inbox"
    elif trigger_type == TriggerType.WEBHOOK:
        trigger_kwargs["webhook_secret"] = webhook_secret

    return ScheduleRecord(
        id=schedule_id,
        name=name,
        instruction="Process documents",
        trigger=TriggerConfig(**trigger_kwargs),
        status=status,
        webhook_id=webhook_id,
    )


def _make_run(
    *,
    run_id: str = "run-001",
    schedule_id: str = "sched-001",
    session_id: str = "sess-001",
    status: str = "running",
) -> ScheduleRunRecord:
    return ScheduleRunRecord(
        id=run_id,
        schedule_id=schedule_id,
        session_id=session_id,
        triggered_at=datetime.now(timezone.utc),
        trigger_reason="cron",
        status=status,
    )


# ---------------------------------------------------------------------------
# Test App Factory
# ---------------------------------------------------------------------------


def _create_test_app(
    *,
    schedule_service: AsyncMock | None = None,
    schedule_store: AsyncMock | None = None,
    scheduling_engine: AsyncMock | None = None,
    session_store: AsyncMock | None = None,
) -> FastAPI:
    """Build a test FastAPI app with Phase 5 routers and mocked app.state.

    Overrides ``get_current_user`` so that ``require_role`` (which depends
    on ``get_current_user`` internally) resolves to a user with the ADMIN
    role, bypassing all RBAC checks.
    """
    from app.routers.dashboard import router as dashboard_router
    from app.routers.events import router as events_router
    from app.routers.schedules import router as schedules_router
    from app.routers.webhooks import router as webhooks_router

    app = FastAPI()

    # Mount routers
    app.include_router(schedules_router, prefix="/api/schedules")
    app.include_router(events_router, prefix="/api/events")
    app.include_router(webhooks_router, prefix="/api/webhooks")
    app.include_router(dashboard_router, prefix="/api/dashboard")

    # Set mocked services on app.state
    if schedule_service:
        app.state.schedule_service = schedule_service
    if schedule_store:
        app.state.schedule_store = schedule_store
    if scheduling_engine:
        app.state.scheduling_engine = scheduling_engine
    if session_store:
        app.state.session_store = session_store

    # ---- Auth override -------------------------------------------------
    # Overriding get_current_user is sufficient: require_role internally
    # calls Depends(get_current_user), so FastAPI resolves the override.
    async def _mock_current_user() -> User:
        return _TEST_USER

    app.dependency_overrides[get_current_user] = _mock_current_user

    # get_settings is also needed since get_current_user depends on it.
    # Provide a lightweight mock with AUTH_ENABLED=False.
    _mock_settings = MagicMock()
    _mock_settings.AUTH_ENABLED = False

    app.dependency_overrides[get_settings] = lambda: _mock_settings

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_schedule_service() -> AsyncMock:
    svc = AsyncMock()
    svc.create_schedule.return_value = _make_schedule()
    svc.update_schedule.return_value = _make_schedule()
    svc.pause_schedule.return_value = _make_schedule(status="paused")
    svc.resume_schedule.return_value = _make_schedule()
    svc.delete_schedule.return_value = None
    svc.trigger_now.return_value = "sess-001"
    return svc


@pytest.fixture()
def mock_schedule_store() -> AsyncMock:
    store = AsyncMock()
    store.list_schedules.return_value = [_make_schedule()]
    store.get_schedule.return_value = _make_schedule()
    store.list_runs.return_value = [_make_run()]
    store.count_schedules.return_value = 5
    store.count_runs_since.return_value = 10
    store.get_recent_runs.return_value = [_make_run()]
    store.get_schedules_by_trigger_type.return_value = []
    return store


@pytest.fixture()
def mock_scheduling_engine() -> MagicMock:
    # Use MagicMock base because get_upcoming_runs is called *without* await
    # in the dashboard router.  Async methods are set individually.
    engine = MagicMock()
    engine.handle_event = AsyncMock(return_value=["sess-001"])
    engine.handle_webhook = AsyncMock(return_value="sess-001")
    engine.get_upcoming_runs.return_value = [
        {"schedule_id": "sched-001", "name": "Test", "next_run_at": "2026-01-01T06:00:00Z"},
    ]
    return engine


@pytest.fixture()
def mock_session_store() -> AsyncMock:
    store = AsyncMock()
    now = datetime.now(timezone.utc)
    store.list_sessions.return_value = [
        SessionRecord(
            id="sess-001",
            created_at=now,
            updated_at=now,
            status=SessionStatus.COMPLETED,
            model="gpt-4.1",
            instruction="Test",
            metrics=SessionMetrics(total_tool_calls=3, documents_processed=2),
        ),
    ]
    return store


@pytest.fixture()
def client(
    mock_schedule_service: AsyncMock,
    mock_schedule_store: AsyncMock,
    mock_scheduling_engine: MagicMock,
    mock_session_store: AsyncMock,
) -> TestClient:
    app = _create_test_app(
        schedule_service=mock_schedule_service,
        schedule_store=mock_schedule_store,
        scheduling_engine=mock_scheduling_engine,
        session_store=mock_session_store,
    )
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests — Schedules CRUD Router
# ---------------------------------------------------------------------------


class TestSchedulesRouter:
    """Tests for /api/schedules endpoints."""

    def test_create_schedule(
        self, client: TestClient, mock_schedule_service: AsyncMock,
    ) -> None:
        body = {
            "name": "Test Schedule",
            "instruction": "Process documents",
            "trigger": {"type": "cron", "cron": "0 6 * * *"},
        }
        response = client.post("/api/schedules", json=body)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Daily Vendor"
        mock_schedule_service.create_schedule.assert_awaited_once()

    def test_list_schedules(
        self, client: TestClient, mock_schedule_store: AsyncMock,
    ) -> None:
        response = client.get("/api/schedules")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_get_schedule(
        self, client: TestClient, mock_schedule_store: AsyncMock,
    ) -> None:
        response = client.get("/api/schedules/sched-001")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "sched-001"

    def test_get_schedule_not_found(
        self, client: TestClient, mock_schedule_store: AsyncMock,
    ) -> None:
        mock_schedule_store.get_schedule.side_effect = ScheduleNotFoundError("nope")
        response = client.get("/api/schedules/nonexistent")
        assert response.status_code == 404

    def test_update_schedule(
        self, client: TestClient, mock_schedule_service: AsyncMock,
    ) -> None:
        body = {"name": "Updated Name"}
        response = client.patch("/api/schedules/sched-001", json=body)
        assert response.status_code == 200
        mock_schedule_service.update_schedule.assert_awaited_once()

    def test_delete_schedule(
        self, client: TestClient, mock_schedule_service: AsyncMock,
    ) -> None:
        response = client.delete("/api/schedules/sched-001")
        assert response.status_code == 204
        mock_schedule_service.delete_schedule.assert_awaited_once()

    def test_pause_schedule(
        self, client: TestClient, mock_schedule_service: AsyncMock,
    ) -> None:
        response = client.post("/api/schedules/sched-001/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"

    def test_resume_schedule(
        self, client: TestClient, mock_schedule_service: AsyncMock,
    ) -> None:
        response = client.post("/api/schedules/sched-001/resume")
        assert response.status_code == 200

    def test_trigger_now(
        self, client: TestClient, mock_schedule_service: AsyncMock,
    ) -> None:
        response = client.post("/api/schedules/sched-001/trigger")
        assert response.status_code == 202
        data = response.json()
        assert data["session_id"] == "sess-001"
        assert data["trigger_reason"] == "manual"

    def test_list_runs(
        self, client: TestClient, mock_schedule_store: AsyncMock,
    ) -> None:
        response = client.get("/api/schedules/sched-001/runs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1


# ---------------------------------------------------------------------------
# Tests — Events Router
# ---------------------------------------------------------------------------


class TestEventsRouter:
    """Tests for /api/events endpoint."""

    def test_subscription_validation_handshake(
        self, client: TestClient,
    ) -> None:
        """Event Grid sends a validation event on subscription creation."""
        body = [{
            "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
            "data": {"validationCode": "abc-123"},
        }]
        response = client.post("/api/events", json=body)
        assert response.status_code == 200
        data = response.json()
        assert data["validationResponse"] == "abc-123"

    def test_event_dispatch(
        self,
        client: TestClient,
        mock_scheduling_engine: MagicMock,
    ) -> None:
        body = [{
            "eventType": "Microsoft.Storage.BlobCreated",
            "source": "/subscriptions/xxx/storageAccounts/test",
            "subject": "/containers/vendor-inbox/file.pdf",
        }]
        response = client.post("/api/events", json=body)
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True
        assert data["events_processed"] == 1
        mock_scheduling_engine.handle_event.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests — Webhooks Router
# ---------------------------------------------------------------------------


class TestWebhooksRouter:
    """Tests for /api/webhooks/{webhook_id} endpoint."""

    def test_webhook_no_matching_schedule(
        self, client: TestClient, mock_schedule_store: AsyncMock,
    ) -> None:
        mock_schedule_store.get_schedules_by_trigger_type.return_value = []
        response = client.post(
            "/api/webhooks/wh_nonexistent",
            json={"event": "test"},
        )
        assert response.status_code == 404

    def test_webhook_valid_no_secret(
        self,
        client: TestClient,
        mock_schedule_store: AsyncMock,
        mock_scheduling_engine: MagicMock,
    ) -> None:
        """Webhook with no HMAC secret configured should pass."""
        schedule = _make_schedule(
            trigger_type=TriggerType.WEBHOOK,
            webhook_id="wh_abc123",
        )
        mock_schedule_store.get_schedules_by_trigger_type.return_value = [schedule]

        response = client.post(
            "/api/webhooks/wh_abc123",
            json={"event": "test"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True
        assert data["session_id"] == "sess-001"

    def test_webhook_invalid_signature(
        self,
        client: TestClient,
        mock_schedule_store: AsyncMock,
    ) -> None:
        schedule = _make_schedule(
            trigger_type=TriggerType.WEBHOOK,
            webhook_id="wh_sec123",
            webhook_secret="my-secret",
        )
        mock_schedule_store.get_schedules_by_trigger_type.return_value = [schedule]

        response = client.post(
            "/api/webhooks/wh_sec123",
            json={"event": "test"},
            headers={"X-Webhook-Signature": "sha256=badsig"},
        )
        assert response.status_code == 401

    def test_webhook_valid_hmac(
        self,
        client: TestClient,
        mock_schedule_store: AsyncMock,
        mock_scheduling_engine: MagicMock,
    ) -> None:
        from app.utils.hmac_validation import compute_signature

        secret = "my-secret"
        body = json.dumps({"event": "test"}).encode()
        sig = compute_signature(body, secret)

        schedule = _make_schedule(
            trigger_type=TriggerType.WEBHOOK,
            webhook_id="wh_hmac123",
            webhook_secret=secret,
        )
        mock_schedule_store.get_schedules_by_trigger_type.return_value = [schedule]

        response = client.post(
            "/api/webhooks/wh_hmac123",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True


# ---------------------------------------------------------------------------
# Tests — Dashboard Router
# ---------------------------------------------------------------------------


class TestDashboardRouter:
    """Tests for /api/dashboard endpoints."""

    def test_metrics(self, client: TestClient) -> None:
        response = client.get("/api/dashboard/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "total_sessions" in data
        assert "active_schedules" in data
        assert "error_rate" in data

    def test_metrics_custom_days(self, client: TestClient) -> None:
        response = client.get("/api/dashboard/metrics?days=30")
        assert response.status_code == 200

    def test_activity_feed(self, client: TestClient) -> None:
        response = client.get("/api/dashboard/activity")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_upcoming_runs(self, client: TestClient) -> None:
        response = client.get("/api/dashboard/upcoming")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

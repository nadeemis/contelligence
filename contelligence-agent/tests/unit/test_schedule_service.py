"""Unit tests for Phase 5 — Schedule Service (schedule_service.py).

Tests business logic for schedule CRUD operations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schedule_models import (
    CreateScheduleRequest,
    ScheduleRecord,
    TriggerConfig,
    TriggerType,
    UpdateScheduleRequest,
)
from app.services.schedule_service import ScheduleService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cron_request(
    *,
    name: str = "Test Schedule",
    cron: str = "0 6 * * *",
    enabled: bool = True,
) -> CreateScheduleRequest:
    return CreateScheduleRequest(
        name=name,
        instruction="Process documents",
        trigger=TriggerConfig(type=TriggerType.CRON, cron=cron),
        enabled=enabled,
    )


def _make_webhook_request(
    *,
    name: str = "Webhook Schedule",
    secret: str | None = None,
) -> CreateScheduleRequest:
    return CreateScheduleRequest(
        name=name,
        instruction="Handle webhook data",
        trigger=TriggerConfig(
            type=TriggerType.WEBHOOK,
            webhook_secret=secret,
        ),
    )


def _make_schedule(
    *,
    schedule_id: str = "sched-001",
    status: str = "active",
) -> ScheduleRecord:
    return ScheduleRecord(
        id=schedule_id,
        name="Existing Schedule",
        instruction="Do something",
        trigger=TriggerConfig(type=TriggerType.CRON, cron="0 * * * *"),
        status=status,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_store() -> AsyncMock:
    store = AsyncMock()
    store.save_schedule.return_value = None
    store.get_schedule.return_value = _make_schedule()
    return store


@pytest.fixture()
def mock_engine() -> AsyncMock:
    engine = AsyncMock()
    engine.add_schedule.return_value = None
    engine.update_schedule.return_value = None
    engine.pause_schedule.return_value = _make_schedule(status="paused")
    engine.resume_schedule.return_value = _make_schedule(status="active")
    engine.delete_schedule.return_value = None
    engine.fire_schedule.return_value = "sess-001"
    return engine


@pytest.fixture()
def service(mock_store: AsyncMock, mock_engine: AsyncMock) -> ScheduleService:
    return ScheduleService(
        store=mock_store,
        engine=mock_engine,
        agent_base_url="http://localhost:8000",
    )


# ---------------------------------------------------------------------------
# Tests — Create
# ---------------------------------------------------------------------------


class TestCreateSchedule:
    """Tests for ScheduleService.create_schedule."""

    @pytest.mark.asyncio
    async def test_create_cron_schedule(
        self,
        service: ScheduleService,
        mock_store: AsyncMock,
        mock_engine: AsyncMock,
    ) -> None:
        request = _make_cron_request()
        result = await service.create_schedule(request, created_by="user-001")

        assert result.name == "Test Schedule"
        assert result.status == "active"
        assert result.created_by == "user-001"
        assert result.trigger.type == TriggerType.CRON

        mock_store.save_schedule.assert_awaited_once()
        mock_engine.add_schedule.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_paused_schedule(
        self,
        service: ScheduleService,
        mock_engine: AsyncMock,
    ) -> None:
        request = _make_cron_request(enabled=False)
        result = await service.create_schedule(request)

        assert result.status == "paused"
        # Should NOT register with engine when paused
        mock_engine.add_schedule.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_webhook_generates_url(
        self,
        service: ScheduleService,
    ) -> None:
        request = _make_webhook_request()
        result = await service.create_schedule(request)

        assert result.webhook_id is not None
        assert result.webhook_id.startswith("wh_")
        assert result.webhook_url is not None
        assert "api/webhooks" in result.webhook_url
        assert result.webhook_id in result.webhook_url

    @pytest.mark.asyncio
    async def test_create_assigns_uuid_id(
        self,
        service: ScheduleService,
    ) -> None:
        request = _make_cron_request()
        result = await service.create_schedule(request)

        # Should be a valid UUID
        uuid.UUID(result.id)  # raises ValueError if invalid


# ---------------------------------------------------------------------------
# Tests — Update
# ---------------------------------------------------------------------------


class TestUpdateSchedule:
    """Tests for ScheduleService.update_schedule."""

    @pytest.mark.asyncio
    async def test_update_name(
        self,
        service: ScheduleService,
        mock_store: AsyncMock,
        mock_engine: AsyncMock,
    ) -> None:
        update_req = UpdateScheduleRequest(name="New Name")
        result = await service.update_schedule("sched-001", update_req)

        assert result.name == "New Name"
        mock_store.save_schedule.assert_awaited_once()
        mock_engine.update_schedule.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_trigger_to_webhook_generates_id(
        self,
        service: ScheduleService,
        mock_store: AsyncMock,
    ) -> None:
        update_req = UpdateScheduleRequest(
            trigger=TriggerConfig(type=TriggerType.WEBHOOK),
        )
        result = await service.update_schedule("sched-001", update_req)

        assert result.webhook_id is not None
        assert result.webhook_id.startswith("wh_")

    @pytest.mark.asyncio
    async def test_update_instruction(
        self,
        service: ScheduleService,
        mock_store: AsyncMock,
    ) -> None:
        update_req = UpdateScheduleRequest(instruction="New instruction")
        result = await service.update_schedule("sched-001", update_req)
        assert result.instruction == "New instruction"


# ---------------------------------------------------------------------------
# Tests — Pause / Resume / Delete
# ---------------------------------------------------------------------------


class TestLifecycleOps:
    """Tests for pause, resume, delete, trigger_now."""

    @pytest.mark.asyncio
    async def test_pause(
        self,
        service: ScheduleService,
        mock_engine: AsyncMock,
    ) -> None:
        result = await service.pause_schedule("sched-001")
        mock_engine.pause_schedule.assert_awaited_once_with("sched-001")
        assert result.status == "paused"

    @pytest.mark.asyncio
    async def test_resume(
        self,
        service: ScheduleService,
        mock_engine: AsyncMock,
    ) -> None:
        result = await service.resume_schedule("sched-001")
        mock_engine.resume_schedule.assert_awaited_once_with("sched-001")

    @pytest.mark.asyncio
    async def test_delete(
        self,
        service: ScheduleService,
        mock_engine: AsyncMock,
    ) -> None:
        await service.delete_schedule("sched-001")
        mock_engine.delete_schedule.assert_awaited_once_with("sched-001")

    @pytest.mark.asyncio
    async def test_trigger_now(
        self,
        service: ScheduleService,
        mock_engine: AsyncMock,
    ) -> None:
        result = await service.trigger_now("sched-001")
        assert result == "sess-001"
        mock_engine.fire_schedule.assert_awaited_once_with(
            "sched-001", trigger_reason="manual",
        )

    @pytest.mark.asyncio
    async def test_trigger_now_failure(
        self,
        service: ScheduleService,
        mock_engine: AsyncMock,
    ) -> None:
        mock_engine.fire_schedule.return_value = None
        result = await service.trigger_now("sched-001")
        assert result is None

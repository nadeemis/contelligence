"""Unit tests for Phase 5 — Schedule Store (schedule_store.py).

Uses mocked Cosmos DB containers to test CRUD and query operations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.exceptions import ScheduleNotFoundError
from app.models.schedule_models import (
    ScheduleRecord,
    ScheduleRunRecord,
    TriggerConfig,
    TriggerType,
)
from app.services.schedule_store import ScheduleStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_schedule(
    *,
    schedule_id: str = "sched-001",
    name: str = "Test Schedule",
    status: str = "active",
    trigger_type: TriggerType = TriggerType.CRON,
    cron: str = "0 6 * * *",
    interval_minutes: int | None = None,
) -> ScheduleRecord:
    trigger_kwargs: dict = {"type": trigger_type}
    if trigger_type == TriggerType.CRON:
        trigger_kwargs["cron"] = cron
    elif trigger_type == TriggerType.INTERVAL:
        trigger_kwargs["interval_minutes"] = interval_minutes or 60
    elif trigger_type == TriggerType.EVENT:
        trigger_kwargs["event_source"] = "blob:vendor-inbox"
    return ScheduleRecord(
        id=schedule_id,
        name=name,
        instruction="Process documents",
        trigger=TriggerConfig(**trigger_kwargs),
        status=status,
    )


def _make_run(
    *,
    run_id: str | None = None,
    schedule_id: str = "sched-001",
    session_id: str = "sess-001",
    trigger_reason: str = "cron",
    status: str = "running",
) -> ScheduleRunRecord:
    return ScheduleRunRecord(
        id=run_id or str(uuid.uuid4()),
        schedule_id=schedule_id,
        session_id=session_id,
        triggered_at=datetime.now(timezone.utc),
        trigger_reason=trigger_reason,
        status=status,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class AsyncIterator:
    """Helper async iterator for mocking Cosmos query results."""

    def __init__(self, items: list):
        self._items = items
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


@pytest.fixture()
def mock_cosmos_client() -> MagicMock:
    """Create a mocked Cosmos client with database and container clients.

    ``get_database_client`` and ``get_container_client`` are **sync** methods
    on the Azure Cosmos async SDK, so we use ``MagicMock`` for those layers.
    The container-level operations (upsert_item, read_item, …) **are** async,
    so we keep them as ``AsyncMock``.

    ``query_items`` is a special case: the real SDK returns an async iterator
    directly (not a coroutine), so we override it with a plain ``MagicMock``
    whose ``return_value`` can be set to an ``AsyncIterator``.
    """
    client = MagicMock()
    db = MagicMock()
    schedules_container = AsyncMock()
    runs_container = AsyncMock()

    # query_items returns an async iterator, NOT a coroutine
    schedules_container.query_items = MagicMock(return_value=AsyncIterator([]))
    runs_container.query_items = MagicMock(return_value=AsyncIterator([]))

    client.get_database_client.return_value = db
    db.get_container_client.side_effect = lambda name: {
        "schedules": schedules_container,
        "schedule-runs": runs_container,
    }[name]

    return client


@pytest.fixture()
def schedule_store(mock_cosmos_client: MagicMock) -> ScheduleStore:
    return ScheduleStore(mock_cosmos_client, "contelligence-agent")


@pytest.fixture()
def schedules_container(mock_cosmos_client: MagicMock) -> AsyncMock:
    db = mock_cosmos_client.get_database_client.return_value
    return db.get_container_client("schedules")


@pytest.fixture()
def runs_container(mock_cosmos_client: MagicMock) -> AsyncMock:
    db = mock_cosmos_client.get_database_client.return_value
    return db.get_container_client("schedule-runs")


# ---------------------------------------------------------------------------
# Tests — Save / Get
# ---------------------------------------------------------------------------


class TestScheduleStoreSaveAndGet:
    """Tests for save_schedule and get_schedule."""

    @pytest.mark.asyncio
    async def test_save_schedule_calls_upsert(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        record = _make_schedule()
        await schedule_store.save_schedule(record)
        schedules_container.upsert_item.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_schedule_returns_record(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        record = _make_schedule()
        schedules_container.read_item.return_value = record.model_dump(mode="json")
        result = await schedule_store.get_schedule("sched-001")
        assert result.id == "sched-001"
        assert result.name == "Test Schedule"
        schedules_container.read_item.assert_awaited_once_with(
            item="sched-001", partition_key="sched-001",
        )

    @pytest.mark.asyncio
    async def test_get_schedule_not_found(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        schedules_container.read_item.side_effect = CosmosResourceNotFoundError(
            status_code=404, message="Not found",
        )
        with pytest.raises(ScheduleNotFoundError):
            await schedule_store.get_schedule("nonexistent")


# ---------------------------------------------------------------------------
# Tests — Delete
# ---------------------------------------------------------------------------


class TestScheduleStoreDelete:
    """Tests for soft-delete and hard-delete."""

    @pytest.mark.asyncio
    async def test_soft_delete_sets_status(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        record = _make_schedule()
        schedules_container.read_item.return_value = record.model_dump(mode="json")

        await schedule_store.delete_schedule("sched-001")

        # Verify upsert was called with status="deleted"
        upsert_call = schedules_container.upsert_item.call_args
        upserted_doc = upsert_call[0][0]
        assert upserted_doc["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_hard_delete_removes_item(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        await schedule_store.hard_delete_schedule("sched-001")
        schedules_container.delete_item.assert_awaited_once_with(
            item="sched-001", partition_key="sched-001",
        )

    @pytest.mark.asyncio
    async def test_hard_delete_not_found(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        schedules_container.delete_item.side_effect = CosmosResourceNotFoundError(
            status_code=404, message="Not found",
        )
        with pytest.raises(ScheduleNotFoundError):
            await schedule_store.hard_delete_schedule("nonexistent")


# ---------------------------------------------------------------------------
# Tests — List / Count
# ---------------------------------------------------------------------------


class TestScheduleStoreList:
    """Tests for list_schedules and count_schedules."""

    @pytest.mark.asyncio
    async def test_list_schedules_returns_records(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        rec1 = _make_schedule(schedule_id="s1").model_dump(mode="json")
        rec2 = _make_schedule(schedule_id="s2").model_dump(mode="json")
        schedules_container.query_items.return_value = AsyncIterator([rec1, rec2])

        result = await schedule_store.list_schedules()
        assert len(result) == 2
        assert result[0].id == "s1"

    @pytest.mark.asyncio
    async def test_list_schedules_with_status_filter(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        schedules_container.query_items.return_value = AsyncIterator([])
        await schedule_store.list_schedules(status="paused")

        call_args = schedules_container.query_items.call_args
        query = call_args.kwargs.get("query", call_args[0][0] if call_args[0] else "")
        assert "@status" in str(call_args)

    @pytest.mark.asyncio
    async def test_count_schedules(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        schedules_container.query_items.return_value = AsyncIterator([5])
        count = await schedule_store.count_schedules()
        assert count == 5

    @pytest.mark.asyncio
    async def test_get_active_schedules(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        rec = _make_schedule().model_dump(mode="json")
        schedules_container.query_items.return_value = AsyncIterator([rec])
        result = await schedule_store.get_active_schedules()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Tests — Status Updates
# ---------------------------------------------------------------------------


class TestScheduleStoreStatusUpdates:
    """Tests for update_schedule_status, failures tracking, etc."""

    @pytest.mark.asyncio
    async def test_update_status(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        record = _make_schedule()
        schedules_container.read_item.return_value = record.model_dump(mode="json")

        result = await schedule_store.update_schedule_status("sched-001", "paused")
        assert result.status == "paused"
        schedules_container.upsert_item.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_last_run(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        record = _make_schedule()
        schedules_container.read_item.return_value = record.model_dump(mode="json")

        await schedule_store.update_schedule_last_run(
            "sched-001",
            session_id="sess-001",
            run_status="running",
        )

        upsert_call = schedules_container.upsert_item.call_args
        doc = upsert_call[0][0]
        assert doc["last_run_session_id"] == "sess-001"
        assert doc["total_runs"] == 1

    @pytest.mark.asyncio
    async def test_increment_consecutive_failures(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        record = _make_schedule()
        record.consecutive_failures = 2
        schedules_container.read_item.return_value = record.model_dump(mode="json")

        result = await schedule_store.increment_consecutive_failures(
            "sched-001", auto_pause_threshold=3,
        )
        # 2 + 1 = 3, should trigger auto-pause (status="error")
        assert result.consecutive_failures == 3
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_increment_below_threshold(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        record = _make_schedule()
        record.consecutive_failures = 0
        schedules_container.read_item.return_value = record.model_dump(mode="json")

        result = await schedule_store.increment_consecutive_failures(
            "sched-001", auto_pause_threshold=3,
        )
        assert result.consecutive_failures == 1
        assert result.status == "active"  # Not yet paused

    @pytest.mark.asyncio
    async def test_reset_consecutive_failures(
        self,
        schedule_store: ScheduleStore,
        schedules_container: AsyncMock,
    ) -> None:
        record = _make_schedule()
        record.consecutive_failures = 2
        schedules_container.read_item.return_value = record.model_dump(mode="json")

        await schedule_store.reset_consecutive_failures("sched-001")

        upsert_call = schedules_container.upsert_item.call_args
        doc = upsert_call[0][0]
        assert doc["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# Tests — Run Records
# ---------------------------------------------------------------------------


class TestScheduleStoreRuns:
    """Tests for run record CRUD."""

    @pytest.mark.asyncio
    async def test_save_run(
        self,
        schedule_store: ScheduleStore,
        runs_container: AsyncMock,
    ) -> None:
        run = _make_run()
        await schedule_store.save_run(run)
        runs_container.upsert_item.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_run(
        self,
        schedule_store: ScheduleStore,
        runs_container: AsyncMock,
    ) -> None:
        run = _make_run(run_id="run-001")
        runs_container.read_item.return_value = run.model_dump(mode="json")

        await schedule_store.complete_run(
            run_id="run-001",
            schedule_id="sched-001",
            status="completed",
            summary="Done",
            duration_seconds=42.5,
            tool_calls=3,
        )

        upsert_call = runs_container.upsert_item.call_args
        doc = upsert_call[0][0]
        assert doc["status"] == "completed"
        assert doc["summary"] == "Done"
        assert doc["duration_seconds"] == 42.5

    @pytest.mark.asyncio
    async def test_complete_run_not_found(
        self,
        schedule_store: ScheduleStore,
        runs_container: AsyncMock,
    ) -> None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        runs_container.read_item.side_effect = CosmosResourceNotFoundError(
            status_code=404, message="Not found",
        )
        # Should not raise — just logs a warning
        await schedule_store.complete_run("run-999", "sched-001")

    @pytest.mark.asyncio
    async def test_list_runs(
        self,
        schedule_store: ScheduleStore,
        runs_container: AsyncMock,
    ) -> None:
        run = _make_run(run_id="run-001").model_dump(mode="json")
        runs_container.query_items.return_value = AsyncIterator([run])

        result = await schedule_store.list_runs("sched-001")
        assert len(result) == 1
        assert result[0].id == "run-001"

    @pytest.mark.asyncio
    async def test_get_recent_runs(
        self,
        schedule_store: ScheduleStore,
        runs_container: AsyncMock,
    ) -> None:
        run = _make_run(run_id="run-001").model_dump(mode="json")
        runs_container.query_items.return_value = AsyncIterator([run])

        result = await schedule_store.get_recent_runs(limit=5)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_count_runs_since(
        self,
        schedule_store: ScheduleStore,
        runs_container: AsyncMock,
    ) -> None:
        runs_container.query_items.return_value = AsyncIterator([10])
        since = datetime.now(timezone.utc)
        count = await schedule_store.count_runs_since(since=since)
        assert count == 10

"""Schedule Store — CRUD operations for schedules and schedule runs.

All persistence logic for the ``schedules`` and ``schedule-runs`` Cosmos DB
containers lives here.  Follows the same patterns as ``SessionStore``.

Container layout:
- **schedules**      — ``ScheduleRecord`` documents (pk ``/id``)
- **schedule-runs**  — ``ScheduleRunRecord`` documents (pk ``/schedule_id``)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

from app.models.exceptions import ScheduleNotFoundError
from app.models.schedule_models import ScheduleRecord, ScheduleRunRecord
from app.utils.cosmos_helpers import to_cosmos_dict

logger = logging.getLogger(f"contelligence-agent.{__name__}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _safe_read(coro: Any, schedule_id: str) -> Any:
    """Execute a Cosmos read, mapping not-found to ``ScheduleNotFoundError``."""
    try:
        return await coro
    except CosmosResourceNotFoundError:
        raise ScheduleNotFoundError(schedule_id)
    except CosmosHttpResponseError as exc:
        logger.error("Cosmos DB error: %s", exc.message)
        raise


# ---------------------------------------------------------------------------
# ScheduleStore
# ---------------------------------------------------------------------------
from app.store.storage_manager import StorageManager

class ScheduleStore:
    """Data access layer for schedule persistence in Cosmos DB.

    Operates on two containers:

    * **schedules**      — ``ScheduleRecord`` partitioned by ``/id``
    * **schedule-runs**  — ``ScheduleRunRecord`` partitioned by ``/schedule_id``
    """

    def __init__(
        self,
        storage_manager: StorageManager,
    ) -> None:
        
        self.schedules = storage_manager.get_container("schedules")
        self.runs = storage_manager.get_container("schedule-runs")

    # ------------------------------------------------------------------
    # Schedules — Write
    # ------------------------------------------------------------------

    async def save_schedule(self, record: ScheduleRecord) -> None:
        """Upsert a ``ScheduleRecord`` (create or full-replace)."""
        await self.schedules.upsert_item(to_cosmos_dict(record))

    async def delete_schedule(self, schedule_id: str) -> None:
        """Soft-delete a schedule by setting status to 'deleted'."""
        record = await self.get_schedule(schedule_id)
        record.status = "deleted"
        record.updated_at = datetime.now(timezone.utc)
        await self.save_schedule(record)
        logger.info("Schedule %s soft-deleted.", schedule_id)

    async def hard_delete_schedule(self, schedule_id: str) -> None:
        """Permanently remove a schedule document from Cosmos."""
        try:
            await self.schedules.delete_item(
                item=schedule_id, partition_key=schedule_id,
            )
            logger.info("Schedule %s hard-deleted.", schedule_id)
        except CosmosResourceNotFoundError:
            raise ScheduleNotFoundError(schedule_id)

    # ------------------------------------------------------------------
    # Schedules — Read
    # ------------------------------------------------------------------

    async def get_schedule(self, schedule_id: str) -> ScheduleRecord:
        """Point-read a schedule by ID (1 RU)."""
        item = await _safe_read(
            self.schedules.read_item(item=schedule_id, partition_key=schedule_id),
            schedule_id=schedule_id,
        )
        return ScheduleRecord.model_validate(item)

    async def list_schedules(
        self,
        *,
        status: str | None = None,
        trigger_type: str | None = None,
        tag: str | None = None,
        created_by: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ScheduleRecord]:
        """List schedules with optional filters.

        Uses cross-partition queries (schedules container is small).
        """
        conditions: list[str] = ["c.status != 'deleted'"]
        params: list[dict[str, Any]] = []

        if status:
            conditions.append("c.status = @status")
            params.append({"name": "@status", "value": status})

        if trigger_type:
            conditions.append("c.trigger.type = @trigger_type")
            params.append({"name": "@trigger_type", "value": trigger_type})

        if tag:
            conditions.append("ARRAY_CONTAINS(c.tags, @tag)")
            params.append({"name": "@tag", "value": tag})

        if created_by:
            conditions.append("c.created_by = @created_by")
            params.append({"name": "@created_by", "value": created_by})

        where_clause = " AND ".join(conditions)
        query = (
            f"SELECT * FROM c WHERE {where_clause} "
            f"ORDER BY c.created_at DESC "
            f"OFFSET @offset LIMIT @limit"
        )
        params.extend([
            {"name": "@offset", "value": offset},
            {"name": "@limit", "value": limit},
        ])

        items: list[ScheduleRecord] = []
        async for item in self.schedules.query_items(
            query=query,
            parameters=params,
        ):
            items.append(ScheduleRecord.model_validate(item))

        return items

    async def count_schedules(self, *, status: str | None = None) -> int:
        """Count schedules (optionally filtered by status)."""
        conditions = ["c.status != 'deleted'"]
        params: list[dict[str, Any]] = []

        if status:
            conditions.append("c.status = @status")
            params.append({"name": "@status", "value": status})

        query = f"SELECT VALUE COUNT(1) FROM c WHERE {' AND '.join(conditions)}"
        result = 0
        async for val in self.schedules.query_items(
            query=query,
            parameters=params,
        ):
            result = val
        return result

    async def get_active_schedules(self) -> list[ScheduleRecord]:
        """Return all schedules with status 'active'.

        Used by the scheduling engine to load jobs on startup.
        """
        return await self.list_schedules(status="active", limit=1000)

    async def get_schedules_by_trigger_type(
        self, trigger_type: str,
    ) -> list[ScheduleRecord]:
        """Return all active schedules of a specific trigger type."""
        return await self.list_schedules(
            status="active", trigger_type=trigger_type, limit=1000,
        )

    # ------------------------------------------------------------------
    # Schedules — Status Updates
    # ------------------------------------------------------------------

    async def update_schedule_status(
        self,
        schedule_id: str,
        status: str,
    ) -> ScheduleRecord:
        """Update only the status field of a schedule."""
        record = await self.get_schedule(schedule_id)
        record.status = status
        record.updated_at = datetime.now(timezone.utc)
        await self.save_schedule(record)
        return record

    async def update_schedule_last_run(
        self,
        schedule_id: str,
        *,
        session_id: str,
        run_status: str = "running",
        run_at: datetime | None = None,
        next_run_at: datetime | None = None,
    ) -> None:
        """Update a schedule's last-run tracking fields after a trigger fire."""
        record = await self.get_schedule(schedule_id)
        record.last_run_at = run_at or datetime.now(timezone.utc)
        record.last_run_session_id = session_id
        record.last_run_status = run_status
        record.total_runs += 1
        record.updated_at = datetime.now(timezone.utc)
        if next_run_at is not None:
            record.next_run_at = next_run_at
        await self.save_schedule(record)

    async def increment_consecutive_failures(
        self,
        schedule_id: str,
        *,
        auto_pause_threshold: int = 3,
    ) -> ScheduleRecord:
        """Increment failure counter and auto-pause if threshold is exceeded."""
        record = await self.get_schedule(schedule_id)
        record.consecutive_failures += 1
        record.last_run_status = "failed"
        record.updated_at = datetime.now(timezone.utc)

        if record.consecutive_failures >= auto_pause_threshold:
            record.status = "error"
            logger.warning(
                "Schedule %s auto-paused after %d consecutive failures.",
                schedule_id,
                record.consecutive_failures,
            )
        await self.save_schedule(record)
        return record

    async def reset_consecutive_failures(self, schedule_id: str) -> None:
        """Reset failure counter on successful run."""
        record = await self.get_schedule(schedule_id)
        if record.consecutive_failures > 0:
            record.consecutive_failures = 0
            record.updated_at = datetime.now(timezone.utc)
            await self.save_schedule(record)

    # ------------------------------------------------------------------
    # Schedule Runs — Write
    # ------------------------------------------------------------------

    async def save_run(self, run: ScheduleRunRecord) -> None:
        """Upsert a ``ScheduleRunRecord``."""
        await self.runs.upsert_item(to_cosmos_dict(run))

    async def complete_run(
        self,
        run_id: str,
        schedule_id: str,
        *,
        status: str = "completed",
        summary: str | None = None,
        duration_seconds: float | None = None,
        tool_calls: int | None = None,
        documents_processed: int | None = None,
        errors: int | None = None,
    ) -> None:
        """Mark a run as completed/failed with optional metrics."""
        try:
            item = await self.runs.read_item(
                item=run_id, partition_key=schedule_id,
            )
        except CosmosResourceNotFoundError:
            logger.warning("Run %s not found for schedule %s.", run_id, schedule_id)
            return

        run = ScheduleRunRecord.model_validate(item)
        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        if summary is not None:
            run.summary = summary
        if duration_seconds is not None:
            run.duration_seconds = duration_seconds
        if tool_calls is not None:
            run.tool_calls = tool_calls
        if documents_processed is not None:
            run.documents_processed = documents_processed
        if errors is not None:
            run.errors = errors

        await self.runs.upsert_item(to_cosmos_dict(run))

    # ------------------------------------------------------------------
    # Schedule Runs — Read
    # ------------------------------------------------------------------

    async def get_run(self, run_id: str, schedule_id: str) -> ScheduleRunRecord:
        """Point-read a run by ID within its schedule partition."""
        try:
            item = await self.runs.read_item(
                item=run_id, partition_key=schedule_id,
            )
            return ScheduleRunRecord.model_validate(item)
        except CosmosResourceNotFoundError:
            raise ScheduleNotFoundError(f"Run {run_id} (schedule {schedule_id})")

    async def list_runs(
        self,
        schedule_id: str,
        *,
        limit: int = 20,
        status: str | None = None,
    ) -> list[ScheduleRunRecord]:
        """List runs for a schedule, most recent first."""
        conditions = ["c.schedule_id = @schedule_id"]
        params: list[dict[str, Any]] = [
            {"name": "@schedule_id", "value": schedule_id},
        ]

        if status:
            conditions.append("c.status = @status")
            params.append({"name": "@status", "value": status})

        query = (
            f"SELECT * FROM c WHERE {' AND '.join(conditions)} "
            f"ORDER BY c.triggered_at DESC "
            f"OFFSET 0 LIMIT @limit"
        )
        params.append({"name": "@limit", "value": limit})

        items: list[ScheduleRunRecord] = []
        async for item in self.runs.query_items(
            query=query,
            parameters=params,
            partition_key=schedule_id,
        ):
            items.append(ScheduleRunRecord.model_validate(item))

        return items

    async def count_runs_since(
        self,
        *,
        since: datetime,
        status: str | None = None,
    ) -> int:
        """Count runs across all schedules since a given datetime."""
        conditions = ["c.triggered_at >= @since"]
        params: list[dict[str, Any]] = [
            {"name": "@since", "value": since.isoformat()},
        ]
        if status:
            conditions.append("c.status = @status")
            params.append({"name": "@status", "value": status})

        query = f"SELECT VALUE COUNT(1) FROM c WHERE {' AND '.join(conditions)}"
        result = 0
        async for val in self.runs.query_items(
            query=query,
            parameters=params,
        ):
            result = val
        return result

    async def get_recent_runs(
        self,
        *,
        limit: int = 20,
    ) -> list[ScheduleRunRecord]:
        """Get recent runs across all schedules (cross-partition)."""
        query = (
            "SELECT * FROM c ORDER BY c.triggered_at DESC "
            "OFFSET 0 LIMIT @limit"
        )
        items: list[ScheduleRunRecord] = []
        async for item in self.runs.query_items(
            query=query,
            parameters=[{"name": "@limit", "value": limit}],
        ):
            items.append(ScheduleRunRecord.model_validate(item))
        return items

"""Schedule Service — business logic layer between CRUD router and store/engine.

Orchestrates schedule creation, update, deletion, and trigger operations
by coordinating the ``ScheduleStore`` and ``SchedulingEngine``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.models.schedule_models import (
    CreateScheduleRequest,
    ScheduleRecord,
    TriggerType,
    UpdateScheduleRequest,
)

if TYPE_CHECKING:
    from app.services.schedule_store import ScheduleStore
    from app.services.scheduling_engine import SchedulingEngine

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class ScheduleService:
    """Business logic for schedule operations."""

    def __init__(
        self,
        store: "ScheduleStore",
        engine: "SchedulingEngine",
        *,
        agent_base_url: str = "",
    ) -> None:
        self.store = store
        self.engine = engine
        self._agent_base_url = agent_base_url

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_schedule(
        self,
        request: CreateScheduleRequest,
        created_by: str | None = None,
    ) -> ScheduleRecord:
        """Create a new schedule and register it with the engine."""
        schedule_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Generate webhook URL if webhook trigger
        webhook_id: str | None = None
        webhook_url: str | None = None
        if request.trigger.type == TriggerType.WEBHOOK:
            webhook_id = f"wh_{uuid.uuid4().hex[:12]}"
            base = self._agent_base_url.rstrip("/")
            webhook_url = f"{base}/api/webhooks/{webhook_id}"

        from app.models.agent_models import InstructOptions

        record = ScheduleRecord(
            id=schedule_id,
            name=request.name,
            description=request.description,
            instruction=request.instruction,
            trigger=request.trigger,
            options=request.options or InstructOptions(),
            tags=request.tags,
            status="active" if request.enabled else "paused",
            created_at=now,
            updated_at=now,
            created_by=created_by,
            webhook_id=webhook_id,
            webhook_url=webhook_url,
        )

        await self.store.save_schedule(record)

        # Register with engine if active
        if record.status == "active":
            await self.engine.add_schedule(record)

        logger.info(
            "Schedule '%s' (%s) created (trigger=%s, status=%s).",
            record.name,
            record.id,
            record.trigger.type.value,
            record.status,
        )
        return record

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_schedule(
        self,
        schedule_id: str,
        request: UpdateScheduleRequest,
    ) -> ScheduleRecord:
        """Apply partial updates to an existing schedule."""
        record = await self.store.get_schedule(schedule_id)
        now = datetime.now(timezone.utc)

        if request.name is not None:
            record.name = request.name
        if request.description is not None:
            record.description = request.description
        if request.instruction is not None:
            record.instruction = request.instruction
        if request.trigger is not None:
            record.trigger = request.trigger
            # Re-generate webhook_id if trigger type changed to webhook
            if request.trigger.type == TriggerType.WEBHOOK and not record.webhook_id:
                record.webhook_id = f"wh_{uuid.uuid4().hex[:12]}"
                base = self._agent_base_url.rstrip("/")
                record.webhook_url = f"{base}/api/webhooks/{record.webhook_id}"
        if request.options is not None:
            record.options = request.options
        if request.tags is not None:
            record.tags = request.tags

        record.updated_at = now
        await self.store.save_schedule(record)
        await self.engine.update_schedule(record)

        logger.info("Schedule '%s' (%s) updated.", record.name, record.id)
        return record

    # ------------------------------------------------------------------
    # Pause / Resume / Delete
    # ------------------------------------------------------------------

    async def pause_schedule(self, schedule_id: str) -> ScheduleRecord:
        """Pause a schedule."""
        record = await self.engine.pause_schedule(schedule_id)
        logger.info("Schedule %s paused.", schedule_id)
        return record

    async def resume_schedule(self, schedule_id: str) -> ScheduleRecord:
        """Resume a paused schedule."""
        record = await self.engine.resume_schedule(schedule_id)
        logger.info("Schedule %s resumed.", schedule_id)
        return record

    async def delete_schedule(self, schedule_id: str) -> None:
        """Delete (soft-delete) a schedule."""
        await self.engine.delete_schedule(schedule_id)
        logger.info("Schedule %s deleted.", schedule_id)

    # ------------------------------------------------------------------
    # Trigger Now
    # ------------------------------------------------------------------

    async def trigger_now(self, schedule_id: str) -> str | None:
        """Manually fire a schedule immediately.

        Returns the session ID, or ``None`` on failure.
        """
        session_id = await self.engine.fire_schedule(
            schedule_id, trigger_reason="manual",
        )
        if session_id:
            logger.info(
                "Schedule %s manually triggered → session %s",
                schedule_id,
                session_id,
            )
        return session_id

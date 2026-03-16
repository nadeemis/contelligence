"""Scheduling Engine — APScheduler-backed job orchestration.

Manages the lifecycle of scheduled jobs using APScheduler's
``AsyncIOScheduler``.  Integrates with the leader election system
so only one replica runs jobs at a time.

Supports four trigger types:
- **cron** — standard cron expressions via ``CronTrigger``
- **interval** — periodic execution via ``IntervalTrigger``
- **event** — Azure Event Grid subscriptions (jobs registered but
  fired externally via the events router)
- **webhook** — inbound HTTP triggers (jobs registered but fired
  externally via the webhooks router)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.models.schedule_models import (
    ScheduleRecord,
    ScheduleRunRecord,
    TriggerType,
)

if TYPE_CHECKING:
    from app.services.schedule_store import ScheduleStore

logger = logging.getLogger(f"contelligence-agent.{__name__}")


# ---------------------------------------------------------------------------
# Scheduling Engine
# ---------------------------------------------------------------------------


class SchedulingEngine:
    """APScheduler-based scheduling engine with leader-election awareness.

    The engine is started/stopped by the ``SchedulerLeaderElection``
    callbacks.  When this instance becomes leader, ``start()`` is called
    which loads all active schedules from Cosmos and registers them with
    APScheduler.  When leadership is lost, ``stop()`` shuts down
    APScheduler and all running jobs are halted.
    """

    def __init__(
        self,
        schedule_store: "ScheduleStore",
        fire_callback: Callable[
            [ScheduleRecord, str], Coroutine[Any, Any, str | None]
        ],
        *,
        misfire_grace_time: int = 60,
        coalesce: bool = True,
        max_instances: int = 1,
    ) -> None:
        """Initialise the scheduling engine.

        Parameters
        ----------
        schedule_store:
            Cosmos-backed store for schedule CRUD.
        fire_callback:
            Async callable ``(schedule, trigger_reason) -> session_id``.
            Called when a job fires.  Should create an agent session and
            return its ID, or ``None`` on failure.
        misfire_grace_time:
            Seconds to tolerate a late trigger before skipping.
        coalesce:
            Whether to coalesce missed fires into a single run.
        max_instances:
            Maximum simultaneous instances of the same job.
        """
        self.store = schedule_store
        self._fire_callback = fire_callback
        self._misfire_grace_time = misfire_grace_time
        self._coalesce = coalesce
        self._max_instances = max_instances

        self._scheduler: AsyncIOScheduler | None = None
        self._is_running = False

    # ------------------------------------------------------------------
    # Lifecycle (called by leader election)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the APScheduler and load all active schedules."""
        if self._is_running:
            logger.warning("Scheduling engine already running.")
            return

        self._scheduler = AsyncIOScheduler(
            job_defaults={
                "coalesce": self._coalesce,
                "max_instances": self._max_instances,
                "misfire_grace_time": self._misfire_grace_time,
            },
        )
        self._scheduler.start()
        self._is_running = True
        logger.info("APScheduler started.")

        # Load and register all active cron/interval schedules
        try:
            active_schedules = await self.store.get_active_schedules()
            registered = 0
            for schedule in active_schedules:
                if schedule.trigger.type in (TriggerType.CRON, TriggerType.INTERVAL):
                    self._register_job(schedule)
                    registered += 1
            logger.info(
                "Loaded %d active schedules (%d cron/interval registered).",
                len(active_schedules),
                registered,
            )
        except Exception:
            logger.exception("Failed to load active schedules on startup.")

    async def stop(self) -> None:
        """Shut down the APScheduler gracefully."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        self._is_running = False
        logger.info("APScheduler stopped.")

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ------------------------------------------------------------------
    # Job Registration
    # ------------------------------------------------------------------

    def _register_job(self, schedule: ScheduleRecord) -> None:
        """Register or replace an APScheduler job for a schedule."""
        if self._scheduler is None:
            return

        job_id = f"schedule:{schedule.id}"

        # Remove existing job if present (for updates)
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        trigger = self._build_trigger(schedule)
        if trigger is None:
            # Event/webhook triggers don't use APScheduler
            return

        self._scheduler.add_job(
            func=self._fire_job,
            trigger=trigger,
            id=job_id,
            name=schedule.name,
            kwargs={"schedule_id": schedule.id},
            replace_existing=True,
        )
        logger.info(
            "Registered job '%s' (type=%s, id=%s)",
            schedule.name,
            schedule.trigger.type.value,
            schedule.id,
        )

    def _build_trigger(
        self,
        schedule: ScheduleRecord,
    ) -> CronTrigger | IntervalTrigger | None:
        """Build an APScheduler trigger from a ``TriggerConfig``."""
        cfg = schedule.trigger

        if cfg.type == TriggerType.CRON:
            return CronTrigger.from_crontab(
                cfg.cron,
                timezone=cfg.timezone or "UTC",
            )
        elif cfg.type == TriggerType.INTERVAL:
            return IntervalTrigger(minutes=cfg.interval_minutes)
        else:
            # Event and webhook triggers are fired externally
            return None

    def _unregister_job(self, schedule_id: str) -> None:
        """Remove an APScheduler job for a schedule."""
        if self._scheduler is None:
            return
        job_id = f"schedule:{schedule_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info("Unregistered job for schedule %s.", schedule_id)

    # ------------------------------------------------------------------
    # Job Execution
    # ------------------------------------------------------------------

    async def _fire_job(self, schedule_id: str) -> None:
        """Called by APScheduler when a cron/interval trigger fires."""
        await self.fire_schedule(schedule_id, trigger_reason="cron")

    async def fire_schedule(
        self,
        schedule_id: str,
        trigger_reason: str = "manual",
    ) -> str | None:
        """Fire a schedule — create a run record and invoke the agent.

        Returns the session ID on success, or ``None`` on failure.
        This is the unified entry point for all trigger types.
        """
        try:
            schedule = await self.store.get_schedule(schedule_id)
        except Exception:
            logger.exception(f"Failed to load schedule {schedule_id} for firing.")
            return None

        if schedule.status not in ("active",):
            logger.warning(
                f"Skipping fire of schedule {schedule_id} (status={schedule.status})."
            )
            return None

        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        logger.info(
            f"Firing schedule '{schedule.name}' ({schedule_id}) — reason: {trigger_reason}"
        )

        try:
            session_id = await self._fire_callback(schedule, trigger_reason)
        except Exception:
            logger.exception(
                f"Fire callback failed for schedule {schedule_id}."
            )
            # Record the failed run
            run = ScheduleRunRecord(
                id=run_id,
                schedule_id=schedule_id,
                session_id="",
                triggered_at=now,
                trigger_reason=trigger_reason,
                status="failed",
                completed_at=now,
                summary="Fire callback raised an exception",
            )
            await self.store.save_run(run)
            await self.store.increment_consecutive_failures(schedule_id)
            return None

        if not session_id:
            logger.error(
                f"Fire callback returned no session_id for schedule {schedule_id}."
            )
            return None

        # Create the run record
        run = ScheduleRunRecord(
            id=run_id,
            schedule_id=schedule_id,
            session_id=session_id,
            triggered_at=now,
            trigger_reason=trigger_reason,
            status="running",
        )
        await self.store.save_run(run)

        # Update the schedule's last-run info
        next_run = self._compute_next_run(schedule)
        await self.store.update_schedule_last_run(
            schedule_id,
            session_id=session_id,
            run_status="running",
            run_at=now,
            next_run_at=next_run,
        )

        return session_id

    # ------------------------------------------------------------------
    # Schedule Management (called by the CRUD router)
    # ------------------------------------------------------------------

    async def add_schedule(self, schedule: ScheduleRecord) -> None:
        """Register a newly created schedule with APScheduler."""
        if schedule.trigger.type in (TriggerType.CRON, TriggerType.INTERVAL):
            self._register_job(schedule)
            # Compute and store next_run_at
            next_run = self._compute_next_run(schedule)
            if next_run:
                schedule.next_run_at = next_run
                await self.store.save_schedule(schedule)

    async def update_schedule(self, schedule: ScheduleRecord) -> None:
        """Update an existing schedule's APScheduler job."""
        if schedule.status == "active":
            if schedule.trigger.type in (TriggerType.CRON, TriggerType.INTERVAL):
                self._register_job(schedule)
                next_run = self._compute_next_run(schedule)
                if next_run:
                    schedule.next_run_at = next_run
                    await self.store.save_schedule(schedule)
            else:
                # Event/webhook — just ensure no stale APScheduler job
                self._unregister_job(schedule.id)
        else:
            # Paused/error/deleted — remove from APScheduler
            self._unregister_job(schedule.id)

    async def pause_schedule(self, schedule_id: str) -> ScheduleRecord:
        """Pause a schedule — remove from APScheduler."""
        record = await self.store.update_schedule_status(schedule_id, "paused")
        self._unregister_job(schedule_id)
        return record

    async def resume_schedule(self, schedule_id: str) -> ScheduleRecord:
        """Resume a paused schedule — re-register with APScheduler."""
        record = await self.store.update_schedule_status(schedule_id, "active")
        record.consecutive_failures = 0
        record.updated_at = datetime.now(timezone.utc)
        await self.store.save_schedule(record)

        if record.trigger.type in (TriggerType.CRON, TriggerType.INTERVAL):
            self._register_job(record)
            next_run = self._compute_next_run(record)
            if next_run:
                record.next_run_at = next_run
                await self.store.save_schedule(record)
        return record

    async def delete_schedule(self, schedule_id: str) -> None:
        """Delete a schedule — remove from APScheduler and soft-delete."""
        self._unregister_job(schedule_id)
        await self.store.delete_schedule(schedule_id)

    # ------------------------------------------------------------------
    # Next Run Computation
    # ------------------------------------------------------------------

    def _compute_next_run(self, schedule: ScheduleRecord) -> datetime | None:
        """Compute the next trigger time for a schedule."""
        trigger = self._build_trigger(schedule)
        if trigger is None:
            return None

        try:
            # APScheduler triggers have get_next_fire_time()
            next_fire = trigger.get_next_fire_time(
                None, datetime.now(timezone.utc),
            )
            return next_fire
        except Exception:
            logger.warning(
                "Could not compute next run for schedule %s.", schedule.id,
            )
            return None

    def get_upcoming_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return upcoming scheduled job runs from APScheduler.

        Returns a list of dicts with ``schedule_id``, ``name``, and
        ``next_run_at`` for the dashboard.
        """
        if self._scheduler is None:
            return []

        jobs = self._scheduler.get_jobs()
        upcoming: list[dict[str, Any]] = []
        for job in jobs:
            if job.next_run_time is not None:
                schedule_id = job.id.replace("schedule:", "")
                upcoming.append({
                    "schedule_id": schedule_id,
                    "name": job.name,
                    "next_run_at": job.next_run_time.isoformat(),
                })

        # Sort by next_run_at
        upcoming.sort(key=lambda x: x["next_run_at"])
        return upcoming[:limit]

    # ------------------------------------------------------------------
    # Event / Webhook helpers
    # ------------------------------------------------------------------

    async def handle_event(
        self,
        event_source: str,
        event_data: dict[str, Any],
    ) -> list[str]:
        """Handle an external event — fire matching event-triggered schedules.

        Returns a list of session IDs created.
        """
        schedules = await self.store.get_schedules_by_trigger_type(
            TriggerType.EVENT.value,
        )

        session_ids: list[str] = []
        for schedule in schedules:
            cfg = schedule.trigger
            if cfg.event_source and self._event_matches(
                cfg.event_source, cfg.event_filter, event_source, event_data,
            ):
                sid = await self.fire_schedule(
                    schedule.id,
                    trigger_reason=f"event:{event_source}",
                )
                if sid:
                    session_ids.append(sid)

        return session_ids

    async def handle_webhook(
        self,
        webhook_id: str,
        payload: dict[str, Any],
    ) -> str | None:
        """Handle a webhook trigger — fire the matching schedule.

        Returns the session ID if the schedule was found and fired.
        """
        # Find scheduler by webhook_id
        schedules = await self.store.get_schedules_by_trigger_type(
            TriggerType.WEBHOOK.value,
        )
        for schedule in schedules:
            if schedule.webhook_id == webhook_id:
                return await self.fire_schedule(
                    schedule.id,
                    trigger_reason=f"webhook:{webhook_id}",
                )

        logger.warning("No schedule found for webhook_id=%s", webhook_id)
        return None

    @staticmethod
    def _event_matches(
        source_pattern: str,
        filter_pattern: str | None,
        event_source: str,
        event_data: dict[str, Any],
    ) -> bool:
        """Check if an event matches a schedule's event source/filter.

        Supports simple prefix-based matching:
        - source_pattern ``blob:vendor-inbox`` matches event_source ``blob:vendor-inbox/file.pdf``
        - filter_pattern is an optional glob-like suffix pattern
        """
        if not event_source.startswith(source_pattern.split("*")[0]):
            return False

        if filter_pattern:
            import fnmatch
            event_subject = event_data.get("subject", event_source)
            if not fnmatch.fnmatch(event_subject, filter_pattern):
                return False

        return True

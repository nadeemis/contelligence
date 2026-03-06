"""Schedule Run Tracker — monitors session completion and updates run records.

Provides the ``fire_callback`` for the scheduling engine and a background
task that watches for session completion to update the corresponding
``ScheduleRunRecord`` with final metrics.

Architecture:
- The ``fire_and_track`` method is passed as the ``fire_callback`` to
  ``SchedulingEngine``.  It creates an agent session via
  ``PersistentAgentService.create_and_run()`` and starts a background
  poller that waits for session completion.
- On completion, the run record and schedule tracking fields are updated.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.models.schedule_models import ScheduleRecord
from app.models.session_models import SessionStatus

if TYPE_CHECKING:
    from app.services.persistent_agent_service import PersistentAgentService
    from app.services.schedule_store import ScheduleStore
    from app.store.session_store import SessionStore

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# Terminal session statuses
_TERMINAL_STATUSES = frozenset({
    SessionStatus.COMPLETED,
    SessionStatus.FAILED,
    SessionStatus.CANCELLED,
})

# Polling interval for session completion checks
_POLL_INTERVAL_SECONDS = 10

# Maximum time to wait for a session to complete (2 hours)
_MAX_POLL_DURATION_SECONDS = 7200


class ScheduleRunTracker:
    """Tracks scheduled session runs and updates run records on completion."""

    def __init__(
        self,
        agent_service: "PersistentAgentService",
        schedule_store: "ScheduleStore",
        session_store: "SessionStore",
    ) -> None:
        self.agent_service = agent_service
        self.schedule_store = schedule_store
        self.session_store = session_store

        # Track active polling tasks keyed by session_id
        self._poll_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Fire Callback (passed to SchedulingEngine)
    # ------------------------------------------------------------------

    async def fire_and_track(
        self,
        schedule: ScheduleRecord,
        trigger_reason: str,
    ) -> str | None:
        """Create an agent session for a schedule and track its completion.

        This method is the ``fire_callback`` for ``SchedulingEngine``.

        Returns the session ID on success, or ``None`` on failure.
        """
        try:
            from app.models.agent_models import InstructOptions

            # Build session metadata linking back to the schedule
            metadata: dict[str, Any] = {
                "schedule_id": schedule.id,
                "trigger_reason": trigger_reason,
                "schedule_name": schedule.name,
            }

            session_id = await self.agent_service.create_and_run(
                instruction=schedule.instruction,
                options=schedule.options,
                metadata=metadata,
            )

            # Start background polling for session completion
            task = asyncio.create_task(
                self._poll_session_completion(
                    session_id=session_id,
                    schedule_id=schedule.id,
                ),
            )
            self._poll_tasks[session_id] = task
            task.add_done_callback(
                lambda t: self._poll_tasks.pop(session_id, None),
            )

            logger.info(
                "Schedule '%s' fired → session %s (reason: %s)",
                schedule.name,
                session_id,
                trigger_reason,
            )
            return session_id

        except Exception:
            logger.exception(
                "Failed to create session for schedule '%s' (%s).",
                schedule.name,
                schedule.id,
            )
            return None

    # ------------------------------------------------------------------
    # Completion Polling
    # ------------------------------------------------------------------

    async def _poll_session_completion(
        self,
        session_id: str,
        schedule_id: str,
    ) -> None:
        """Poll a session until it reaches a terminal status, then update the run record."""
        elapsed = 0.0

        while elapsed < _MAX_POLL_DURATION_SECONDS:
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

            try:
                session = await self.session_store.get_session(session_id)
            except Exception:
                logger.warning(
                    "Could not read session %s for completion tracking.",
                    session_id,
                )
                continue

            if session.status in _TERMINAL_STATUSES:
                await self._on_session_complete(
                    session_id=session_id,
                    schedule_id=schedule_id,
                    status=session.status,
                    summary=session.summary,
                    metrics=session.metrics,
                )
                return

        # Timeout — mark as failed
        logger.warning(
            "Session %s for schedule %s did not complete within %ds.",
            session_id,
            schedule_id,
            _MAX_POLL_DURATION_SECONDS,
        )
        await self._on_session_complete(
            session_id=session_id,
            schedule_id=schedule_id,
            status=SessionStatus.FAILED,
            summary="Session timed out waiting for completion",
            metrics=None,
        )

    async def _on_session_complete(
        self,
        session_id: str,
        schedule_id: str,
        status: SessionStatus,
        summary: str | None,
        metrics: Any | None,
    ) -> None:
        """Update the run record and schedule after session completion."""
        is_success = status == SessionStatus.COMPLETED
        run_status = "completed" if is_success else "failed"

        try:
            # Find the run record for this session
            runs = await self.schedule_store.list_runs(schedule_id, limit=5)
            matching_run = None
            for run in runs:
                if run.session_id == session_id:
                    matching_run = run
                    break

            if matching_run:
                # Extract metrics from the session
                duration = None
                tool_calls = None
                docs_processed = None
                errors = None

                if metrics is not None:
                    duration = getattr(metrics, "total_duration_seconds", None)
                    tool_calls = getattr(metrics, "total_tool_calls", None)
                    docs_processed = getattr(metrics, "documents_processed", None)
                    errors = getattr(metrics, "errors_encountered", None)

                await self.schedule_store.complete_run(
                    run_id=matching_run.id,
                    schedule_id=schedule_id,
                    status=run_status,
                    summary=summary,
                    duration_seconds=duration,
                    tool_calls=tool_calls,
                    documents_processed=docs_processed,
                    errors=errors,
                )

            # Update schedule tracking
            if is_success:
                await self.schedule_store.reset_consecutive_failures(schedule_id)
                try:
                    schedule = await self.schedule_store.get_schedule(schedule_id)
                    schedule.last_run_status = "completed"
                    schedule.updated_at = datetime.now(timezone.utc)
                    await self.schedule_store.save_schedule(schedule)
                except Exception:
                    pass  # Best effort
            else:
                await self.schedule_store.increment_consecutive_failures(
                    schedule_id,
                )

            logger.info(
                "Session %s completed (%s) for schedule %s.",
                session_id,
                run_status,
                schedule_id,
            )

        except Exception:
            logger.exception(
                "Failed to update run record for session %s (schedule %s).",
                session_id,
                schedule_id,
            )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def cancel_all_tracking(self) -> None:
        """Cancel all active polling tasks on shutdown."""
        for session_id, task in list(self._poll_tasks.items()):
            task.cancel()
            logger.debug("Cancelled poll task for session %s.", session_id)
        self._poll_tasks.clear()

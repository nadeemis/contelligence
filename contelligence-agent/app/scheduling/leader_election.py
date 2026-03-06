"""Distributed leader election for the scheduling engine.

Uses Cosmos DB as a distributed lock store with optimistic concurrency
(ETags) to ensure only one container replica runs the scheduling engine
at a time.

The ``scheduler-locks`` container holds a single lock document that
tracks which replica is the current leader and when the lease expires.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine

from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import (
    CosmosAccessConditionFailedError,
    CosmosResourceNotFoundError,
)

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class SchedulerLeaderElection:
    """Cosmos DB-backed distributed lock for scheduler leadership."""

    LOCK_CONTAINER = "scheduler-locks"
    LOCK_DOCUMENT_ID = "scheduler-leader"
    LEASE_DURATION_SECONDS = 60

    def __init__(
        self,
        cosmos_client: CosmosClient,
        instance_id: str,
        database_name: str = "contelligence-agent",
    ) -> None:
        self.container = (
            cosmos_client.get_database_client(database_name)
            .get_container_client(self.LOCK_CONTAINER)
        )
        self.instance_id = instance_id
        self.is_leader: bool = False
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Core acquisition
    # ------------------------------------------------------------------

    async def try_acquire_leadership(self) -> bool:
        """Attempt to become or remain the scheduler leader.

        Returns ``True`` if this instance is the leader after the call.
        Uses optimistic concurrency (``if_match`` ETag) to prevent
        race conditions between replicas.
        """
        now = datetime.now(timezone.utc)
        try:
            lock = await self.container.read_item(
                item=self.LOCK_DOCUMENT_ID,
                partition_key=self.LOCK_DOCUMENT_ID,
            )
            lease_expiry = datetime.fromisoformat(lock["lease_expires_at"])
            # Ensure timezone-aware comparison
            if lease_expiry.tzinfo is None:
                lease_expiry = lease_expiry.replace(tzinfo=timezone.utc)

            if lease_expiry < now:
                # Lease expired — take over with ETag check
                lock["leader_id"] = self.instance_id
                lock["lease_expires_at"] = (
                    now + timedelta(seconds=self.LEASE_DURATION_SECONDS)
                ).isoformat()
                lock["acquired_at"] = now.isoformat()
                await self.container.replace_item(
                    item=self.LOCK_DOCUMENT_ID,
                    body=lock,
                    if_match=lock["_etag"],  # Optimistic concurrency
                )
                self.is_leader = True
            elif lock["leader_id"] == self.instance_id:
                # Already leader — renew lease
                lock["lease_expires_at"] = (
                    now + timedelta(seconds=self.LEASE_DURATION_SECONDS)
                ).isoformat()
                await self.container.replace_item(
                    item=self.LOCK_DOCUMENT_ID,
                    body=lock,
                )
                self.is_leader = True
            else:
                self.is_leader = False

        except CosmosResourceNotFoundError:
            # No lock exists yet — create it
            try:
                await self.container.create_item(
                    {
                        "id": self.LOCK_DOCUMENT_ID,
                        "leader_id": self.instance_id,
                        "lease_expires_at": (
                            now + timedelta(seconds=self.LEASE_DURATION_SECONDS)
                        ).isoformat(),
                        "acquired_at": now.isoformat(),
                    }
                )
                self.is_leader = True
            except Exception:
                # Another replica may have created it simultaneously
                self.is_leader = False

        except CosmosAccessConditionFailedError:
            # Another instance beat us — ETag mismatch
            self.is_leader = False

        except Exception:
            logger.exception("Unexpected error during leadership acquisition")
            self.is_leader = False

        return self.is_leader

    # ------------------------------------------------------------------
    # Background leader loop
    # ------------------------------------------------------------------

    async def run_leader_loop(
        self,
        scheduler_start_fn: Callable[[], Coroutine[Any, Any, None]],
        scheduler_stop_fn: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        """Continuously attempt leadership and start/stop the scheduler.

        This method runs indefinitely and should be started as an
        ``asyncio.Task``.  It detects leadership transitions and calls
        the appropriate callback.
        """
        self._running = True
        while self._running:
            was_leader = self.is_leader
            is_leader = await self.try_acquire_leadership()

            if is_leader and not was_leader:
                logger.info(
                    "Instance %s became scheduler leader", self.instance_id,
                )
                try:
                    await scheduler_start_fn()
                except Exception:
                    logger.exception("Failed to start scheduler after leadership gain")
            elif not is_leader and was_leader:
                logger.warning(
                    "Instance %s lost scheduler leadership", self.instance_id,
                )
                try:
                    await scheduler_stop_fn()
                except Exception:
                    logger.exception("Failed to stop scheduler after leadership loss")

            # Renew at half the lease duration to avoid expiry
            await asyncio.sleep(self.LEASE_DURATION_SECONDS / 2)

    # ------------------------------------------------------------------
    # Graceful release
    # ------------------------------------------------------------------

    async def release_leadership(self) -> None:
        """Release leadership during graceful shutdown.

        Sets the lease expiry to *now* so another replica can take
        over immediately.  If the release fails, the lease will
        naturally expire after ``LEASE_DURATION_SECONDS``.
        """
        self._running = False

        if self.is_leader:
            try:
                lock = await self.container.read_item(
                    item=self.LOCK_DOCUMENT_ID,
                    partition_key=self.LOCK_DOCUMENT_ID,
                )
                if lock.get("leader_id") == self.instance_id:
                    lock["lease_expires_at"] = datetime.now(timezone.utc).isoformat()
                    await self.container.replace_item(
                        item=self.LOCK_DOCUMENT_ID,
                        body=lock,
                    )
                    logger.info(
                        "Instance %s released leadership", self.instance_id,
                    )
            except Exception:
                logger.warning(
                    "Failed to release leadership for %s — "
                    "lease will expire naturally",
                    self.instance_id,
                    exc_info=True,
                )
            self.is_leader = False

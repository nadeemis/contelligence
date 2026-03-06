"""Session retention cleanup — background coroutine run by the
scheduler leader that purges expired sessions, conversation turns,
output records, and associated blobs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.connectors.blob_connector import BlobConnectorAdapter
    from app.store.session_store import SessionStore

    from .models import RetentionPolicy

logger = logging.getLogger(f"contelligence-agent.{__name__}")

class RetentionCleanup:
    """Executes the session retention policy.

    Queries for sessions older than ``retention_policy.session_retention_days``
    whose status is terminal (completed, failed, cancelled), then removes:

    1. Conversation turns (Cosmos ``conversation`` container)
    2. Output records (Cosmos ``outputs`` container)
    3. Blob prefixes under ``outputs/{session_id}/``
    4. The session document itself
    """

    def __init__(
        self,
        session_store: "SessionStore",
        blob_connector: "BlobConnectorAdapter",
        retention_policy: "RetentionPolicy",
    ) -> None:
        self._store = session_store
        self._blob = blob_connector
        self._policy = retention_policy

    async def run_cleanup_cycle(self) -> dict[str, int]:
        """Execute one cleanup cycle.  Returns counts of purged items."""
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=self._policy.session_retention_days,
        )
        cutoff_iso = cutoff.isoformat()

        logger.info(
            "Retention cleanup: purging sessions completed before %s",
            cutoff_iso,
        )

        # Query expired terminal sessions
        expired = await self._query_expired_sessions(cutoff_iso)

        purged_sessions = 0
        purged_turns = 0
        purged_outputs = 0
        purged_blobs = 0

        for session in expired:
            session_id = session["id"]
            try:
                # 1. Delete conversation turns
                turns = await self._store.delete_turns(session_id)
                purged_turns += turns

                # 2. Delete output records
                outputs = await self._store.delete_outputs(session_id)
                purged_outputs += outputs

                # 3. Delete blob prefix
                blobs = await self._blob.delete_prefix(
                    container_name="outputs",
                    prefix=f"{session_id}/",
                )
                purged_blobs += blobs

                # 4. Delete the session document
                await self._store.delete_session(session_id)
                purged_sessions += 1

                logger.debug(
                    "Purged session %s: %d turns, %d outputs, %d blobs",
                    session_id, turns, outputs, blobs,
                )
            except Exception:
                logger.exception(
                    "Failed to purge session %s — will retry next cycle",
                    session_id,
                )

        result = {
            "sessions": purged_sessions,
            "turns": purged_turns,
            "outputs": purged_outputs,
            "blobs": purged_blobs,
        }
        logger.info("Retention cleanup complete: %s", result)
        return result

    async def _query_expired_sessions(
        self, cutoff_iso: str,
    ) -> list[dict]:
        """Query Cosmos for terminal sessions older than the cutoff."""
        container = self._store._sessions_container
        query = (
            "SELECT c.id FROM c "
            "WHERE c.status IN ('completed', 'failed', 'cancelled') "
            "AND c.created_at < @cutoff"
        )
        params = [{"name": "@cutoff", "value": cutoff_iso}]

        items: list[dict] = []
        async for item in container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True,
        ):
            items.append(item)

        logger.info("Found %d expired sessions for cleanup.", len(items))
        return items

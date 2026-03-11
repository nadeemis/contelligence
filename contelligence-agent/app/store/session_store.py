"""Session Store — CRUD operations for sessions, turns, and output artifacts.

All persistence logic for the ``sessions``, ``conversation``, and ``outputs``
Cosmos DB containers lives here.  Methods are intentionally thin wrappers
around Cosmos SDK calls with consistent error mapping.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

from app.models.exceptions import SessionNotFoundError
from app.models.session_models import (
    ConversationTurn,
    DelegationRecord,
    OutputArtifact,
    SessionEvent,
    SessionMetrics,
    SessionRecord,
    SessionStatus,
)
from app.utils.cosmos_helpers import to_cosmos_dict

logger = logging.getLogger(f"contelligence-agent.{__name__}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _safe_cosmos_read(coro: Any, not_found_msg: str = "Resource not found") -> Any:
    """Execute a Cosmos read operation, mapping not-found to ``SessionNotFoundError``."""
    try:
        return await coro
    except CosmosResourceNotFoundError:
        raise SessionNotFoundError(not_found_msg)
    except CosmosHttpResponseError as exc:
        logger.error("Cosmos DB error: %s", exc.message)
        raise


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------

from app.store.storage_manager import StorageManager

class SessionStore:
    """Data access layer for session persistence in Cosmos DB.

    Operates on three containers:

    * **sessions**     — ``SessionRecord`` documents partitioned by ``/id``
    * **conversation** — ``ConversationTurn`` documents partitioned by ``/session_id``
    * **outputs**      — ``OutputArtifact`` documents partitioned by ``/session_id``
    """

    def __init__(
        self,
        storage_manager: StorageManager,
    ) -> None:

        self.sessions = storage_manager.get_container("sessions")
        self.conversation = storage_manager.get_container("conversation")
        self.outputs = storage_manager.get_container("outputs")
        self.events = storage_manager.get_container("events")
        
    # ------------------------------------------------------------------
    # Sessions container
    # ------------------------------------------------------------------
    async def save_session(self, record: SessionRecord) -> None:
        """Upsert a ``SessionRecord`` (create or full-replace)."""
        await self.sessions.upsert_item(to_cosmos_dict(record))

    async def get_session(self, session_id: str) -> SessionRecord:
        """Point-read a session by its ID (1 RU)."""
        item = await _safe_cosmos_read(
            self.sessions.read_item(item=session_id, partition_key=session_id),
            not_found_msg=session_id,
        )
        return SessionRecord.model_validate(item)

    async def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        summary: str | None = None,
    ) -> None:
        """Read-modify-write the session status and optional summary."""
        record = await self.get_session(session_id)
        record.status = status
        record.updated_at = datetime.now(timezone.utc)
        if summary is not None:
            record.summary = summary
        await self.save_session(record)

    async def update_session_metrics(
        self,
        session_id: str,
        **metric_updates: int | float,
    ) -> None:
        """Incrementally add delta values to session metrics.

        Example::

            await store.update_session_metrics(
                session_id, total_tool_calls=1, documents_processed=1
            )
        """
        record = await self.get_session(session_id)
        for key, value in metric_updates.items():
            if hasattr(record.metrics, key):
                current = getattr(record.metrics, key)
                setattr(record.metrics, key, current + value)
        record.updated_at = datetime.now(timezone.utc)
        await self.save_session(record)

    async def list_sessions(
        self,
        status: SessionStatus | None = None,
        user_id: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[SessionRecord]:
        """Cross-partition query with optional filters, newest first."""
        conditions: list[str] = []
        params: list[dict[str, Any]] = []

        if status is not None:
            conditions.append("c.status = @status")
            params.append({"name": "@status", "value": status.value})
        if user_id is not None:
            conditions.append("c.user_id = @user_id")
            params.append({"name": "@user_id", "value": user_id})
        if since is not None:
            conditions.append("c.created_at >= @since")
            params.append({"name": "@since", "value": since.isoformat()})

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT TOP {limit} * FROM c{where} ORDER BY c.created_at DESC"

        items = self.sessions.query_items(
            query=query,
            parameters=params or None,
        )
        return [SessionRecord.model_validate(item) async for item in items]

    # ------------------------------------------------------------------
    # Conversation container
    # ------------------------------------------------------------------

    async def save_turn(self, turn: ConversationTurn) -> None:
        """Upsert a conversation turn."""
        await self.conversation.upsert_item(to_cosmos_dict(turn))

    async def get_turns(self, session_id: str) -> list[ConversationTurn]:
        """Retrieve all turns for a session, ordered by sequence."""
        query = "SELECT * FROM c WHERE c.session_id = @sid ORDER BY c.sequence ASC"
        params = [{"name": "@sid", "value": session_id}]
        items = self.conversation.query_items(
            query=query,
            parameters=params,
            partition_key=session_id,
        )
        return [ConversationTurn.model_validate(item) async for item in items]

    async def update_tool_call(
        self,
        session_id: str,
        tool_name: str,
        result: dict[str, Any] | None,
        result_blob_ref: str | None,
        completed_at: datetime,
        status: str,
        error: str | None = None,
    ) -> None:
        """Update the most recent *running* tool turn for *tool_name*."""
        query = (
            "SELECT * FROM c WHERE c.session_id = @sid AND c.role = 'tool' "
            "AND c.tool_call.tool_name = @tool AND c.tool_call.status = 'running' "
            "ORDER BY c.sequence DESC OFFSET 0 LIMIT 1"
        )
        params = [
            {"name": "@sid", "value": session_id},
            {"name": "@tool", "value": tool_name},
        ]
        items = self.conversation.query_items(
            query=query,
            parameters=params,
            partition_key=session_id,
        )
        async for item in items:
            turn = ConversationTurn.model_validate(item)
            if turn.tool_call is not None:
                turn.tool_call.result = result
                turn.tool_call.result_blob_ref = result_blob_ref
                turn.tool_call.completed_at = completed_at
                turn.tool_call.duration_ms = int(
                    (completed_at - turn.tool_call.started_at).total_seconds() * 1000
                )
                turn.tool_call.status = status
                if error is not None:
                    turn.tool_call.error = error
                await self.save_turn(turn)
            break

    # ------------------------------------------------------------------
    # Outputs container
    # ------------------------------------------------------------------

    async def save_output(self, artifact: OutputArtifact) -> None:
        """Upsert an output artifact."""
        await self.outputs.upsert_item(to_cosmos_dict(artifact))

    async def get_outputs(self, session_id: str) -> list[OutputArtifact]:
        """Retrieve all output artifacts for a session, ordered by creation time."""
        query = "SELECT * FROM c WHERE c.session_id = @sid ORDER BY c.created_at ASC"
        params = [{"name": "@sid", "value": session_id}]
        items = self.outputs.query_items(
            query=query,
            parameters=params,
            partition_key=session_id,
        )
        return [OutputArtifact.model_validate(item) async for item in items]

    async def get_output(self, session_id: str, output_id: str) -> OutputArtifact:
        """Point-read a specific output artifact."""
        item = await _safe_cosmos_read(
            self.outputs.read_item(item=output_id, partition_key=session_id),
            not_found_msg=f"Output {output_id} in session {session_id}",
        )
        return OutputArtifact.model_validate(item)

    # ------------------------------------------------------------------
    # Delegation tracking (Phase 3)
    # ------------------------------------------------------------------
    # TODO: consider removing this
    async def append_delegation(
        self,
        session_id: str,
        record: DelegationRecord,
    ) -> None:
        """Append a delegation record to the parent session."""
        session = await self.get_session(session_id)
        session.delegations.append(record)
        session.updated_at = datetime.now(timezone.utc)
        await self.save_session(session)

    async def update_delegation_status(
        self,
        session_id: str,
        sub_session_id: str,
        status: str,
        result_summary: str | None = None,
    ) -> None:
        """Update the status of a delegation record within the parent session."""
        session = await self.get_session(session_id)
        for delegation in session.delegations:
            if delegation.sub_session_id == sub_session_id:
                delegation.status = status  # type: ignore[assignment]
                delegation.completed_at = datetime.now(timezone.utc).isoformat()
                if result_summary is not None:
                    delegation.result_summary = result_summary
                break
        session.updated_at = datetime.now(timezone.utc)
        await self.save_session(session)

    # ------------------------------------------------------------------
    # Phase 4 — Retention cleanup operations
    # ------------------------------------------------------------------

    async def delete_turns(self, session_id: str) -> int:
        """Delete all conversation turns for a session.  Returns count."""
        query = "SELECT c.id FROM c WHERE c.session_id = @sid"
        params = [{"name": "@sid", "value": session_id}]
        items = self.conversation.query_items(
            query=query, parameters=params, partition_key=session_id,
        )
        count = 0
        async for item in items:
            await self.conversation.delete_item(
                item=item["id"], partition_key=session_id,
            )
            count += 1
        return count

    async def delete_outputs(self, session_id: str) -> int:
        """Delete all output artifact records for a session.  Returns count."""
        query = "SELECT c.id FROM c WHERE c.session_id = @sid"
        params = [{"name": "@sid", "value": session_id}]
        items = self.outputs.query_items(
            query=query, parameters=params, partition_key=session_id,
        )
        count = 0
        async for item in items:
            await self.outputs.delete_item(
                item=item["id"], partition_key=session_id,
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Events container
    # ------------------------------------------------------------------

    async def save_event(self, event: SessionEvent) -> None:
        """Upsert a session event."""
        await self.events.upsert_item(to_cosmos_dict(event))

    async def get_events(
        self,
        session_id: str,
        event_group: str | None = None,
        event_type: str | None = None,
        limit: int = 200,
    ) -> list[SessionEvent]:
        """Retrieve events for a session, optionally filtered by group or type."""
        conditions = ["c.session_id = @sid"]
        params: list[dict[str, Any]] = [{"name": "@sid", "value": session_id}]

        if event_group is not None:
            conditions.append("c.event_group = @group")
            params.append({"name": "@group", "value": event_group})
        if event_type is not None:
            conditions.append("c.event_type = @etype")
            params.append({"name": "@etype", "value": event_type})

        where = " AND ".join(conditions)
        query = f"SELECT TOP {limit} * FROM c WHERE {where} ORDER BY c.timestamp ASC"
        items = self.events.query_items(
            query=query, parameters=params, partition_key=session_id,
        )
        return [SessionEvent.model_validate(item) async for item in items]

    async def delete_events(self, session_id: str) -> int:
        """Delete all events for a session.  Returns count."""
        query = "SELECT c.id FROM c WHERE c.session_id = @sid"
        params = [{"name": "@sid", "value": session_id}]
        items = self.events.query_items(
            query=query, parameters=params, partition_key=session_id,
        )
        count = 0
        async for item in items:
            await self.events.delete_item(
                item=item["id"], partition_key=session_id,
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Session document
    # ------------------------------------------------------------------

    async def delete_session(self, session_id: str) -> None:
        """Delete a session document."""
        try:
            await self.sessions.delete_item(
                item=session_id, partition_key=session_id,
            )
        except CosmosResourceNotFoundError:
            pass  # Already deleted

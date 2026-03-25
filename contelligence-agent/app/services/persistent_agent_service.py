"""Persistent Agent Service — durable session orchestration.

Replaces Phase 1's ``AgentService`` as the primary service class.  Every
Copilot SDK event is intercepted, persisted to Cosmos DB via ``SessionStore``,
and forwarded to the SSE event queue for real-time streaming.

Includes:
- **Large result offloading** (WS-4): tool results exceeding a configurable
  threshold are stored in Azure Blob Storage and replaced with a reference stub.
- **Output artifact tracking** (WS-5): write tools (``write_blob``,
  ``upload_to_search``, ``upsert_cosmos``) automatically register output
  artifacts.
- **Session resume** (WS-7): an existing session's conversation history can be
  loaded from Cosmos, serialised into SDK messages, and continued.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from app.connectors import BlobConnectorAdapter, LocalBlobConnectorAdapter
from app.core.event_loop import run_agent_loop
from app.core.session_factory import CopilotSession, SessionFactory
from app.models.agent_models import AgentEvent, InstructOptions
from app.models.exceptions import SessionNotFoundError
from app.models.session_models import (
    ConversationTurn,
    SessionEvent,
    SessionMetrics,
    SessionRecord,
    SessionStatus,
    ToolCallRecord,
)
from app.store.session_store import SessionStore
from app.skills import SkillsManager
from app.utils.sse import format_sse

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LARGE_RESULT_THRESHOLD_BYTES = 50_000  # 50 KB — configurable via AppSettings

EXTRACTION_TOOLS = frozenset({
    "extract_pdf",
    "extract_docx",
    "extract_xlsx",
    "extract_pptx",
    "call_doc_intelligence",
    "scrape_webpage",
    "transcribe_audio",
})

WRITE_TOOLS = frozenset({"write_blob", "upload_to_search", "upsert_cosmos"})

RESUMABLE_STATUSES = frozenset({
    SessionStatus.COMPLETED,
    SessionStatus.FAILED,
    SessionStatus.CANCELLED,
    SessionStatus.WAITING_FOR_INPUT,
})

# ---------------------------------------------------------------------------
# Event group classification
# ---------------------------------------------------------------------------

TOOL_EVENT_TYPES = frozenset({
    "tool_call_start",
    "tool_call_complete",
    "tool_call_error",
    "tool_execution_start",
    "tool_execution_complete",
    "tool_execution_partial_result",
    "tool_execution_progress",
    "tool_user_requested",
})

ASSISTANT_EVENT_TYPES = frozenset({
    "message",
    "assistant_intent",
    "reasoning",
    "assistant_streaming_delta",
    "assistant_usage",
    "system_message",
})

SESSION_EVENT_TYPES = frozenset({
    "session_start",
    "session_complete",
    "session_error",
    "session_info",
    "session_warning",
    "session_resume",
    "session_shutdown",
    "session_handoff",
    "session_model_change",
    "session_mode_changed",
    "session_plan_changed",
    "session_title_changed",
    "session_context_changed",
    "session_truncation",
    "session_compaction_start",
    "session_compaction_complete",
    "session_snapshot_rewind",
    "session_task_complete",
    "session_workspace_file_changed",
})

TURN_USER_EVENT_TYPES = frozenset({
    "user_message",
    "turn_start",
    "turn_end",
    "usage_info",
    "pending_messages_modified",
})

AGENT_EVENT_TYPES = frozenset({
    "subagent_started",
    "subagent_completed",
    "subagent_failed",
    "subagent_selected",
    "subagent_deselected",
    "delegation_start",
    "delegation_progress",
    "delegation_complete",
    "delegation_error",
})

META_EVENT_TYPES = frozenset({
    "hook_start",
    "hook_end",
    "skill_invoked",
    "approval_required",
    "abort",
    "unknown_event",
})

# ---------------------------------------------------------------------------
# EventTee — fan-out adapter for dual-queue persistence
# ---------------------------------------------------------------------------


class _EventTee:
    """Write-only queue adapter that pushes events to two queues.

    Hooks and ``on_event`` callbacks push events to this adapter.
    Events are duplicated to both the *sse_queue* (for real-time streaming
    to clients) and the *persist_queue* (for durable persistence).

    The ``persist_queue`` reference is mutable so it can be swapped when
    a session is continued via ``send_reply``.
    """

    def __init__(
        self,
        sse_queue: asyncio.Queue[AgentEvent],
        persist_queue: asyncio.Queue[AgentEvent],
    ) -> None:
        self.sse_queue = sse_queue
        self.persist_queue = persist_queue

    def put_nowait(self, item: AgentEvent) -> None:
        self.sse_queue.put_nowait(item)
        self.persist_queue.put_nowait(item)

    async def put(self, item: AgentEvent) -> None:
        self.sse_queue.put_nowait(item)
        self.persist_queue.put_nowait(item)


# ---------------------------------------------------------------------------
# PersistentAgentService
# ---------------------------------------------------------------------------


class PersistentAgentService:
    """Orchestrates agent sessions with full persistence to Cosmos DB."""

    def __init__(
        self,
        session_factory: SessionFactory,
        session_store: SessionStore,
        system_prompt: str,
        blob_connector: BlobConnectorAdapter | LocalBlobConnectorAdapter,
        outputs_container: str = "agent-outputs",
        large_result_threshold: int = LARGE_RESULT_THRESHOLD_BYTES,
        approval_manager: Any | None = None,
        dynamic_registry: Any | None = None,
        skills_manager: SkillsManager | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.store = session_store
        self.system_prompt = system_prompt
        self.blob_connector = blob_connector
        self.outputs_container = outputs_container
        self.large_result_threshold = large_result_threshold
        self.approval_manager = approval_manager
        self.dynamic_registry = dynamic_registry
        self.skills_manager = skills_manager

        # In-memory tracking (same pattern as Phase 1 AgentService)
        self.active_sessions: dict[str, CopilotSession] = {}
        self.event_queues: dict[str, asyncio.Queue] = {}
        self._event_tees: dict[str, _EventTee] = {}
        self._session_tasks: dict[str, asyncio.Task] = {}
        self._session_options: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # System prompt builder — no longer injects agents or skills
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Build the system prompt.

        Custom agents and skills are passed directly to the SDK session
        via ``SessionConfig.custom_agents`` and ``SessionConfig.skill_directories``
        respectively.
        """
        return self.system_prompt

    # ------------------------------------------------------------------
    # Public API — create & run
    # ------------------------------------------------------------------

    async def create_and_run(
        self,
        session_id: str | None,
        instruction: str,
        options: InstructOptions,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new persistent session and start the agent loop.

        Returns the session ID.
        """
        metadata = metadata or {}
        session_id = session_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Resolve and validate selected agents via DynamicAgentRegistry
        selected_agents: dict = {}
        allowed_agents: list[str] = []
        if self.dynamic_registry is not None:
            selected_agents = await self.dynamic_registry.get_agents_for_session(
                options.agents
            )
            allowed_agents = list(selected_agents.keys())

        # ----------------------------------------------------------
        # Convert agents to SDK CustomAgentConfig format
        # ----------------------------------------------------------
        from app.agents.sdk_adapters import agents_to_sdk_configs

        sdk_custom_agents: list[dict] = []
        if selected_agents:
            sdk_custom_agents = agents_to_sdk_configs(
                selected_agents,
                mcp_servers=self.session_factory.mcp_servers,
            )
        # logger.debug(f"SDK custom agents config for session {session_id}: {json.dumps(sdk_custom_agents, indent=2)}")
        
        # ----------------------------------------------------------
        # Resolve skill directories for SDK native loading
        # ----------------------------------------------------------
        skill_directories: list[str] = []
        disabled_skills: list[str] = []
        active_skill_ids: list[str] = list(options.skill_ids) if options.skill_ids else []

        if self.skills_manager is not None:
            try:
                skill_directories = self.skills_manager.get_skill_directories()

                # Collect active skill IDs (from agents' bound_skills + explicit)
                for agent_def in selected_agents.values():
                    bound = getattr(agent_def, "bound_skills", None) or []
                    for name in bound:
                        if name not in active_skill_ids:
                            active_skill_ids.append(name)
            except Exception:
                logger.warning(
                    "Session %s: failed to resolve skill directories — continuing without",
                    session_id,
                    exc_info=True,
                )

        # Build system prompt (no longer includes agents or skills)
        dynamic_prompt = self._build_system_prompt()

        # 1. Persist SessionRecord
        record = SessionRecord(
            id=session_id,
            created_at=now,
            updated_at=now,
            status=SessionStatus.ACTIVE,
            model=options.model,
            instruction=instruction,
            user_id=metadata.get("user_id"),
            schedule_id=metadata.get("schedule_id"),
            trigger_reason=metadata.get("trigger_reason"),
            options=options.model_dump(),
            metrics=SessionMetrics(),
            allowed_agents=allowed_agents,
            active_skill_ids=active_skill_ids,
        )
        await self.store.save_session(record)

        # 2. Persist initial user turn (sequence 0)
        await self.store.save_turn(
            ConversationTurn(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sequence=0,
                timestamp=now,
                role="user",
                prompt=instruction,
            )
        )

        # 3. Wire up event queues + SDK session + background task
        #    SSE queue — consumed by stream_events() for real-time delivery
        #    Persist queue — consumed by _persistence_consumer() for durable storage
        #    EventTee — hooks and on_event push here; events fan out to both queues
        sse_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        persist_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        tee = _EventTee(sse_queue, persist_queue)
        self.event_queues[session_id] = sse_queue
        self._event_tees[session_id] = tee

        try:
            sdk_session = await self.session_factory.create_session(
                session_id=session_id,
                model=options.model,
                system_prompt=dynamic_prompt,
                event_queue=tee,  # type: ignore[arg-type]  # duck-typed
                custom_agents=sdk_custom_agents or None,
                skill_directories=skill_directories or None,
                disabled_skills=disabled_skills or None,
            )
        except Exception as exc:
            logger.exception(
                "Session %s failed to create SDK session: %s",
                session_id, exc,
            )
            await self.store.update_session_status(
                session_id, SessionStatus.FAILED,
            )
            await sse_queue.put(
                AgentEvent(
                    type="session_error",
                    data={"error": f"Failed to create SDK session: {exc}"},
                    session_id=session_id,
                )
            )
            self.event_queues.pop(session_id, None)
            self._event_tees.pop(session_id, None)
            raise

        self.active_sessions[session_id] = sdk_session

        # Track session options for approval flow
        self._session_options[session_id] = options.model_dump()

        turn_seq = [1]  # mutable counter (sequence 0 = initial user turn)
        task = asyncio.create_task(
            self._run_persistent_loop(
                sdk_session, session_id, instruction, tee,
                persist_queue, turn_seq,
            )
        )
        self._session_tasks[session_id] = task

        # Enforce timeout
        asyncio.create_task(
            self._enforce_timeout(session_id, options.timeout_minutes)
        )

        logger.info("Session %s created (model=%s)", session_id, options.model)
        return session_id

    # ------------------------------------------------------------------
    # Public API — stream events (same as Phase 1)
    # ------------------------------------------------------------------

    async def stream_events(self, session_id: str) -> AsyncGenerator[dict, None]:
        """Async generator yielding SSE-formatted events."""
        queue = self.event_queues.get(session_id)
        if not queue:
            yield format_sse("session_error", {"error": "Session not found"})
            return

        while True:
            try:
                event: AgentEvent = await asyncio.wait_for(queue.get(), timeout=300)
            except asyncio.TimeoutError:
                yield format_sse("keepalive", {"message": "keepalive"})
                continue

            yield format_sse(event.type, event.data)

            if event.type in ("session_completed", "session_error"):
                break

    # ------------------------------------------------------------------
    # Public API — send reply with persistence
    # ------------------------------------------------------------------

    async def send_reply(self, session_id: str, message: str) -> None:
        """Persist user reply, update status, and forward to SDK session."""
        sdk_session = self.active_sessions.get(session_id)
        if not sdk_session:
            raise SessionNotFoundError(session_id)

        # Persist user reply
        turns = await self.store.get_turns(session_id)
        next_seq = len(turns)
        await self.store.save_turn(
            ConversationTurn(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sequence=next_seq,
                timestamp=datetime.now(timezone.utc),
                role="user",
                prompt=message,
            )
        )

        # Transition back to ACTIVE
        await self.store.update_session_status(session_id, SessionStatus.ACTIVE)

        # NOTE: do NOT call sdk_session.send_message() here — the
        # _run_persistent_loop → run_agent_loop → session.run() path
        # sends the message and waits for idle.  Sending here as well
        # would double-deliver the prompt to the SDK.

        # Re-run the agent loop for the follow-up
        tee = self._event_tees.get(session_id)
        if tee:
            # Swap to a fresh persist queue for this continuation
            persist_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            tee.persist_queue = persist_queue
            turn_seq = [next_seq + 1]
            task = asyncio.create_task(
                self._run_persistent_loop(
                    sdk_session, session_id, message, tee,
                    persist_queue, turn_seq,
                )
            )
            self._session_tasks[session_id] = task

    # ------------------------------------------------------------------
    # Public API — cancel with persistence
    # ------------------------------------------------------------------

    async def cancel(self, session_id: str) -> None:
        """Cancel an active session and persist the cancellation."""
        sdk_session = self.active_sessions.pop(session_id, None)
        task = self._session_tasks.pop(session_id, None)
        queue = self.event_queues.pop(session_id, None)
        self._event_tees.pop(session_id, None)
        self._session_options.pop(session_id, None)

        # Persist cancellation
        try:
            await self.store.update_session_status(
                session_id, SessionStatus.CANCELLED
            )
        except SessionNotFoundError:
            pass  # Session may not have been persisted yet

        if task and not task.done():
            task.cancel()
        if sdk_session:
            await sdk_session.close()
        if queue:
            queue.put_nowait(
                AgentEvent(
                    type="session_error",
                    data={"error": "Session cancelled"},
                    session_id=session_id,
                )
            )

    # ------------------------------------------------------------------
    # Public API — delete session and all related data
    # ------------------------------------------------------------------

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        """Delete a session and all related data.

        1. Cancel the session if it is currently active in memory.
        2. Retrieve output artifacts to identify blob storage references.
        3. Delete blobs associated with the session (outputs + large results).
        4. Delete all Cosmos DB data: turns, events, session doc.

        Returns a summary dict with counts of deleted resources.
        """
        # 1. Verify the session exists in Cosmos (raises SessionNotFoundError)
        await self.store.get_session(session_id)

        # 2. Cancel if active in memory
        if session_id in self.active_sessions:
            await self.cancel(session_id)

        # 3. Delete blob artifacts for this session
        blobs_deleted = 0
        try:
            blobs_deleted = await self.blob_connector.delete_prefix(
                self.outputs_container, f"{session_id}/",
            )
        except Exception:
            logger.warning(
                "Failed to delete blobs for session %s — continuing with Cosmos cleanup",
                session_id,
                exc_info=True,
            )

        # 4. Delete all Cosmos documents in parallel
        turns_deleted, events_deleted = await asyncio.gather(
            self.store.delete_turns(session_id),
            self.store.delete_events(session_id),
        )

        # 5. Delete the session document itself
        await self.store.delete_session(session_id)

        summary = {
            "session_id": session_id,
            "turns_deleted": turns_deleted,
            "events_deleted": events_deleted,
            "blobs_deleted": blobs_deleted,
        }
        logger.info("Deleted session %s: %s", session_id, summary)
        return summary

    # ------------------------------------------------------------------
    # Public API — session status
    # ------------------------------------------------------------------
    async def get_session_status(self, session_id: str) -> dict[str, Any]:
        """Return session status from in-memory tracking or Cosmos."""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            return {"session_id": session_id, "status": session.status}

        # Fall back to Cosmos
        try:
            record = await self.store.get_session(session_id)
            return {"session_id": session_id, "status": record.status.value}
        except SessionNotFoundError:
            return {"session_id": session_id, "status": "not_found"}

    # ------------------------------------------------------------------
    # Public API — session resume
    # ------------------------------------------------------------------
    async def resume_session(
        self,
        session_id: str,
        instruction: str,
        options: InstructOptions,
    ) -> str:
        """Resume a previously completed/failed/paused session.

        Loads conversation history from Cosmos, rebuilds the SDK message
        list, and continues with the new instruction.

        Returns the same *session_id*.
        """
        from fastapi import HTTPException

        # 1. Validate resumability
        record = await self.store.get_session(session_id)

        if record.status == SessionStatus.ACTIVE:
            if session_id in self.active_sessions:
                logger.debug(f"Session {session_id} is already active in memory — treating resume as follow-up message.")
                
                # Session is genuinely running in memory — treat as a
                # follow-up message rather than a full resume.
                await self.send_reply(session_id, instruction)
                return session_id
            # else: stale ACTIVE status (e.g. after server restart) — safe
            # to resume by rebuilding the SDK session from history.
        elif record.status not in RESUMABLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Session cannot be resumed — status is '{record.status.value}'. "
                    f"Only sessions with status "
                    f"{[s.value for s in RESUMABLE_STATUSES]} can be resumed."
                ),
            )

        # 2. Determine the next turn sequence from persisted history
        turns = await self.store.get_turns(session_id)
        logger.debug(
            f"Loaded {len(turns)} conversation turns for session {session_id} resume."
        )
        next_sequence = len(turns)

        # 3. Update session status to ACTIVE
        record.status = SessionStatus.ACTIVE
        record.updated_at = datetime.now(timezone.utc)
        await self.store.save_session(record)

        # 4. Save new user instruction as next turn
        await self.store.save_turn(
            ConversationTurn(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sequence=next_sequence,
                timestamp=datetime.now(timezone.utc),
                role="user",
                prompt=instruction,
            )
        )

        # 5. Resolve agents and skills for the resumed session
        #    (same logic as create_and_run but applied to resume)
        selected_agents: dict = {}
        if self.dynamic_registry is not None:
            try:
                agent_ids = record.options.get("agents", []) if record.options else []
                selected_agents = await self.dynamic_registry.get_agents_for_session(
                    agent_ids
                )
            except Exception:
                logger.warning(
                    "Session %s: failed to resolve agents for resume — continuing without",
                    session_id, exc_info=True,
                )

        from app.agents.sdk_adapters import agents_to_sdk_configs

        sdk_custom_agents: list[dict] = []
        if selected_agents:
            sdk_custom_agents = agents_to_sdk_configs(
                selected_agents,
                mcp_servers=self.session_factory.mcp_servers,
            )

        skill_directories: list[str] = []
        if self.skills_manager is not None:
            try:
                skill_directories = self.skills_manager.get_skill_directories()
            except Exception:
                logger.warning(
                    "Session %s: failed to resolve skill directories for resume",
                    session_id, exc_info=True,
                )

        # 6. Resume SDK session — the SDK preserves conversation history
        #    server-side, so we don't need to replay messages manually.
        sse_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        persist_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        tee = _EventTee(sse_queue, persist_queue)
        self.event_queues[session_id] = sse_queue
        self._event_tees[session_id] = tee

        try:
            sdk_session = await self.session_factory.resume_session(
                session_id=session_id,
                model=options.model or record.model,
                system_prompt=self.system_prompt,
                event_queue=tee,  # type: ignore[arg-type]
                custom_agents=sdk_custom_agents or None,
                skill_directories=skill_directories or None,
            )
        except Exception as exc:
            logger.exception(
                f"Session {session_id} failed to resume SDK session: {exc}"
            )
            await self.store.update_session_status(
                session_id, SessionStatus.FAILED,
            )
            # Notify any SSE listeners of the failure
            await sse_queue.put(
                AgentEvent(
                    type="session_error",
                    data={"error": f"Failed to resume SDK session: {exc}"},
                    session_id=session_id,
                )
            )
            # Clean up event queues
            self.event_queues.pop(session_id, None)
            self._event_tees.pop(session_id, None)
            raise

        self.active_sessions[session_id] = sdk_session

        # 6. Start persistent loop
        turn_seq = [next_sequence + 1]
        task = asyncio.create_task(
            self._run_persistent_loop(
                sdk_session, session_id, instruction, tee,
                persist_queue, turn_seq,
            )
        )
        self._session_tasks[session_id] = task

        logger.info(f"Session {session_id} resumed")
        return session_id

    # # ------------------------------------------------------------------
    # # Large result offloading (WS-4)
    # # ------------------------------------------------------------------

    # async def _store_large_result(
    #     self,
    #     session_id: str,
    #     tool_name: str,
    #     result: dict[str, Any],
    # ) -> str:
    #     """Offload a large tool result to Blob Storage, returning the blob reference."""
    #     timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
    #     blob_path = f"{session_id}/tool_results/{tool_name}_{timestamp}.json"

    #     await self.blob_connector.upload_blob(
    #         container=self.outputs_container,
    #         path=blob_path,
    #         data=json.dumps(result, default=str).encode("utf-8"),
    #         content_type="application/json",
    #     )

    #     return f"{self.outputs_container}/{blob_path}"

    # async def fetch_large_result(self, blob_ref: str) -> dict[str, Any]:
    #     """Fetch an offloaded tool result from Blob Storage."""
    #     parts = blob_ref.split("/", 1)
    #     container = parts[0]
    #     path = parts[1]
    #     data = await self.blob_connector.download_blob(container, path)
    #     return json.loads(data)

    # ------------------------------------------------------------------
    # Output artifact tracking (WS-5)
    # ------------------------------------------------------------------

    # async def _register_output(
    #     self,
    #     session_id: str,
    #     tool_name: str,
    #     params: dict[str, Any],
    #     result: dict[str, Any],
    # ) -> None:
    #     """Register an output artifact when a write tool completes."""
    #     if tool_name not in WRITE_TOOLS:
    #         return

    #     artifact: OutputArtifact | None = None
    #     now = datetime.now(timezone.utc)

    #     if tool_name == "write_blob":
    #         content = params.get("data", params.get("content", ""))
    #         size = len(content.encode("utf-8")) if isinstance(content, str) else len(content)
    #         artifact = OutputArtifact(
    #             id=str(uuid.uuid4()),
    #             session_id=session_id,
    #             name=params.get("path", "unknown").split("/")[-1],
    #             description=f"Written to {params.get('container', '')}/{params.get('path', '')}",
    #             artifact_type=self._infer_type(
    #                 params.get("content_type", "application/json")
    #             ),
    #             storage_type="blob",
    #             storage_location=f"{params.get('container', '')}/{params.get('path', '')}",
    #             size_bytes=size,
    #             content_type=params.get("content_type", "application/json"),
    #             created_at=now,
    #         )

    #     elif tool_name == "upload_to_search":
    #         artifact = OutputArtifact(
    #             id=str(uuid.uuid4()),
    #             session_id=session_id,
    #             name=f"{params.get('index', 'unknown')} index upload",
    #             description=(
    #                 f"Uploaded {result.get('uploaded', result.get('succeeded', 0))} "
    #                 f"docs to '{params.get('index', 'unknown')}'"
    #             ),
    #             artifact_type="search_index",
    #             storage_type="search_index",
    #             storage_location=params.get("index", "unknown"),
    #             record_count=result.get("uploaded", result.get("succeeded", 0)),
    #             created_at=now,
    #         )

    #     elif tool_name == "upsert_cosmos":
    #         doc = params.get("document", {})
    #         artifact = OutputArtifact(
    #             id=str(uuid.uuid4()),
    #             session_id=session_id,
    #             name=f"Cosmos upsert: {params.get('container', 'unknown')}",
    #             description=(
    #                 f"Upserted document to "
    #                 f"{params.get('database', 'default')}/{params.get('container', 'unknown')}"
    #             ),
    #             artifact_type="json",
    #             storage_type="cosmos",
    #             storage_location=(
    #                 f"{params.get('database', 'default')}/"
    #                 f"{params.get('container', 'unknown')}/"
    #                 f"{doc.get('id', 'unknown')}"
    #             ),
    #             created_at=now,
    #         )

    #     if artifact is not None:
    #         await self.store.save_output(artifact)
    #         await self.store.update_session_metrics(
    #             session_id, outputs_produced=1
    #         )

    @staticmethod
    def _infer_type(content_type: str) -> str:
        """Map MIME content type to a human-readable artifact type."""
        mapping = {
            "application/json": "json",
            "text/csv": "csv",
            "application/pdf": "pdf",
            "text/plain": "text",
            "text/markdown": "markdown",
            "text/html": "html",
        }
        return mapping.get(content_type, "blob_ref")

    # ------------------------------------------------------------------
    # Internal — persistent event loop
    # ------------------------------------------------------------------

    async def _run_persistent_loop(
        self,
        session: CopilotSession,
        session_id: str,
        instruction: str,
        event_tee: _EventTee,
        persist_queue: asyncio.Queue[AgentEvent],
        turn_sequence: list[int],
    ) -> None:
        """Run the SDK agent loop, persisting every event.

        Events flow through the ``_EventTee`` which fans them out to both
        the SSE queue (for real-time streaming) and the *persist_queue*.
        A background ``_persistence_consumer`` reads from the persist queue
        and durably stores each event before the loop completes.

        Passes ``approval_manager`` and ``session_options`` to
        ``run_agent_loop`` so that destructive tool calls can be gated by
        user approval.
        """
        # Start persistence consumer — runs concurrently with the agent loop
        consumer = asyncio.create_task(
            self._persistence_consumer(session_id, persist_queue, turn_sequence)
        )

        try:
            session_opts = self._session_options.get(session_id, {})
            await run_agent_loop(
                session,
                instruction,
                event_tee,  # type: ignore[arg-type]  # duck-typed
                approval_manager=self.approval_manager,
                session_options=session_opts,
            )
        except Exception as exc:
            logger.exception("Session %s failed: %s", session_id, exc)
            await self.store.update_session_status(
                session_id, SessionStatus.FAILED
            )
            await event_tee.put(
                AgentEvent(
                    type="session_error",
                    data={"error": str(exc)},
                    session_id=session_id,
                )
            )

        # Wait for all events to be persisted before cleanup
        await consumer

        self.active_sessions.pop(session_id, None)
        self._session_tasks.pop(session_id, None)
        self._session_options.pop(session_id, None)

        # Persist final session state (completion/failure)
        await self._persist_session_events(session, session_id, turn_sequence)

    # ------------------------------------------------------------------
    # Internal — persistence consumer
    # ------------------------------------------------------------------

    async def _persistence_consumer(
        self,
        session_id: str,
        persist_queue: asyncio.Queue[AgentEvent],
        turn_sequence: list[int],
    ) -> None:
        """Drain *persist_queue* and durably store each event.

        Runs as a concurrent task alongside the agent loop.  Terminates
        when a terminal event (``session_complete`` or ``session_error``)
        is received.
        """
        while True:
            try:
                event = await asyncio.wait_for(persist_queue.get(), timeout=300)
            except asyncio.TimeoutError:
                # Safety valve — keep waiting
                continue

            try:
                await self._persist_event(session_id, event, turn_sequence)
            except Exception:
                logger.exception(
                    "Failed to persist event %s for session %s",
                    event.type, session_id,
                )

            if event.type in ("session_complete", "session_error"):
                break

    async def _persist_event(
        self,
        session_id: str,
        event: AgentEvent,
        turn_sequence: list[int],
    ) -> None:
        """Dispatch a single ``AgentEvent`` to the appropriate group persist method.

        Every event is persisted to the ``events`` Cosmos container via
        the group handler.  Events that also require structured persistence
        (conversation turns, session metrics) are handled within their
        group function.
        """
        etype = event.type

        if etype in TOOL_EVENT_TYPES:
            await self._persist_tool_event(session_id, event, turn_sequence)
        elif etype in ASSISTANT_EVENT_TYPES:
            await self._persist_assistant_event(session_id, event, turn_sequence)
        elif etype in SESSION_EVENT_TYPES:
            await self._persist_session_lifecycle_event(session_id, event)
        elif etype in TURN_USER_EVENT_TYPES:
            await self._persist_turn_user_event(session_id, event)
        elif etype in AGENT_EVENT_TYPES:
            await self._persist_agent_event(session_id, event)
        elif etype in META_EVENT_TYPES:
            await self._persist_meta_event(session_id, event)
        else:
            # Forward-compatible: persist unknown events under "meta"
            await self._save_session_event(session_id, event, "meta")

    # ------------------------------------------------------------------
    # Internal — save a generic SessionEvent to Cosmos
    # ------------------------------------------------------------------

    async def _save_session_event(
        self,
        session_id: str,
        event: AgentEvent,
        group: str,
    ) -> None:
        """Create and persist a ``SessionEvent`` in the events container."""
        await self.store.save_event(
            SessionEvent(
                id=str(uuid.uuid4()),
                session_id=session_id,
                event_type=event.type,
                event_group=group,
                data=event.data,
                timestamp=event.timestamp,
            )
        )

    # ------------------------------------------------------------------
    # Group: Tool events
    # ------------------------------------------------------------------

    async def _persist_tool_event(
        self,
        session_id: str,
        event: AgentEvent,
        turn_sequence: list[int],
    ) -> None:
        """Persist all tool-related events.

        Hook events (``tool_call_start/complete/error``) also write
        structured ``ConversationTurn`` records for conversation replay.
        SDK events (``tool_execution_*``) are stored as raw events only.
        """
        etype = event.type

        # Structured persistence for hook-originated tool events
        if etype == "tool_call_start":
            await self.persist_tool_start(
                session_id,
                event.data.get("tool", "unknown"),
                event.data.get("params", {}),
                turn_sequence,
            )
        elif etype == "tool_call_complete" or etype == "tool_execution_complete":
            await self.persist_tool_complete(
                session_id,
                event.data.get("tool", "unknown"),
                event.data,
            )
        elif etype == "tool_call_error":
            await self.persist_tool_error(
                session_id,
                event.data.get("tool", "unknown"),
                event.data.get("error", "Unknown error"),
            )

        # All tool events → events container
        await self._save_session_event(session_id, event, "tool")

    # ------------------------------------------------------------------
    # Group: Assistant / message events
    # ------------------------------------------------------------------

    async def _persist_assistant_event(
        self,
        session_id: str,
        event: AgentEvent,
        turn_sequence: list[int],
    ) -> None:
        """Persist all assistant-related events.

        ``message`` events also create a structured ``ConversationTurn``
        for conversation history replay.  Other assistant events
        (reasoning, intent, streaming deltas, usage) are stored as
        raw events for observability and audit.
        """
        etype = event.type

        if etype == "message":
            content = event.data.get("content", "")
            if content not in ("", None):
                await self.persist_assistant_message(
                    session_id,
                    content,
                    turn_sequence,
                )
        elif etype == "assistant_usage":
            # Also update session-level metrics with token counts
            input_tokens = event.data.get("input_tokens") or 0
            output_tokens = event.data.get("output_tokens") or 0
            total = input_tokens + output_tokens
            if total > 0:
                try:
                    record = await self.store.get_session(session_id)
                    record.metrics.input_tokens += int(input_tokens)
                    record.metrics.output_tokens += int(output_tokens)
                    record.metrics.cache_read_tokens += int(event.data.get("cache_read_tokens") or 0)
                    record.metrics.cache_write_tokens += int(event.data.get("cache_write_tokens") or 0)
                    record.metrics.model = event.data.get("model", None)
                    if record.metrics.cost is None:
                        record.metrics.cost = 0.0
                    record.metrics.cost += float(event.data.get("cost", 0.0) or 0.0)
                    
                    record.metrics.total_tokens_used += int(total)
                    record.updated_at = datetime.now(timezone.utc)
                    await self.store.save_session(record)
                except Exception:
                    logger.exception(f"Error while persisting assistant_usage for session {session_id}")
                    logger.debug(f"Could not persist assistant_usage for session {session_id}")

        # All assistant events → events container
        await self._save_session_event(session_id, event, "assistant")

    # ------------------------------------------------------------------
    # Group: Session lifecycle events
    # ------------------------------------------------------------------

    async def _persist_session_lifecycle_event(
        self,
        session_id: str,
        event: AgentEvent,
    ) -> None:
        """Persist all session lifecycle events.

        All events are stored in the events container.  Specific events
        also trigger structured updates (e.g. session status changes).
        """
        etype = event.type

        if etype == "session_completed":
            # Extract final metrics from shutdown data when available
            model_metrics = event.data.get("model_metrics")
            if model_metrics and isinstance(model_metrics, dict):
                try:
                    record = await self.store.get_session(session_id)
                    record.updated_at = datetime.now(timezone.utc)
                    await self.store.save_session(record)
                except Exception:
                    logger.debug(
                        "Could not persist shutdown metrics for session %s",
                        session_id,
                    )

        elif etype == "session_task_complete":
            summary = event.data.get("summary")
            if summary:
                try:
                    record = await self.store.get_session(session_id)
                    record.summary = summary
                    record.updated_at = datetime.now(timezone.utc)
                    await self.store.save_session(record)
                except Exception:
                    logger.debug(
                        "Could not persist task_complete summary for session %s",
                        session_id,
                    )

        elif etype == "session_title_changed":
            # Store title in session metadata for quick lookup
            try:
                record = await self.store.get_session(session_id)
                record.updated_at = datetime.now(timezone.utc)
                await self.store.save_session(record)
            except Exception:
                logger.debug(
                    "Could not persist title change for session %s",
                    session_id,
                )

        # All session lifecycle events → events container
        await self._save_session_event(session_id, event, "session")

    # ------------------------------------------------------------------
    # Group: Turn / user events
    # ------------------------------------------------------------------

    async def _persist_turn_user_event(
        self,
        session_id: str,
        event: AgentEvent,
    ) -> None:
        """Persist turn, user, and usage events.

        ``usage_info`` events also update session-level token metrics.
        """
        etype = event.type

        if etype == "usage_info":
            current_tokens = event.data.get("current_tokens")
            if current_tokens is not None:
                try:
                    record = await self.store.get_session(session_id)
                    record.metrics.total_tokens_used = int(current_tokens)
                    record.updated_at = datetime.now(timezone.utc)
                    await self.store.save_session(record)
                except Exception:
                    logger.debug(
                        "Could not persist usage_info for session %s",
                        session_id,
                    )

        # All turn/user events → events container
        await self._save_session_event(session_id, event, "turn")

    # ------------------------------------------------------------------
    # Group: Agent / delegation events
    # ------------------------------------------------------------------

    async def _persist_agent_event(
        self,
        session_id: str,
        event: AgentEvent,
    ) -> None:
        """Persist subagent and delegation events."""
        # All agent events → events container
        await self._save_session_event(session_id, event, "agent")

    # ------------------------------------------------------------------
    # Group: Meta events (hooks, skills, approval, etc.)
    # ------------------------------------------------------------------

    async def _persist_meta_event(
        self,
        session_id: str,
        event: AgentEvent,
    ) -> None:
        """Persist hook, skill, approval, and other meta events."""
        # All meta events → events container
        await self._save_session_event(session_id, event, "meta")

    async def _persist_session_events(
        self,
        session: CopilotSession,
        session_id: str,
        turn_sequence: list[int],
    ) -> None:
        """Persist session outcome based on CopilotSession status.

        Since Phase 1's CopilotSession uses callback-based event flow (the
        SDK's ``on_event`` handler pushes events to the queue), we persist
        the final session state after ``session.run()`` completes.
        """
        if session.status == "completed":
            # Mark session as completed
            record = await self.store.get_session(session_id)
            duration = (datetime.now(timezone.utc) - record.created_at).total_seconds()
            await self.store.update_session_status(
                session_id, SessionStatus.COMPLETED,
                summary=session._last_message or None,
            )
            # Set total_duration absolutely
            record = await self.store.get_session(session_id)
            record.metrics.total_duration_seconds = duration
            record.updated_at = datetime.now(timezone.utc)
            await self.store.save_session(record)
        elif session.status == "error":
            await self.store.update_session_status(
                session_id, SessionStatus.FAILED
            )

    # ------------------------------------------------------------------
    # Internal — persist individual events from hooks
    # ------------------------------------------------------------------

    async def persist_tool_start(
        self,
        session_id: str,
        tool_name: str,
        params: dict[str, Any] | str,
        turn_sequence: list[int],
    ) -> None:
        """Persist a tool execution start event (called from hooks)."""
        now = datetime.now(timezone.utc)
        # params may arrive as a JSON string from the SDK event — parse it
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except (json.JSONDecodeError, TypeError):
                params = {"_raw": params}
        await self.store.save_turn(
            ConversationTurn(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sequence=turn_sequence[0],
                timestamp=now,
                role="tool",
                tool_call=ToolCallRecord(
                    tool_name=tool_name,
                    parameters=params,
                    started_at=now,
                    status="running",
                ),
            )
        )
        turn_sequence[0] += 1
        await self.store.update_session_metrics(
            session_id, total_tool_calls=1
        )

    async def persist_tool_complete(
        self,
        session_id: str,
        tool_name: str,
        result: dict[str, Any] | None,
    ) -> None:
        """Persist a tool execution complete event (called from hooks)."""
        now = datetime.now(timezone.utc)
        stored_result = result
        # result_ref: str | None = None

        # Check for large result offloading
        if result is not None:
            result_json = json.dumps(result, default=str)
            if len(result_json.encode("utf-8")) > self.large_result_threshold:
                # result_ref = await self._store_large_result(
                #     session_id, tool_name, result
                # )
                stored_result = {
                    "_note": "Result too large for inline storage.",
                }

        await self.store.update_tool_call(
            session_id=session_id,
            tool_name=tool_name,
            result=stored_result,
            completed_at=now,
            status="success",
        )

        # Update documents_processed for extraction tools
        if tool_name in EXTRACTION_TOOLS:
            await self.store.update_session_metrics(
                session_id, documents_processed=1
            )

        # # Register output artifacts for write tools
        # if tool_name in WRITE_TOOLS and result is not None:
        #     # We need the original params — retrieve from the turn record
        #     turns = await self.store.get_turns(session_id)
        #     for turn in reversed(turns):
        #         if (
        #             turn.role == "tool"
        #             and turn.tool_call
        #             and turn.tool_call.tool_name == tool_name
        #             and turn.tool_call.status == "success"
        #         ):
        #             await self._register_output(
        #                 session_id, tool_name, turn.tool_call.parameters, result
        #             )
        #             break

    async def persist_tool_error(
        self,
        session_id: str,
        tool_name: str,
        error: str,
    ) -> None:
        """Persist a tool execution error event (called from hooks)."""
        await self.store.update_tool_call(
            session_id=session_id,
            tool_name=tool_name,
            result=None,
            completed_at=datetime.now(timezone.utc),
            status="error",
            error=error,
        )
        await self.store.update_session_metrics(
            session_id, errors_encountered=1
        )

    async def persist_assistant_message(
        self,
        session_id: str,
        content: str,
        turn_sequence: list[int],
    ) -> None:
        """Persist an assistant message as a conversation turn."""
        await self.store.save_turn(
            ConversationTurn(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sequence=turn_sequence[0],
                timestamp=datetime.now(timezone.utc),
                role="assistant",
                content=content,
            )
        )
        turn_sequence[0] += 1

    # ------------------------------------------------------------------
    # Internal — timeout enforcement
    # ------------------------------------------------------------------

    async def _enforce_timeout(
        self, session_id: str, timeout_minutes: int
    ) -> None:
        """Cancel a session after the configured timeout period."""
        await asyncio.sleep(timeout_minutes * 60)
        if session_id in self.active_sessions:
            logger.warning(
                "Session %s timed out after %d min",
                session_id,
                timeout_minutes,
            )
            await self.cancel(session_id)

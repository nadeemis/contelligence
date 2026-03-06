"""Agent Delegation Service — manages sub-session delegation to custom agents.

The ``AgentDelegator`` creates scoped Copilot SDK sub-sessions, enforces
safety limits, links sub-sessions to parents, and collects results.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from copilot import CopilotClient

from app.agents.dynamic_registry import DynamicAgentRegistry
from app.core.session_factory import CopilotSession, SessionFactory
from app.core.tool_registry import ToolRegistry
from app.models.agent_models import AgentEvent
from app.models.session_models import DelegationRecord
from app.services.context_collector import ContextCollector
from app.store.session_store import SessionStore

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class AgentDelegator:
    """Manages delegation from the main agent to specialized custom agents."""

    def __init__(
        self,
        session_factory: SessionFactory,
        session_store: SessionStore,
        dynamic_registry: DynamicAgentRegistry | None = None,
        context_collector: ContextCollector | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.store = session_store
        self.registry = dynamic_registry
        self.context_collector = context_collector or ContextCollector(session_store)

    async def delegate(
        self,
        agent_name: str,
        instruction: str,
        context: dict[str, Any] | None = None,
        parent_session_id: str | None = None,
        event_queue: asyncio.Queue[AgentEvent] | None = None,
        allowed_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        """Delegate a subtask to a custom agent.

        Parameters
        ----------
        agent_name:
            Agent id to delegate to.
        instruction:
            Clear task description for the sub-agent.
        context:
            Optional context data to inject into the instruction.
        parent_session_id:
            The calling session's ID for parent→child linking.
        event_queue:
            Optional queue for streaming delegation events back to the caller.
        allowed_agents:
            If set, the target agent must be in this list (session-level restriction).

        Returns
        -------
        dict with keys: ``agent``, ``sub_session_id``, ``content``, ``status``.
        """
        # Enforce session-level agent restrictions
        if allowed_agents and agent_name not in allowed_agents:
            raise ValueError(
                f"Agent '{agent_name}' is not allowed in this session. "
                f"Allowed agents: {allowed_agents}"
            )

        logger.warning(
            f"Starting delegation to agent '{agent_name}' with instruction: {instruction[:200]}"
        )
        
        logger.warning(
            f"Context data for delegation: {json.dumps(context, indent=2, default=str)}"
        )
        
        # Resolve from dynamic registry if available, else fall back to static dict
        if self.registry is not None:
            agent_def = await self.registry.get_agent(agent_name)
            if agent_def is None:
                available = await self.registry.get_all_agents()
                raise ValueError(
                    f"Unknown agent: {agent_name!r}. "
                    f"Available: {list(available.keys())}"
                )
            # Fire-and-forget usage tracking
            asyncio.create_task(self.registry._store.increment_usage(agent_name))
        else:
            from app.agents import CUSTOM_AGENTS
            agent_def = CUSTOM_AGENTS.get(agent_name)
            if agent_def is None:
                raise ValueError(
                    f"Unknown agent: {agent_name!r}. "
                    f"Available: {list(CUSTOM_AGENTS.keys())}"
                )

        # Generate sub-session ID
        short_id = uuid.uuid4().hex[:8]
        sub_session_id = (
            f"{parent_session_id}-{agent_name}-{short_id}"
            if parent_session_id
            else f"-{agent_name}-{short_id}"
        )

        # Emit delegation_start event
        if event_queue is not None:
            event_queue.put_nowait(
                AgentEvent(
                    type="delegation_start",
                    data={
                        "agent": agent_name,
                        "sub_session_id": sub_session_id,
                        "instruction": instruction[:200],
                    },
                    session_id=parent_session_id or "",
                )
            )

        # Link parent→child in the session store
        if parent_session_id:
            await self._link_sub_session(
                parent_session_id=parent_session_id,
                sub_session_id=sub_session_id,
                agent_name=agent_name,
                instruction=instruction,
            )

        # Filter tools to the agent's allowed set
        tools_override = self.session_factory.tool_registry.filter_tools(
            agent_def.tools
        )

        # Filter MCP servers to the agent's allowed set
        mcp_override: dict[str, Any] = {}
        for key in agent_def.mcp_servers:
            if key in self.session_factory.mcp_servers:
                mcp_override[key] = self.session_factory.mcp_servers[key]

        # ----------------------------------------------------------
        # Collect parent session context automatically
        # ----------------------------------------------------------
        parent_context_block = ""
        if parent_session_id:
            try:
                parent_context_block = await self.context_collector.collect(
                    parent_session_id
                )
                if parent_context_block:
                    logger.info(
                        "Collected %d chars of parent context for delegation "
                        "to '%s' (parent: %s)",
                        len(parent_context_block),
                        agent_name,
                        parent_session_id,
                    )
            except Exception:
                logger.warning(
                    "Failed to collect parent context for delegation to '%s' "
                    "— proceeding with explicit context only.",
                    agent_name,
                    exc_info=True,
                )

        # Build the full instruction with auto-collected + explicit context
        full_instruction = instruction

        # Auto-collected parent context goes first (background data)
        if parent_context_block:
            full_instruction = (
                f"{instruction}\n\n{parent_context_block}"
            )

        # Explicit context_data from the LLM's delegate_task call
        # goes after — it may refine or add to the auto-collected context
        if context and context.get("data"):
            full_instruction = (
                f"{full_instruction}\n\n### Explicit Context from Caller\n"
                f"```json\n{json.dumps(context['data'], indent=2, default=str)}\n```"
            )

        try:
            result = await self._run_agent_task(
                sub_session_id=sub_session_id,
                agent_def_prompt=agent_def.prompt,
                model=agent_def.model,
                tools_override=tools_override,
                mcp_override=mcp_override,
                instruction=full_instruction,
                timeout=agent_def.timeout_seconds,
                event_queue=event_queue,
                parent_session_id=parent_session_id or "",
                agent_name=agent_name,
            )

            # Update delegation status to completed
            if parent_session_id:
                await self.store.update_delegation_status(
                    parent_session_id,
                    sub_session_id,
                    status="completed",
                    result_summary=result.get("content", "")[:500],
                )

            # Emit delegation_complete event
            if event_queue is not None:
                event_queue.put_nowait(
                    AgentEvent(
                        type="delegation_complete",
                        data={
                            "agent": agent_name,
                            "sub_session_id": sub_session_id,
                            "content": result.get("content", "")[:500],
                        },
                        session_id=parent_session_id or "",
                    )
                )

            return {
                "agent": agent_name,
                "sub_session_id": sub_session_id,
                "content": result.get("content", ""),
                "status": "completed",
            }

        except asyncio.TimeoutError:
            logger.warning(
                "Delegation to %s timed out after %ds (sub-session: %s)",
                agent_name,
                agent_def.timeout_seconds,
                sub_session_id,
            )
            if parent_session_id:
                await self.store.update_delegation_status(
                    parent_session_id,
                    sub_session_id,
                    status="timed_out",
                    result_summary="Delegation timed out",
                )
            if event_queue is not None:
                event_queue.put_nowait(
                    AgentEvent(
                        type="delegation_error",
                        data={
                            "agent": agent_name,
                            "sub_session_id": sub_session_id,
                            "error": (
                                f"Delegation timed out after "
                                f"{agent_def.timeout_seconds}s"
                            ),
                        },
                        session_id=parent_session_id or "",
                    )
                )
            return {
                "agent": agent_name,
                "sub_session_id": sub_session_id,
                "content": "Delegation timed out — partial results may be available.",
                "status": "timed_out",
            }

        except Exception as exc:
            logger.exception(
                "Delegation to %s failed (sub-session: %s): %s",
                agent_name,
                sub_session_id,
                exc,
            )
            if parent_session_id:
                await self.store.update_delegation_status(
                    parent_session_id,
                    sub_session_id,
                    status="failed",
                    result_summary=str(exc)[:500],
                )
            if event_queue is not None:
                event_queue.put_nowait(
                    AgentEvent(
                        type="delegation_error",
                        data={
                            "agent": agent_name,
                            "sub_session_id": sub_session_id,
                            "error": str(exc),
                        },
                        session_id=parent_session_id or "",
                    )
                )
            return {
                "agent": agent_name,
                "sub_session_id": sub_session_id,
                "content": f"Delegation failed: {exc}",
                "status": "failed",
            }

    # ------------------------------------------------------------------
    # Internal — run the delegated task
    # ------------------------------------------------------------------

    async def _run_agent_task(
        self,
        sub_session_id: str,
        agent_def_prompt: str,
        model: str,
        tools_override: list,
        mcp_override: dict[str, Any],
        instruction: str,
        timeout: int,
        event_queue: asyncio.Queue[AgentEvent] | None,
        parent_session_id: str,
        agent_name: str,
    ) -> dict[str, Any]:
        """Create and run a Copilot SDK sub-session for the delegated task."""
        # Create a sub-event-queue that forwards events as delegation_progress
        sub_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()

        session = await self.session_factory.create_session(
            session_id=sub_session_id,
            model=model,
            system_prompt=agent_def_prompt,
            event_queue=sub_queue,
            tools_override=tools_override,
            mcp_override=mcp_override if mcp_override else None,
        )

        async def _forward_events() -> None:
            """Forward sub-session events as delegation_progress to the parent."""
            while True:
                try:
                    evt = await asyncio.wait_for(sub_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if event_queue is not None:
                    event_queue.put_nowait(
                        AgentEvent(
                            type="delegation_progress",
                            data={
                                "agent": agent_name,
                                "sub_session_id": sub_session_id,
                                "event_type": evt.type,
                                "event_data": evt.data,
                            },
                            session_id=parent_session_id,
                        )
                    )

                if evt.type in ("session_complete", "session_error"):
                    break

        # Run the session + event forwarder with timeout
        forward_task = asyncio.create_task(_forward_events())
        try:
            await asyncio.wait_for(
                session.run(instruction, sub_queue),
                timeout=timeout,
            )
        finally:
            forward_task.cancel()
            try:
                await forward_task
            except asyncio.CancelledError:
                pass
            await session.close()

        return {"content": session._last_message}

    # ------------------------------------------------------------------
    # Internal — session linking
    # ------------------------------------------------------------------

    async def _link_sub_session(
        self,
        parent_session_id: str,
        sub_session_id: str,
        agent_name: str,
        instruction: str,
    ) -> None:
        """Record the delegation relationship in the session store."""
        record = DelegationRecord(
            sub_session_id=sub_session_id,
            agent_name=agent_name,
            instruction=instruction[:500],
            started_at=datetime.now(timezone.utc).isoformat(),
            status="running",
        )
        await self.store.append_delegation(parent_session_id, record)

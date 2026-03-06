"""Session factory and Copilot session wrapper for the contelligence-agent.

Provides ``SessionFactory`` for creating ``CopilotSession`` instances that
wrap the GitHub Copilot SDK session and bridge SDK events into our
``AgentEvent`` / ``asyncio.Queue`` system.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from copilot import CopilotClient, Tool, PermissionHandler, CopilotSession as SDKSession

from app.core.client_factory import CopilotClientFactory
from app.core.tool_registry import ToolDefinition, ToolRegistry
from app.models.agent_models import AgentEvent
from app.utils.copilot_health import (
    CopilotClientUnhealthyError,
    CopilotHealthResult,
    verify_copilot_client,
)

logger = logging.getLogger(f"contelligence-agent.{__name__}")

class CopilotSession:
    """Wrapper around a Copilot SDK session that bridges events to asyncio.Queue.

    This class encapsulates the SDK session object, registers event and hook
    callbacks, and translates incoming SDK events into ``AgentEvent`` objects
    pushed to the caller's ``asyncio.Queue``.
    """

    def __init__(self, sdk_session: SDKSession, session_id: str) -> None:
        self.sdk_session = sdk_session
        self.session_id = session_id
        self.status: str = "active"
        self.created_at: datetime = datetime.now(timezone.utc)
        self._last_message: str = ""
        self._last_error: dict[str, Any] | None = None
        self._event_queue: Any = None
        self._done: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._listener_registered: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        instruction: str,
        event_queue: Any,
    ) -> None:
        """Send *instruction* to the Copilot agent and stream events to *event_queue*.

        Blocks until the SDK session reaches ``session.idle`` (the agent
        finished processing) or an error occurs.
        """
        done = asyncio.Event()
        loop = asyncio.get_running_loop()

        # Store mutable references so the single on_event handler
        # always uses the current queue / done signal / loop.
        self._event_queue = event_queue
        self._done = done
        self._loop = loop
        self.status = "active"
        self._last_error = None
       
        if not self._listener_registered:
            self._register_event_handler()
            self._listener_registered = True
            
        try:
            await self.sdk_session.send({"prompt": instruction})
            await done.wait()
        except Exception as exc:
            self.status = "error"
            await event_queue.put(
                AgentEvent(
                    type="session_error",
                    data={"error": str(exc)},
                    session_id=self.session_id,
                )
            )

    def _register_event_handler(self) -> None:
        """Register the SDK event handler exactly once.

        The handler reads ``self._event_queue``, ``self._done``, and
        ``self._loop`` so that subsequent ``run()`` calls can update those
        references without adding duplicate listeners.
        """

        def on_event(event: Any) -> None:
            etype = event.type.value
            d = event.data
            eq = self._event_queue
            loop = self._loop

            if eq is None or loop is None:
                return

            def _emit(agent_type: str, data: dict[str, Any]) -> None:
                """Push an AgentEvent onto the queue from any thread."""
                loop.call_soon_threadsafe(
                    eq.put_nowait,
                    AgentEvent(type=agent_type, data=data, session_id=self.session_id),
                )

            # ── Abort ──────────────────────────────────────────────

            if etype == "abort":
                self.status = "error"
                _emit("abort", {})

            # ── Assistant events ───────────────────────────────────

            elif etype == "assistant.intent":
                _emit("assistant_intent", {
                    "intent": getattr(d, "intent", None),
                })

            elif etype == "assistant.message":
                self._last_message = getattr(d, "content", None) or ""
                _emit("message", {"content": self._last_message})

            elif etype == "assistant.message_delta":
                _emit("reasoning", {"content": getattr(d, "delta_content", None) or ""})

            elif etype == "assistant.reasoning":
                _emit("reasoning", {"content": getattr(d, "content", None) or ""})

            elif etype == "assistant.reasoning_delta":
                _emit("reasoning", {"content": getattr(d, "delta_content", None) or ""})

            elif etype == "assistant.streaming_delta":
                content = getattr(d, "delta_content", None) or ""
                if content:
                    _emit("assistant_streaming_delta", {
                        "content": content,
                    })

            elif etype == "assistant.turn_start":
                _emit("turn_start", {
                    "turn_id": getattr(d, "turn_id", None),
                    "interaction_id": getattr(d, "interaction_id", None),
                })

            elif etype == "assistant.turn_end":
                _emit("turn_end", {"turn_id": getattr(d, "turn_id", None)})

            elif etype == "assistant.usage":
                _emit("assistant_usage", {
                    "input_tokens": getattr(d, "input_tokens", None),
                    "output_tokens": getattr(d, "output_tokens", None),
                    "cache_read_tokens": getattr(d, "cache_read_tokens", None),
                    "cache_write_tokens": getattr(d, "cache_write_tokens", None),
                    "model": getattr(d, "model", None),
                    "duration": getattr(d, "duration", None),
                    "cost": getattr(d, "cost", None),
                })

            # ── Hook events ────────────────────────────────────────

            elif etype == "hook.start":
                _emit("hook_start", {
                    "hook_invocation_id": getattr(d, "hook_invocation_id", None),
                    "hook_type": getattr(d, "hook_type", None),
                    "tool_name": getattr(d, "tool_name", None),
                    "tool_call_id": getattr(d, "tool_call_id", None),
                })

            elif etype == "hook.end":
                _emit("hook_end", {
                    "hook_invocation_id": getattr(d, "hook_invocation_id", None),
                    "hook_type": getattr(d, "hook_type", None),
                    "tool_name": getattr(d, "tool_name", None),
                    "tool_call_id": getattr(d, "tool_call_id", None),
                })

            # ── Pending messages ───────────────────────────────────

            elif etype == "pending_messages.modified":
                _emit("pending_messages_modified", {})

            # ── Session lifecycle events ───────────────────────────

            elif etype == "session.compaction_start":
                _emit("session_compaction_start", {
                    "pre_compaction_tokens": getattr(d, "pre_compaction_tokens", None),
                    "pre_compaction_messages_length": getattr(d, "pre_compaction_messages_length", None),
                })

            elif etype == "session.compaction_complete":
                _emit("session_compaction_complete", {
                    "post_compaction_tokens": getattr(d, "post_compaction_tokens", None),
                    "tokens_removed": getattr(d, "tokens_removed", None),
                    "messages_removed": getattr(d, "messages_removed", None),
                    "success": getattr(d, "success", None),
                })

            elif etype == "session.context_changed":
                _emit("session_context_changed", {
                    "cwd": getattr(d, "cwd", None),
                    "branch": getattr(d, "branch", None),
                    "git_root": getattr(d, "git_root", None),
                })

            elif etype == "session.error":
                error_msg = getattr(d, "message", None) or "Unknown error"
                error_type = getattr(d, "error_type", None) or "unknown"
                status_code = getattr(d, "status_code", None)
                self.status = "error"
                self._last_error = {
                    "error": error_msg,
                    "error_type": error_type,
                    "status_code": status_code,
                }
                logger.warning(
                    "SDK session %s error: [%s] %s (status=%s)",
                    self.session_id, error_type, error_msg, status_code,
                )
                _emit("session_error", self._last_error)

            elif etype == "session.handoff":
                repo = getattr(d, "repository", None)
                if hasattr(repo, "to_dict"):
                    repo = repo.to_dict()
                source_type = getattr(d, "source_type", None)
                _emit("session_handoff", {
                    "remote_session_id": getattr(d, "remote_session_id", None),
                    "source_type": getattr(source_type, "value", source_type),
                    "repository": repo,
                })

            elif etype == "session.idle":
                if self.status == "error":
                    _emit("session_error", self._last_error or {"error": "Unknown error"})
                else:
                    self.status = "completed"
                    _emit("session_complete", {"response": self._last_message})
                if self._done is not None:
                    loop.call_soon_threadsafe(self._done.set)

            elif etype == "session.info":
                _emit("session_info", {
                    "message": getattr(d, "message", None),
                    "info_type": getattr(d, "info_type", None),
                })

            elif etype == "session.model_change":
                _emit("session_model_change", {
                    "new_model": getattr(d, "new_model", None),
                    "previous_model": getattr(d, "previous_model", None),
                })

            elif etype == "session.mode_changed":
                _emit("session_mode_changed", {
                    "new_mode": getattr(d, "new_mode", None),
                    "previous_mode": getattr(d, "previous_mode", None),
                })

            elif etype == "session.plan_changed":
                _emit("session_plan_changed", {
                    "content": getattr(d, "content", None),
                })

            elif etype == "session.resume":
                resume_time = getattr(d, "resume_time", None)
                _emit("session_resume", {
                    "resume_time": resume_time.isoformat() if resume_time else None,
                    "event_count": getattr(d, "event_count", None),
                })

            elif etype == "session.shutdown":
                shutdown_type = getattr(d, "shutdown_type", None)
                code_changes = getattr(d, "code_changes", None)
                model_metrics = getattr(d, "model_metrics", None)
                _emit("session_shutdown", {
                    "shutdown_type": getattr(shutdown_type, "value", shutdown_type),
                    "summary": getattr(d, "summary", None),
                    "code_changes": code_changes.to_dict() if hasattr(code_changes, "to_dict") else None,
                    "model_metrics": (
                        {k: v.to_dict() for k, v in model_metrics.items()}
                        if model_metrics else None
                    ),
                    "total_premium_requests": getattr(d, "total_premium_requests", None),
                })

            elif etype == "session.snapshot_rewind":
                _emit("session_snapshot_rewind", {
                    "checkpoint_number": getattr(d, "checkpoint_number", None),
                    "checkpoint_path": getattr(d, "checkpoint_path", None),
                })

            elif etype == "session.start":
                context = getattr(d, "context", None)
                if hasattr(context, "to_dict"):
                    context = context.to_dict()
                _emit("session_start", {
                    "session_id": getattr(d, "session_id", None),
                    "copilot_version": getattr(d, "copilot_version", None),
                    "selected_model": getattr(d, "selected_model", None),
                    "context": context,
                })

            elif etype == "session.task_complete":
                code_changes = getattr(d, "code_changes", None)
                _emit("session_task_complete", {
                    "summary": getattr(d, "summary", None),
                    "code_changes": code_changes.to_dict() if hasattr(code_changes, "to_dict") else None,
                })

            elif etype == "session.title_changed":
                _emit("session_title_changed", {
                    "title": getattr(d, "title", None),
                })

            elif etype == "session.truncation":
                _emit("session_truncation", {
                    "messages_removed_during_truncation": getattr(d, "messages_removed_during_truncation", None),
                    "tokens_removed_during_truncation": getattr(d, "tokens_removed_during_truncation", None),
                    "token_limit": getattr(d, "token_limit", None),
                    "performed_by": getattr(d, "performed_by", None),
                })

            elif etype == "session.usage_info":
                _emit("usage_info", {
                    "current_tokens": getattr(d, "current_tokens", None),
                    "token_limit": getattr(d, "token_limit", None),
                    "messages_length": getattr(d, "messages_length", None),
                })

            elif etype == "session.warning":
                _emit("session_warning", {
                    "message": getattr(d, "message", None),
                    "warning_type": getattr(d, "warning_type", None),
                })

            elif etype == "session.workspace_file_changed":
                operation = getattr(d, "operation", None)
                _emit("session_workspace_file_changed", {
                    "operation": getattr(operation, "value", operation),
                    "path": getattr(d, "path", None),
                })

            # ── Skill events ───────────────────────────────────────

            elif etype == "skill.invoked":
                _emit("skill_invoked", {
                    "name": getattr(d, "name", None),
                    "plugin_name": getattr(d, "plugin_name", None),
                })

            # ── Subagent events ────────────────────────────────────

            elif etype == "subagent.completed":
                _emit("subagent_completed", {
                    "agent_name": getattr(d, "agent_name", None),
                    "summary": getattr(d, "summary", None),
                })

            elif etype == "subagent.deselected":
                _emit("subagent_deselected", {
                    "agent_name": getattr(d, "agent_name", None),
                })

            elif etype == "subagent.failed":
                error = getattr(d, "error", None)
                if hasattr(error, "to_dict"):
                    error = error.to_dict()
                _emit("subagent_failed", {
                    "agent_name": getattr(d, "agent_name", None),
                    "error": error,
                })

            elif etype == "subagent.selected":
                _emit("subagent_selected", {
                    "agent_name": getattr(d, "agent_name", None),
                    "agent_description": getattr(d, "agent_description", None),
                    "tools": getattr(d, "tools", None),
                })

            elif etype == "subagent.started":
                _emit("subagent_started", {
                    "agent_name": getattr(d, "agent_name", None),
                })

            # ── System message ─────────────────────────────────────

            elif etype == "system.message":
                _emit("system_message", {
                    "content": getattr(d, "content", None),
                })

            # ── Tool execution events ──────────────────────────────

            elif etype == "tool.execution_complete":
                result = getattr(d, "result", None)
                if hasattr(result, "to_dict"):
                    result = result.to_dict()
                _emit("tool_execution_complete", {
                    "tool_name": getattr(d, "tool_name", None),
                    "tool_call_id": getattr(d, "tool_call_id", None),
                    "result": result,
                    "duration": getattr(d, "duration", None),
                })

            elif etype == "tool.execution_partial_result":
                _emit("tool_execution_partial_result", {
                    "tool_name": getattr(d, "tool_name", None),
                    "tool_call_id": getattr(d, "tool_call_id", None),
                    "partial_output": getattr(d, "partial_output", None),
                })

            elif etype == "tool.execution_progress":
                _emit("tool_execution_progress", {
                    "tool_name": getattr(d, "tool_name", None),
                    "tool_call_id": getattr(d, "tool_call_id", None),
                    "progress_message": getattr(d, "progress_message", None),
                })

            elif etype == "tool.execution_start":
                _emit("tool_execution_start", {
                    "tool_name": getattr(d, "tool_name", None),
                    "tool_call_id": getattr(d, "tool_call_id", None),
                    "arguments": getattr(d, "arguments", None),
                })

            elif etype == "tool.user_requested":
                _emit("tool_user_requested", {
                    "tool_name": getattr(d, "tool_name", None),
                    "tool_call_id": getattr(d, "tool_call_id", None),
                    "is_user_requested": getattr(d, "is_user_requested", None),
                })

            # ── User message ───────────────────────────────────────

            elif etype == "user.message":
                _emit("user_message", {"content": getattr(d, "content", None) or ""})

            # ── Unknown / forward compatibility ────────────────────

            else:
                logger.info(
                    "SDK session %s unrecognized event type: %s",
                    self.session_id, etype,
                )
                _emit("unknown_event", {"original_type": etype})

        self.sdk_session.on(on_event)

    async def send_message(self, message: str) -> None:
        """Send a follow-up message to the SDK session."""
        self._last_message = ""
        await self.sdk_session.send({"prompt": message})

    async def close(self) -> None:
        """Destroy the SDK session and mark as completed."""
        self.status = "completed"
        try:
            await self.sdk_session.destroy()
        except Exception:
            logger.warning("Error destroying SDK session %s", self.session_id)
        logger.info("Session %s closed", self.session_id)


# ----------------------------------------------------------------------
# SessionFactory
# ----------------------------------------------------------------------


class SessionFactory:
    """Factory that creates ``CopilotSession`` instances backed by the SDK.

    Holds shared dependencies (CopilotClientFactory, tool registry, tool
    context, provider config, MCP servers) so that individual sessions
    receive consistent configuration.

    The ``CopilotClientFactory`` is used instead of a raw ``CopilotClient``
    so the underlying client can be reset (e.g. after credential rotation)
    without rebuilding the entire session factory.
    """

    def __init__(
        self,
        client_factory: CopilotClientFactory,
        tool_registry: ToolRegistry,
        tool_context: dict[str, Any] | None = None,
        default_model: str = "gpt-4.1",
        provider_config: dict[str, Any] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        working_directory: str | None = None,
        skill_directories: list[str] | None = None,
    ) -> None:
        self.client_factory = client_factory
        self.tool_registry = tool_registry
        self.tool_context: dict[str, Any] = tool_context or {}
        self.default_model = default_model
        self.provider_config = provider_config
        self.mcp_servers: dict[str, Any] = mcp_servers or {}
        self.working_directory = working_directory
        self.skill_directories: list[str] = skill_directories or []
        self._health: CopilotHealthResult | None = None

    @property
    def copilot_client(self) -> CopilotClient:
        """Return the current ``CopilotClient`` from the factory."""
        return self.client_factory.client

    # ------------------------------------------------------------------
    # Preflight health check
    # ------------------------------------------------------------------

    async def verify(self, *, full_probe: bool = True) -> CopilotHealthResult:
        """Run a preflight check and cache the result.

        Call this once after construction (typically during app startup).
        When ``full_probe=True`` a throwaway session sends a trivial prompt
        to the configured model + provider, catching auth *and* provider
        misconfigurations before any real session is created.

        Raises
        ------
        CopilotClientUnhealthyError
            If the check fails.  The exception carries the full
            ``CopilotHealthResult`` for diagnostics.
        """
        result = await verify_copilot_client(
            self.copilot_client,
            provider_config=self.provider_config,
            model=self.default_model,
            full_probe=full_probe,
        )
        self._health = result
        if not result.healthy:
            raise CopilotClientUnhealthyError(result)
        logger.info("Copilot SDK preflight check passed: %s", result.summary())
        return result

    @property
    def health(self) -> CopilotHealthResult | None:
        """Last preflight check result, or ``None`` if :meth:`verify` was never called."""
        return self._health

    async def create_session(
        self,
        session_id: str | None = None,
        model: str | None = None,
        system_prompt: str = "",
        event_queue: asyncio.Queue[AgentEvent] | None = None,
        tools_override: list[ToolDefinition] | None = None,
        mcp_override: dict[str, Any] | None = None,
        messages: list[dict[str, Any]] | None = None,
        custom_agents: list[dict[str, Any]] | None = None,
        skill_directories: list[str] | None = None,
        disabled_skills: list[str] | None = None,
        working_directory: str | None = None,
    ) -> CopilotSession:
        """Create and return a new ``CopilotSession``.

        Parameters
        ----------
        session_id:
            Unique identifier for the session.  Generated when not provided.
        model:
            The LLM model name.  Falls back to ``self.default_model``.
        system_prompt:
            An optional system message prepended to the conversation.
        event_queue:
            If provided, SDK hooks are registered to push ``tool_call_start``
            and ``tool_call_complete`` events for real-time observability.
        tools_override:
            If provided, use these tools instead of the full registry.
            Used by custom agents to restrict the tool set.
        mcp_override:
            If provided, use these MCP server configs instead of the
            factory default.  Used by custom agents.
        messages:
            If provided, preload the session with this conversation history.
            Used when resuming a previously persisted session.
        custom_agents:
            SDK ``CustomAgentConfig`` dicts to register as sub-agents.
            The SDK handles delegation natively when these are provided.
        skill_directories:
            Filesystem paths the SDK should load skills from.
            Merged with factory-level ``self.skill_directories``.
        disabled_skills:
            Skill names to disable for this session.
        working_directory:
            Override the factory-level working directory for this session.
        """
        # Fail fast if preflight check ran and failed
        if self._health is not None and not self._health.healthy:
            raise CopilotClientUnhealthyError(self._health)

        sid = session_id or str(uuid.uuid4())

        if tools_override is not None:
            copilot_tools = [self._wrap_tool(td) for td in tools_override]
        else:
            copilot_tools = self._make_copilot_tools()

        config: dict[str, Any] = {
            "model": model or self.default_model,
            "tools": copilot_tools,
            "streaming": True,
            # "available_tools": [t.name for t in copilot_tools], # if this is set, the SDK only allows those tools to be used in this session, even if more are registered at the client level.  Useful for custom agents that want to restrict the toolset.
        }

        # MCP servers — sub-sessions may restrict to a subset
        effective_mcp = mcp_override if mcp_override is not None else self.mcp_servers
        if effective_mcp:
            config["mcp_servers"] = effective_mcp

        if sid:
            config["session_id"] = sid

        if system_prompt:
            config["system_message"] = {"content": system_prompt}

        if messages:
            config["messages"] = messages

        if self.provider_config:
            config["provider"] = self.provider_config

        # Custom agents — pass to SDK for native sub-agent delegation
        if custom_agents:
            config["custom_agents"] = custom_agents

        # Skill directories — merge factory defaults with session-specific
        effective_skills = list(self.skill_directories)
        if skill_directories:
            for sd in skill_directories:
                if sd not in effective_skills:
                    effective_skills.append(sd)
        if effective_skills:
            config["skill_directories"] = effective_skills

        if disabled_skills:
            config["disabled_skills"] = disabled_skills

        # Working directory — session override or factory default
        effective_wd = working_directory or self.working_directory
        if effective_wd:
            config["working_directory"] = effective_wd

        # Register hooks for tool-call observability if we have an event queue.
        if event_queue is not None:
            config["hooks"] = self._make_hooks(event_queue, sid)

        config["on_permission_request"] = PermissionHandler.approve_all
        sdk_session = await self.copilot_client.create_session(config)
        return CopilotSession(sdk_session, sid)

    async def resume_session(
        self,
        session_id: str,
        model: str | None = None,
        system_prompt: str = "",
        event_queue: asyncio.Queue[AgentEvent] | None = None,
        tools_override: list[ToolDefinition] | None = None,
        mcp_override: dict[str, Any] | None = None,
        custom_agents: list[dict[str, Any]] | None = None,
        skill_directories: list[str] | None = None,
        disabled_skills: list[str] | None = None,
        working_directory: str | None = None,
    ) -> CopilotSession:
        """Resume an existing SDK session by its ID.

        Uses the SDK's native ``CopilotClient.resume_session()`` which
        preserves the full conversation history server-side, rather than
        creating a brand-new session with messages replayed.

        Parameters
        ----------
        session_id:
            The ID of the session to resume (must have been previously
            created via ``create_session``).
        model:
            The LLM model name.  Falls back to ``self.default_model``.
        system_prompt:
            An optional system message for the resumed session.
        event_queue:
            If provided, SDK hooks are registered to push ``tool_call_start``
            and ``tool_call_complete`` events for real-time observability.
        tools_override:
            If provided, use these tools instead of the full registry.
        mcp_override:
            If provided, use these MCP server configs instead of the
            factory default.
        custom_agents:
            SDK ``CustomAgentConfig`` dicts for the resumed session.
        skill_directories:
            Filesystem paths the SDK should load skills from.
        disabled_skills:
            Skill names to disable for this session.
        working_directory:
            Override the factory-level working directory.
        """
        # Fail fast if preflight check ran and failed
        if self._health is not None and not self._health.healthy:
            raise CopilotClientUnhealthyError(self._health)

        if tools_override is not None:
            copilot_tools = [self._wrap_tool(td) for td in tools_override]
        else:
            copilot_tools = self._make_copilot_tools()

        config: dict[str, Any] = {
            "tools": copilot_tools,
            "streaming": True,
            "on_permission_request": PermissionHandler.approve_all,
        }

        if model or self.default_model:
            config["model"] = model or self.default_model

        # MCP servers — sub-sessions may restrict to a subset
        effective_mcp = mcp_override if mcp_override is not None else self.mcp_servers
        if effective_mcp:
            config["mcp_servers"] = effective_mcp

        if system_prompt:
            config["system_message"] = {"content": system_prompt}

        if self.provider_config:
            config["provider"] = self.provider_config

        # Custom agents — pass to SDK for native sub-agent delegation
        if custom_agents:
            config["custom_agents"] = custom_agents

        # Skill directories — merge factory defaults with session-specific
        effective_skills = list(self.skill_directories)
        if skill_directories:
            for sd in skill_directories:
                if sd not in effective_skills:
                    effective_skills.append(sd)
        if effective_skills:
            config["skill_directories"] = effective_skills

        if disabled_skills:
            config["disabled_skills"] = disabled_skills

        # Working directory — session override or factory default
        effective_wd = working_directory or self.working_directory
        if effective_wd:
            config["working_directory"] = effective_wd

        # Register hooks for tool-call observability if we have an event queue.
        if event_queue is not None:
            config["hooks"] = self._make_hooks(event_queue, session_id)

        sdk_session = await self.copilot_client.resume_session(session_id, config)
        return CopilotSession(sdk_session, session_id)

    # ------------------------------------------------------------------
    # Tool bridging
    # ------------------------------------------------------------------

    def _make_copilot_tools(self) -> list[Tool]:
        """Convert all registered ``ToolDefinition`` objects to ``copilot.Tool``."""
        return [self._wrap_tool(td) for td in self.tool_registry.get_all_tools()]

    def _wrap_tool(self, tool_def: ToolDefinition) -> Tool:
        """Wrap a ``ToolDefinition`` as a ``copilot.Tool``.

        The wrapper bridges our ``(params, context) -> dict`` handler
        signature to the SDK's ``handler(invocation) -> str`` convention.
        The tool context is captured in the closure so each invocation
        receives the shared connector instances.
        """
        context = self.tool_context

        async def handler(invocation: dict[str, Any]) -> str:
            parsed_args = invocation.get("arguments", {})
            params = tool_def.parameters_model.model_validate(parsed_args)
            result = tool_def.handler(params, context)
            if asyncio.iscoroutine(result):
                result = await result
            return json.dumps(result, default=str)

        return Tool(
            name=tool_def.name,
            description=tool_def.description,
            parameters=tool_def.parameters_model.model_json_schema(),
            handler=handler,
            overrides_built_in_tool=False, # TODO: consider allowing this for advanced use cases
        )

    # ------------------------------------------------------------------
    # SDK hooks for tool-call telemetry
    # ------------------------------------------------------------------

    @staticmethod
    def _make_hooks(
        event_queue: Any,
        session_id: str,
    ) -> dict[str, Any]:
        """Build Copilot SDK hook handlers that emit tool-call events."""
        tool_start_times: dict[str, float] = {}

        async def on_pre_tool_use(
            input_data: dict[str, Any],
            invocation: Any,
        ) -> dict[str, Any]:
            tool_name = input_data.get("toolName", "unknown")
            tool_start_times[tool_name] = time.monotonic()
            event_queue.put_nowait(
                AgentEvent(
                    type="tool_call_start",
                    data={
                        "tool": tool_name,
                        "params": input_data.get("toolArgs", {}),
                    },
                    session_id=session_id,
                )
            )
            return {"permissionDecision": "allow"}

        async def on_post_tool_use(
            input_data: dict[str, Any],
            invocation: Any,
        ) -> dict[str, Any]:
            tool_name = input_data.get("toolName", "unknown")
            start = tool_start_times.pop(tool_name, None)
            duration_ms = int((time.monotonic() - start) * 1000) if start else 0
            event_queue.put_nowait(
                AgentEvent(
                    type="tool_call_complete",
                    data={
                        "tool": tool_name,
                        "duration_ms": duration_ms,
                    },
                    session_id=session_id,
                )
            )
            return {}

        async def on_error_occurred(
            input_data: dict[str, Any],
            invocation: Any,
        ) -> dict[str, Any]:
            event_queue.put_nowait(
                AgentEvent(
                    type="tool_call_error",
                    data={
                        "tool": input_data.get("toolName", "unknown"),
                        "error": input_data.get("error", "Unknown error"),
                        "context": input_data.get("errorContext", ""),
                    },
                    session_id=session_id,
                )
            )
            return {"errorHandling": "skip"}

        return {
            "on_pre_tool_use": on_pre_tool_use,
            "on_post_tool_use": on_post_tool_use,
            "on_error_occurred": on_error_occurred,
        }

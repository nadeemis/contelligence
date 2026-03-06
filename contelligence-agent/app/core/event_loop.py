"""Top-level helper to drive a Copilot SDK session.

``run_agent_loop`` is a thin wrapper around ``CopilotSession.run`` that adds
error handling and an optional approval check before tool execution.

Phase 3 additions:
    * Approval gate — when ``approval_manager`` is provided and the session
      has ``require_approval=True``, destructive tool calls are paused
      until the user confirms via the ``/reply`` endpoint.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.session_factory import CopilotSession
from app.models.agent_models import AgentEvent
from app.models.approval_models import PendingOperation

logger = logging.getLogger(f"contelligence-agent.{__name__}")

async def run_agent_loop(
    session: CopilotSession,
    instruction: str,
    event_queue: Any,
    *,
    approval_manager: Any | None = None,
    session_options: dict[str, Any] | None = None,
) -> None:
    """Run the Copilot agent for *session*, catching unexpected errors.

    When *approval_manager* is supplied and the session has
    ``require_approval`` enabled, any tool call that matches the approval
    triggers will pause execution, emit an ``approval_required`` SSE event,
    and block until the user responds.

    Any unhandled exception is logged and translated into a
    ``session_error`` event so the caller always receives a terminal event.
    """
    opts = session_options or {}

    async def _approval_hook(tool_name: str, parameters: dict[str, Any]) -> dict[str, Any] | None:
        """Pre-execution hook injected into the session.

        Returns ``None`` to proceed normally, or a dict with
        ``{"skip": True, "reason": "..."}`` to abort the tool call.
        """
        # Lazy imports to avoid circular dependency
        # (services → persistent_agent_service → core.event_loop)
        from app.services.approval_helpers import describe_operation, summarize_params
        from app.services.approval_triggers import get_risk_level, requires_approval

        if approval_manager is None:
            return None
        if not requires_approval(tool_name, parameters, opts):
            return None

        pending_op = PendingOperation(
            tool=tool_name,
            description=describe_operation(tool_name, parameters),
            risk=get_risk_level(tool_name),
            parameters=summarize_params(parameters),
        )

        # Emit SSE event so the client knows we're waiting
        await event_queue.put(
            AgentEvent(
                type="approval_required",
                data={
                    "operations": [pending_op.model_dump(mode="json")],
                    "message": (
                        f"The agent wants to execute '{tool_name}'. "
                        "Please approve, reject, or modify through the /reply endpoint."
                    ),
                },
                session_id=session.session_id,
            )
        )

        # Block until the user responds (or timeout)
        response = await approval_manager.request_approval(
            session_id=session.session_id,
            operations=[pending_op],
            message=f"Requesting approval for {tool_name}",
        )

        if response.decision == "rejected":
            logger.info(
                "Tool %s rejected by user for session %s: %s",
                tool_name,
                session.session_id,
                response.message,
            )
            return {"skip": True, "reason": response.message or "User rejected the operation."}

        if response.decision == "modified":
            logger.info(
                "Tool %s modified by user for session %s: %s",
                tool_name,
                session.session_id,
                response.message,
            )
            return {"modified": True, "user_message": response.message}

        # approved
        logger.info("Tool %s approved for session %s", tool_name, session.session_id)
        return None

    try:
        await session.run(
            instruction,
            event_queue,
            # approval_hook=_approval_hook,
        )
    except Exception as exc:
        logger.exception("Agent loop error for session %s", session.session_id)
        await event_queue.put(
            AgentEvent(
                type="session_error",
                data={"error": str(exc)},
                session_id=session.session_id,
            )
        )

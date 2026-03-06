"""Atomic tool: delegate_task — delegate a subtask to a custom agent.

This tool is registered in the main agent's tool set so it can delegate
work to specialized sub-agents (doc-processor, data-analyst, qa-reviewer)
via the Copilot SDK function-calling interface.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import ToolDefinition


class DelegateTaskParams(BaseModel):
    """Parameters for the ``delegate_task`` tool."""

    agent_name: str = Field(
        description=(
            "Name of the custom agent to delegate to. "
            "Must be one of the agents listed in the Agent Delegation section "
            "of your system prompt."
        )
    )
    instruction: str = Field(
        description=(
            "Clear, self-contained task description for the sub-agent. "
            "Must include: (1) the specific task and expected output format, "
            "(2) any constraints or requirements, and (3) references to the "
            "context_data fields where the sub-agent can find input data. "
            "The sub-agent has NO access to your conversation history — "
            "everything it needs must be in this instruction or context_data."
        )
    )
    context_data: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "All data the sub-agent needs to complete the task. "
            "IMPORTANT: The sub-agent cannot see any files you have already read "
            "or results you have already obtained. You MUST include here: "
            "(1) extracted/read file contents from previous steps, "
            "(2) query results or data retrieved by earlier tools, "
            "(3) any intermediate analysis or summaries relevant to the task. "
            "Structure as a dict with descriptive keys, e.g.: "
            "{'invoice_content': '...', 'vendor_list': [...], 'rules': '...'}. "
            "Note: Parent session context is also auto-injected, but always "
            "pass key data explicitly for reliability."
        ),
    )


async def _delegate_task_handler(
    params: DelegateTaskParams,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Execute delegation to a custom agent.

    The ``context`` dict is expected to contain:
    - ``delegator``: the ``AgentDelegator`` instance
    - ``session_id``: the current parent session ID
    - ``event_queue``: optional ``asyncio.Queue`` for delegation events
    """
    delegator = context.get("delegator")
    if delegator is None:
        return {
            "error": "Agent delegation is not available — delegator not initialized."
        }

    session_id = context.get("session_id", "")
    event_queue = context.get("event_queue")

    result = await delegator.delegate(
        agent_name=params.agent_name,
        instruction=params.instruction,
        context={"data": params.context_data} if params.context_data else None,
        parent_session_id=session_id,
        event_queue=event_queue,
    )
    return result


delegate_task_tool = ToolDefinition(
    name="delegate_task",
    description=(
        "Delegate a subtask to a specialized agent. "
        "The sub-agent runs in an isolated session with NO access to your "
        "conversation history. You MUST pass all necessary data through "
        "the instruction and context_data parameters. This includes any "
        "file contents you have already extracted, query results, or "
        "intermediate analysis. Parent session context is auto-injected "
        "as a safety net, but always pass key data explicitly in context_data."
    ),
    parameters_model=DelegateTaskParams,
    handler=_delegate_task_handler,
)

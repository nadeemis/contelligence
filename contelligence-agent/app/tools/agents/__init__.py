"""Agent delegation tools — tools that allow delegation to sub-agents."""

from __future__ import annotations

from .delegate_tool import delegate_task_tool

AGENT_TOOLS = [delegate_task_tool]
"""Core integration layer for the contelligence-agent.

Re-exports the public surface of the core package so consumers can write::

    from app.core import ToolRegistry, SessionFactory, run_agent_loop
"""

from __future__ import annotations

from app.core.event_loop import run_agent_loop
from app.core.session_factory import CopilotSession, SessionFactory
from app.core.tool_registry import ToolDefinition, ToolRegistry, define_tool

__all__ = [
    "CopilotSession",
    "SessionFactory",
    "ToolDefinition",
    "ToolRegistry",
    "define_tool",
    "run_agent_loop",
]

"""Tool registry aggregation for contelligence-agent.

Collects all tool definitions from the extraction, storage, AI, agent,
and skills modules and provides a helper to bulk-register them with a
:class:`ToolRegistry`.
"""

from __future__ import annotations

from .extraction import EXTRACTION_TOOLS
from .storage import STORAGE_TOOLS
from .ai import AI_TOOLS
from .agents import AGENT_TOOLS
from .skills import SKILL_TOOLS
from .devops import DEVOPS_TOOLS
from .powerbi import POWERBI_TOOLS

ALL_TOOLS = EXTRACTION_TOOLS + STORAGE_TOOLS + AI_TOOLS + SKILL_TOOLS + DEVOPS_TOOLS + POWERBI_TOOLS


def register_all_tools(registry: object) -> None:
    """Register every known tool with the given *registry*."""
    for tool in ALL_TOOLS:
        registry.register(tool)

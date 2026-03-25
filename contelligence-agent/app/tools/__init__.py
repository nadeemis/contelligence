"""Tool registry aggregation for contelligence-agent.

Collects all tool definitions from the extraction, storage, AI, agent,
and skills modules and provides a helper to bulk-register them with a
:class:`ToolRegistry`.
"""

from __future__ import annotations

from ..core.tool_registry import ToolRegistry

from .extraction import EXTRACTION_TOOLS
from .storage import STORAGE_TOOLS
from .ai import AI_TOOLS
from .devops import DEVOPS_TOOLS
from .powerbi import POWERBI_TOOLS
from .desktop import DESKTOP_TOOLS
from .browser import BROWSER_TOOLS
from .msteams import MSTEAMS_TOOLS
from .sharepoint import SHAREPOINT_TOOLS

ALL_TOOLS = EXTRACTION_TOOLS + STORAGE_TOOLS + AI_TOOLS \
          + DEVOPS_TOOLS + POWERBI_TOOLS \
          + DESKTOP_TOOLS + BROWSER_TOOLS + MSTEAMS_TOOLS + SHAREPOINT_TOOLS


def register_all_tools(registry: ToolRegistry) -> None:
    """Register every known tool with the given *registry*."""
    for tool in ALL_TOOLS:
        registry.register(tool)

"""Custom agents module — agent registry, definitions, and prompts.

Usage::

    from app.agents import CUSTOM_AGENTS, AgentDefinition

    agent = CUSTOM_AGENTS["doc-processor"]
    print(agent.display_name)  # "Document Processor"
"""

from __future__ import annotations

from .models import AgentDefinition
from .prompts import (
    DATA_ANALYST_PROMPT,
    DOCUMENT_PROCESSOR_PROMPT,
    QA_REVIEWER_PROMPT,
)
from .custom_agents import CUSTOM_AGENTS
from .dynamic_registry import DynamicAgentRegistry
from .sdk_adapters import agent_def_to_sdk_config, agents_to_sdk_configs

__all__ = [
    "AgentDefinition",
    "DynamicAgentRegistry",
    "CUSTOM_AGENTS",
    "DATA_ANALYST_PROMPT",
    "DOCUMENT_PROCESSOR_PROMPT",
    "QA_REVIEWER_PROMPT",
    "agent_def_to_sdk_config",
    "agents_to_sdk_configs",
]

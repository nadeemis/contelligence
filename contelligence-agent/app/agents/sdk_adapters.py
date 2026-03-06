"""Adapters for converting internal agent models to Copilot SDK types.

Provides ``agent_def_to_sdk_config`` for converting ``AgentDefinition``
objects into the SDK's ``CustomAgentConfig`` format, which can be passed
directly to ``SessionConfig.custom_agents``.
"""

from __future__ import annotations

from typing import Any

from app.agents.models import AgentDefinition


def agent_def_to_sdk_config(
    agent_def: AgentDefinition,
    mcp_servers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert an ``AgentDefinition`` to an SDK ``CustomAgentConfig`` dict.

    Parameters
    ----------
    agent_def:
        Internal agent definition.
    mcp_servers:
        Full MCP server config dict.  The agent's ``mcp_servers`` list
        references keys in this mapping; only matched entries are included.

    Returns
    -------
    A dict conforming to the SDK's ``CustomAgentConfig`` TypedDict.
    """
    config: dict[str, Any] = {
        "name": agent_def.name,
        "display_name": agent_def.display_name,
        "description": agent_def.description,
        "prompt": agent_def.prompt,
    }

    # Map tool names — the SDK accepts a list of tool name strings
    if agent_def.tools:
        config["tools"] = [t for t in agent_def.tools]

    # Resolve MCP servers for this agent from the full config
    if agent_def.mcp_servers and mcp_servers:
        agent_mcp: dict[str, Any] = {}
        for key in agent_def.mcp_servers:
            if key in mcp_servers:
                agent_mcp[key] = mcp_servers[key]
        if agent_mcp:
            config["mcp_servers"] = agent_mcp

    return config


def agents_to_sdk_configs(
    agents: dict[str, AgentDefinition],
    mcp_servers: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convert a dict of ``AgentDefinition`` objects to SDK configs.

    Parameters
    ----------
    agents:
        Mapping of agent-id → AgentDefinition.
    mcp_servers:
        Full MCP server config dict for resolving agent MCP references.

    Returns
    -------
    List of SDK ``CustomAgentConfig`` dicts.
    """
    return [
        agent_def_to_sdk_config(agent_def, mcp_servers)
        for agent_def in agents.values()
    ]

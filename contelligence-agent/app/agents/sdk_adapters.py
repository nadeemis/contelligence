"""Adapters for converting internal agent models to Copilot SDK types.

Provides ``agent_def_to_sdk_config`` for converting ``AgentDefinition``
objects into the SDK's ``CustomAgentConfig`` format, which can be passed
directly to ``SessionConfig.custom_agents``.
"""

from __future__ import annotations

from typing import Any

from copilot.session import CustomAgentConfig

from app.agents.models import AgentDefinition


def agent_def_to_sdk_config(
    agent_def: AgentDefinition,
    mcp_servers: dict[str, Any] | None = None,
) -> CustomAgentConfig:
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
    An SDK ``CustomAgentConfig`` object.
    """
    
    # Resolve MCP servers for this agent from the full config
    agent_mcp: dict[str, Any] = {}
    if mcp_servers:
        for key in mcp_servers.keys():
            agent_mcp[key] = mcp_servers[key]
        
    config: CustomAgentConfig = CustomAgentConfig(
        name=agent_def.name,
        display_name=agent_def.display_name,
        description=agent_def.description,
        prompt=agent_def.prompt,
        tools=agent_def.tools or [],
        mcp_servers=agent_mcp
    )

    return config


def agents_to_sdk_configs(
    agents: dict[str, AgentDefinition],
    mcp_servers: dict[str, Any] | None = None,
) -> list[CustomAgentConfig]:
    """Convert a dict of ``AgentDefinition`` objects to SDK CustomAgentConfig configs.

    Parameters
    ----------
    agents:
        Mapping of agent-id → AgentDefinition.
    mcp_servers:
        Full MCP server config dict for resolving agent MCP references.

    Returns
    -------
    List of SDK ``CustomAgentConfig`` objects.
    """
    return [
        agent_def_to_sdk_config(agent_def, mcp_servers)
        for agent_def in agents.values()
    ]

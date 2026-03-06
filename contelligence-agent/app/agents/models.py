"""Pydantic model for custom agent definitions."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentDefinition(BaseModel):
    """Typed configuration for a custom agent persona.

    Each definition specifies the agent's identity, focused tool subset,
    MCP server access, system prompt, and safety limits.
    """

    name: str = Field(description="Internal identifier (e.g., 'doc-processor')")
    display_name: str = Field(description="Human-readable agent name")
    description: str = Field(description="One-line description of expertise")
    tools: list[str] | None = Field(
        default=None,
        description="List of atomic tool names this agent can use"
    )
    mcp_servers: list[str] = Field(
        description="List of MCP server keys (e.g., ['azure'])"
    )
    prompt: str = Field(description="Full system prompt for this agent")
    model: str = Field(
        default="gpt-4.1",
        description="Default model (overridable per delegation)",
    )
    max_tool_calls: int = Field(
        default=50,
        description="Safety limit on tool calls per delegation",
    )
    timeout_seconds: int = Field(
        default=300,
        description="Max time in seconds for a delegated task",
    )
    bound_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Skill names always loaded at Level 2 when this agent handles a task. "
            "These skills' full instructions are injected into the system prompt "
            "without the agent needing to call read_skill."
        ),
    )

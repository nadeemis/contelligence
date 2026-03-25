"""Pydantic models for custom agent definitions.

User-created agents are stored as documents in the ``agents`` Cosmos DB
container. The schema extends the existing ``AgentDefinition`` Pydantic
model with persistence metadata.

Phase: Custom Agent Management
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentSource(str, Enum):
    """Distinguishes built-in agents from user-created ones."""

    BUILT_IN = "built-in"
    USER_CREATED = "user-created"


class AgentStatus(str, Enum):
    """Lifecycle status of a custom agent definition."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"


class AgentDefinitionRecord(BaseModel):
    """Persisted agent definition stored in the Cosmos DB ``agents`` container.

    Built-in agents are NOT stored in Cosmos DB — they live in code.
    Only user-created agents use this model.
    """

    # Identity
    id: str = Field(description="Unique agent ID (slug format: 'invoice-expert')")
    display_name: str = Field(description="Human-readable name shown in UI")
    description: str = Field(description="One-line summary of the agent's expertise")
    icon: str = Field(
        default="bot",
        description="Lucide icon name for the UI (e.g., 'file-text', 'bar-chart', 'shield-check')",
    )

    # Source & lifecycle
    source: AgentSource = Field(default=AgentSource.USER_CREATED)
    status: AgentStatus = Field(default=AgentStatus.DRAFT)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    created_by: str | None = Field(default=None, description="User ID of creator")

    # Agent behavior
    prompt: str = Field(description="Full system prompt defining the agent's persona and behavior")
    tools: list[str] = Field(
        description="List of atomic tool names this agent is allowed to call",
    )
    model: str = Field(
        default="gpt-4.1",
        description="Default LLM model for this agent's sub-sessions",
    )

    # Safety limits
    max_tool_calls: int = Field(
        default=50,
        description="Maximum tool calls per delegation (safety circuit-breaker)",
    )
    timeout_seconds: int = Field(
        default=300,
        description="Maximum wall-clock time for a delegated task",
    )

    # Skills Integration — bound skills
    bound_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Skill IDs always loaded at Level 2 when this agent handles a task. "
            "These skills' instructions are injected into the agent's system prompt."
        ),
    )

    # Metadata
    tags: list[str] = Field(
        default_factory=list,
        description="Searchable tags (e.g., ['finance', 'extraction', 'compliance'])",
    )
    version: int = Field(
        default=1,
        description="Monotonically increasing version number, bumped on each edit",
    )
    usage_count: int = Field(
        default=0,
        description="Number of times this agent has been delegated to (updated async)",
    )

    # Cosmos DB metadata
    partition_key: str = Field(
        default="",
        description="Set to id for Cosmos partitioning",
    )

    def model_post_init(self, __context: Any) -> None:
        """Ensure partition_key mirrors id."""
        if not self.partition_key:
            self.partition_key = self.id

    model_config = {"populate_by_name": True}

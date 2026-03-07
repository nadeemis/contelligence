"""Pydantic models for Skills Integration.

Defines the ``SkillRecord`` for Cosmos DB persistence and supporting
enums. Skills follow the open Agent Skills specification
(https://agentskills.io/specification).

Phase: Skills Integration
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SkillSource(str, Enum):
    """Where the skill came from."""

    BUILT_IN = "built-in"
    USER_CREATED = "user-created"
    MARKETPLACE = "marketplace"  # Future: shared skill catalog


class SkillStatus(str, Enum):
    """Lifecycle status of a skill."""

    ACTIVE = "active"
    DISABLED = "disabled"
    DRAFT = "draft"


class SkillRecord(BaseModel):
    """Persisted skill metadata stored in the Cosmos DB ``skills`` container.

    Each record corresponds to one Skill directory (``SKILL.md`` + optional
    ``references/``, ``scripts/``, ``assets/``).  The actual Skill files live
    in Azure Blob Storage under ``skills/{name}/``; this record stores parsed
    metadata for fast queries and the full instructions body for Level 2
    loading.
    """

    # Identity
    id: str = Field(description="Unique skill ID (same as name, slug format)")
    name: str = Field(
        description="Skill name from SKILL.md frontmatter (lowercase, hyphens, max 64 chars)",
    )
    description: str = Field(
        description="Skill description from SKILL.md frontmatter (max 1024 chars)",
    )

    # Optional spec fields
    license: str | None = Field(default=None, description="SPDX license identifier")
    compatibility: str | None = Field(
        default=None,
        description="Compatibility string (e.g., 'Contelligence v1.0+')",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata from SKILL.md frontmatter",
    )

    # Taxonomy
    tags: list[str] = Field(
        default_factory=list,
        description="Searchable tags (e.g., ['finance', 'extraction'])",
    )

    # Source & lifecycle
    source: SkillSource = Field(default=SkillSource.USER_CREATED)
    status: SkillStatus = Field(default=SkillStatus.DRAFT)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime | None = Field(default=None)
    created_by: str | None = Field(default=None, description="User ID of creator")

    # Storage
    blob_prefix: str = Field(
        default="",
        description="Blob storage prefix (e.g., 'skills/invoice-processing/')",
    )

    # Content — Level 2 instructions (body of SKILL.md, minus frontmatter)
    instructions: str | None = Field(
        default=None,
        description="Full SKILL.md body (Markdown) for Level 2 loading",
    )

    # File listing
    files: list[str] = Field(
        default_factory=list,
        description="Relative paths of all files in this Skill directory",
    )

    # Agent bindings
    bound_to_agents: list[str] = Field(
        default_factory=list,
        description="Agent IDs that have this Skill as a bound (always-loaded) Skill",
    )

    # Metrics
    version: int = Field(default=1, description="Monotonically increasing version number")
    usage_count: int = Field(
        default=0,
        description="Number of times this Skill has been activated in a session",
    )

    # Cosmos DB metadata
    partition_key: str = Field(
        default="skill",
        description="Partition key value — all skills share the 'skill' partition",
    )


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------


class CreateSkillRequest(BaseModel):
    """Payload for creating a new skill via the API."""

    name: str = Field(description="Skill name (slug format)")
    description: str = Field(description="Skill description (max 1024 chars)")
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    status: SkillStatus = Field(default=SkillStatus.DRAFT)
    instructions: str = Field(description="Full SKILL.md body (Markdown)")


class UpdateSkillRequest(BaseModel):
    """Payload for updating an existing skill via the API."""

    name: str | None = None
    description: str | None = None
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] | None = None
    tags: list[str] | None = None
    status: SkillStatus | None = None
    instructions: str | None = None


class SkillSummary(BaseModel):
    """Lightweight skill info for list endpoints."""

    id: str
    name: str
    description: str
    tags: list[str]
    source: SkillSource
    status: SkillStatus
    usage_count: int
    bound_to_agents: list[str]
    created_at: datetime
    updated_at: datetime | None = None


class SkillValidationResult(BaseModel):
    """Result of SKILL.md validation."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parsed_name: str | None = None
    parsed_description: str | None = None

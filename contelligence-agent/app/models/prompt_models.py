"""Pydantic models for prompt management — system prompt and agent prompts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class PromptType(str, Enum):
    """Discriminator for the kind of prompt stored."""
    SYSTEM = "system"
    AGENT = "agent"


class PromptRecord(BaseModel):
    """Persistent prompt record stored in Cosmos DB / SQLite.

    Partition key: ``/id``
    """
    id: str = Field(description="Unique key — 'system-prompt' or 'agent:<agent-name>'")
    prompt_type: PromptType
    name: str = Field(description="Human-readable label (e.g. 'System Prompt', 'Document Processor')")
    content: str = Field(description="The full prompt text")
    version: int = Field(default=1)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: str = Field(default="admin")


# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------

class PromptUpdateRequest(BaseModel):
    """Body for PUT /admin/prompts/{prompt_id}."""
    content: str = Field(min_length=1, description="New prompt text")


class PromptResponse(BaseModel):
    """Returned by GET / PUT prompt endpoints."""
    id: str
    prompt_type: PromptType
    name: str
    content: str
    version: int
    updated_at: datetime
    is_default: bool = Field(
        default=False,
        description="True when the prompt has never been customised (i.e. built-in default is active)",
    )


class PromptListResponse(BaseModel):
    """Returned by GET /admin/prompts."""
    prompts: list[PromptResponse]

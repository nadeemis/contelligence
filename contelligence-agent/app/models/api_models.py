"""API response models for Phase 2 session retrieval endpoints.

These Pydantic models are used in ``response_model`` parameters for
OpenAPI documentation and client code generation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.session_models import SessionMetrics


class SessionListItem(BaseModel):
    """Summary item returned by ``GET /sessions``."""

    id: str
    created_at: datetime
    status: str
    instruction: str
    model: str
    metrics: SessionMetrics
    summary: str | None = None
    title: str | None = None
    title_source: str | None = None
    tags: list[str] = []
    pinned: bool = False
    parent_session_id: str | None = None


class SessionLogsResponse(BaseModel):
    """Response from ``GET /sessions/{id}/logs``."""

    session_id: str
    turns: list[dict[str, Any]]


class SessionOutputsResponse(BaseModel):
    """Response from ``GET /sessions/{id}/outputs``."""

    session_id: str
    outputs: list[dict[str, Any]]

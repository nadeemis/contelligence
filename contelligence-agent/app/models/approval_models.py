"""Pydantic models for the human-in-the-loop approval workflow.

These models describe pending operations that require user confirmation,
the approval request presented to the user, and the user's response.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class PendingOperation(BaseModel):
    """Describes a single operation awaiting user approval."""

    tool: str
    """Tool name (e.g. ``write_blob``, ``upsert_cosmos``)."""

    description: str
    """Human-readable description of the operation."""

    risk: Literal["medium", "high"] = "medium"
    """Risk level for display purposes."""

    parameters: dict
    """Key parameters summarised for display (destination, count, etc.)."""


class ApprovalResponse(BaseModel):
    """The user's decision for a pending approval."""

    decision: Literal["approved", "rejected", "modified"]
    message: str = ""
    """Optional message — e.g. reason for rejection or modified instructions."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalRequest(BaseModel):
    """A full approval request stored while waiting for the user."""

    session_id: str
    operations: list[PendingOperation]
    message: str
    """Agent's explanation of what it intends to do."""

    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    response: ApprovalResponse | None = None

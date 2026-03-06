"""Retention policy models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetentionPolicy(BaseModel):
    """Configures when sessions and blobs are purged.

    All durations are in **days**.
    """

    session_retention_days: int = Field(
        default=90,
        description="Days to keep completed sessions in Cosmos DB",
    )
    blob_archive_days: int = Field(
        default=90,
        description="Days before blob outputs move to Cool tier",
    )
    blob_delete_days: int = Field(
        default=730,
        description="Days before blob outputs are permanently deleted",
    )

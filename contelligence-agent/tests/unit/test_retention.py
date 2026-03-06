"""Unit tests for Phase 4 — Session Retention models and cleanup."""

from __future__ import annotations

import pytest

from app.retention.models import RetentionPolicy


class TestRetentionPolicy:
    """Test the retention policy model."""

    def test_defaults(self) -> None:
        policy = RetentionPolicy()
        assert policy.session_retention_days == 90
        assert policy.blob_archive_days == 90
        assert policy.blob_delete_days == 730

    def test_custom_values(self) -> None:
        policy = RetentionPolicy(
            session_retention_days=30,
            blob_archive_days=60,
            blob_delete_days=365,
        )
        assert policy.session_retention_days == 30
        assert policy.blob_archive_days == 60
        assert policy.blob_delete_days == 365

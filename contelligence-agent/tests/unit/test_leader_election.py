"""Unit tests for Phase 4 — Leader Election."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.scheduling.leader_election import SchedulerLeaderElection


@pytest.fixture
def mock_container() -> AsyncMock:
    return AsyncMock()


class TestLeaderElection:
    """Test the scheduler leader election logic."""

    @pytest.mark.asyncio
    async def test_acquire_leadership_new_lock(
        self, mock_container: AsyncMock,
    ) -> None:
        """When no lock exists, creating one should succeed."""
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        mock_container.read_item.side_effect = CosmosResourceNotFoundError(
            status_code=404, message="Not found",
        )
        mock_container.create_item.return_value = {}

        sle = SchedulerLeaderElection(container=mock_container, lease_seconds=30)
        acquired = await sle.try_acquire_leadership()
        assert acquired is True
        assert sle._is_leader is True

    @pytest.mark.asyncio
    async def test_acquire_leadership_other_leader(
        self, mock_container: AsyncMock,
    ) -> None:
        """When another instance holds the lock, acquisition should fail."""
        from datetime import datetime, timezone, timedelta

        mock_container.read_item.return_value = {
            "id": "scheduler-leader",
            "instance_id": "other-instance",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=60)
            ).isoformat(),
            "_etag": "some-etag",
        }

        sle = SchedulerLeaderElection(container=mock_container, lease_seconds=30)
        sle._instance_id = "my-instance"
        acquired = await sle.try_acquire_leadership()
        assert acquired is False
        assert sle._is_leader is False

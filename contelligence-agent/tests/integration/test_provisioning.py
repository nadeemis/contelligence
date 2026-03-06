"""AC-14: Cosmos DB containers provisioned correctly.

Integration tests for ``provision_cosmos_db()`` verifying that the
correct databases and containers are created with expected partition keys.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.provisioning.cosmos_provisioner import provision_cosmos_db


class TestCosmosProvisioning:
    """Verify the provisioner creates the expected Cosmos resources."""

    @pytest.mark.asyncio
    async def test_creates_database(self) -> None:
        client = AsyncMock()
        db_mock = AsyncMock()
        client.create_database_if_not_exists.return_value = db_mock
        db_mock.create_container_if_not_exists.return_value = AsyncMock()

        await provision_cosmos_db(client, "contelligence-agent-db")

        client.create_database_if_not_exists.assert_called_once_with(
            id="contelligence-agent-db"
        )

    @pytest.mark.asyncio
    async def test_creates_sessions_container(self) -> None:
        client = AsyncMock()
        db_mock = AsyncMock()
        client.create_database_if_not_exists.return_value = db_mock
        db_mock.create_container_if_not_exists.return_value = AsyncMock()

        await provision_cosmos_db(client, "test-db")

        # Find the call that creates 'sessions' container
        calls = db_mock.create_container_if_not_exists.call_args_list
        container_ids = [c.kwargs.get("id") for c in calls]
        assert "sessions" in container_ids

    @pytest.mark.asyncio
    async def test_creates_conversation_container(self) -> None:
        client = AsyncMock()
        db_mock = AsyncMock()
        client.create_database_if_not_exists.return_value = db_mock
        db_mock.create_container_if_not_exists.return_value = AsyncMock()

        await provision_cosmos_db(client, "test-db")

        calls = db_mock.create_container_if_not_exists.call_args_list
        container_ids = [c.kwargs.get("id") for c in calls]
        assert "conversation" in container_ids

    @pytest.mark.asyncio
    async def test_creates_outputs_container(self) -> None:
        client = AsyncMock()
        db_mock = AsyncMock()
        client.create_database_if_not_exists.return_value = db_mock
        db_mock.create_container_if_not_exists.return_value = AsyncMock()

        await provision_cosmos_db(client, "test-db")

        calls = db_mock.create_container_if_not_exists.call_args_list
        container_ids = [c.kwargs.get("id") for c in calls]
        assert "outputs" in container_ids

    @pytest.mark.asyncio
    async def test_creates_three_containers(self) -> None:
        client = AsyncMock()
        db_mock = AsyncMock()
        client.create_database_if_not_exists.return_value = db_mock
        db_mock.create_container_if_not_exists.return_value = AsyncMock()

        await provision_cosmos_db(client, "test-db")

        assert db_mock.create_container_if_not_exists.call_count == 3

    @pytest.mark.asyncio
    async def test_sessions_container_partitioned_by_id(self) -> None:
        client = AsyncMock()
        db_mock = AsyncMock()
        client.create_database_if_not_exists.return_value = db_mock
        db_mock.create_container_if_not_exists.return_value = AsyncMock()

        await provision_cosmos_db(client, "test-db")

        calls = db_mock.create_container_if_not_exists.call_args_list
        for c in calls:
            if c.kwargs.get("id") == "sessions":
                pk = c.kwargs.get("partition_key")
                assert pk is not None
                # PartitionKey path should be /id
                assert "/id" in str(pk)

    @pytest.mark.asyncio
    async def test_conversation_container_partitioned_by_session_id(self) -> None:
        client = AsyncMock()
        db_mock = AsyncMock()
        client.create_database_if_not_exists.return_value = db_mock
        db_mock.create_container_if_not_exists.return_value = AsyncMock()

        await provision_cosmos_db(client, "test-db")

        calls = db_mock.create_container_if_not_exists.call_args_list
        for c in calls:
            if c.kwargs.get("id") == "conversation":
                pk = c.kwargs.get("partition_key")
                assert pk is not None
                assert "/session_id" in str(pk)

    @pytest.mark.asyncio
    async def test_idempotent_provisioning(self) -> None:
        """Calling provision_cosmos_db twice should not raise."""
        client = AsyncMock()
        db_mock = AsyncMock()
        client.create_database_if_not_exists.return_value = db_mock
        db_mock.create_container_if_not_exists.return_value = AsyncMock()

        await provision_cosmos_db(client, "test-db")
        await provision_cosmos_db(client, "test-db")

        # Should be called 6 times total (3 containers × 2 calls)
        assert db_mock.create_container_if_not_exists.call_count == 6

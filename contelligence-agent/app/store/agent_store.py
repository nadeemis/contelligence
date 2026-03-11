"""Agent Store — CRUD operations for user-defined agent definitions in Cosmos DB.

Phase: Custom Agent Management
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from azure.cosmos.exceptions import (
    CosmosHttpResponseError,
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)

from app.models.custom_agent_models import (
    AgentDefinitionRecord,
    AgentStatus,
)

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class AgentNotFoundError(Exception):
    """Raised when an agent ID does not exist."""


class AgentAlreadyExistsError(Exception):
    """Raised when attempting to create an agent with a duplicate ID."""

from app.store.storage_manager import StorageManager

class AgentStore:
    """CRUD operations for user-defined agent definitions in Cosmos DB.

    The ``agents`` container uses ``/id`` as its partition key, so every
    point-read and point-write consumes only 1 RU.
    """

    def __init__(
        self,
        storage_manager: StorageManager,
    ) -> None:
        
        self.container = storage_manager.get_container("agents")
        
    # ── Create ─────────────────────────────────────────────────
    async def create_agent(
        self, record: AgentDefinitionRecord,
    ) -> AgentDefinitionRecord:
        """Create a new agent definition. Raises ``AgentAlreadyExistsError`` on conflict."""
        try:
            await self.container.create_item(record.model_dump(mode="json"))
            logger.info("Created agent '%s'.", record.id)
            return record
        except CosmosResourceExistsError:
            raise AgentAlreadyExistsError(f"Agent '{record.id}' already exists")

    # ── Read ───────────────────────────────────────────────────

    async def get_agent(self, agent_id: str) -> AgentDefinitionRecord:
        """Point-read an agent by ID (1 RU)."""
        try:
            item = await self.container.read_item(
                item=agent_id, partition_key=agent_id,
            )
            return AgentDefinitionRecord.model_validate(item)
        except CosmosResourceNotFoundError:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")

    async def list_agents(
        self,
        status: AgentStatus | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentDefinitionRecord]:
        """List agents with optional filtering by status and tags."""
        conditions = ["1=1"]
        params: list[dict[str, Any]] = []

        if status:
            conditions.append("c.status = @status")
            params.append({"name": "@status", "value": status.value})

        if tags:
            # Match agents that have ANY of the specified tags
            for i, tag in enumerate(tags):
                conditions.append(f"ARRAY_CONTAINS(c.tags, @tag{i})")
                params.append({"name": f"@tag{i}", "value": tag})

        query = (
            f"SELECT * FROM c WHERE {' AND '.join(conditions)} "
            f"ORDER BY c.updated_at DESC "
            f"OFFSET {offset} LIMIT {limit}"
        )

        items: list[AgentDefinitionRecord] = []
        async for item in self.container.query_items(
            query=query,
            parameters=params,
            partition_key=None,  # Cross-partition for listing
        ):
            items.append(AgentDefinitionRecord.model_validate(item))
        return items

    # ── Update ─────────────────────────────────────────────────

    async def update_agent(
        self, record: AgentDefinitionRecord,
    ) -> AgentDefinitionRecord:
        """Full-replace an agent definition. Bumps version automatically."""
        record.version += 1
        record.updated_at = datetime.now(timezone.utc)
        await self.container.upsert_item(record.model_dump(mode="json"))
        logger.info("Updated agent '%s' to version %d.", record.id, record.version)
        return record

    # ── Delete ─────────────────────────────────────────────────

    async def delete_agent(self, agent_id: str) -> None:
        """Hard-delete an agent definition."""
        try:
            await self.container.delete_item(
                item=agent_id, partition_key=agent_id,
            )
            logger.info("Deleted agent '%s'.", agent_id)
        except CosmosResourceNotFoundError:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")

    # ── Archive (soft-delete) ──────────────────────────────────

    async def archive_agent(self, agent_id: str) -> AgentDefinitionRecord:
        """Set an agent's status to ARCHIVED (soft-delete)."""
        record = await self.get_agent(agent_id)
        record.status = AgentStatus.ARCHIVED
        return await self.update_agent(record)

    # ── Usage tracking ─────────────────────────────────────────

    async def increment_usage(self, agent_id: str) -> None:
        """Increment the ``usage_count`` field (fire-and-forget, best-effort)."""
        try:
            record = await self.get_agent(agent_id)
            record.usage_count += 1
            await self.container.upsert_item(record.model_dump(mode="json"))
        except Exception:
            logger.debug(
                "Failed to increment usage for agent %s",
                agent_id,
                exc_info=False,
            )

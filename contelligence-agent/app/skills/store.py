"""Skill Store — CRUD operations for skills in Cosmos DB.

Follows the same pattern as ``AgentStore`` for user-defined agent definitions.

Phase: Skills Integration
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
from app.store.storage_manager import StorageManager
from app.models.skill_models import SkillRecord, SkillStatus

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class SkillNotFoundError(Exception):
    """Raised when a skill ID does not exist."""


class SkillAlreadyExistsError(Exception):
    """Raised when attempting to create a skill with a duplicate ID."""


class SkillStore:
    """CRUD operations for skill records in Cosmos DB.

    The ``skills`` container uses ``/partition_key`` as its partition key.
    All skills share the ``"skill"`` partition, enabling efficient cross-skill
    queries while keeping the container small.
    """

    def __init__(
        self,
        storage_manager: StorageManager,
    ) -> None:

        self.container = storage_manager.get_container("skills")


    # ── Create ─────────────────────────────────────────────────
    async def create_skill(self, record: SkillRecord) -> SkillRecord:
        """Create a new skill. Raises ``SkillAlreadyExistsError`` on conflict."""
        try:
            await self.container.create_item(record.model_dump(mode="json"))
            logger.info("Created skill '%s'.", record.id)
            return record
        except CosmosResourceExistsError:
            raise SkillAlreadyExistsError(f"Skill '{record.id}' already exists")

    # ── Read ─────────────────────────────────────────────────
    async def get_skill(self, skill_id: str) -> SkillRecord:
        """Point-read a skill by ID."""
        try:
            item = await self.container.read_item(
                item=skill_id,
                partition_key="skill",
            )
            return SkillRecord.model_validate(item)
        except CosmosResourceNotFoundError:
            raise SkillNotFoundError(f"Skill '{skill_id}' not found")

    async def list_skills(
        self,
        status: SkillStatus | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkillRecord]:
        """List skills with optional filtering by status and tags."""
        conditions = ["c.partition_key = 'skill'"]
        params: list[dict[str, Any]] = []

        if status:
            conditions.append("c.status = @status")
            params.append({"name": "@status", "value": status.value})

        if tags:
            for i, tag in enumerate(tags):
                conditions.append(f"ARRAY_CONTAINS(c.tags, @tag{i})")
                params.append({"name": f"@tag{i}", "value": tag})

        query = (
            f"SELECT * FROM c WHERE {' AND '.join(conditions)} "
            f"ORDER BY c.updated_at DESC "
            f"OFFSET {offset} LIMIT {limit}"
        )

        items: list[SkillRecord] = []
        async for item in self.container.query_items(
            query=query,
            parameters=params or None,
            partition_key="skill",
        ):
            items.append(SkillRecord.model_validate(item))
        return items

    # ── Update ───────────────────────────────────────────────

    async def update_skill(
        self,
        skill_id: str,
        updates: dict[str, Any],
    ) -> SkillRecord:
        """Partial update of a skill record.

        Reads current state, applies updates, bumps version, and upserts.
        """
        current = await self.get_skill(skill_id)
        data = current.model_dump(mode="json")

        for key, value in updates.items():
            if key in data and value is not None:
                data[key] = value

        data["version"] = current.version + 1
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        await self.container.upsert_item(data)
        logger.info("Updated skill '%s' to version %d.", skill_id, data["version"])
        return SkillRecord.model_validate(data)

    # ── Delete ───────────────────────────────────────────────

    async def delete_skill(self, skill_id: str) -> None:
        """Delete a skill record from Cosmos DB."""
        try:
            await self.container.delete_item(
                item=skill_id,
                partition_key="skill",
            )
            logger.info("Deleted skill '%s'.", skill_id)
        except CosmosResourceNotFoundError:
            raise SkillNotFoundError(f"Skill '{skill_id}' not found")

    # ── Increment usage ──────────────────────────────────────

    async def increment_usage(self, skill_id: str) -> None:
        """Increment the usage counter for a skill (best-effort)."""
        try:
            current = await self.get_skill(skill_id)
            data = current.model_dump(mode="json")
            data["usage_count"] = current.usage_count + 1
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            await self.container.upsert_item(data)
        except Exception:
            logger.warning(
                "Failed to increment usage for skill '%s'.", skill_id, exc_info=True,
            )

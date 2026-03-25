"""Prompt Store — CRUD operations for customised system and agent prompts.

Stores user-modified prompts in the ``prompts`` container (Cosmos DB or SQLite)
with fallback to the built-in defaults defined in code.  Every prompt is keyed
by a stable ``id``:

- ``system-prompt`` — the main Contelligence system prompt
- ``agent:<name>`` — a built-in agent prompt (e.g. ``agent:doc-processor``)

The store is intentionally thin: it reads/writes whole prompt documents and
leaves formatting to callers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.agents.custom_agents import CUSTOM_AGENTS
from app.agents.prompts import (
    DATA_ANALYST_PROMPT,
    DOCUMENT_PROCESSOR_PROMPT,
    QA_REVIEWER_PROMPT,
)
from app.models.prompt_models import PromptRecord, PromptResponse, PromptType
from app.prompts.system_prompt import (
    CONTELLIGENCE_AGENT_SYSTEM_PROMPT,
    SYSTEM_PROMPT_VERSION,
)
from app.store.storage_manager import StorageManager

logger = logging.getLogger(f"contelligence-agent.{__name__}")

CONTAINER_NAME = "prompts"
SYSTEM_PROMPT_ID = "system-prompt"


def _agent_prompt_id(agent_name: str) -> str:
    return f"agent:{agent_name}"


# ---------------------------------------------------------------------------
# Built-in defaults (code-defined, read-only reference copies)
# ---------------------------------------------------------------------------

_DEFAULT_AGENT_PROMPTS: dict[str, str] = {
    "doc-processor": DOCUMENT_PROCESSOR_PROMPT,
    "data-analyst": DATA_ANALYST_PROMPT,
    "qa-reviewer": QA_REVIEWER_PROMPT,
}

_DEFAULT_AGENT_DISPLAY_NAMES: dict[str, str] = {
    name: defn.display_name for name, defn in CUSTOM_AGENTS.items()
}


class PromptStore:
    """Data-access layer for prompt customisation.

    Reads from and writes to the ``prompts`` container via :class:`StorageManager`.
    Falls back to code-defined defaults when no customised document exists.
    """

    def __init__(self, storage_manager: StorageManager) -> None:
        self._container = storage_manager.get_container(CONTAINER_NAME)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_record(self, prompt_id: str) -> PromptRecord | None:
        """Point-read a prompt document. Returns ``None`` if not found."""
        try:
            item = await self._container.read_item(
                item=prompt_id, partition_key=prompt_id,
            )
            return PromptRecord.model_validate(item)
        except (CosmosResourceNotFoundError, Exception) as exc:
            # CosmosResourceNotFoundError for Cosmos, general Exception for
            # SQLite shim which may raise differently.
            if "NotFound" in type(exc).__name__ or "not found" in str(exc).lower():
                return None
            raise

    async def _upsert_record(self, record: PromptRecord) -> PromptRecord:
        """Upsert a prompt document and return the saved version."""
        await self._container.upsert_item(record.model_dump(mode="json"))
        logger.info("Upserted prompt '%s' (v%d).", record.id, record.version)
        return record

    def _to_response(self, record: PromptRecord, *, is_default: bool = False) -> PromptResponse:
        return PromptResponse(
            id=record.id,
            prompt_type=record.prompt_type,
            name=record.name,
            content=record.content,
            version=record.version,
            updated_at=record.updated_at,
            is_default=is_default,
        )

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    async def get_system_prompt(self) -> PromptResponse:
        """Return the active system prompt (customised or default)."""
        record = await self._get_record(SYSTEM_PROMPT_ID)
        if record is not None:
            return self._to_response(record, is_default=False)

        # Fallback to built-in default
        default = PromptRecord(
            id=SYSTEM_PROMPT_ID,
            prompt_type=PromptType.SYSTEM,
            name="System Prompt",
            content=CONTELLIGENCE_AGENT_SYSTEM_PROMPT,
            version=0,
        )
        return self._to_response(default, is_default=True)

    async def update_system_prompt(self, content: str, updated_by: str = "admin") -> PromptResponse:
        """Save a customised system prompt."""
        existing = await self._get_record(SYSTEM_PROMPT_ID)
        version = (existing.version + 1) if existing else 1

        record = PromptRecord(
            id=SYSTEM_PROMPT_ID,
            prompt_type=PromptType.SYSTEM,
            name="System Prompt",
            content=content,
            version=version,
            updated_at=datetime.now(timezone.utc),
            updated_by=updated_by,
        )
        await self._upsert_record(record)
        return self._to_response(record, is_default=False)

    async def reset_system_prompt(self) -> PromptResponse:
        """Delete the customised system prompt so the built-in default is used."""
        try:
            await self._container.delete_item(
                item=SYSTEM_PROMPT_ID, partition_key=SYSTEM_PROMPT_ID,
            )
            logger.info("Deleted customised system prompt — reverted to default.")
        except Exception:
            pass  # already at default
        return await self.get_system_prompt()

    async def get_system_prompt_text(self) -> str:
        """Return just the prompt text (used by agent orchestration)."""
        resp = await self.get_system_prompt()
        return resp.content

    # ------------------------------------------------------------------
    # Agent prompts
    # ------------------------------------------------------------------

    async def get_agent_prompt(self, agent_name: str) -> PromptResponse:
        """Return the active prompt for a built-in agent."""
        prompt_id = _agent_prompt_id(agent_name)
        record = await self._get_record(prompt_id)
        if record is not None:
            return self._to_response(record, is_default=False)

        # Fallback to built-in default
        default_content = _DEFAULT_AGENT_PROMPTS.get(agent_name)
        if default_content is None:
            raise ValueError(f"Unknown built-in agent: {agent_name}")

        default = PromptRecord(
            id=prompt_id,
            prompt_type=PromptType.AGENT,
            name=_DEFAULT_AGENT_DISPLAY_NAMES.get(agent_name, agent_name),
            content=default_content,
            version=0,
        )
        return self._to_response(default, is_default=True)

    async def update_agent_prompt(
        self,
        agent_name: str,
        content: str,
        updated_by: str = "admin",
    ) -> PromptResponse:
        """Save a customised agent prompt."""
        if agent_name not in _DEFAULT_AGENT_PROMPTS:
            raise ValueError(f"Unknown built-in agent: {agent_name}")

        prompt_id = _agent_prompt_id(agent_name)
        existing = await self._get_record(prompt_id)
        version = (existing.version + 1) if existing else 1

        record = PromptRecord(
            id=prompt_id,
            prompt_type=PromptType.AGENT,
            name=_DEFAULT_AGENT_DISPLAY_NAMES.get(agent_name, agent_name),
            content=content,
            version=version,
            updated_at=datetime.now(timezone.utc),
            updated_by=updated_by,
        )
        await self._upsert_record(record)
        return self._to_response(record, is_default=False)

    async def reset_agent_prompt(self, agent_name: str) -> PromptResponse:
        """Delete the customised agent prompt so the built-in default is used."""
        if agent_name not in _DEFAULT_AGENT_PROMPTS:
            raise ValueError(f"Unknown built-in agent: {agent_name}")

        prompt_id = _agent_prompt_id(agent_name)
        try:
            await self._container.delete_item(
                item=prompt_id, partition_key=prompt_id,
            )
            logger.info("Deleted customised prompt for agent '%s'.", agent_name)
        except Exception:
            pass
        return await self.get_agent_prompt(agent_name)

    async def get_agent_prompt_text(self, agent_name: str) -> str:
        """Return just the prompt text (used by agent delegation)."""
        resp = await self.get_agent_prompt(agent_name)
        return resp.content

    # ------------------------------------------------------------------
    # List all prompts
    # ------------------------------------------------------------------

    async def list_prompts(self) -> list[PromptResponse]:
        """Return all prompts (system + agent), merging DB overrides with defaults."""
        results: list[PromptResponse] = []

        # System prompt
        results.append(await self.get_system_prompt())

        # All built-in agent prompts
        for agent_name in _DEFAULT_AGENT_PROMPTS:
            results.append(await self.get_agent_prompt(agent_name))

        return results

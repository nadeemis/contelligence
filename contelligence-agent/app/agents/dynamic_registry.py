"""Dynamic Agent Registry — merges built-in and user-created agents.

The ``DynamicAgentRegistry`` is the single source of truth for agent
lookups. It combines the hardcoded ``CUSTOM_AGENTS`` dict with
user-defined agents loaded from Cosmos DB, cached with a configurable TTL.

Phase: Custom Agent Management
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.agents.models import AgentDefinition
from app.agents import CUSTOM_AGENTS
from app.models.custom_agent_models import AgentDefinitionRecord, AgentStatus
from app.store.agent_store import AgentStore

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# Cache TTL — user-created agents are refreshed from Cosmos every 60 seconds
_CACHE_TTL_SECONDS = 60


class DynamicAgentRegistry:
    """Unified agent registry combining built-in and user-created agents.

    Built-in agents (from ``CUSTOM_AGENTS``) are always present and cannot
    be modified or deleted through the UI.  User-created agents are loaded
    from Cosmos DB and cached with a configurable TTL.

    The registry is the single source of truth for the ``AgentDelegator``
    and for the system prompt generation that lists available agents.
    """

    def __init__(
        self,
        agent_store: AgentStore,
        cache_ttl_seconds: int = _CACHE_TTL_SECONDS,
    ) -> None:
        self._store = agent_store
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, AgentDefinition] = {}
        self._user_records_cache: dict[str, AgentDefinitionRecord] = {}
        self._cache_timestamp: float = 0.0
        self._lock = asyncio.Lock()

    # ── Public API ─────────────────────────────────────────────

    async def get_all_agents(self) -> dict[str, AgentDefinition]:
        """Return merged dict of built-in + user-created agents."""
        await self._refresh_if_stale()
        merged = dict(CUSTOM_AGENTS)
        merged.update(self._cache)
        return merged

    async def get_agent(self, agent_id: str) -> AgentDefinition | None:
        """Look up a single agent by ID (built-in or user-created)."""
        if agent_id in CUSTOM_AGENTS:
            return CUSTOM_AGENTS[agent_id]
        await self._refresh_if_stale()
        return self._cache.get(agent_id)

    async def get_agents_for_session(
        self,
        agent_ids: list[str],
    ) -> dict[str, AgentDefinition]:
        """Return only the agents the session is allowed to use.

        If ``agent_ids`` is empty, returns ALL active agents (default behavior).
        If ``agent_ids`` is non-empty, returns only those agents, raising
        ``ValueError`` for any unknown IDs.
        """
        all_agents = await self.get_all_agents()
        if not agent_ids:
            return all_agents

        selected: dict[str, AgentDefinition] = {}
        unknown: list[str] = []
        for aid in agent_ids:
            if aid in all_agents:
                selected[aid] = all_agents[aid]
            else:
                unknown.append(aid)

        if unknown:
            raise ValueError(
                f"Unknown agent(s): {unknown}. "
                f"Available: {list(all_agents.keys())}"
            )
        return selected

    async def list_available_agents(self) -> list[dict[str, Any]]:
        """Return a summary list suitable for the API / Web UI.

        Each item includes: id, display_name, description, source, status,
        tools, mcp_servers, tags, icon, usage_count, editable.
        """
        all_agents = await self.get_all_agents()
        result: list[dict[str, Any]] = []

        for agent_id, agent_def in all_agents.items():
            is_builtin = agent_id in CUSTOM_AGENTS
            # Try to get metadata from the user record cache
            user_rec = self._user_records_cache.get(agent_id)

            result.append({
                "id": agent_id,
                "display_name": agent_def.display_name,
                "description": agent_def.description,
                "source": "built-in" if is_builtin else "user-created",
                "status": "active" if is_builtin else (
                    user_rec.status.value if user_rec else "active"
                ),
                "tools": agent_def.tools,
                "mcp_servers": agent_def.mcp_servers,
                "model": agent_def.model,
                "max_tool_calls": agent_def.max_tool_calls,
                "timeout_seconds": agent_def.timeout_seconds,
                "tags": getattr(user_rec, "tags", []) if user_rec else [],
                "icon": getattr(user_rec, "icon", "bot") if user_rec else "bot",
                "usage_count": getattr(user_rec, "usage_count", 0) if user_rec else 0,
                "editable": not is_builtin,
                "created_at": (
                    user_rec.created_at.isoformat() if user_rec and user_rec.created_at else None
                ),
                "updated_at": (
                    user_rec.updated_at.isoformat() if user_rec and user_rec.updated_at else None
                ),
            })
        return result

    def invalidate_cache(self) -> None:
        """Force a cache refresh on next access (call after create/update/delete)."""
        self._cache_timestamp = 0.0

    # ── Internal ───────────────────────────────────────────────

    async def _refresh_if_stale(self) -> None:
        """Reload user agents from Cosmos if cache is stale."""
        if time.monotonic() - self._cache_timestamp < self._cache_ttl:
            return
        async with self._lock:
            # Double-check after acquiring lock
            if time.monotonic() - self._cache_timestamp < self._cache_ttl:
                return
            await self._load_user_agents()

    async def _load_user_agents(self) -> None:
        """Fetch all active user-created agents from Cosmos and cache them."""
        try:
            records = await self._store.list_agents(status=AgentStatus.ACTIVE)
            new_cache: dict[str, AgentDefinition] = {}
            new_records: dict[str, AgentDefinitionRecord] = {}

            for rec in records:
                new_cache[rec.id] = AgentDefinition(
                    name=rec.id,
                    display_name=rec.display_name,
                    description=rec.description,
                    tools=rec.tools,
                    mcp_servers=rec.mcp_servers,
                    prompt=rec.prompt,
                    model=rec.model,
                    max_tool_calls=rec.max_tool_calls,
                    timeout_seconds=rec.timeout_seconds,
                )
                new_records[rec.id] = rec

            self._cache = new_cache
            self._user_records_cache = new_records
            self._cache_timestamp = time.monotonic()
            logger.info(
                "Refreshed user-agent cache: %d agents loaded", len(new_cache),
            )
        except Exception:
            logger.exception("Failed to refresh user-agent cache")

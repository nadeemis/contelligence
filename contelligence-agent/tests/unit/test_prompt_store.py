"""Unit tests for PromptStore — prompt customisation CRUD with fallback to defaults."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.models.prompt_models import PromptType
from app.prompts.prompt_store import PromptStore, SYSTEM_PROMPT_ID


# ---------------------------------------------------------------------------
# In-memory storage shim (mimics the container client API)
# ---------------------------------------------------------------------------

class _InMemoryContainer:
    """Minimal in-memory mock of a Cosmos / SQLite container client."""

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    async def read_item(self, *, item: str, partition_key: str) -> dict:
        if item not in self._docs:
            from azure.cosmos.exceptions import CosmosResourceNotFoundError
            raise CosmosResourceNotFoundError(status_code=404, message="Not found")
        return self._docs[item]

    async def upsert_item(self, body: dict) -> dict:
        doc_id = body["id"]
        self._docs[doc_id] = body
        return body

    async def delete_item(self, *, item: str, partition_key: str) -> None:
        self._docs.pop(item, None)


class _FakeStorageManager:
    """StorageManager stand-in that returns an in-memory container."""

    def __init__(self) -> None:
        self._containers: dict[str, _InMemoryContainer] = {}

    def get_container(self, name: str):
        if name not in self._containers:
            self._containers[name] = _InMemoryContainer()
        return self._containers[name]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def store() -> PromptStore:
    sm = _FakeStorageManager()
    return PromptStore(sm)


# ---------------------------------------------------------------------------
# System prompt tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_system_prompt_returns_default(store: PromptStore):
    resp = await store.get_system_prompt()
    assert resp.id == SYSTEM_PROMPT_ID
    assert resp.prompt_type == PromptType.SYSTEM
    assert resp.is_default is True
    assert resp.version == 0
    assert len(resp.content) > 100  # sanity: non-trivial default


@pytest.mark.asyncio
async def test_update_system_prompt(store: PromptStore):
    updated = await store.update_system_prompt("Custom system prompt text")
    assert updated.content == "Custom system prompt text"
    assert updated.is_default is False
    assert updated.version == 1

    # Second update bumps version
    updated2 = await store.update_system_prompt("Even newer prompt")
    assert updated2.version == 2
    assert updated2.content == "Even newer prompt"


@pytest.mark.asyncio
async def test_get_system_prompt_returns_custom_after_update(store: PromptStore):
    await store.update_system_prompt("My custom prompt")
    resp = await store.get_system_prompt()
    assert resp.content == "My custom prompt"
    assert resp.is_default is False


@pytest.mark.asyncio
async def test_reset_system_prompt(store: PromptStore):
    await store.update_system_prompt("Temporary override")
    reset = await store.reset_system_prompt()
    assert reset.is_default is True
    assert reset.version == 0


@pytest.mark.asyncio
async def test_get_system_prompt_text(store: PromptStore):
    text = await store.get_system_prompt_text()
    assert isinstance(text, str)
    assert "Contelligence" in text


# ---------------------------------------------------------------------------
# Agent prompt tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_agent_prompt_returns_default(store: PromptStore):
    resp = await store.get_agent_prompt("doc-processor")
    assert resp.id == "agent:doc-processor"
    assert resp.prompt_type == PromptType.AGENT
    assert resp.is_default is True
    assert "Document Processor" in resp.content


@pytest.mark.asyncio
async def test_update_agent_prompt(store: PromptStore):
    updated = await store.update_agent_prompt("data-analyst", "Custom analyst instructions")
    assert updated.content == "Custom analyst instructions"
    assert updated.is_default is False
    assert updated.version == 1


@pytest.mark.asyncio
async def test_reset_agent_prompt(store: PromptStore):
    await store.update_agent_prompt("qa-reviewer", "Override")
    reset = await store.reset_agent_prompt("qa-reviewer")
    assert reset.is_default is True
    assert "Quality Reviewer" in reset.content


@pytest.mark.asyncio
async def test_update_unknown_agent_raises(store: PromptStore):
    with pytest.raises(ValueError, match="Unknown built-in agent"):
        await store.update_agent_prompt("nonexistent-agent", "text")


@pytest.mark.asyncio
async def test_get_unknown_agent_raises(store: PromptStore):
    with pytest.raises(ValueError, match="Unknown built-in agent"):
        await store.get_agent_prompt("nonexistent-agent")


# ---------------------------------------------------------------------------
# List prompts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_prompts_returns_all(store: PromptStore):
    prompts = await store.list_prompts()
    ids = {p.id for p in prompts}
    assert SYSTEM_PROMPT_ID in ids
    assert "agent:doc-processor" in ids
    assert "agent:data-analyst" in ids
    assert "agent:qa-reviewer" in ids
    # All should be defaults initially
    assert all(p.is_default for p in prompts)


@pytest.mark.asyncio
async def test_list_prompts_reflects_updates(store: PromptStore):
    await store.update_system_prompt("Updated system")
    await store.update_agent_prompt("doc-processor", "Updated doc proc")

    prompts = await store.list_prompts()
    by_id = {p.id: p for p in prompts}

    assert by_id[SYSTEM_PROMPT_ID].is_default is False
    assert by_id[SYSTEM_PROMPT_ID].content == "Updated system"
    assert by_id["agent:doc-processor"].is_default is False
    assert by_id["agent:doc-processor"].content == "Updated doc proc"
    # Unchanged agents should still be defaults
    assert by_id["agent:data-analyst"].is_default is True
    assert by_id["agent:qa-reviewer"].is_default is True

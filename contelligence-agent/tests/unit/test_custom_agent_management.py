"""Tests for Custom Agent Management — models, store, registry, router, prompt.

Covers:
- ``AgentDefinitionRecord`` Pydantic model validation
- ``AgentStore`` CRUD operations (mocked Cosmos DB)
- ``DynamicAgentRegistry`` — merge, cache, agent-for-session resolution
- ``build_delegation_prompt_section()`` output correctness
- ``InstructOptions.agents`` and ``SessionRecord.allowed_agents`` fields
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.models import AgentDefinition
from app.models.agent_models import InstructOptions
from app.models.custom_agent_models import (
    AgentDefinitionRecord,
    AgentSource,
    AgentStatus,
)
from app.models.session_models import SessionMetrics, SessionRecord, SessionStatus
from app.prompts.agent_delegation_prompt import build_delegation_prompt_section


# ===========================================================================
# AgentDefinitionRecord model tests
# ===========================================================================


class TestAgentDefinitionRecord:
    """Validate Pydantic model for user-created agent definitions."""

    def test_defaults(self) -> None:
        """Record should populate sensible defaults."""
        record = AgentDefinitionRecord(
            id="test-agent",
            display_name="Test Agent",
            description="A test agent",
            prompt="You are a test agent.",
            tools=["extract_pdf"],
        )
        assert record.source == AgentSource.USER_CREATED
        assert record.status == AgentStatus.ACTIVE
        assert record.model == "gpt-4.1"
        assert record.max_tool_calls == 50
        assert record.timeout_seconds == 300
        assert record.icon == "bot"
        assert record.tags == []
        assert record.mcp_servers == ["azure"]
        assert record.usage_count == 0
        assert record.version == 1

    def test_partition_key_mirrors_id(self) -> None:
        record = AgentDefinitionRecord(
            id="my-agent",
            display_name="My Agent",
            description="desc",
            prompt="prompt",
            tools=[],
        )
        assert record.partition_key == "my-agent"

    def test_created_at_defaults_to_utc_now(self) -> None:
        before = datetime.now(timezone.utc)
        record = AgentDefinitionRecord(
            id="ts-test",
            display_name="TS",
            description="desc",
            prompt="p",
            tools=[],
        )
        after = datetime.now(timezone.utc)
        assert before <= record.created_at <= after

    def test_source_enum_values(self) -> None:
        assert AgentSource.BUILT_IN == "built-in"
        assert AgentSource.USER_CREATED == "user-created"

    def test_status_enum_values(self) -> None:
        assert AgentStatus.ACTIVE == "active"
        assert AgentStatus.ARCHIVED == "archived"
        assert AgentStatus.DRAFT == "draft"


# ===========================================================================
# Extended model field tests
# ===========================================================================


class TestInstructOptionsAgents:
    """Verify the new ``agents`` field on InstructOptions."""

    def test_agents_default_empty_list(self) -> None:
        opts = InstructOptions()
        assert opts.agents == []

    def test_agents_custom_list(self) -> None:
        opts = InstructOptions(agents=["doc-processor", "invoice-expert"])
        assert opts.agents == ["doc-processor", "invoice-expert"]

    def test_backward_compatible_dump(self) -> None:
        opts = InstructOptions()
        dumped = opts.model_dump()
        assert "agents" in dumped
        assert dumped["agents"] == []


class TestSessionRecordAllowedAgents:
    """Verify the new ``allowed_agents`` field on SessionRecord."""

    def test_allowed_agents_default_empty(self) -> None:
        record = SessionRecord(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status=SessionStatus.ACTIVE,
            model="gpt-4.1",
            instruction="test",
            metrics=SessionMetrics(),
        )
        assert record.allowed_agents == []

    def test_allowed_agents_populated(self) -> None:
        record = SessionRecord(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status=SessionStatus.ACTIVE,
            model="gpt-4.1",
            instruction="test",
            metrics=SessionMetrics(),
            allowed_agents=["doc-processor", "invoice-expert"],
        )
        assert record.allowed_agents == ["doc-processor", "invoice-expert"]


# ===========================================================================
# AgentStore tests (mocked Cosmos DB)
# ===========================================================================


def _make_mock_container() -> AsyncMock:
    """Create a mock Cosmos container client."""
    mock = AsyncMock()
    mock.create_item = AsyncMock()
    mock.read_item = AsyncMock()
    mock.replace_item = AsyncMock()
    mock.delete_item = AsyncMock()
    mock.query_items = MagicMock()
    return mock


class TestAgentStore:
    """Test AgentStore CRUD with mocked Cosmos container."""

    @pytest.fixture
    def store(self) -> Any:
        from app.store.agent_store import AgentStore

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_container = _make_mock_container()
        mock_client.get_database_client.return_value = mock_db
        mock_db.get_container_client.return_value = mock_container

        store = AgentStore(mock_client)
        store._container = mock_container
        return store

    @pytest.mark.asyncio
    async def test_create_agent(self, store: Any) -> None:
        record = AgentDefinitionRecord(
            id="new-agent",
            display_name="New Agent",
            description="A new agent",
            prompt="System prompt",
            tools=["extract_pdf"],
        )
        store._container.create_item.return_value = record.model_dump()
        result = await store.create_agent(record)
        assert result.id == "new-agent"
        store._container.create_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_agent(self, store: Any) -> None:
        record_data = AgentDefinitionRecord(
            id="existing-agent",
            display_name="Existing",
            description="An existing agent",
            prompt="prompt",
            tools=["read_blob"],
        ).model_dump()
        store._container.read_item.return_value = record_data
        result = await store.get_agent("existing-agent")
        assert result.id == "existing-agent"

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, store: Any) -> None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        from app.store.agent_store import AgentNotFoundError

        store._container.read_item.side_effect = CosmosResourceNotFoundError(
            status_code=404, message="Not found"
        )
        with pytest.raises(AgentNotFoundError):
            await store.get_agent("missing-agent")

    @pytest.mark.asyncio
    async def test_update_agent_bumps_version(self, store: Any) -> None:
        record = AgentDefinitionRecord(
            id="update-me",
            display_name="Pre-update",
            description="desc",
            prompt="prompt",
            tools=["read_blob"],
            version=1,
        )
        store._container.replace_item.return_value = record.model_dump()
        result = await store.update_agent(record)
        # After update, version should have been bumped
        call_args = store._container.replace_item.call_args
        body = call_args.kwargs.get("body") or call_args[1].get("body") or call_args[0][1]
        assert body["version"] == 2

    @pytest.mark.asyncio
    async def test_delete_agent(self, store: Any) -> None:
        store._container.delete_item.return_value = None
        await store.delete_agent("to-delete")
        store._container.delete_item.assert_called_once_with(
            item="to-delete", partition_key="to-delete"
        )

    @pytest.mark.asyncio
    async def test_archive_agent(self, store: Any) -> None:
        record_data = AgentDefinitionRecord(
            id="to-archive",
            display_name="Archive Me",
            description="desc",
            prompt="prompt",
            tools=["read_blob"],
            status=AgentStatus.ACTIVE,
        ).model_dump()
        store._container.read_item.return_value = record_data
        store._container.replace_item.return_value = {
            **record_data, "status": "archived"
        }
        result = await store.archive_agent("to-archive")
        assert result.status == AgentStatus.ARCHIVED


# ===========================================================================
# DynamicAgentRegistry tests
# ===========================================================================


class TestDynamicAgentRegistry:
    """Test the unified registry merging built-in + user agents."""

    @pytest.fixture
    def mock_store(self) -> Any:
        """AgentStore mock that returns no user agents by default."""
        store = AsyncMock()
        store.list_agents = AsyncMock(return_value=[])
        store.increment_usage = AsyncMock()
        return store

    @pytest.fixture
    def registry(self, mock_store: Any) -> Any:
        from app.agents.dynamic_registry import DynamicAgentRegistry
        return DynamicAgentRegistry(store=mock_store, cache_ttl_seconds=0)

    @pytest.mark.asyncio
    async def test_built_in_agents_always_present(self, registry: Any) -> None:
        agents = await registry.get_all_agents()
        assert "doc-processor" in agents
        assert "data-analyst" in agents
        assert "qa-reviewer" in agents

    @pytest.mark.asyncio
    async def test_user_agents_merged(self, registry: Any, mock_store: Any) -> None:
        mock_store.list_agents.return_value = [
            AgentDefinitionRecord(
                id="custom-one",
                display_name="Custom One",
                description="A custom agent",
                prompt="You are custom one.",
                tools=["read_blob"],
                source=AgentSource.USER_CREATED,
                status=AgentStatus.ACTIVE,
            ),
        ]
        agents = await registry.get_all_agents()
        assert "custom-one" in agents
        assert "doc-processor" in agents  # still has built-ins

    @pytest.mark.asyncio
    async def test_get_agent_returns_none_for_unknown(self, registry: Any) -> None:
        result = await registry.get_agent("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_agent_returns_built_in(self, registry: Any) -> None:
        result = await registry.get_agent("doc-processor")
        assert result is not None
        assert isinstance(result, AgentDefinition)

    @pytest.mark.asyncio
    async def test_get_agents_for_session_all_when_empty(self, registry: Any) -> None:
        """Empty agent list should return all active agents."""
        agents = await registry.get_agents_for_session([])
        assert len(agents) >= 3  # at least the built-in agents

    @pytest.mark.asyncio
    async def test_get_agents_for_session_specific(self, registry: Any) -> None:
        agents = await registry.get_agents_for_session(["doc-processor"])
        assert "doc-processor" in agents
        assert "data-analyst" not in agents

    @pytest.mark.asyncio
    async def test_get_agents_for_session_invalid_raises(self, registry: Any) -> None:
        with pytest.raises(ValueError, match="not found"):
            await registry.get_agents_for_session(["nonexistent-agent"])

    @pytest.mark.asyncio
    async def test_list_available_agents_returns_summaries(self, registry: Any) -> None:
        agents = await registry.list_available_agents()
        assert len(agents) >= 3
        for a in agents:
            assert "id" in a
            assert "display_name" in a
            assert "source" in a
            assert "editable" in a

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, registry: Any) -> None:
        """After invalidate_cache(), next call should reload from store."""
        await registry.get_all_agents()
        registry.invalidate_cache()
        await registry.get_all_agents()
        # Store should have been called at least twice (before + after invalidation)
        assert registry._store.list_agents.call_count >= 2


# ===========================================================================
# Delegation prompt builder tests
# ===========================================================================


class TestBuildDelegationPromptSection:
    """Test the system prompt section builder."""

    def test_empty_agents_returns_no_agents_message(self) -> None:
        result = build_delegation_prompt_section({})
        assert "No specialist agents" in result
        assert "Handle all tasks directly" in result

    def test_single_agent(self) -> None:
        agents = {
            "doc-processor": AgentDefinition(
                name="doc-processor",
                display_name="Document Processor",
                description="Extracts and transforms documents",
                tools=["extract_pdf", "extract_docx", "read_blob"],
                mcp_servers=["azure"],
                prompt="You are a doc processor.",
            ),
        }
        result = build_delegation_prompt_section(agents)
        assert "Document Processor" in result
        assert "`doc-processor`" in result
        assert "Extracts and transforms documents" in result
        assert "extract_pdf" in result
        assert "Delegation Rules" in result

    def test_multiple_agents(self) -> None:
        agents = {
            "agent-a": AgentDefinition(
                name="agent-a",
                display_name="Agent A",
                description="Does A things",
                tools=["tool_1"],
                mcp_servers=["azure"],
                prompt="...",
            ),
            "agent-b": AgentDefinition(
                name="agent-b",
                display_name="Agent B",
                description="Does B things",
                tools=["tool_2", "tool_3"],
                mcp_servers=["azure"],
                prompt="...",
            ),
        }
        result = build_delegation_prompt_section(agents)
        assert "Agent A" in result
        assert "Agent B" in result
        assert "Use ONLY agents from the list above" in result

    def test_tools_truncated_when_many(self) -> None:
        agents = {
            "many-tools": AgentDefinition(
                name="many-tools",
                display_name="Many Tools",
                description="Has lots of tools",
                tools=["t1", "t2", "t3", "t4", "t5", "t6"],
                mcp_servers=["azure"],
                prompt="...",
            ),
        }
        result = build_delegation_prompt_section(agents)
        assert "+2 more" in result


# ===========================================================================
# Delegator allowed_agents enforcement tests
# ===========================================================================


class TestDelegatorAllowedAgents:
    """Test that AgentDelegator enforces session-level agent restrictions."""

    @pytest.mark.asyncio
    async def test_delegate_blocked_by_allowed_agents(self) -> None:
        from app.services.delegator import AgentDelegator

        delegator = AgentDelegator(
            session_factory=MagicMock(),
            session_store=AsyncMock(),
        )
        with pytest.raises(ValueError, match="not allowed"):
            await delegator.delegate(
                agent_name="doc-processor",
                instruction="test",
                allowed_agents=["data-analyst"],
            )

    @pytest.mark.asyncio
    async def test_delegate_allowed_agents_none_allows_all(self) -> None:
        """When allowed_agents is None, any agent should be permitted."""
        from app.services.delegator import AgentDelegator

        mock_registry = AsyncMock()
        mock_registry.get_agent = AsyncMock(return_value=None)
        mock_registry.get_all_agents = AsyncMock(return_value={})
        mock_registry._store = AsyncMock()

        delegator = AgentDelegator(
            session_factory=MagicMock(),
            session_store=AsyncMock(),
            dynamic_registry=mock_registry,
        )
        # Should NOT raise ValueError for allowed_agents
        # Will raise ValueError for unknown agent, which is expected
        with pytest.raises(ValueError, match="Unknown agent"):
            await delegator.delegate(
                agent_name="nonexistent",
                instruction="test",
                allowed_agents=None,
            )

"""Integration tests for end-to-end delegation flow.

Tests the full delegation pipeline: delegator → sub-session creation →
event emission → session linking.

Marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.registry import CUSTOM_AGENTS
from app.models.agent_models import AgentEvent
from app.services.delegator import AgentDelegator


pytestmark = pytest.mark.integration


def _make_session_factory() -> MagicMock:
    """Build a mock SessionFactory that produces working sub-sessions."""
    factory = MagicMock()
    factory.mcp_servers = {"azure": {"type": "stdio"}}
    factory.tool_registry = MagicMock()
    factory.tool_registry.filter_tools.return_value = []

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.content = "Sub-agent completed the task successfully."
    mock_session.run = AsyncMock(return_value=mock_result)
    factory.create_session = AsyncMock(return_value=mock_session)

    return factory


def _make_store() -> AsyncMock:
    store = AsyncMock()
    store.append_delegation = AsyncMock()
    store.update_delegation_status = AsyncMock()
    return store


class TestDelegationFlow:

    @pytest.mark.asyncio
    async def test_full_delegation_to_doc_processor(self) -> None:
        factory = _make_session_factory()
        store = _make_store()
        delegator = AgentDelegator(factory, store)
        queue: asyncio.Queue = asyncio.Queue()

        result = await delegator.delegate(
            agent_name="doc-processor",
            instruction="Extract text from report.pdf",
            parent_session_id="session-001",
            event_queue=queue,
        )

        assert result["agent"] == "doc-processor"
        assert result["status"] == "completed"
        assert result["sub_session_id"].startswith("session-001::doc-processor::")

        # Events: delegation_start then delegation_complete
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        assert len(events) >= 2
        start_events = [e for e in events if e.type == "delegation_start"]
        complete_events = [e for e in events if e.type == "delegation_complete"]
        assert len(start_events) == 1
        assert len(complete_events) == 1

    @pytest.mark.asyncio
    async def test_delegation_links_session(self) -> None:
        factory = _make_session_factory()
        store = _make_store()
        delegator = AgentDelegator(factory, store)

        await delegator.delegate(
            agent_name="qa-reviewer",
            instruction="Review extraction quality",
            parent_session_id="session-002",
        )

        # Session store should have append_delegation called
        store.append_delegation.assert_awaited_once()
        # And update_delegation_status on completion
        store.update_delegation_status.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("agent_name", list(CUSTOM_AGENTS.keys()))
    async def test_all_agents_can_be_delegated(self, agent_name: str) -> None:
        """Each registered agent should be delegatable."""
        factory = _make_session_factory()
        store = _make_store()
        delegator = AgentDelegator(factory, store)

        result = await delegator.delegate(
            agent_name=agent_name,
            instruction="Perform a task",
            parent_session_id="session-all",
        )
        assert result["agent"] == agent_name
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_delegation_with_context_data(self) -> None:
        factory = _make_session_factory()
        store = _make_store()
        delegator = AgentDelegator(factory, store)

        result = await delegator.delegate(
            agent_name="data-analyst",
            instruction="Analyze these records",
            context={"data": {"source": "blob/data.csv", "rows": 1000}},
            parent_session_id="session-ctx",
        )

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_delegation_error_handling(self) -> None:
        """If the sub-session raises, delegator should handle gracefully."""
        factory = _make_session_factory()
        # Make run raise
        factory.create_session.return_value.run.side_effect = RuntimeError("Sub-agent failed")
        store = _make_store()
        delegator = AgentDelegator(factory, store)
        queue: asyncio.Queue = asyncio.Queue()

        result = await delegator.delegate(
            agent_name="doc-processor",
            instruction="Extract",
            parent_session_id="session-err",
            event_queue=queue,
        )

        assert result["status"] == "failed"
        # Should have error event
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        error_events = [e for e in events if e.type == "delegation_error"]
        assert len(error_events) >= 1

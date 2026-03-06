"""Tests for AgentService."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.agent_models import AgentEvent, InstructOptions
from app.models.exceptions import SessionNotFoundError
from app.services.agent_service import AgentService


def _make_service(
    session_factory: MagicMock | None = None,
    system_prompt: str = "You are a test agent.",
) -> AgentService:
    """Build an AgentService with a mocked session factory."""
    if session_factory is None:
        session_factory = MagicMock()
        mock_session = AsyncMock()
        mock_session.session_id = "test-session-id"
        mock_session.status = "active"
        mock_session.close = AsyncMock()
        mock_session.send_message = AsyncMock()
        session_factory.create_session = AsyncMock(return_value=mock_session)

    return AgentService(
        session_factory=session_factory,
        system_prompt=system_prompt,
    )


class TestCreateAndRun:

    @pytest.mark.asyncio
    async def test_returns_session_id(self) -> None:
        """create_and_run should return a UUID session id string."""
        service = _make_service()
        options = InstructOptions(model="gpt-4.1")

        with patch("app.services.agent_service.run_agent_loop", new_callable=AsyncMock):
            session_id = await service.create_and_run(
                instruction="Extract documents",
                options=options,
            )

        assert isinstance(session_id, str)
        assert len(session_id) > 0

    @pytest.mark.asyncio
    async def test_session_stored(self) -> None:
        """The created session should be stored in active_sessions."""
        service = _make_service()
        options = InstructOptions()

        with patch("app.services.agent_service.run_agent_loop", new_callable=AsyncMock):
            session_id = await service.create_and_run(
                instruction="test", options=options,
            )

        assert session_id in service.active_sessions
        assert session_id in service.event_queues

    @pytest.mark.asyncio
    async def test_event_queue_created(self) -> None:
        service = _make_service()
        options = InstructOptions()

        with patch("app.services.agent_service.run_agent_loop", new_callable=AsyncMock):
            session_id = await service.create_and_run(
                instruction="x", options=options,
            )

        assert isinstance(service.event_queues[session_id], asyncio.Queue)


class TestStreamEvents:

    @pytest.mark.asyncio
    async def test_yields_sse_events(self) -> None:
        """stream_events should yield SSE-formatted dicts."""
        service = _make_service()

        # Manually set up a queue with events.
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        queue.put_nowait(
            AgentEvent(type="message", data={"content": "hi"}, session_id="s1")
        )
        queue.put_nowait(
            AgentEvent(type="session_complete", data={"response": "done"}, session_id="s1")
        )
        service.event_queues["s1"] = queue

        events = []
        async for sse_dict in service.stream_events("s1"):
            events.append(sse_dict)

        assert len(events) == 2
        assert events[0]["event"] == "message"
        assert events[1]["event"] == "session_complete"

    @pytest.mark.asyncio
    async def test_unknown_session_yields_error(self) -> None:
        """Streaming from a nonexistent session should yield a session_error."""
        service = _make_service()

        events = []
        async for sse_dict in service.stream_events("does-not-exist"):
            events.append(sse_dict)

        assert len(events) == 1
        assert events[0]["event"] == "session_error"


class TestSendReply:

    @pytest.mark.asyncio
    async def test_raises_for_unknown_session(self) -> None:
        """send_reply should raise SessionNotFoundError for unknown ids."""
        service = _make_service()

        with pytest.raises(SessionNotFoundError):
            await service.send_reply("unknown-id", "hello")

    @pytest.mark.asyncio
    async def test_sends_message_to_session(self) -> None:
        """send_reply on a known session should call send_message."""
        service = _make_service()
        options = InstructOptions()

        with patch("app.services.agent_service.run_agent_loop", new_callable=AsyncMock):
            session_id = await service.create_and_run(
                instruction="start", options=options,
            )
            await service.send_reply(session_id, "continue")

        session = service.active_sessions[session_id]
        session.send_message.assert_awaited_once_with("continue")


class TestCancel:

    @pytest.mark.asyncio
    async def test_cancel_removes_session(self) -> None:
        """cancel should remove the session from active_sessions."""
        service = _make_service()
        options = InstructOptions()

        with patch("app.services.agent_service.run_agent_loop", new_callable=AsyncMock):
            session_id = await service.create_and_run(
                instruction="start", options=options,
            )

        await service.cancel(session_id)
        assert session_id not in service.active_sessions

    @pytest.mark.asyncio
    async def test_cancel_unknown_session_graceful(self) -> None:
        """Cancelling an unknown session should not raise."""
        service = _make_service()
        # Should not raise.
        await service.cancel("nonexistent")

    @pytest.mark.asyncio
    async def test_cancel_closes_session(self) -> None:
        """cancel should call close() on the session."""
        service = _make_service()
        options = InstructOptions()

        with patch("app.services.agent_service.run_agent_loop", new_callable=AsyncMock):
            session_id = await service.create_and_run(
                instruction="start", options=options,
            )

        session = service.active_sessions[session_id]
        await service.cancel(session_id)
        session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_puts_error_event(self) -> None:
        """cancel should put a session_error event into the queue."""
        service = _make_service()
        options = InstructOptions()

        with patch("app.services.agent_service.run_agent_loop", new_callable=AsyncMock):
            session_id = await service.create_and_run(
                instruction="start", options=options,
            )

        queue = service.event_queues[session_id]
        await service.cancel(session_id)

        event = await queue.get()
        assert event.type == "session_error"
        assert "cancelled" in event.data.get("error", "").lower()

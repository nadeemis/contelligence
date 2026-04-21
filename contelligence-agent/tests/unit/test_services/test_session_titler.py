"""Unit tests for SessionTitler — heuristic + Copilot SDK paths."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.session_titler import SessionTitler
from app.settings import AppSettings


def _settings(**overrides) -> AppSettings:
    base = {
        "ENABLE_SESSION_AUTO_RENAME": True,
        "SESSION_TITLE_MODEL": "gpt-4.1-mini",
        "SESSION_TITLE_MAX_CHARS": 60,
        "SESSION_TITLE_TIMEOUT_SECONDS": 8.0,
        "SESSION_TITLE_MIN_TURNS": 0,
    }
    base.update(overrides)
    return AppSettings(_env_file=None, **base)


# ---------------------------------------------------------------------------
# Copilot SDK fakes
# ---------------------------------------------------------------------------


class _FakeSdkSession:
    """Minimal Copilot SDK session stand-in.

    Captures the ``on(handler)`` callback and drives it synchronously during
    ``send()`` so tests stay deterministic.
    """

    def __init__(
        self,
        *,
        reply: str | None = None,
        raise_error: str | None = None,
        never_idle: bool = False,
    ) -> None:
        self._handler = None
        self._reply = reply
        self._raise_error = raise_error
        self._never_idle = never_idle
        self.destroyed = False

    def on(self, handler):  # type: ignore[no-untyped-def]
        self._handler = handler

    async def send(self, _payload):  # type: ignore[no-untyped-def]
        if self._handler is None or self._never_idle:
            return

        if self._reply is not None:
            self._handler(
                SimpleNamespace(
                    type=SimpleNamespace(value="assistant.message"),
                    data=SimpleNamespace(content=self._reply),
                ),
            )

        if self._raise_error is not None:
            self._handler(
                SimpleNamespace(
                    type=SimpleNamespace(value="session.error"),
                    data=SimpleNamespace(message=self._raise_error),
                ),
            )
            return

        self._handler(
            SimpleNamespace(
                type=SimpleNamespace(value="session.idle"),
                data=SimpleNamespace(),
            ),
        )

    async def destroy(self):  # type: ignore[no-untyped-def]
        self.destroyed = True


def _make_factory(session: _FakeSdkSession) -> MagicMock:
    """Return a mock ``CopilotClientFactory`` that yields *session*."""
    client = MagicMock()
    client.create_session = AsyncMock(return_value=session)
    factory = MagicMock()
    factory.client = client
    return factory


# ---------------------------------------------------------------------------
# Heuristic
# ---------------------------------------------------------------------------


class TestHeuristic:
    def test_drops_leading_stopwords(self) -> None:
        t = SessionTitler(client_factory=None, settings=_settings())
        result = asyncio.run(t.generate_title(
            "Please summarise the Q3 financial report and flag anomalies",
        ))
        assert "Please" not in result
        assert result.startswith("Summarise")

    def test_empty_instruction_returns_placeholder(self) -> None:
        t = SessionTitler(client_factory=None, settings=_settings())
        assert asyncio.run(t.generate_title("   ")) == "Untitled Session"

    def test_truncates_long_output(self) -> None:
        t = SessionTitler(
            client_factory=None,
            settings=_settings(SESSION_TITLE_MAX_CHARS=20),
        )
        result = asyncio.run(t.generate_title(
            "build a very long detailed plan for our new product",
        ))
        assert len(result) <= 20
        assert result.endswith("…")

    def test_preserves_acronyms(self) -> None:
        t = SessionTitler(client_factory=None, settings=_settings())
        result = asyncio.run(t.generate_title(
            "build a PDF report for customer Acme",
        ))
        assert "PDF" in result


# ---------------------------------------------------------------------------
# Feature flag / short-circuit paths
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    def test_disabled_flag_skips_sdk(self) -> None:
        factory = _make_factory(_FakeSdkSession(reply="Ignored"))
        t = SessionTitler(
            client_factory=factory,
            settings=_settings(ENABLE_SESSION_AUTO_RENAME=False),
        )
        result = asyncio.run(t.generate_title("test the system end to end"))
        factory.client.create_session.assert_not_called()
        assert result

    def test_min_turns_gate_skips_sdk(self) -> None:
        factory = _make_factory(_FakeSdkSession(reply="Ignored"))
        t = SessionTitler(
            client_factory=factory,
            settings=_settings(SESSION_TITLE_MIN_TURNS=5),
        )
        result = asyncio.run(t.generate_title("hello world", turns=[]))
        factory.client.create_session.assert_not_called()
        assert result

    def test_no_factory_uses_heuristic(self) -> None:
        t = SessionTitler(client_factory=None, settings=_settings())
        result = asyncio.run(t.generate_title("analyse the customer churn data"))
        assert result
        assert "Analyse" in result or "Customer" in result


# ---------------------------------------------------------------------------
# Copilot SDK path
# ---------------------------------------------------------------------------


class TestCopilotPath:
    @pytest.mark.asyncio
    async def test_success_sanitises_output(self) -> None:
        session = _FakeSdkSession(reply='  "Q3 Financial Review"  ')
        factory = _make_factory(session)
        t = SessionTitler(client_factory=factory, settings=_settings())

        result = await t.generate_title("Summarise Q3 financials")
        assert result == "Q3 Financial Review"
        assert session.destroyed is True

    @pytest.mark.asyncio
    async def test_timeout_falls_back(self) -> None:
        session = _FakeSdkSession(reply=None, never_idle=True)
        factory = _make_factory(session)
        t = SessionTitler(
            client_factory=factory,
            settings=_settings(SESSION_TITLE_TIMEOUT_SECONDS=0.05),
        )

        result = await t.generate_title("build a dashboard for sales metrics")
        assert result
        assert "Dashboard" in result or "Sales" in result or "Build" in result

    @pytest.mark.asyncio
    async def test_error_falls_back(self) -> None:
        session = _FakeSdkSession(reply=None, raise_error="boom")
        factory = _make_factory(session)
        t = SessionTitler(client_factory=factory, settings=_settings())

        result = await t.generate_title("find unresolved Jira tickets")
        assert result
        assert session.destroyed is True

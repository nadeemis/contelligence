"""Session Titler — generate concise titles for sessions.

Used by :class:`PersistentAgentService` to auto-rename sessions after they
complete, and by the ``POST /sessions/{id}/rename`` endpoint when the user
explicitly asks for an auto-rename.

Resolution strategy (in order):

1. If ``ENABLE_SESSION_AUTO_RENAME`` is ``False`` → return the heuristic
   fallback (no Copilot call, no cost).
2. If a :class:`CopilotClientFactory` is available → spin up a throw-away
   Copilot SDK session, send a tiny prompt, collect the assistant message,
   and destroy the session.
3. If the SDK call times out or errors → fall back to the heuristic.

The heuristic extracts the first ~6 meaningful words from the instruction
(Title Case, sanitised).  It is deterministic and never fails.

No external model service (Azure OpenAI, OpenAI) is required — the titler
reuses the same Copilot runtime that powers the rest of the agent.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from app.settings import AppSettings

if TYPE_CHECKING:  # pragma: no cover — typing only
    from app.core.client_factory import CopilotClientFactory
    from app.models.session_models import ConversationTurn

logger = logging.getLogger(f"contelligence-agent.{__name__}")


_TITLE_PROMPT = (
    "You are generating a short title for a completed AI assistant session. "
    "Return ONLY the title — 3 to 7 words, Title Case, no quotes, no trailing "
    "punctuation. Describe the task concisely.\n\n"
    "{context}\n\n"
    "Title:"
)

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_STRIP_RE = re.compile(r"""^['"“”‘’`\s]+|['"“”‘’`\s\.!?,;:]+$""")
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "to", "of", "in", "on", "for",
    "with", "please", "can", "you", "i", "we", "me", "my", "is", "are",
    "be", "do", "does", "about", "from", "by", "this", "that",
}


class SessionTitler:
    """Produce a short human-readable title for a session."""

    def __init__(
        self,
        client_factory: "CopilotClientFactory | None",
        settings: AppSettings,
    ) -> None:
        self._client_factory = client_factory
        self._settings = settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_title(
        self,
        instruction: str,
        *,
        turns: "list[ConversationTurn] | None" = None,
        summary: str | None = None,
    ) -> str:
        """Generate a title for the session.

        Always returns a non-empty string — falls back to the heuristic on
        failure rather than raising.
        """
        max_chars = self._settings.SESSION_TITLE_MAX_CHARS

        heuristic = self._heuristic_title(instruction, max_chars=max_chars)

        # Flag disabled → skip SDK entirely.
        if not self._settings.ENABLE_SESSION_AUTO_RENAME:
            return heuristic

        # Min-turns gate — avoids wasting a call on sessions that never got started.
        min_turns = max(self._settings.SESSION_TITLE_MIN_TURNS, 0)
        if min_turns > 0 and turns is not None and len(turns) < min_turns:
            return heuristic

        if self._client_factory is None:
            return heuristic

        try:
            title = await asyncio.wait_for(
                self._generate_via_copilot(instruction, turns=turns, summary=summary),
                timeout=self._settings.SESSION_TITLE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("SessionTitler: Copilot call timed out, using heuristic.")
            return heuristic
        except Exception as exc:  # noqa: BLE001 — never fail the caller
            logger.warning(
                "SessionTitler: Copilot call failed (%s), using heuristic.",
                exc,
            )
            return heuristic

        cleaned = self._sanitise_title(title, max_chars=max_chars)
        return cleaned or heuristic

    # ------------------------------------------------------------------
    # Copilot SDK path
    # ------------------------------------------------------------------

    async def _generate_via_copilot(
        self,
        instruction: str,
        *,
        turns: "list[ConversationTurn] | None",
        summary: str | None,
    ) -> str:
        assert self._client_factory is not None

        from copilot.session import PermissionHandler  # Avoid circular import
        
        context = self._build_context(instruction, turns=turns, summary=summary)
        prompt = _TITLE_PROMPT.format(context=context)

        client = self._client_factory.client

        # Create a throw-away session scoped just to this title generation.
        # ``system_message`` is not needed — the prompt itself carries all the
        # instruction.  Disable streaming and tools — we only want a one-shot
        # assistant.message.
        sdk_session = await client.create_session(
            model=self._settings.SESSION_TITLE_MODEL,
            streaming=False,
            tools=[],
            on_permission_request=PermissionHandler.approve_all,
            on_user_input_request=None,
        )

        loop = asyncio.get_running_loop()
        done = asyncio.Event()
        collected: dict[str, str] = {"content": "", "error": ""}

        def _on_event(event: Any) -> None:
            """Handle SDK events — runs on the SDK worker thread."""
            try:
                etype = getattr(event.type, "value", str(event.type))
                data = event.data

                if etype == "assistant.message":
                    content = getattr(data, "content", None) or ""
                    if content:
                        collected["content"] = content
                elif etype == "session.idle":
                    loop.call_soon_threadsafe(done.set)
                elif etype == "session.error":
                    collected["error"] = (
                        getattr(data, "message", None) or "session error"
                    )
                    loop.call_soon_threadsafe(done.set)
                elif etype == "abort":
                    collected["error"] = "aborted"
                    loop.call_soon_threadsafe(done.set)
            except Exception:  # noqa: BLE001
                # Never let a bad event crash the worker thread.
                logger.debug("SessionTitler: event handler error", exc_info=True)

        sdk_session.on(_on_event)

        try:
            await sdk_session.send(prompt=prompt)
            await done.wait()
        finally:
            try:
                await sdk_session.destroy()
            except Exception:  # noqa: BLE001
                logger.debug(
                    "SessionTitler: failed to destroy ephemeral session",
                    exc_info=True,
                )

        if collected["error"]:
            raise RuntimeError(collected["error"])
        return collected["content"].strip()

    @staticmethod
    def _build_context(
        instruction: str,
        *,
        turns: "list[ConversationTurn] | None",
        summary: str | None,
    ) -> str:
        parts: list[str] = [f"User instruction: {instruction.strip()}"]
        if summary:
            parts.append(f"Session summary: {summary.strip()}")
        if turns:
            # Last 2 assistant messages, trimmed.
            assistant_msgs = [t for t in turns if t.role == "assistant" and t.content]
            for t in assistant_msgs[-2:]:
                snippet = (t.content or "").strip().replace("\n", " ")[:280]
                parts.append(f"Assistant excerpt: {snippet}")
        return "\n".join(parts)[:2000]

    # ------------------------------------------------------------------
    # Sanitisation & heuristic
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitise_title(raw: str, *, max_chars: int) -> str:
        if not raw:
            return ""
        # Collapse whitespace/newlines, strip wrapping quotes.
        single_line = _WHITESPACE_RE.sub(" ", raw.replace("\n", " ")).strip()
        single_line = _PUNCT_STRIP_RE.sub("", single_line)
        if len(single_line) > max_chars:
            single_line = single_line[: max_chars - 1].rstrip() + "…"
        return single_line

    @staticmethod
    def _heuristic_title(instruction: str, *, max_chars: int) -> str:
        """Deterministic fallback — first ~6 meaningful words, Title Case."""
        if not instruction or not instruction.strip():
            return "Untitled Session"

        cleaned = _WHITESPACE_RE.sub(" ", instruction.strip())
        words = [w for w in cleaned.split(" ") if w]

        # Keep first 8 words, drop leading stopwords for a punchier title.
        significant: list[str] = []
        for w in words[:12]:
            lw = w.lower().strip(".,!?:;\"'()[]")
            if len(significant) == 0 and lw in _STOPWORDS:
                continue
            significant.append(w)
            if len(significant) >= 6:
                break

        if not significant:
            significant = words[:6]

        title = " ".join(significant)
        # Title Case but preserve tokens that already contain uppercase
        # letters (e.g. "PDF", "API", "SessionStore").
        parts = []
        for token in title.split(" "):
            if not token:
                continue
            if any(ch.isupper() for ch in token[1:]) or token.isupper():
                parts.append(token)
            else:
                parts.append(token[:1].upper() + token[1:].lower())
        title = " ".join(parts)

        return SessionTitler._sanitise_title(title, max_chars=max_chars)

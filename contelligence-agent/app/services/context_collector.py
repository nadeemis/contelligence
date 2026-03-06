"""Context Collector — extracts accumulated context from a parent session.

When the main agent delegates to a sub-agent, the sub-agent starts a fresh
Copilot SDK session with no knowledge of what the parent has already done.
This module bridges that gap by reading the parent session's persisted
conversation turns (tool results, assistant summaries) and producing a
formatted context string that can be injected into the sub-session's
instruction.

Usage (called by ``AgentDelegator.delegate()``)::

    collector = ContextCollector(session_store)
    parent_context = await collector.collect(parent_session_id)
    # parent_context is then prepended/appended to the sub-agent's instruction
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.models.session_models import ConversationTurn
from app.store.session_store import SessionStore

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# Tools whose results are high-value and should always be forwarded
EXTRACTION_TOOLS = frozenset({
    "extract_pdf",
    "extract_docx",
    "extract_xlsx",
    "extract_pptx",
    "call_doc_intelligence",
    "scrape_webpage",
    "transcribe_audio",
})

# Tools whose results provide useful context but are lower priority
CONTEXT_TOOLS = frozenset({
    "read_blob",
    "list_blobs",
    "query_cosmos",
    "query_search",
    "search_documents",
})

# Default character budget for the collected context block
DEFAULT_MAX_CHARS = 80_000


class ContextCollector:
    """Reads a parent session's conversation history and extracts
    accumulated context (tool results, assistant summaries) for injection
    into a delegated sub-session.
    """

    def __init__(
        self,
        session_store: SessionStore,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self.store = session_store
        self.max_chars = max_chars

    async def collect(
        self,
        parent_session_id: str,
        *,
        include_assistant_messages: bool = True,
        include_tool_results: bool = True,
    ) -> str:
        """Collect accumulated context from the parent session.

        Reads conversation turns from Cosmos DB and builds a formatted
        context string containing:

        1. **Extraction tool results** (highest priority) — file contents
           already processed by ``extract_pdf``, ``extract_docx``, etc.
        2. **Other tool results** — ``read_blob``, ``query_cosmos``, etc.
        3. **Assistant summaries** — assistant messages that may contain
           synthesized analysis.

        The output is truncated to ``max_chars`` to stay within token
        budgets. Extraction results are prioritized — if space is tight,
        lower-priority items are dropped first.

        Parameters
        ----------
        parent_session_id:
            The session whose history to read.
        include_assistant_messages:
            Whether to include assistant message summaries.
        include_tool_results:
            Whether to include tool call results.

        Returns
        -------
        A Markdown-formatted string ready for injection into a sub-agent's
        instruction.  Returns an empty string if there is no meaningful
        context to forward.
        """
        if not parent_session_id:
            return ""

        try:
            turns = await self.store.get_turns(parent_session_id)
        except Exception:
            logger.warning(
                "Could not load turns for parent session %s — "
                "delegating without parent context.",
                parent_session_id,
                exc_info=True,
            )
            return ""

        if not turns:
            return ""

        # Partition turns into buckets by priority
        extraction_results: list[dict[str, Any]] = []
        other_tool_results: list[dict[str, Any]] = []
        assistant_messages: list[str] = []

        for turn in turns:
            if include_tool_results and turn.role == "tool" and turn.tool_call:
                tc = turn.tool_call
                if tc.status != "success" or tc.result is None:
                    continue

                # Skip blob-offloaded results (they'd just be a ref stub)
                if isinstance(tc.result, dict) and tc.result.get("_ref"):
                    continue

                entry = {
                    "tool": tc.tool_name,
                    "parameters": _summarize_params(tc.parameters),
                    "result": tc.result,
                }

                if tc.tool_name in EXTRACTION_TOOLS:
                    extraction_results.append(entry)
                elif tc.tool_name in CONTEXT_TOOLS:
                    other_tool_results.append(entry)

            elif include_assistant_messages and turn.role == "assistant" and turn.content:
                # Only keep substantive messages (skip very short acks)
                if len(turn.content) > 50:
                    assistant_messages.append(turn.content)

        if not extraction_results and not other_tool_results and not assistant_messages:
            return ""

        # Build the context string, respecting the character budget
        sections: list[str] = []
        remaining = self.max_chars

        # Priority 1: Extraction results (file contents)
        if extraction_results:
            block = _format_tool_results(
                "Extracted File Contents",
                extraction_results,
                remaining,
            )
            if block:
                sections.append(block)
                remaining -= len(block)

        # Priority 2: Other tool results
        if other_tool_results and remaining > 500:
            block = _format_tool_results(
                "Data Retrieved from Tools",
                other_tool_results,
                remaining,
            )
            if block:
                sections.append(block)
                remaining -= len(block)

        # Priority 3: Assistant summaries (useful for multi-turn analysis)
        if assistant_messages and remaining > 500:
            block = _format_assistant_messages(assistant_messages, remaining)
            if block:
                sections.append(block)

        if not sections:
            return ""

        header = (
            "## Parent Session Context\n"
            "The following data was already processed by the main agent in "
            "earlier steps of this workflow. Use it as input for your task.\n"
        )
        return header + "\n".join(sections)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _summarize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return a compact summary of tool parameters (drop large values)."""
    summary: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str) and len(value) > 200:
            summary[key] = value[:200] + "…"
        else:
            summary[key] = value
    return summary


def _format_tool_results(
    heading: str,
    results: list[dict[str, Any]],
    max_chars: int,
) -> str:
    """Format a list of tool results into a Markdown section."""
    lines = [f"\n### {heading}\n"]
    char_count = len(lines[0])

    for entry in results:
        tool_name = entry["tool"]
        params = entry["parameters"]
        result = entry["result"]

        result_str = json.dumps(result, indent=2, default=str)

        # If a single result exceeds budget, truncate it
        per_entry_budget = max(max_chars // max(len(results), 1), 2000)
        if len(result_str) > per_entry_budget:
            result_str = result_str[:per_entry_budget] + "\n... [truncated]"

        block = (
            f"\n**{tool_name}** (params: {json.dumps(params, default=str)})\n"
            f"```json\n{result_str}\n```\n"
        )

        if char_count + len(block) > max_chars:
            lines.append(
                f"\n*({len(results) - len(lines) + 1} more result(s) omitted "
                f"due to size constraints)*\n"
            )
            break

        lines.append(block)
        char_count += len(block)

    return "".join(lines)


def _format_assistant_messages(
    messages: list[str],
    max_chars: int,
) -> str:
    """Format assistant messages into a Markdown section."""
    lines = ["\n### Assistant Analysis from Earlier Steps\n"]
    char_count = len(lines[0])

    # Use only the last few messages (most relevant)
    recent = messages[-3:]

    for i, msg in enumerate(recent, 1):
        # Truncate individual messages if needed
        budget = max_chars // max(len(recent), 1)
        if len(msg) > budget:
            msg = msg[:budget] + "\n... [truncated]"

        block = f"\n**Step {len(messages) - len(recent) + i} summary:**\n{msg}\n"
        if char_count + len(block) > max_chars:
            break
        lines.append(block)
        char_count += len(block)

    return "".join(lines)

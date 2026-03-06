"""Tests for the SSE formatting utility."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.utils.sse import format_sse


class TestFormatSSE:

    def test_returns_dict_with_event_and_data_keys(self) -> None:
        result = format_sse("message", {"content": "hello"})
        assert isinstance(result, dict)
        assert "event" in result
        assert "data" in result

    def test_event_field_matches_input(self) -> None:
        result = format_sse("tool_call_start", {"tool": "read_blob"})
        assert result["event"] == "tool_call_start"

    def test_data_is_json_string(self) -> None:
        result = format_sse("message", {"content": "hi"})
        parsed = json.loads(result["data"])
        assert parsed == {"content": "hi"}

    def test_empty_data(self) -> None:
        result = format_sse("reasoning", {})
        parsed = json.loads(result["data"])
        assert parsed == {}

    def test_nested_data(self) -> None:
        data = {"result": {"pages": [1, 2, 3], "total": 3}}
        result = format_sse("tool_call_complete", data)
        parsed = json.loads(result["data"])
        assert parsed["result"]["pages"] == [1, 2, 3]

    def test_data_with_non_serializable_defaults_to_str(self) -> None:
        """format_sse passes default=str to json.dumps, so datetimes
        should be serialized as strings rather than raising."""
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        data = {"timestamp": ts}
        result = format_sse("event", data)
        parsed = json.loads(result["data"])
        # str(datetime) produces a readable representation.
        assert "2025" in parsed["timestamp"]

    def test_various_event_types(self) -> None:
        """All event types should be passed through unchanged."""
        for event_type in (
            "reasoning",
            "tool_call_start",
            "tool_call_complete",
            "tool_call_error",
            "message",
            "approval_required",
            "session_complete",
            "session_error",
            "keepalive",
        ):
            result = format_sse(event_type, {"ok": True})
            assert result["event"] == event_type

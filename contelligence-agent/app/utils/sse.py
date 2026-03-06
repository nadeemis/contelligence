from __future__ import annotations
import json
from typing import Any

def format_sse(event_type: str, data: dict[str, Any]) -> dict:
    """Format an event for sse-starlette EventSourceResponse."""
    return {
        "event": event_type,
        "data": json.dumps(data, default=str),
    }

"""Helpers for the approval workflow — human-readable descriptions and
parameter summaries for pending operations.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Description templates per tool name
# ---------------------------------------------------------------------------

_DESCRIPTION_TEMPLATES: dict[str, Any] = {
    "write_blob": lambda p: (
        f"Write '{p.get('path', 'unknown file')}' "
        f"to container '{p.get('container', 'unknown')}'"
        + (" (overwrite)" if p.get("overwrite") else "")
    ),
    "upload_to_search": lambda p: (
        f"Upload {p.get('document_count', p.get('count', '?'))} document(s) "
        f"to search index '{p.get('index', 'unknown')}'"
    ),
    "upsert_cosmos": lambda p: (
        f"Upsert document to Cosmos DB container "
        f"'{p.get('container', 'unknown')}'"
    ),
    "delete_blob": lambda p: (
        f"Delete '{p.get('path', 'unknown file')}' "
        f"from container '{p.get('container', 'unknown')}'"
    ),
}


def describe_operation(tool_name: str, parameters: dict[str, Any]) -> str:
    """Return a human-readable description of the operation.

    Falls back to a generic message when no template is registered.
    """
    template = _DESCRIPTION_TEMPLATES.get(tool_name)
    if template is not None:
        try:
            return template(parameters)
        except Exception:
            pass
    # Generic fallback
    return f"Execute '{tool_name}' with provided parameters"


# ---------------------------------------------------------------------------
# Parameter summarisation
# ---------------------------------------------------------------------------

# Keys deemed important enough to surface in the approval request.
_SUMMARY_KEYS = (
    "container",
    "path",
    "index",
    "database",
    "count",
    "document_count",
    "overwrite",
    "query",
    "filters",
    "destination",
)


def summarize_params(parameters: dict[str, Any]) -> dict[str, Any]:
    """Extract key parameters suitable for display in an approval request.

    Large values (lists, long strings) are truncated to keep the SSE
    payload small and readable.
    """
    summary: dict[str, Any] = {}
    for key in _SUMMARY_KEYS:
        if key in parameters:
            val = parameters[key]
            if isinstance(val, str) and len(val) > 200:
                val = val[:200] + "…"
            elif isinstance(val, list):
                val = f"[{len(val)} items]"
            summary[key] = val
    return summary

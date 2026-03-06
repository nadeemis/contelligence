"""Approval trigger conditions — determines which tool calls require
user confirmation before execution.

The ``requires_approval`` function is the main entry point: it inspects
the tool name, parameters, and session options to decide whether the
agent should pause for confirmation.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# ---------------------------------------------------------------------------
# Trigger definitions
# ---------------------------------------------------------------------------

APPROVAL_TRIGGERS: dict[str, dict[str, Any]] = {
    # Atomic tool triggers
    "write_blob": {"condition": "overwrite", "risk": "medium"},
    "upload_to_search": {"condition": "always", "risk": "medium"},
    "upsert_cosmos": {"condition": "always", "risk": "medium"},
    "delete_blob": {"condition": "always", "risk": "high"},

    # MCP-based triggers (wildcard patterns)
    "mcp_delete_*": {"condition": "always", "risk": "high"},
    "mcp_create_schedule": {"condition": "always", "risk": "high"},
    "mcp_update_*": {"condition": "always", "risk": "medium"},
}

# If any single operation exceeds this many items, require approval.
BATCH_THRESHOLD: int = 50


def get_risk_level(tool_name: str) -> str:
    """Return the risk label for *tool_name* (``"medium"`` by default)."""
    for pattern, spec in APPROVAL_TRIGGERS.items():
        if fnmatch.fnmatch(tool_name, pattern):
            return spec.get("risk", "medium")
    return "medium"


def requires_approval(
    tool_name: str,
    parameters: dict[str, Any],
    session_options: dict[str, Any],
) -> bool:
    """Return ``True`` if *tool_name* with *parameters* needs user approval.

    Returns ``False`` immediately when the session has opted out of the
    approval flow (``require_approval=False``).
    """
    if not session_options.get("require_approval", True):
        return False

    # Check explicit triggers
    for pattern, spec in APPROVAL_TRIGGERS.items():
        if fnmatch.fnmatch(tool_name, pattern):
            condition = spec.get("condition", "always")
            if condition == "always":
                return True
            if condition == "overwrite" and parameters.get("overwrite"):
                return True

    # Check batch threshold
    batch_keys = ("count", "document_count", "num_documents", "batch_size")
    for key in batch_keys:
        val = parameters.get(key)
        if isinstance(val, int) and val > BATCH_THRESHOLD:
            logger.info(
                "Batch threshold (%d) exceeded for %s (param %s=%d)",
                BATCH_THRESHOLD,
                tool_name,
                key,
                val,
            )
            return True

    # Check list-type payload sizes
    for key in ("documents", "texts", "items"):
        val = parameters.get(key)
        if isinstance(val, list) and len(val) > BATCH_THRESHOLD:
            return True

    return False

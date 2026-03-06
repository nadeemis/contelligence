"""Unique instance identification for container replicas.

Used by the scheduler leader election (WS-2) and structured logging (WS-4)
to identify which replica handled a request.
"""

from __future__ import annotations

import os
import uuid

_instance_id: str | None = None


def get_instance_id() -> str:
    """Return a unique instance ID for this container replica.

    Prefers the ``CONTAINER_APP_REVISION`` environment variable
    (automatically set by Azure Container Apps in production).  Falls
    back to a random UUID prefix for local development.
    """
    global _instance_id
    if _instance_id is None:
        _instance_id = os.getenv(
            "CONTAINER_APP_REVISION",
            f"local-{uuid.uuid4().hex[:8]}",
        )
    return _instance_id

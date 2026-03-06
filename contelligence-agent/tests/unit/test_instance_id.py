"""Unit tests for Phase 4 — Instance ID helper."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.utils.instance import get_instance_id


class TestInstanceId:
    """Test the instance ID utility."""

    def test_returns_revision_when_set(self) -> None:
        with patch.dict(os.environ, {"CONTAINER_APP_REVISION": "rev-abc-123"}):
            # Clear cached value
            import importlib
            import app.utils.instance as mod
            mod._instance_id = None
            iid = mod.get_instance_id()
            assert iid == "rev-abc-123"

    def test_returns_uuid_fallback(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import app.utils.instance as mod
            mod._instance_id = None
            iid = mod.get_instance_id()
            assert len(iid) == 8  # short UUID

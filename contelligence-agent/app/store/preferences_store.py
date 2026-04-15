"""Preferences Store — CRUD for user preferences.

Persists ``UserPreferences`` documents in the ``user-preferences``
Cosmos DB container (or SQLite table via ``StorageManager``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.models.session_models import UserPreferences
from app.store.storage_manager import StorageManager
from app.utils.cosmos_helpers import to_cosmos_dict

logger = logging.getLogger(f"contelligence-agent.{__name__}")

CONTAINER_NAME = "user-preferences"


class PreferencesStore:
    """Data access layer for user preferences."""

    def __init__(self, storage_manager: StorageManager) -> None:
        self.container = storage_manager.get_container(CONTAINER_NAME)

    async def get_preferences(self, user_id: str) -> UserPreferences | None:
        """Read preferences for a user. Returns ``None`` if not found."""
        try:
            item = await self.container.read_item(item=user_id, partition_key=user_id)
            return UserPreferences.model_validate(item)
        except CosmosResourceNotFoundError:
            return None
        except Exception:
            # For local SQLite mode, the container API may not raise
            # CosmosResourceNotFoundError — handle generically.
            logger.debug("Preferences not found for user %s", user_id, exc_info=True)
            return None

    async def save_preferences(self, prefs: UserPreferences) -> None:
        """Upsert user preferences."""
        prefs.updated_at = datetime.now(timezone.utc)
        await self.container.upsert_item(to_cosmos_dict(prefs))

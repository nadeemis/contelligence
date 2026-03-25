"""Storage manager abstraction — common base class with Cosmos DB and SQLite implementations.

Provides a unified interface for application storage operations.  Tools use
the high-level ``query()`` / ``upsert()`` methods; stores use ``get_container()``
to obtain SDK-compatible container clients.

The underlying connectors (``CosmosConnectorAdapter``, ``SQLiteCosmosClient``)
remain unchanged and can still be used directly when needed.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class StorageManager(ABC):
    """Abstract base class for application storage operations.

    Subclasses must implement both the high-level helpers (``query``,
    ``upsert``) consumed by tools and the low-level ``get_container``
    accessor consumed by stores.
    """

    @abstractmethod
    async def ensure_initialized(self) -> None:
        """Initialise the storage backend (connect, create tables, etc.)."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources held by the storage backend."""

    @abstractmethod
    def get_container(self, name: str) -> Any:
        """Return a container client for *name*.

        The returned object exposes SDK-level async methods:
        ``upsert_item``, ``read_item``, ``query_items``, ``create_item``,
        ``replace_item``, ``delete_item``.
        """

    @abstractmethod
    async def query(
        self,
        container: str,
        query_str: str,
        *,
        parameters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SQL query against *container* and return result documents."""

    @abstractmethod
    async def upsert(
        self,
        container: str,
        document: dict[str, Any],
        *,
        partition_key: str | None = None,
    ) -> dict[str, Any]:
        """Upsert *document* into *container*."""


# ---------------------------------------------------------------------------
# Cosmos DB implementation
# ---------------------------------------------------------------------------

from app.connectors import CosmosConnectorAdapter

class CosmosStorageManager(StorageManager):
    """Storage manager backed by Azure Cosmos DB.

    Delegates to a ``CosmosConnectorAdapter`` internally.
    """

    def __init__(
        self,
        cosmos_connector: CosmosConnectorAdapter,
        database_name: str,
    ) -> None:
        self._connector = cosmos_connector
        self._database_name = database_name

    async def ensure_initialized(self) -> None:
        await self._connector.ensure_initialized()

    async def close(self) -> None:
        await self._connector.close()

    def get_container(self, name: str) -> Any:
        return (
            self._connector._client
            .get_database_client(self._database_name)
            .get_container_client(name)
        )

    async def query(
        self,
        container: str,
        query_str: str,
        *,
        parameters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._connector.query(
            container, query_str, parameters=parameters,
        )

    async def upsert(
        self,
        container: str,
        document: dict[str, Any],
        *,
        partition_key: str | None = None,
    ) -> dict[str, Any]:
        return await self._connector.upsert(
            container, document, partition_key=partition_key,
        )


# ---------------------------------------------------------------------------
# SQLite implementation (local development mode)
# ---------------------------------------------------------------------------

from app.connectors import SQLiteCosmosClient

class SQLiteStorageManager(StorageManager):
    """Storage manager backed by SQLite via ``SQLiteCosmosClient``.

    Used when ``STORAGE_MODE == "local"`` so the full application stack
    works without an Azure Cosmos DB instance.
    """

    def __init__(
        self,
        sqlite_client: SQLiteCosmosClient,
        database_name: str = "contelligence",
    ) -> None:
        self._client = sqlite_client
        self._database_name = database_name

    async def ensure_initialized(self) -> None:
        await self._client.ensure_initialized()

    async def close(self) -> None:
        await self._client.close()

    def get_container(self, name: str) -> Any:
        return (
            self._client
            .get_database_client(self._database_name)
            .get_container_client(name)
        )

    async def query(
        self,
        container: str,
        query_str: str,
        *,
        parameters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        container_client = self.get_container(container)
        items: list[dict[str, Any]] = []
        async for item in container_client.query_items(
            query=query_str, parameters=parameters,
        ):
            items.append(dict(item))
        logger.info(
            "query (local) container=%s returned %d items",
            container, len(items),
        )
        return items

    async def upsert(
        self,
        container: str,
        document: dict[str, Any],
        *,
        partition_key: str | None = None,
    ) -> dict[str, Any]:
        container_client = self.get_container(container)
        result = await container_client.upsert_item(body=document)
        logger.info(
            "upsert (local) container=%s id=%s",
            container, document.get("id", "<unknown>"),
        )
        return dict(result)

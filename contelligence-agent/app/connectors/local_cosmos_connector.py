"""Local Cosmos DB connector — wraps SQLiteCosmosClient to provide the same
API as CosmosConnectorAdapter.

Used when STORAGE_MODE == "local" so that tools like ``query_cosmos`` and
``upsert_cosmos`` work without an Azure Cosmos DB instance.
"""

from __future__ import annotations

import logging
from typing import Any

from app.connectors.sqlite_shim import SQLiteCosmosClient

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class LocalCosmosConnectorAdapter:
    """Drop-in replacement for CosmosConnectorAdapter backed by SQLite."""

    def __init__(self, sqlite_client: SQLiteCosmosClient, database_name: str = "contelligence") -> None:
        self._client = sqlite_client
        self._database_name = database_name

    def _resolve_database(self, database: str | None) -> str:
        return database or self._database_name

    async def ensure_initialized(self) -> None:
        await self._client.ensure_initialized()

    async def upsert(
        self,
        container: str,
        document: dict[str, Any],
        *,
        database: str | None = None,
        partition_key: str | None = None,
    ) -> dict[str, Any]:
        db_name = self._resolve_database(database)
        db_client = self._client.get_database_client(db_name)
        container_client = db_client.get_container_client(container)
        result = await container_client.upsert_item(body=document)
        logger.info(
            "upsert (local) database=%s container=%s id=%s",
            db_name, container, document.get("id", "<unknown>"),
        )
        return dict(result)

    async def query(
        self,
        container: str,
        query_str: str,
        *,
        parameters: list[dict[str, Any]] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        db_name = self._resolve_database(database)
        db_client = self._client.get_database_client(db_name)
        container_client = db_client.get_container_client(container)

        items: list[dict[str, Any]] = []
        query_iterable = container_client.query_items(
            query=query_str,
            parameters=parameters,
        )
        async for item in query_iterable:
            items.append(dict(item))

        logger.info(
            "query (local) database=%s container=%s returned %d items",
            db_name, container, len(items),
        )
        return items

    async def close(self) -> None:
        await self._client.close()

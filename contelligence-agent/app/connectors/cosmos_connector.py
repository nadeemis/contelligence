from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")

class CosmosConnectorAdapter:
    """Thin async wrapper around Azure Cosmos DB SDK client."""

    def __init__(
        self,
        endpoint: str,
        key: str = "",
        database_name: str = "",
    ) -> None:
        self._endpoint = endpoint
        self._key = key
        self._database_name = database_name
        self._client = None
        self._credential = None

    # Retry / timeout defaults for transient network errors (DNS blips,
    # connection resets, laptop-sleep reconnects, etc.).
    _RETRY_TOTAL: int = 5
    _RETRY_BACKOFF_MAX: int = 30          # seconds
    _RETRY_CONNECT: int = 3
    _RETRY_READ: int = 3
    _CONNECTION_TIMEOUT: int = 10         # seconds
    _REQUEST_TIMEOUT: int = 30            # seconds

    async def ensure_initialized(self) -> None:
        if self._client is not None:
            return
        from azure.cosmos.aio import CosmosClient

        client_kwargs: dict = dict(
            retry_total=self._RETRY_TOTAL,
            retry_backoff_max=self._RETRY_BACKOFF_MAX,
            retry_connect=self._RETRY_CONNECT,
            retry_read=self._RETRY_READ,
            connection_timeout=self._CONNECTION_TIMEOUT,
            timeout=self._REQUEST_TIMEOUT,
        )

        if self._key:
            self._client = CosmosClient(
                url=self._endpoint, credential=self._key,
                **client_kwargs,
            )
        else:
            from azure.identity.aio import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
            self._client = CosmosClient(
                url=self._endpoint, credential=self._credential,
                **client_kwargs,
            )

        logger.info(
            f"Cosmos client initialised (retry_total={self._RETRY_TOTAL}, retry_connect={self._RETRY_CONNECT}, "
            f"conn_timeout={self._CONNECTION_TIMEOUT}s, req_timeout={self._REQUEST_TIMEOUT}s)"
        )

    def _resolve_database(self, database: str | None) -> str:
        """Return the explicit database name or fall back to the default."""
        name = database or self._database_name
        if not name:
            raise ValueError(
                "No database name provided and no default was configured."
            )
        return name

    async def upsert(
        self,
        container: str,
        document: dict[str, Any],
        *,
        database: str | None = None,
        partition_key: str | None = None,
    ) -> dict[str, Any]:
        """Upsert a document into a Cosmos DB container.

        If *partition_key* is given it is passed as an ``enable_cross_partition_query``
        optimisation hint; Cosmos derives the actual partition from the document body.

        Returns the upserted item as a dict.
        """
        await self.ensure_initialized()
        db_name = self._resolve_database(database)
        db_client = self._client.get_database_client(db_name)
        container_client = db_client.get_container_client(container)
        result = await container_client.upsert_item(body=document)
        logger.info(
            "upsert database=%s container=%s id=%s",
            db_name,
            container,
            document.get("id", "<unknown>"),
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
        """Execute a SQL query against a Cosmos DB container.

        *parameters* should be a list of ``{"name": "@param", "value": ...}``
        dicts (Cosmos parameterised-query format).

        Returns a list of result documents.
        """
        await self.ensure_initialized()
        db_name = self._resolve_database(database)
        db_client = self._client.get_database_client(db_name)
        container_client = db_client.get_container_client(container)

        items: list[dict[str, Any]] = []
        query_iterable = container_client.query_items(
            query=query_str,
            parameters=parameters,
            enable_cross_partition_query=True,
        )
        async for item in query_iterable:
            items.append(dict(item))

        logger.info(
            "query database=%s container=%s returned %d items",
            db_name,
            container,
            len(items),
        )
        return items

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
        if self._credential is not None and hasattr(self._credential, "close"):
            await self._credential.close()
            self._credential = None

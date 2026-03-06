from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")

class SearchConnectorAdapter:
    """Thin async wrapper around Azure AI Search SDK clients."""

    def __init__(
        self,
        account_name: str,
        credential_type: str = "default_azure_credential",
        api_key: str = "",
        api_version: str = "2024-07-01",
    ) -> None:
        self._account_name = account_name
        self._credential_type = credential_type
        self._api_key = api_key
        self._api_version = api_version
        self._index_client = None
        self._credential: Any = None

    @property
    def _endpoint(self) -> str:
        return f"https://{self._account_name}.search.windows.net"

    async def ensure_initialized(self) -> None:
        if self._index_client is not None:
            return
        from azure.search.documents.indexes.aio import SearchIndexClient

        if self._api_key:
            from azure.core.credentials import AzureKeyCredential

            self._credential = AzureKeyCredential(self._api_key)
        else:
            from azure.identity.aio import DefaultAzureCredential

            self._credential = DefaultAzureCredential()

        self._index_client = SearchIndexClient(
            endpoint=self._endpoint,
            credential=self._credential,
            api_version=self._api_version,
        )

    def _get_search_client(self, index: str) -> Any:
        """Create a per-index SearchClient (since index varies per call)."""
        from azure.search.documents.aio import SearchClient

        return SearchClient(
            endpoint=self._endpoint,
            index_name=index,
            credential=self._credential,
            api_version=self._api_version,
        )

    async def upload_documents(
        self,
        index: str,
        documents: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Upload or merge documents into a search index.

        Returns a dict with ``succeeded`` and ``failed`` counts.
        """
        await self.ensure_initialized()
        search_client = self._get_search_client(index)
        try:
            result = await search_client.upload_documents(documents=documents)
            succeeded = sum(1 for r in result if r.succeeded)
            failed = len(result) - succeeded
            logger.info(
                "upload_documents index=%s succeeded=%d failed=%d",
                index,
                succeeded,
                failed,
            )
            return {"succeeded": succeeded, "failed": failed}
        finally:
            await search_client.close()

    async def search(
        self,
        index: str,
        query: str,
        *,
        top: int = 10,
        filters: str | None = None,
        select: list[str] | None = None,
        vector: list[float] | None = None,
        vector_fields: str = "contentVector",
        query_type: str = "keyword",
        semantic_configuration: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a search query against an index.

        Supports keyword, vector, hybrid (keyword + vector), and semantic
        query types via ``query_type``.

        Args:
            index: Target search index name.
            query: Full-text query string (ignored for pure vector search).
            top: Maximum results to return.
            filters: OData filter expression.
            select: Fields to return; all if ``None``.
            vector: Embedding vector for vector/hybrid queries.
            vector_fields: Comma-separated index field names storing vectors.
            query_type: One of ``keyword``, ``vector``, ``hybrid``, or
                ``semantic``.
            semantic_configuration: Required when ``query_type`` is
                ``semantic``.

        Returns a list of result dicts with ``@search.score`` and
        optionally ``@search.reranker_score``.
        """
        await self.ensure_initialized()
        search_client = self._get_search_client(index)

        try:
            search_kwargs: dict[str, Any] = {
                "top": top,
                "filter": filters,
                "select": select,
            }

            # --- Build query-type-specific kwargs ---
            if query_type == "vector":
                from azure.search.documents.models import VectorizedQuery

                search_kwargs["search_text"] = None
                search_kwargs["vector_queries"] = [
                    VectorizedQuery(
                        vector=vector,
                        k_nearest_neighbors=top,
                        fields=vector_fields,
                    )
                ]
            elif query_type == "hybrid":
                from azure.search.documents.models import VectorizedQuery

                search_kwargs["search_text"] = query
                search_kwargs["vector_queries"] = [
                    VectorizedQuery(
                        vector=vector,
                        k_nearest_neighbors=top,
                        fields=vector_fields,
                    )
                ]
            elif query_type == "semantic":
                search_kwargs["search_text"] = query
                search_kwargs["query_type"] = "semantic"
                if semantic_configuration:
                    search_kwargs["semantic_configuration_name"] = semantic_configuration
                # Optionally include vector for semantic + vector
                if vector is not None:
                    from azure.search.documents.models import VectorizedQuery

                    search_kwargs["vector_queries"] = [
                        VectorizedQuery(
                            vector=vector,
                            k_nearest_neighbors=top,
                            fields=vector_fields,
                        )
                    ]
            else:
                # Default keyword search
                search_kwargs["search_text"] = query

            results: list[dict[str, Any]] = []
            async for item in search_client.search(**search_kwargs):
                doc = dict(item)
                doc["@search.score"] = item.get("@search.score", 0.0)
                reranker = item.get("@search.reranker_score")
                if reranker is not None:
                    doc["@search.reranker_score"] = reranker
                results.append(doc)

            return results
        finally:
            await search_client.close()

    async def close(self) -> None:
        if self._index_client:
            await self._index_client.close()
            self._index_client = None
        # If credential is closeable (DefaultAzureCredential), close it too
        if hasattr(self._credential, "close"):
            await self._credential.close()
        self._credential = None

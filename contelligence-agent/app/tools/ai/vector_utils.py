"""Vector search helper utilities.

Convenience functions for common embedding + search patterns used by the
agent and tools.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_vector_query(
    vector: list[float],
    *,
    k: int = 10,
    fields: str = "contentVector",
) -> dict[str, Any]:
    """Return kwargs suitable for passing to ``SearchClient.search``.

    This builds the ``VectorizedQuery`` object used by the Azure AI Search
    SDK.  Callers can merge the returned dict into their search call kwargs.

    >>> vq = build_vector_query([0.1, 0.2, 0.3], k=5)
    >>> vq["vector_queries"][0].fields
    'contentVector'
    """
    from azure.search.documents.models import VectorizedQuery

    return {
        "vector_queries": [
            VectorizedQuery(
                vector=vector,
                k=k,
                fields=fields,
            )
        ]
    }


async def semantic_search(
    *,
    search_connector: Any,
    openai_connector: Any,
    index: str,
    query_text: str,
    top: int = 10,
    model: str = "text-embedding-3-large",
    dimensions: int = 1536,
    vector_fields: str = "contentVector",
    filters: str | None = None,
    select: list[str] | None = None,
    semantic_configuration: str | None = None,
) -> list[dict[str, Any]]:
    """End-to-end semantic search: embed query → hybrid (or semantic) search.

    If ``semantic_configuration`` is provided, uses semantic reranking.
    Otherwise falls back to hybrid (keyword + vector).

    This is a convenience wrapper that combines the embedding generation and
    search steps into a single call — useful for service-level code that
    doesn't go through the tool interface.
    """
    # 1. Generate embedding for the query text
    embed_result = await openai_connector.generate_embeddings(
        texts=[query_text],
        model=model,
        dimensions=dimensions,
    )
    vector = embed_result["embeddings"][0]

    # 2. Determine query type
    query_type = "semantic" if semantic_configuration else "hybrid"

    # 3. Execute search
    results = await search_connector.search(
        index=index,
        query=query_text,
        top=top,
        filters=filters,
        select=select,
        vector=vector,
        vector_fields=vector_fields,
        query_type=query_type,
        semantic_configuration=semantic_configuration,
    )

    logger.info(
        "semantic_search index=%s type=%s returned=%d",
        index,
        query_type,
        len(results),
    )
    return results

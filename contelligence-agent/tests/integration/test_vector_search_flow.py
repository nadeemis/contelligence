"""Integration tests for the vector search pipeline.

Tests the flow: generate embeddings → upload to search → vector/hybrid/semantic query.

Marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.tools.ai.generate_embeddings import GenerateEmbeddingsParams, generate_embeddings
from app.tools.storage.query_search_index import QuerySearchIndexParams, query_search_index
from app.tools.ai.vector_utils import build_vector_query, semantic_search


pytestmark = pytest.mark.integration


def _make_context(
    openai_mock: AsyncMock,
    search_mock: AsyncMock,
) -> dict[str, Any]:
    return {"openai": openai_mock, "search": search_mock}


class TestVectorSearchPipeline:

    @pytest.mark.asyncio
    async def test_embed_then_vector_search(self) -> None:
        """Full pipeline: embed texts, then perform vector search."""
        openai_mock = AsyncMock()
        openai_mock.generate_embeddings.return_value = {
            "model": "text-embedding-3-large",
            "count": 1,
            "embeddings": [[0.1, 0.2, 0.3] * 512],
            "dimensions": 1536,
            "total_tokens": 10,
        }

        search_mock = AsyncMock()
        search_mock.search.return_value = [
            {"id": "doc-1", "title": "Architecture", "@search.score": 0.95},
            {"id": "doc-2", "title": "Deployment", "@search.score": 0.87},
        ]

        ctx = _make_context(openai_mock, search_mock)

        # Step 1: Generate embedding
        embed_params = GenerateEmbeddingsParams(texts=["architecture overview"])
        embed_result = await generate_embeddings.handler(embed_params, ctx)

        assert embed_result["count"] == 1
        vector = embed_result["embeddings"][0]

        # Step 2: Vector search with the generated embedding
        search_params = QuerySearchIndexParams(
            index="documents",
            query_type="vector",
            vector=vector,
        )
        search_result = await query_search_index.handler(search_params, ctx)

        assert search_result["query_type"] == "vector"
        assert search_result["count"] == 2
        assert search_result["results"][0]["@search.score"] == 0.95

    @pytest.mark.asyncio
    async def test_embed_then_hybrid_search(self) -> None:
        """Full pipeline: embed query, then hybrid (keyword + vector) search."""
        openai_mock = AsyncMock()
        openai_mock.generate_embeddings.return_value = {
            "embeddings": [[0.2, 0.3, 0.4] * 512],
            "total_tokens": 8,
        }

        search_mock = AsyncMock()
        search_mock.search.return_value = [
            {"id": "doc-3", "title": "Hybrid Hit", "@search.score": 0.93},
        ]

        ctx = _make_context(openai_mock, search_mock)

        # Step 1: Embed
        embed_params = GenerateEmbeddingsParams(texts=["deploy container apps"])
        embed_result = await generate_embeddings.handler(embed_params, ctx)
        vector = embed_result["embeddings"][0]

        # Step 2: Hybrid search
        search_params = QuerySearchIndexParams(
            index="documents",
            query="deploy container apps",
            query_type="hybrid",
            vector=vector,
        )
        search_result = await query_search_index.handler(search_params, ctx)

        assert search_result["query_type"] == "hybrid"
        assert search_result["count"] == 1

    @pytest.mark.asyncio
    async def test_embed_then_semantic_search(self) -> None:
        """Full pipeline: semantic search with reranker scores."""
        openai_mock = AsyncMock()
        openai_mock.generate_embeddings.return_value = {
            "embeddings": [[0.5, 0.6, 0.7] * 512],
            "total_tokens": 12,
        }

        search_mock = AsyncMock()
        search_mock.search.return_value = [
            {
                "id": "doc-4",
                "title": "Semantic Result",
                "@search.score": 0.88,
                "@search.reranker_score": 3.7,
            },
        ]

        ctx = _make_context(openai_mock, search_mock)

        # Embed
        embed_params = GenerateEmbeddingsParams(texts=["event-driven architecture"])
        embed_result = await generate_embeddings.handler(embed_params, ctx)

        # Semantic search
        search_params = QuerySearchIndexParams(
            index="documents",
            query="event-driven architecture",
            query_type="semantic",
            vector=embed_result["embeddings"][0],
            semantic_configuration="default-semantic-cfg",
        )
        search_result = await query_search_index.handler(search_params, ctx)

        assert search_result["query_type"] == "semantic"
        assert search_result["results"][0].get("@search.reranker_score") == 3.7

    @pytest.mark.asyncio
    async def test_batch_embed_pipeline(self) -> None:
        """Embed multiple chunks then search against them."""
        openai_mock = AsyncMock()
        openai_mock.generate_embeddings.return_value = {
            "embeddings": [[0.1] * 1536 for _ in range(5)],
            "total_tokens": 50,
        }

        search_mock = AsyncMock()
        search_mock.search.return_value = [
            {"id": f"chunk-{i}", "@search.score": 0.9 - i * 0.05}
            for i in range(5)
        ]

        ctx = _make_context(openai_mock, search_mock)

        # Batch embed 5 chunks
        embed_params = GenerateEmbeddingsParams(
            texts=[f"chunk {i} content" for i in range(5)]
        )
        embed_result = await generate_embeddings.handler(embed_params, ctx)
        assert embed_result["count"] == 5

        # Search with first chunk's vector
        search_params = QuerySearchIndexParams(
            index="documents",
            query_type="vector",
            vector=embed_result["embeddings"][0],
            top=5,
        )
        search_result = await query_search_index.handler(search_params, ctx)
        assert search_result["count"] == 5


class TestSemanticSearchHelper:

    @pytest.mark.asyncio
    async def test_semantic_search_helper_hybrid(self) -> None:
        """semantic_search helper performs embed + search in one call."""
        openai_mock = AsyncMock()
        openai_mock.generate_embeddings.return_value = {
            "embeddings": [[0.1, 0.2, 0.3]],
            "total_tokens": 5,
        }

        search_mock = AsyncMock()
        search_mock.search.return_value = [
            {"id": "1", "title": "Result", "@search.score": 0.9},
        ]

        results = await semantic_search(
            search_connector=search_mock,
            openai_connector=openai_mock,
            index="docs",
            query_text="test query",
            top=10,
        )

        assert len(results) == 1
        # Verify hybrid mode was used (no semantic_configuration)
        call_kwargs = search_mock.search.call_args.kwargs
        assert call_kwargs["query_type"] == "hybrid"

    @pytest.mark.asyncio
    async def test_semantic_search_helper_semantic(self) -> None:
        """semantic_search with semantic_configuration uses semantic type."""
        openai_mock = AsyncMock()
        openai_mock.generate_embeddings.return_value = {
            "embeddings": [[0.1, 0.2]],
            "total_tokens": 3,
        }

        search_mock = AsyncMock()
        search_mock.search.return_value = []

        await semantic_search(
            search_connector=search_mock,
            openai_connector=openai_mock,
            index="docs",
            query_text="query",
            semantic_configuration="my-cfg",
        )

        call_kwargs = search_mock.search.call_args.kwargs
        assert call_kwargs["query_type"] == "semantic"
        assert call_kwargs["semantic_configuration"] == "my-cfg"

    @pytest.mark.asyncio
    async def test_semantic_search_custom_model_and_dims(self) -> None:
        openai_mock = AsyncMock()
        openai_mock.generate_embeddings.return_value = {
            "embeddings": [[0.1] * 256],
            "total_tokens": 3,
        }

        search_mock = AsyncMock()
        search_mock.search.return_value = []

        await semantic_search(
            search_connector=search_mock,
            openai_connector=openai_mock,
            index="docs",
            query_text="query",
            model="text-embedding-3-small",
            dimensions=256,
        )

        embed_call = openai_mock.generate_embeddings.call_args
        assert embed_call.kwargs["model"] == "text-embedding-3-small"
        assert embed_call.kwargs["dimensions"] == 256

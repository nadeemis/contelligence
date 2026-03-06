"""Tests for vector search — query_search_index tool and vector_utils.

Covers:
- QuerySearchIndexParams validation (keyword, vector, hybrid, semantic)
- Parameter combination validation (model_validator)
- build_vector_query utility
- semantic_search helper
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.tools.storage.query_search_index import (
    QuerySearchIndexParams,
    query_search_index,
)
from app.tools.ai.vector_utils import build_vector_query, semantic_search


# ===========================================================================
# QuerySearchIndexParams validation
# ===========================================================================

class TestQuerySearchIndexParamsValidation:

    def test_keyword_valid(self) -> None:
        params = QuerySearchIndexParams(
            index="docs", query="azure functions", query_type="keyword"
        )
        assert params.query_type == "keyword"

    def test_keyword_requires_query(self) -> None:
        with pytest.raises(ValidationError, match="query.*required"):
            QuerySearchIndexParams(
                index="docs", query="", query_type="keyword"
            )

    def test_vector_valid(self) -> None:
        params = QuerySearchIndexParams(
            index="docs",
            query_type="vector",
            vector=[0.1, 0.2, 0.3],
        )
        assert params.query_type == "vector"
        assert params.vector is not None

    def test_vector_requires_vector(self) -> None:
        with pytest.raises(ValidationError, match="vector.*required"):
            QuerySearchIndexParams(
                index="docs", query_type="vector"
            )

    def test_hybrid_valid(self) -> None:
        params = QuerySearchIndexParams(
            index="docs",
            query="search term",
            query_type="hybrid",
            vector=[0.1, 0.2, 0.3],
        )
        assert params.query_type == "hybrid"

    def test_hybrid_requires_both_query_and_vector(self) -> None:
        # Missing vector
        with pytest.raises(ValidationError, match="vector.*required"):
            QuerySearchIndexParams(
                index="docs", query="term", query_type="hybrid"
            )
        # Missing query
        with pytest.raises(ValidationError, match="query.*required"):
            QuerySearchIndexParams(
                index="docs",
                query="",
                query_type="hybrid",
                vector=[0.1],
            )

    def test_semantic_valid(self) -> None:
        params = QuerySearchIndexParams(
            index="docs",
            query="search term",
            query_type="semantic",
            semantic_configuration="my-semantic-config",
        )
        assert params.query_type == "semantic"

    def test_semantic_requires_query(self) -> None:
        with pytest.raises(ValidationError, match="query.*required"):
            QuerySearchIndexParams(
                index="docs",
                query="",
                query_type="semantic",
                semantic_configuration="cfg",
            )

    def test_semantic_requires_configuration(self) -> None:
        with pytest.raises(ValidationError, match="semantic_configuration.*required"):
            QuerySearchIndexParams(
                index="docs",
                query="term",
                query_type="semantic",
            )

    def test_default_query_type_keyword(self) -> None:
        params = QuerySearchIndexParams(index="docs", query="hello")
        assert params.query_type == "keyword"

    def test_default_vector_fields(self) -> None:
        params = QuerySearchIndexParams(index="docs", query="hello")
        assert params.vector_fields == "contentVector"


# ===========================================================================
# query_search_index tool handler
# ===========================================================================

class TestQuerySearchIndexTool:

    @pytest.mark.asyncio
    async def test_keyword_search(self, tool_context: dict[str, Any]) -> None:
        params = QuerySearchIndexParams(
            index="documents", query="architecture", query_type="keyword"
        )
        result = await query_search_index.handler(params, tool_context)

        assert result["query_type"] == "keyword"
        assert result["count"] == 2
        tool_context["search"].search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_vector_search(self, tool_context: dict[str, Any]) -> None:
        params = QuerySearchIndexParams(
            index="documents",
            query_type="vector",
            vector=[0.1, 0.2, 0.3],
        )
        result = await query_search_index.handler(params, tool_context)

        assert result["query_type"] == "vector"
        call_kwargs = tool_context["search"].search.call_args
        assert call_kwargs.kwargs.get("vector") == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_hybrid_search(self, tool_context: dict[str, Any]) -> None:
        params = QuerySearchIndexParams(
            index="documents",
            query="deploy",
            query_type="hybrid",
            vector=[0.4, 0.5, 0.6],
        )
        result = await query_search_index.handler(params, tool_context)

        assert result["query_type"] == "hybrid"
        call_kwargs = tool_context["search"].search.call_args
        assert call_kwargs.kwargs.get("query") == "deploy"
        assert call_kwargs.kwargs.get("vector") == [0.4, 0.5, 0.6]

    @pytest.mark.asyncio
    async def test_semantic_search_tool(self, tool_context: dict[str, Any]) -> None:
        tool_context["search"].search.return_value = [
            {
                "id": "1",
                "title": "Result",
                "@search.score": 0.9,
                "@search.reranker_score": 3.5,
            },
        ]
        params = QuerySearchIndexParams(
            index="documents",
            query="explain microservices",
            query_type="semantic",
            semantic_configuration="my-config",
        )
        result = await query_search_index.handler(params, tool_context)

        assert result["query_type"] == "semantic"
        call_kwargs = tool_context["search"].search.call_args
        assert call_kwargs.kwargs.get("semantic_configuration") == "my-config"

    @pytest.mark.asyncio
    async def test_results_structure(self, tool_context: dict[str, Any]) -> None:
        params = QuerySearchIndexParams(
            index="docs", query="test", query_type="keyword"
        )
        result = await query_search_index.handler(params, tool_context)

        assert "index" in result
        assert "query_type" in result
        assert "count" in result
        assert "results" in result
        assert isinstance(result["results"], list)


# ===========================================================================
# build_vector_query
# ===========================================================================

class TestBuildVectorQuery:

    def test_returns_vector_queries_key(self) -> None:
        vq = build_vector_query([0.1, 0.2, 0.3])
        assert "vector_queries" in vq
        assert len(vq["vector_queries"]) == 1

    def test_default_k_and_fields(self) -> None:
        vq = build_vector_query([0.1, 0.2])
        query = vq["vector_queries"][0]
        assert query.k == 10
        assert query.fields == "contentVector"

    def test_custom_k_and_fields(self) -> None:
        vq = build_vector_query([0.1], k=5, fields="embeddingField")
        query = vq["vector_queries"][0]
        assert query.k == 5
        assert query.fields == "embeddingField"

    def test_vector_passed_through(self) -> None:
        vec = [0.1, 0.2, 0.3, 0.4]
        vq = build_vector_query(vec)
        assert vq["vector_queries"][0].vector == vec


# ===========================================================================
# semantic_search helper
# ===========================================================================

class TestSemanticSearchHelper:

    @pytest.mark.asyncio
    async def test_end_to_end(
        self,
        mock_search_connector: AsyncMock,
        mock_openai_connector: AsyncMock,
    ) -> None:
        """semantic_search embeds then searches."""
        mock_openai_connector.generate_embeddings.return_value = {
            "embeddings": [[0.1, 0.2, 0.3]],
            "total_tokens": 5,
        }
        mock_search_connector.search.return_value = [
            {"id": "1", "title": "Hit", "@search.score": 0.9},
        ]

        results = await semantic_search(
            search_connector=mock_search_connector,
            openai_connector=mock_openai_connector,
            index="docs",
            query_text="test query",
            top=5,
        )

        assert len(results) == 1
        mock_openai_connector.generate_embeddings.assert_awaited_once()
        mock_search_connector.search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_semantic_config(
        self,
        mock_search_connector: AsyncMock,
        mock_openai_connector: AsyncMock,
    ) -> None:
        mock_openai_connector.generate_embeddings.return_value = {
            "embeddings": [[0.1, 0.2]],
            "total_tokens": 3,
        }
        mock_search_connector.search.return_value = []

        await semantic_search(
            search_connector=mock_search_connector,
            openai_connector=mock_openai_connector,
            index="docs",
            query_text="query",
            semantic_configuration="my-cfg",
        )

        call_kwargs = mock_search_connector.search.call_args.kwargs
        assert call_kwargs["query_type"] == "semantic"
        assert call_kwargs["semantic_configuration"] == "my-cfg"

    @pytest.mark.asyncio
    async def test_without_semantic_config_uses_hybrid(
        self,
        mock_search_connector: AsyncMock,
        mock_openai_connector: AsyncMock,
    ) -> None:
        mock_openai_connector.generate_embeddings.return_value = {
            "embeddings": [[0.1, 0.2]],
            "total_tokens": 3,
        }
        mock_search_connector.search.return_value = []

        await semantic_search(
            search_connector=mock_search_connector,
            openai_connector=mock_openai_connector,
            index="docs",
            query_text="query",
        )

        call_kwargs = mock_search_connector.search.call_args.kwargs
        assert call_kwargs["query_type"] == "hybrid"

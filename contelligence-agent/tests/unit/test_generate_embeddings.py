"""Tests for the generate_embeddings tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.tools.ai.generate_embeddings import GenerateEmbeddingsParams, generate_embeddings


class TestGenerateEmbeddings:

    @pytest.mark.asyncio
    async def test_basic_embedding(self, tool_context: dict[str, Any]) -> None:
        params = GenerateEmbeddingsParams(texts=["hello world", "test text"])
        result = await generate_embeddings.handler(params, tool_context)

        assert result["model"] == "text-embedding-3-large"
        assert result["count"] == 2
        assert len(result["embeddings"]) == 2
        assert result["dimensions"] == 3

    @pytest.mark.asyncio
    async def test_custom_model(self, tool_context: dict[str, Any]) -> None:
        params = GenerateEmbeddingsParams(
            texts=["sample"],
            model="text-embedding-3-large",
        )
        await generate_embeddings.handler(params, tool_context)

        tool_context["openai"].generate_embeddings.assert_awaited_once_with(
            texts=["sample"],
            model="text-embedding-3-large",
            dimensions=1536,
        )

    @pytest.mark.asyncio
    async def test_single_text(self, tool_context: dict[str, Any]) -> None:
        tool_context["openai"].generate_embeddings.return_value = {
            "model": "text-embedding-3-large",
            "count": 1,
            "embeddings": [[0.1, 0.2]],
            "dimensions": 2,
            "total_tokens": 5,
        }

        params = GenerateEmbeddingsParams(texts=["sole input"])
        result = await generate_embeddings.handler(params, tool_context)

        assert result["count"] == 1
        assert result["dimensions"] == 2

    @pytest.mark.asyncio
    async def test_empty_embeddings(self, tool_context: dict[str, Any]) -> None:
        """Edge case: empty texts input returns early with zero embeddings."""
        params = GenerateEmbeddingsParams(texts=[])
        result = await generate_embeddings.handler(params, tool_context)

        assert result["count"] == 0
        assert result["dimensions"] == 1536  # default dimensions preserved
        assert result["total_tokens"] == 0

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, tool_context: dict[str, Any]) -> None:
        """A RateLimitError from the openai SDK should be caught and returned."""
        import openai

        rate_error = openai.RateLimitError(
            message="Rate limit exceeded",
            response=AsyncMock(status_code=429, headers={}),
            body=None,
        )
        tool_context["openai"].generate_embeddings.side_effect = rate_error

        params = GenerateEmbeddingsParams(texts=["test"])
        result = await generate_embeddings.handler(params, tool_context)

        assert "error" in result
        assert "rate limit" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_default_model_is_large(self) -> None:
        """The default model should be text-embedding-3-large."""
        params = GenerateEmbeddingsParams(texts=["x"])
        assert params.model == "text-embedding-3-large"

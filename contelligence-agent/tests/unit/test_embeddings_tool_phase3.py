"""Phase 3 tests for the generate_embeddings tool.

Covers:
- Default model changed to text-embedding-3-large
- Configurable dimensions parameter
- Batch chunking for >100 texts
- Token usage tracking
- Empty input handling
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.tools.ai.generate_embeddings import (
    GenerateEmbeddingsParams,
    _MAX_BATCH_SIZE,
    generate_embeddings,
)


def _make_context(connector_mock: AsyncMock) -> dict[str, Any]:
    """Build a minimal tool context with the given OpenAI connector mock."""
    return {"openai": connector_mock}


def _make_embed_response(
    count: int,
    dims: int = 1536,
    model: str = "text-embedding-3-large",
    tokens: int = 10,
) -> dict[str, Any]:
    """Build a Phase 3 style embedding response."""
    return {
        "model": model,
        "count": count,
        "embeddings": [[0.1] * dims for _ in range(count)],
        "dimensions": dims,
        "total_tokens": tokens,
    }


class TestGenerateEmbeddingsPhase3:

    @pytest.mark.asyncio
    async def test_default_model_is_large(self) -> None:
        """Default model should be text-embedding-3-large."""
        params = GenerateEmbeddingsParams(texts=["hello"])
        assert params.model == "text-embedding-3-large"

    @pytest.mark.asyncio
    async def test_custom_dimensions(self) -> None:
        mock = AsyncMock()
        mock.generate_embeddings.return_value = _make_embed_response(1, dims=256)

        params = GenerateEmbeddingsParams(texts=["hello"], dimensions=256)
        result = await generate_embeddings.handler(params, _make_context(mock))

        mock.generate_embeddings.assert_awaited_once_with(
            texts=["hello"],
            model="text-embedding-3-large",
            dimensions=256,
        )
        assert result["dimensions"] == 256

    @pytest.mark.asyncio
    async def test_default_dimensions_1536(self) -> None:
        params = GenerateEmbeddingsParams(texts=["test"])
        assert params.dimensions == 1536

    @pytest.mark.asyncio
    async def test_batch_chunking_over_max_batch(self) -> None:
        """Input >_MAX_BATCH_SIZE should be split into multiple calls."""
        total = _MAX_BATCH_SIZE + 20  # 120 texts
        mock = AsyncMock()

        # First call returns 100, second returns 20
        mock.generate_embeddings.side_effect = [
            _make_embed_response(_MAX_BATCH_SIZE, tokens=100),
            _make_embed_response(20, tokens=20),
        ]

        params = GenerateEmbeddingsParams(texts=[f"text-{i}" for i in range(total)])
        result = await generate_embeddings.handler(params, _make_context(mock))

        # Should have called generate_embeddings twice
        assert mock.generate_embeddings.await_count == 2
        assert result["count"] == total
        assert result["total_tokens"] == 120

    @pytest.mark.asyncio
    async def test_exact_batch_boundary(self) -> None:
        """Exactly _MAX_BATCH_SIZE texts should be a single call."""
        mock = AsyncMock()
        mock.generate_embeddings.return_value = _make_embed_response(
            _MAX_BATCH_SIZE, tokens=50
        )

        params = GenerateEmbeddingsParams(
            texts=[f"t-{i}" for i in range(_MAX_BATCH_SIZE)]
        )
        result = await generate_embeddings.handler(params, _make_context(mock))

        assert mock.generate_embeddings.await_count == 1
        assert result["count"] == _MAX_BATCH_SIZE

    @pytest.mark.asyncio
    async def test_large_batch_three_chunks(self) -> None:
        """250 texts should be chunked into 3 calls (100+100+50)."""
        mock = AsyncMock()
        mock.generate_embeddings.side_effect = [
            _make_embed_response(100, tokens=100),
            _make_embed_response(100, tokens=100),
            _make_embed_response(50, tokens=50),
        ]

        params = GenerateEmbeddingsParams(texts=[f"t-{i}" for i in range(250)])
        result = await generate_embeddings.handler(params, _make_context(mock))

        assert mock.generate_embeddings.await_count == 3
        assert result["count"] == 250
        assert result["total_tokens"] == 250

    @pytest.mark.asyncio
    async def test_empty_input(self) -> None:
        """Empty texts list returns zero count and zero tokens."""
        mock = AsyncMock()
        params = GenerateEmbeddingsParams(texts=[])
        result = await generate_embeddings.handler(params, _make_context(mock))

        assert result["count"] == 0
        assert result["total_tokens"] == 0
        assert result["embeddings"] == []
        mock.generate_embeddings.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_token_tracking(self) -> None:
        mock = AsyncMock()
        mock.generate_embeddings.return_value = _make_embed_response(2, tokens=42)

        params = GenerateEmbeddingsParams(texts=["a", "b"])
        result = await generate_embeddings.handler(params, _make_context(mock))

        assert result["total_tokens"] == 42

    @pytest.mark.asyncio
    async def test_rate_limit_error(self) -> None:
        """RateLimitError should be caught and returned as error dict."""
        import openai

        mock = AsyncMock()
        mock.generate_embeddings.side_effect = openai.RateLimitError(
            message="Rate limit exceeded",
            response=AsyncMock(status_code=429, headers={}),
            body=None,
        )

        params = GenerateEmbeddingsParams(texts=["hello"])
        result = await generate_embeddings.handler(params, _make_context(mock))

        assert "error" in result
        assert "rate limit" in result["error"].lower()

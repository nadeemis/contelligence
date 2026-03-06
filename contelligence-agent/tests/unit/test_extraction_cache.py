"""Unit tests for Phase 4 — Extraction Cache."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.caching.extraction_cache import ExtractionCache


@pytest.fixture
def mock_container() -> AsyncMock:
    """Create a mock Cosmos container."""
    container = AsyncMock()
    return container


class TestExtractionCache:
    """Test the extraction cache."""

    def test_cache_key_deterministic(self) -> None:
        k1 = ExtractionCache._cache_key("https://blob/a.pdf", "etag1")
        k2 = ExtractionCache._cache_key("https://blob/a.pdf", "etag1")
        assert k1 == k2

    def test_cache_key_differs_on_etag(self) -> None:
        k1 = ExtractionCache._cache_key("https://blob/a.pdf", "etag1")
        k2 = ExtractionCache._cache_key("https://blob/a.pdf", "etag2")
        assert k1 != k2

    @pytest.mark.asyncio
    async def test_get_hit(self, mock_container: AsyncMock) -> None:
        mock_container.read_item.return_value = {"result": {"key": "value"}}
        cache = ExtractionCache(mock_container, ttl_days=7)
        result = await cache.get("url", "etag")
        assert result == {"key": "value"}
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0

    @pytest.mark.asyncio
    async def test_get_miss(self, mock_container: AsyncMock) -> None:
        mock_container.read_item.side_effect = Exception("Not found")
        cache = ExtractionCache(mock_container, ttl_days=7)
        result = await cache.get("url", "etag")
        assert result is None
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_put(self, mock_container: AsyncMock) -> None:
        cache = ExtractionCache(mock_container, ttl_days=3)
        await cache.put("url", "etag", {"data": "test"})
        mock_container.upsert_item.assert_called_once()
        doc = mock_container.upsert_item.call_args[0][0]
        assert doc["ttl"] == 3 * 86400
        assert doc["result"] == {"data": "test"}

    @pytest.mark.asyncio
    async def test_invalidate_success(self, mock_container: AsyncMock) -> None:
        cache = ExtractionCache(mock_container)
        result = await cache.invalidate("url", "etag")
        assert result is True

    @pytest.mark.asyncio
    async def test_invalidate_not_found(self, mock_container: AsyncMock) -> None:
        mock_container.delete_item.side_effect = Exception("Not found")
        cache = ExtractionCache(mock_container)
        result = await cache.invalidate("url", "etag")
        assert result is False

    def test_get_stats(self, mock_container: AsyncMock) -> None:
        cache = ExtractionCache(mock_container, ttl_days=7)
        stats = cache.get_stats()
        assert stats["enabled"] is True
        assert stats["hit_ratio"] == 0.0

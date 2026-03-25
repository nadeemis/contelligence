"""Extraction cache — avoids re-running Document Intelligence on blobs
that have already been processed.

Uses a Cosmos DB container (``extraction-cache``) keyed by a composite
of ``blob_url + etag`` so stale entries are automatically invalidated
when the source blob changes.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger(f"contelligence-agent.{__name__}")

class ExtractionCache:
    """Cosmos-backed cache for extraction results.

    Each cache entry is stored as:

    .. code-block:: json

        {
            "id": "<sha256(blob_url|etag)>",
            "pk": "<sha256(blob_url|etag)>",
            "blob_url": "...",
            "etag": "...",
            "result": { ... },
            "created_at": "...",
            "ttl": 604800
        }

    The Cosmos container **must** have a default TTL enabled so entries
    auto-expire.
    """

    def __init__(
        self,
        container: Any,
        ttl_days: int = 7,
    ) -> None:
        self._container = container
        self._ttl_seconds = ttl_days * 86_400
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _cache_key(blob_url: str, etag: str) -> str:
        """Deterministic cache key from blob URL + etag."""
        raw = f"{blob_url}|{etag}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, blob_url: str, etag: str) -> dict[str, Any] | None:
        """Retrieve a cached extraction result.

        Returns ``None`` on cache miss.
        """
        key = self._cache_key(blob_url, etag)
        try:
            item = await self._container.read_item(item=key, partition_key=key)
            self._hits += 1
            logger.debug("Cache HIT for %s (etag=%s)", blob_url, etag[:12])
            return item.get("result")
        except Exception:
            self._misses += 1
            logger.debug("Cache MISS for %s (etag=%s)", blob_url, etag[:12])
            return None

    async def put(
        self,
        blob_url: str,
        etag: str,
        result: dict[str, Any],
    ) -> None:
        """Store an extraction result in the cache."""
        key = self._cache_key(blob_url, etag)
        doc = {
            "id": key,
            "pk": key,
            "blob_url": blob_url,
            "etag": etag,
            "result": result,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ttl": self._ttl_seconds,
        }
        await self._container.upsert_item(doc)
        logger.debug("Cached result for %s (etag=%s, ttl=%ds)",
                      blob_url, etag[:12], self._ttl_seconds)

    async def invalidate(self, blob_url: str, etag: str) -> bool:
        """Remove a specific cache entry.  Returns ``True`` if deleted."""
        key = self._cache_key(blob_url, etag)
        try:
            await self._container.delete_item(item=key, partition_key=key)
            return True
        except Exception:
            return False

    async def clear(self) -> None:
        """Purge all cache entries (admin operation)."""
        query = "SELECT c.id, c.pk FROM c"
        items = self._container.query_items(query=query, enable_cross_partition_query=True)
        count = 0
        async for item in items:
            await self._container.delete_item(item=item["id"], partition_key=item["pk"])
            count += 1
        self._hits = 0
        self._misses = 0
        logger.info("Cleared %d cache entries.", count)

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        return {
            "enabled": True,
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_ratio": round(self._hits / total, 4) if total else 0.0,
            "ttl_seconds": self._ttl_seconds,
        }

"""Caching helpers — convenience utilities for tool-level cache
integration.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

from app.observability.metrics import cache_hit_counter, cache_miss_counter

logger = logging.getLogger(f"contelligence-agent.{__name__}")

async def cached_extraction(
    cache: Any | None,
    blob_url: str,
    etag: str,
    extract_fn: Callable[..., Coroutine[Any, Any, dict]],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run ``extract_fn`` with transparent caching.

    1. Check the cache for an existing result.
    2. On hit → return immediately, recording a metric.
    3. On miss → call ``extract_fn(*args, **kwargs)``, store in cache,
       recording a metric.
    4. If caching is disabled (``cache is None``), just run ``extract_fn``.
    """
    if cache is not None:
        cached = await cache.get(blob_url, etag)
        if cached is not None:
            cache_hit_counter.add(1, {"blob_url": blob_url})
            return cached

        cache_miss_counter.add(1, {"blob_url": blob_url})

    # Execute the real extraction
    result = await extract_fn(*args, **kwargs)

    if cache is not None:
        try:
            await cache.put(blob_url, etag, result)
        except Exception:
            logger.warning("Failed to cache extraction result for %s", blob_url, exc_info=True)

    return result

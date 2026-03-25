"""No-op stubs for optional Azure connectors.

Used when STORAGE_MODE == "local" to provide the same API surface
without requiring any Azure service dependencies.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class NoOpSearchConnector:
    """Stub search connector — all operations are no-ops or return empty results."""

    async def ensure_initialized(self) -> None:
        logger.info("Search connector disabled (local mode).")

    async def search(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"results": [], "count": 0}

    async def upload_documents(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def close(self) -> None:
        pass


class NoOpDocIntelligenceConnector:
    """Stub Document Intelligence connector — raises informative errors."""

    async def ensure_initialized(self) -> None:
        logger.info("Document Intelligence connector disabled (local mode).")

    async def analyze(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "Document Intelligence is not available in local/standalone mode. "
            "Configure AZURE_DOC_INTELLIGENCE_ENDPOINT in .env to enable."
        )

    async def close(self) -> None:
        pass


class NoOpOpenAIConnector:
    """Stub OpenAI connector — raises informative errors if called."""

    async def ensure_initialized(self) -> None:
        logger.info("Azure OpenAI connector disabled (local mode — using Copilot SDK).")

    async def generate_embeddings(self, *args: Any, **kwargs: Any) -> list[list[float]]:
        raise NotImplementedError(
            "Azure OpenAI embeddings are not available in local/standalone mode."
        )

    def get_client(self) -> None:
        raise NotImplementedError(
            "Azure OpenAI client is not available in local/standalone mode."
        )

    async def close(self) -> None:
        pass

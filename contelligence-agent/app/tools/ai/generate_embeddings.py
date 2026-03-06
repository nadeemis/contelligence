"""Tool for generating vector embeddings via Azure OpenAI.

Phase 3 enhancements:
- Default model upgraded to ``text-embedding-3-large``
- Configurable ``dimensions`` parameter
- Automatic batch chunking for >100 input texts
- Token usage tracking
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool, ToolDefinition

logger = logging.getLogger(__name__)

# Azure OpenAI embeddings API limit per request
_MAX_BATCH_SIZE = 100


class GenerateEmbeddingsParams(BaseModel):
    """Parameters for the generate_embeddings tool."""

    texts: list[str] = Field(
        description="List of text strings to generate embeddings for."
    )
    model: str = Field(
        default="text-embedding-3-large",
        description="Azure OpenAI embedding model deployment name.",
    )
    dimensions: int = Field(
        default=1536,
        description=(
            "Desired embedding dimensions (model-dependent). "
            "text-embedding-3-large supports 256, 1024, or 3072."
        ),
    )


@define_tool(
    name="generate_embeddings",
    description=(
        "Generate vector embeddings for a list of text strings using Azure "
        "OpenAI. Returns one embedding vector per input text. "
        "Use this when you need to make content searchable via "
        "vector/semantic search, or when creating embeddings for document "
        "chunks. Supports batch processing (up to 100 texts at a time) and "
        "configurable dimensions."
    ),
    parameters_model=GenerateEmbeddingsParams,
)
async def generate_embeddings(params: GenerateEmbeddingsParams, context: dict) -> dict:
    """Handle generate_embeddings tool invocations."""
    import openai

    connector = context["openai"]

    # Handle empty input
    if not params.texts:
        return {
            "model": params.model,
            "count": 0,
            "embeddings": [],
            "dimensions": params.dimensions,
            "total_tokens": 0,
        }

    try:
        all_embeddings: list[list[float]] = []
        total_tokens = 0

        # Chunk into batches of _MAX_BATCH_SIZE
        for i in range(0, len(params.texts), _MAX_BATCH_SIZE):
            batch = params.texts[i : i + _MAX_BATCH_SIZE]
            result = await connector.generate_embeddings(
                texts=batch,
                model=params.model,
                dimensions=params.dimensions,
            )
            all_embeddings.extend(result["embeddings"])
            total_tokens += result.get("total_tokens", 0)

        dimensions = len(all_embeddings[0]) if all_embeddings else params.dimensions

        logger.info(
            "generate_embeddings model=%s count=%d dimensions=%d tokens=%d",
            params.model,
            len(all_embeddings),
            dimensions,
            total_tokens,
        )
        return {
            "model": params.model,
            "count": len(all_embeddings),
            "embeddings": all_embeddings,
            "dimensions": dimensions,
            "total_tokens": total_tokens,
        }
    except openai.RateLimitError as exc:
        logger.warning("generate_embeddings rate limited: %s", exc)
        return {
            "error": "Rate limit exceeded. Please retry after a short delay.",
            "retry_after_seconds": getattr(exc, "retry_after", 10),
        }

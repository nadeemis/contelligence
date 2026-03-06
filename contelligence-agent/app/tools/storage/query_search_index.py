"""Tool for querying an Azure AI Search index.

Phase 3 enhancements:
- Vector, hybrid, and semantic query types
- VectorizedQuery construction
- Semantic reranker score propagation
- Parameter validation
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.tool_registry import define_tool, ToolDefinition

logger = logging.getLogger(__name__)


class QuerySearchIndexParams(BaseModel):
    """Parameters for the query_search_index tool."""

    index: str = Field(
        description="Name of the Azure AI Search index to query."
    )
    query: str = Field(
        default="",
        description=(
            "Full-text search query string. Required for keyword, hybrid, "
            "and semantic searches. Ignored for pure vector search."
        ),
    )
    top: int = Field(
        default=10,
        description="Maximum number of results to return.",
    )
    filters: str | None = Field(
        default=None,
        description=(
            "OData filter expression (e.g. \"status eq 'active'\")."
        ),
    )
    select: list[str] | None = Field(
        default=None,
        description="List of field names to include in results. Returns all fields if omitted.",
    )
    query_type: Literal["keyword", "vector", "hybrid", "semantic"] = Field(
        default="keyword",
        description=(
            "Search mode. 'keyword' = full-text BM25; 'vector' = pure "
            "vector similarity; 'hybrid' = keyword + vector; 'semantic' = "
            "BM25 with semantic reranking (optionally combined with vector)."
        ),
    )
    vector: list[float] | None = Field(
        default=None,
        description=(
            "Embedding vector for vector/hybrid queries. Generate with the "
            "generate_embeddings tool first."
        ),
    )
    vector_fields: str = Field(
        default="contentVector",
        description=(
            "Comma-separated names of vector fields in the search index to "
            "search against."
        ),
    )
    semantic_configuration: str | None = Field(
        default=None,
        description=(
            "Semantic configuration name. Required when query_type is "
            "'semantic'. Defined in the search index."
        ),
    )

    @model_validator(mode="after")
    def _validate_params(self) -> "QuerySearchIndexParams":
        if self.query_type in ("vector", "hybrid") and self.vector is None:
            raise ValueError(
                f"'vector' is required when query_type is '{self.query_type}'. "
                "Use the generate_embeddings tool to create a vector first."
            )
        if self.query_type in ("keyword", "hybrid", "semantic") and not self.query:
            raise ValueError(
                f"'query' is required when query_type is '{self.query_type}'."
            )
        if self.query_type == "semantic" and not self.semantic_configuration:
            raise ValueError(
                "'semantic_configuration' is required when query_type is 'semantic'."
            )
        return self


@define_tool(
    name="query_search_index",
    description=(
        "Query an Azure AI Search index. Supports keyword (BM25), vector "
        "(cosine similarity), hybrid (keyword + vector), and semantic "
        "(BM25 + semantic reranker) query types. For vector or hybrid "
        "queries, first generate an embedding with generate_embeddings and "
        "pass the resulting vector. Returns matching documents with "
        "relevance scores."
    ),
    parameters_model=QuerySearchIndexParams,
)
async def query_search_index(params: QuerySearchIndexParams, context: dict) -> dict:
    """Handle query_search_index tool invocations."""
    connector = context["search"]

    results: list[dict[str, Any]] = await connector.search(
        index=params.index,
        query=params.query,
        top=params.top,
        filters=params.filters,
        select=params.select,
        vector=params.vector,
        vector_fields=params.vector_fields,
        query_type=params.query_type,
        semantic_configuration=params.semantic_configuration,
    )
    logger.info(
        "query_search_index index=%s type=%s query=%r returned %d results",
        params.index,
        params.query_type,
        params.query[:60] if params.query else "<vector>",
        len(results),
    )
    return {
        "index": params.index,
        "query_type": params.query_type,
        "count": len(results),
        "results": results,
    }

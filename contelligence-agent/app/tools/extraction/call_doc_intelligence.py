"""Tool for extracting content using Azure Document Intelligence (OCR)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

logger = logging.getLogger(__name__)


class CallDocIntelligenceParams(BaseModel):
    """Parameters for the call_doc_intelligence tool."""

    container: str = Field(..., description="Azure Blob Storage container name.")
    path: str = Field(..., description="Blob path to the document.")
    model: str = Field(
        "prebuilt-layout",
        description=(
            "Document Intelligence model to use. Options: "
            "'prebuilt-layout', 'prebuilt-invoice', 'prebuilt-receipt', "
            "'prebuilt-document', or a custom model ID."
        ),
    )
    pages: str | None = Field(
        None,
        description=(
            "Page range filter, e.g. '1-5' or '1,3,7'. Omit to process all pages."
        ),
    )


@define_tool(
    name="call_doc_intelligence",
    description=(
        "Extract content from documents using Azure Document Intelligence (OCR). "
        "Handles scanned documents, images, complex layouts, forms, invoices, and "
        "receipts. Use this when extract_pdf returns empty or garbled text, or when "
        "you need form field extraction. Available models: prebuilt-layout, "
        "prebuilt-invoice, prebuilt-receipt, prebuilt-document, or a custom model ID."
    ),
    parameters_model=CallDocIntelligenceParams,
)
async def call_doc_intelligence(
    params: CallDocIntelligenceParams, context: dict
) -> dict[str, Any]:
    """Download a document from blob storage and analyse it with Doc Intelligence."""
    try:
        blob = context["blob"]
        doc_intel = context["doc_intelligence"]

        logger.info(
            "Downloading blob %s/%s for Doc Intelligence analysis",
            params.container,
            params.path,
        )
        document_bytes: bytes = await blob.download_blob(params.container, params.path)

        logger.info(
            "Analysing document with model=%s pages=%s",
            params.model,
            params.pages,
        )
        result = await doc_intel.analyze(
            document_bytes=document_bytes,
            model_id=params.model,
            pages=params.pages,
        )

        # Restructure tables into headers/rows format for consistency with other tools
        tables: list[dict[str, Any]] = []
        for raw_table in result.get("tables", []):
            row_count = raw_table.get("row_count", 0)
            col_count = raw_table.get("column_count", 0)
            cells = raw_table.get("cells", [])

            # Build a 2D grid from cell data
            grid: list[list[str]] = [[""] * col_count for _ in range(row_count)]
            for cell in cells:
                r = cell.get("row_index", 0)
                c = cell.get("column_index", 0)
                if 0 <= r < row_count and 0 <= c < col_count:
                    grid[r][c] = cell.get("content", "")

            if grid:
                tables.append({"headers": grid[0], "rows": grid[1:]})

        return {
            "filename": params.path,
            "model_used": params.model,
            "page_count": result.get("page_count", 0),
            "text": result.get("text", ""),
            "tables": tables,
            "key_value_pairs": result.get("key_value_pairs", []),
            "layout": result.get("layout", []),
        }

    except Exception as exc:
        logger.exception(
            "call_doc_intelligence failed for %s/%s", params.container, params.path
        )
        return {"error": str(exc), "filename": params.path}

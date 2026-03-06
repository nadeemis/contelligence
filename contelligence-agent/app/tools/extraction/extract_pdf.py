"""Tool for extracting text, tables, and metadata from PDF files."""

from __future__ import annotations

import io
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

class ExtractPdfParams(BaseModel):
    """Parameters for the extract_pdf tool."""

    container: str = Field(..., description="Azure Blob Storage container name.")
    path: str = Field(..., description="Blob path to the PDF file.")
    extract_tables: bool = Field(
        True, description="Whether to extract tables from the PDF."
    )
    extract_images: bool = Field(
        False, description="Whether to extract embedded image metadata."
    )
    pages: str | None = Field(
        None,
        description=(
            "Page filter expression. Supports ranges like '1-5' and "
            "comma-separated values like '1,3,7'. Omit to process all pages."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_pages(pages_str: str, total_pages: int) -> set[int]:
    """Parse a page filter string into a set of 0-based page indices.

    Accepts formats like ``"1-5"``, ``"1,3,7"``, or ``"1-3,5,8-10"``.
    Input values are 1-based; the returned set is 0-based.
    """
    indices: set[int] = set()
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = max(int(start_s.strip()) - 1, 0)
            end = min(int(end_s.strip()) - 1, total_pages - 1)
            indices.update(range(start, end + 1))
        else:
            idx = int(part) - 1
            if 0 <= idx < total_pages:
                indices.add(idx)
    return indices


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

@define_tool(
    name="extract_pdf",
    description=(
        "Extract text, tables, and metadata from a PDF stored in Azure Blob "
        "Storage. Uses PyMuPDF (pymupdf) for fast, accurate extraction. Supports "
        "page-range filtering and optional table extraction."
    ),
    parameters_model=ExtractPdfParams,
)
async def extract_pdf(params: ExtractPdfParams, context: dict) -> dict[str, Any]:
    """Download a PDF from blob storage and extract its contents."""
    try:
        import pymupdf  # PyMuPDF

        blob = context["blob"]
        logger.info("Downloading PDF blob %s/%s", params.container, params.path)
        pdf_bytes: bytes = await blob.download_blob(params.container, params.path)

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)

        # Determine which pages to process.
        if params.pages:
            page_indices = _parse_pages(params.pages, total_pages)
        else:
            page_indices = set(range(total_pages))

        all_text: list[str] = []
        all_tables: list[dict[str, Any]] = []

        for page_num in sorted(page_indices):
            page = doc[page_num]

            # --- text ---
            page_text = page.get_text()
            if page_text:
                all_text.append(page_text)

            # --- tables ---
            if params.extract_tables:
                try:
                    tables = page.find_tables()
                    for table in tables:
                        extracted = table.extract()
                        if not extracted:
                            continue
                        headers = extracted[0] if extracted else []
                        rows = extracted[1:] if len(extracted) > 1 else []
                        all_tables.append(
                            {
                                "page": page_num + 1,
                                "headers": headers,
                                "rows": rows,
                            }
                        )
                except Exception as tbl_err:
                    logger.warning(
                        "Table extraction failed on page %d: %s",
                        page_num + 1,
                        tbl_err,
                    )

        metadata = dict(doc.metadata) if doc.metadata else {}
        doc.close()

        return {
            "filename": params.path,
            "page_count": total_pages,
            "text": "\n".join(all_text),
            "tables": all_tables,
            "metadata": metadata,
        }

    except Exception as exc:
        logger.exception("extract_pdf failed for %s/%s", params.container, params.path)
        return {"error": str(exc), "filename": params.path}

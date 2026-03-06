"""Tests for the extract_pdf tool."""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.tools.extraction.extract_pdf import ExtractPdfParams, extract_pdf, _parse_pages


# ---------------------------------------------------------------------------
# _parse_pages helper
# ---------------------------------------------------------------------------

class TestParsePages:

    def test_single_page(self) -> None:
        assert _parse_pages("1", 10) == {0}

    def test_comma_separated(self) -> None:
        assert _parse_pages("1,3,5", 10) == {0, 2, 4}

    def test_range(self) -> None:
        assert _parse_pages("2-4", 10) == {1, 2, 3}

    def test_mixed(self) -> None:
        assert _parse_pages("1-3,5,8-10", 10) == {0, 1, 2, 4, 7, 8, 9}

    def test_out_of_range_page_ignored(self) -> None:
        result = _parse_pages("100", 5)
        assert len(result) == 0

    def test_range_clamped_to_total(self) -> None:
        result = _parse_pages("3-20", 5)
        # Pages 3,4,5 -> 0-based 2,3,4
        assert result == {2, 3, 4}


# ---------------------------------------------------------------------------
# extract_pdf tool (uses fitz / PyMuPDF)
# ---------------------------------------------------------------------------

def _create_minimal_pdf() -> bytes:
    """Create a minimal single-page PDF in memory using PyMuPDF (fitz)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Hello from the test PDF.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestExtractPdf:

    @pytest.mark.asyncio
    async def test_basic_extraction(self, tool_context: dict[str, Any]) -> None:
        """Extracting a simple PDF should return text and metadata."""
        pdf_bytes = _create_minimal_pdf()
        tool_context["blob"].download_blob.return_value = pdf_bytes

        params = ExtractPdfParams(
            container="test-container",
            path="docs/sample.pdf",
        )
        result = await extract_pdf.handler(params, tool_context)

        assert result["filename"] == "docs/sample.pdf"
        assert result["page_count"] == 1
        assert "Hello from the test PDF" in result["text"]
        assert isinstance(result["tables"], list)
        assert isinstance(result["metadata"], dict)

    @pytest.mark.asyncio
    async def test_pages_filter(self, tool_context: dict[str, Any]) -> None:
        """When a pages filter is provided, only those pages should be processed."""
        import fitz

        # Create a 3-page PDF.
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 72), f"Page {i + 1} content")
        pdf_bytes = doc.tobytes()
        doc.close()

        tool_context["blob"].download_blob.return_value = pdf_bytes

        params = ExtractPdfParams(
            container="c",
            path="multi.pdf",
            pages="2",
        )
        result = await extract_pdf.handler(params, tool_context)

        assert result["page_count"] == 3
        # Only page 2 text should appear.
        assert "Page 2 content" in result["text"]
        assert "Page 1 content" not in result["text"]
        assert "Page 3 content" not in result["text"]

    @pytest.mark.asyncio
    async def test_extract_tables_disabled(self, tool_context: dict[str, Any]) -> None:
        """When extract_tables=False, the tables list should be empty."""
        pdf_bytes = _create_minimal_pdf()
        tool_context["blob"].download_blob.return_value = pdf_bytes

        params = ExtractPdfParams(
            container="c",
            path="notables.pdf",
            extract_tables=False,
        )
        result = await extract_pdf.handler(params, tool_context)
        assert result["tables"] == []

    @pytest.mark.asyncio
    async def test_blob_download_error(self, tool_context: dict[str, Any]) -> None:
        """If blob download fails, the tool should return an error dict."""
        tool_context["blob"].download_blob.side_effect = RuntimeError("Network error")

        params = ExtractPdfParams(container="c", path="bad.pdf")
        result = await extract_pdf.handler(params, tool_context)

        assert "error" in result
        assert "Network error" in result["error"]
        assert result["filename"] == "bad.pdf"

    @pytest.mark.asyncio
    async def test_invalid_pdf_bytes(self, tool_context: dict[str, Any]) -> None:
        """Passing non-PDF bytes should result in an error dict, not an exception."""
        tool_context["blob"].download_blob.return_value = b"not-a-pdf"

        params = ExtractPdfParams(container="c", path="corrupt.pdf")
        result = await extract_pdf.handler(params, tool_context)

        assert "error" in result

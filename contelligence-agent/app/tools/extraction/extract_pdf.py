"""Tool for extracting text, tables, and metadata from PDF files."""

from __future__ import annotations

import base64
import io
import logging
import pathlib
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

class ExtractPdfParams(BaseModel):
    """Parameters for the extract_pdf tool."""

    file_bytes: bytes | None = Field(
        None,
        description="Raw bytes of the PDF file. Preferred when the caller already has the content in memory.",
    )
    file_bytes_b64: str | None = Field(
        None,
        description="Base64-encoded PDF file content.",
    )
    local_path: str | None = Field(
        None,
        description="Absolute or relative path to a PDF file on the local filesystem.",
    )
    storage_account: str | None = Field(
        default=None,
        description=(
            "Azure Storage account name to connect to. "
            "Provide this to read from a storage account "
            "(authentication uses DefaultAzureCredential)."
        ),
    )
    container: str | None = Field(
        None, description="Azure Blob Storage container name."
    )
    path: str | None = Field(
        None, description="Blob path to the PDF file."
    )
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
    format: Literal["markdown", "json"] = Field(
        "markdown",
        description="Output format: 'markdown' returns a rendered markdown document, 'json' returns structured data.",
    )
    filename: str | None = Field(
        None,
        description="Optional descriptive filename for the result metadata.",
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
        "Extract text, tables, and metadata from a PDF file. Accepts the file "
        "as raw bytes (file_bytes), base64-encoded bytes (file_bytes_b64), a "
        "local filesystem path (local_path), or reads from Azure Blob Storage "
        "(storage_account + container + path). Returns a markdown document (default) or "
        "structured JSON. Uses PyMuPDF (pymupdf) for fast, accurate "
        "extraction. Supports page-range filtering and optional table extraction."
    ),
    parameters_model=ExtractPdfParams,
)
async def extract_pdf(params: ExtractPdfParams, context: dict) -> dict[str, Any]:
    """Extract contents from a PDF provided as bytes, local path, or fetched from blob storage."""
    try:
        import pymupdf  # PyMuPDF

        # Resolve the file bytes from the supplied source.
        if params.file_bytes:
            logger.info("Parsing PDF from supplied raw bytes")
            pdf_bytes: bytes = params.file_bytes
        elif params.file_bytes_b64:
            logger.info("Parsing PDF from base64-encoded bytes")
            pdf_bytes = base64.b64decode(params.file_bytes_b64)
        elif params.local_path:
            resolved = pathlib.Path(params.local_path).expanduser().resolve()
            if not resolved.is_file():
                return {
                    "error": f"Local file not found: {resolved}",
                    "filename": params.filename or params.local_path,
                }
            logger.info("Reading PDF from local path %s", resolved)
            pdf_bytes = resolved.read_bytes()
        elif params.storage_account and params.container and params.path:
            from app.connectors.blob_connector import BlobConnectorAdapter
            try:
                connector = BlobConnectorAdapter(
                    account_name=params.storage_account,
                    credential_type="default_azure_credential",
                )
                logger.info("Downloading PDF blob %s/%s", params.container, params.path)
                pdf_bytes = await connector.download_blob(params.container, params.path)
            except Exception as blob_err:
                return {
                    "error": f"Failed to download PDF from blob storage: {blob_err}",
                    "filename": params.filename or params.path,
                }
            finally:
                if connector is not None:
                    await connector.close()
        else:
            return {
                "error": (
                    "Provide one of: file_bytes, file_bytes_b64, local_path, "
                    "or storage_account + container + path."
                ),
                "filename": params.filename or "",
            }

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

        label = params.filename or params.local_path or params.path or "unknown.pdf"

        if params.format == "markdown":
            return {
                "filename": label,
                "page_count": total_pages,
                "content": _pdf_to_markdown(label, all_text, all_tables, metadata),
            }

        return {
            "filename": label,
            "page_count": total_pages,
            "text": "\n".join(all_text),
            "tables": all_tables,
            "metadata": metadata,
        }

    except Exception as exc:
        label = params.filename or params.local_path or params.path or "unknown.pdf"
        logger.exception("extract_pdf failed for %s", label)
        return {"error": str(exc), "filename": label}


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def _pdf_to_markdown(
    label: str,
    page_texts: list[str],
    tables: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> str:
    """Convert extracted PDF data into a readable markdown document."""
    parts: list[str] = [f"# {label}", ""]

    # Metadata
    meta_items = {k: v for k, v in metadata.items() if v}
    if meta_items:
        parts.append("## Metadata")
        parts.append("")
        for key, value in meta_items.items():
            parts.append(f"- **{key}:** {value}")
        parts.append("")

    # Body text, page by page
    for i, page_text in enumerate(page_texts, 1):
        stripped = page_text.strip()
        if stripped:
            parts.append(f"## Page {i}")
            parts.append("")
            parts.append(stripped)
            parts.append("")

    # Tables
    if tables:
        parts.append("## Tables")
        parts.append("")
        for tbl in tables:
            page_num = tbl.get("page", "?")
            parts.append(f"### Table (page {page_num})")
            parts.append("")
            headers = tbl.get("headers", [])
            rows = tbl.get("rows", [])
            if headers:
                parts.append("| " + " | ".join(str(h) if h else "" for h in headers) + " |")
                parts.append("| " + " | ".join("---" for _ in headers) + " |")
                for row in rows:
                    parts.append("| " + " | ".join(str(c) if c else "" for c in row) + " |")
            parts.append("")

    return "\n".join(parts).rstrip() + "\n"

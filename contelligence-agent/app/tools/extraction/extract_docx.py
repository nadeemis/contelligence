"""Tool for extracting text, tables, styles, and metadata from DOCX files."""

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

class ExtractDocxParams(BaseModel):
    """Parameters for the extract_docx tool."""

    container: str = Field(..., description="Azure Blob Storage container name.")
    path: str = Field(..., description="Blob path to the DOCX file.")


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

@define_tool(
    name="extract_docx",
    description=(
        "Extract text, tables, styles, and metadata from a Word DOCX file "
        "stored in Azure Blob Storage. Uses python-docx for parsing."
    ),
    parameters_model=ExtractDocxParams,
)
async def extract_docx(params: ExtractDocxParams, context: dict) -> dict[str, Any]:
    """Download a DOCX from blob storage and extract its contents."""
    try:
        from docx import Document

        blob = context["blob"]
        logger.info("Downloading DOCX blob %s/%s", params.container, params.path)
        docx_bytes: bytes = await blob.download_blob(params.container, params.path)

        doc = Document(io.BytesIO(docx_bytes))

        # --- text ---
        text = "\n".join(para.text for para in doc.paragraphs)

        # --- tables ---
        tables: list[dict[str, Any]] = []
        for table in doc.tables:
            rows_data: list[list[str]] = []
            for row in table.rows:
                rows_data.append([cell.text for cell in row.cells])
            if rows_data:
                headers = rows_data[0]
                data_rows = rows_data[1:]
            else:
                headers = []
                data_rows = []
            tables.append({"headers": headers, "rows": data_rows})

        # --- styles ---
        styles: list[str] = list(
            {para.style.name for para in doc.paragraphs if para.style and para.style.name}
        )

        # --- metadata ---
        metadata: dict[str, Any] = {}
        try:
            props = doc.core_properties
            metadata = {
                "author": props.author or "",
                "title": props.title or "",
                "subject": props.subject or "",
                "created": str(props.created) if props.created else "",
                "modified": str(props.modified) if props.modified else "",
                "last_modified_by": props.last_modified_by or "",
                "revision": props.revision,
            }
        except Exception as meta_err:
            logger.warning("Could not extract DOCX metadata: %s", meta_err)

        return {
            "filename": params.path,
            "text": text,
            "tables": tables,
            "styles": styles,
            "metadata": metadata,
        }

    except Exception as exc:
        logger.exception(
            "extract_docx failed for %s/%s", params.container, params.path
        )
        return {"error": str(exc), "filename": params.path}

"""Tool for extracting sheet data from Excel XLSX files."""

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

class ExtractXlsxParams(BaseModel):
    """Parameters for the extract_xlsx tool."""

    container: str = Field(..., description="Azure Blob Storage container name.")
    path: str = Field(..., description="Blob path to the XLSX file.")
    sheets: str | None = Field(
        None,
        description=(
            "Comma-separated sheet names to extract. "
            "Omit to extract all sheets."
        ),
    )


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

@define_tool(
    name="extract_xlsx",
    description=(
        "Extract tabular data from an Excel XLSX workbook stored in Azure "
        "Blob Storage. Uses openpyxl to read sheets, headers, and rows. "
        "Supports filtering by sheet name."
    ),
    parameters_model=ExtractXlsxParams,
)
async def extract_xlsx(params: ExtractXlsxParams, context: dict) -> dict[str, Any]:
    """Download an XLSX from blob storage and extract its sheet data."""
    try:
        from openpyxl import load_workbook

        blob = context["blob"]
        logger.info("Downloading XLSX blob %s/%s", params.container, params.path)
        xlsx_bytes: bytes = await blob.download_blob(params.container, params.path)

        wb = load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)

        # Determine which sheets to process.
        if params.sheets:
            requested = [s.strip() for s in params.sheets.split(",")]
            sheet_names = [s for s in requested if s in wb.sheetnames]
        else:
            sheet_names = wb.sheetnames

        sheets_data: list[dict[str, Any]] = []
        for name in sheet_names:
            ws = wb[name]
            rows: list[list[Any]] = []
            for row in ws.iter_rows(values_only=True):
                rows.append([cell for cell in row])

            if rows:
                headers = [str(h) if h is not None else "" for h in rows[0]]
                data_rows = [
                    [str(c) if c is not None else "" for c in row]
                    for row in rows[1:]
                ]
            else:
                headers = []
                data_rows = []

            sheets_data.append(
                {
                    "name": name,
                    "headers": headers,
                    "rows": data_rows,
                    "row_count": len(data_rows),
                }
            )

        wb.close()

        return {
            "filename": params.path,
            "sheets": sheets_data,
        }

    except Exception as exc:
        logger.exception(
            "extract_xlsx failed for %s/%s", params.container, params.path
        )
        return {"error": str(exc), "filename": params.path}

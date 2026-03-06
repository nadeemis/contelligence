"""Tool for extracting slide content from PowerPoint PPTX files."""

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

class ExtractPptxParams(BaseModel):
    """Parameters for the extract_pptx tool."""

    container: str = Field(..., description="Azure Blob Storage container name.")
    path: str = Field(..., description="Blob path to the PPTX file.")


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

@define_tool(
    name="extract_pptx",
    description=(
        "Extract slide content from a PowerPoint PPTX file stored in Azure "
        "Blob Storage. Uses python-pptx to read titles, text, notes, and "
        "shape types from each slide."
    ),
    parameters_model=ExtractPptxParams,
)
async def extract_pptx(params: ExtractPptxParams, context: dict) -> dict[str, Any]:
    """Download a PPTX from blob storage and extract its slide content."""
    try:
        from pptx import Presentation
        from pptx.util import Inches  # noqa: F401 – imported for type hints

        blob = context["blob"]
        logger.info("Downloading PPTX blob %s/%s", params.container, params.path)
        pptx_bytes: bytes = await blob.download_blob(params.container, params.path)

        prs = Presentation(io.BytesIO(pptx_bytes))

        slides_data: list[dict[str, Any]] = []
        for idx, slide in enumerate(prs.slides, start=1):
            # --- title ---
            title = ""
            if slide.shapes.title and slide.shapes.title.has_text_frame:
                title = slide.shapes.title.text_frame.text

            # --- text from all shapes ---
            texts: list[str] = []
            shape_types: list[str] = []
            for shape in slide.shapes:
                shape_types.append(str(shape.shape_type))
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        para_text = paragraph.text.strip()
                        if para_text:
                            texts.append(para_text)

            # --- notes ---
            notes = ""
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes = slide.notes_slide.notes_text_frame.text

            slides_data.append(
                {
                    "number": idx,
                    "title": title,
                    "text": "\n".join(texts),
                    # "notes": notes,
                    # "shapes": shape_types,
                }
            )

        return {
            "filename": params.path,
            "slide_count": len(slides_data),
            "slides": slides_data,
        }

    except Exception as exc:
        logger.exception(
            "extract_pptx failed for %s/%s", params.container, params.path
        )
        return {"error": str(exc), "filename": params.path}

"""Document creation tools for the contelligence-agent."""

from __future__ import annotations

from .create_pptx import create_pptx
from .create_docx import create_docx

CREATION_TOOLS = [
    create_pptx,
    create_docx,
]

"""Document extraction tools for the contelligence-agent."""

from __future__ import annotations

from .extract_pdf import extract_pdf
from .extract_docx import extract_docx
from .extract_xlsx import extract_xlsx
from .extract_pptx import extract_pptx
from .call_doc_intelligence import call_doc_intelligence
# from .scrape_webpage import scrape_webpage
# from .transcribe_audio import transcribe_audio

EXTRACTION_TOOLS = [
    extract_pdf,
    extract_docx,
    extract_xlsx,
    extract_pptx,
    call_doc_intelligence,
    # scrape_webpage,
    # transcribe_audio,
]

"""Custom agent registry — maps agent names to their definitions.

The ``CUSTOM_AGENTS`` dictionary is the single source of truth for every
specialized agent persona available for delegation. Each entry specifies
the agent's focused tool subset, MCP server access, and system prompt.
"""

from __future__ import annotations

from .models import AgentDefinition
from .prompts import (
    DATA_ANALYST_PROMPT,
    DOCUMENT_PROCESSOR_PROMPT,
    QA_REVIEWER_PROMPT,
)

CUSTOM_AGENTS: dict[str, AgentDefinition] = {
    "doc-processor": AgentDefinition(
        name="doc-processor",
        display_name="Document Processor",
        description="Expert at extracting and transforming document content",
        tools=[
            "extract_pdf",
            "extract_docx",
            "extract_xlsx",
            "extract_pptx",
            "call_doc_intelligence",
            "scrape_webpage",
            "transcribe_audio",
            "read_blob",
            "write_blob",
        ],
        prompt=DOCUMENT_PROCESSOR_PROMPT,
    ),
    "data-analyst": AgentDefinition(
        name="data-analyst",
        display_name="Data Analyst",
        description="Analyzes processed data, produces insights and reports",
        # tools=[
        #     "query_search_index",
        #     "query_cosmos",
        #     "read_blob",
        #     "write_blob",
        #     "generate_embeddings",
        # ],
        tools=None,  # No tools - gives access to all tools for maximum flexibility in analysis and reporting
        prompt=DATA_ANALYST_PROMPT,
        infer=True,
    ),
    "qa-reviewer": AgentDefinition(
        name="qa-reviewer",
        display_name="Quality Reviewer",
        description="Validates extraction quality and flags issues",
        tools=[
            "read_blob",
            "query_cosmos",
            "query_search_index",
            "extract_pdf",
            "call_doc_intelligence",
        ],
        prompt=QA_REVIEWER_PROMPT,
    ),
}

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")

class DocIntelligenceConnectorAdapter:
    """Thin async wrapper around Azure AI Document Intelligence SDK client."""

    def __init__(
        self,
        endpoint: str,
        key: str = "",
    ) -> None:
        self._endpoint = endpoint
        self._key = key
        self._client = None
        self._credential = None

    async def ensure_initialized(self) -> None:
        if self._client is not None:
            return
        from azure.ai.documentintelligence.aio import DocumentIntelligenceClient

        if self._key:
            from azure.core.credentials import AzureKeyCredential

            self._client = DocumentIntelligenceClient(
                endpoint=self._endpoint,
                credential=AzureKeyCredential(self._key),
            )
        else:
            from azure.identity.aio import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
            self._client = DocumentIntelligenceClient(
                endpoint=self._endpoint,
                credential=self._credential,
            )

    async def analyze(
        self,
        document_bytes: bytes,
        *,
        model_id: str = "prebuilt-layout",
        pages: str | None = None,
    ) -> dict[str, Any]:
        """Analyse a document and return structured extraction results.

        Returns a dict with keys:
        - ``text``: the full extracted text
        - ``tables``: list of table dicts (row_count, column_count, cells)
        - ``key_value_pairs``: list of {key, value, confidence} dicts
        - ``layout``: list of paragraph dicts with role and content
        - ``page_count``: number of pages detected
        """
        await self.ensure_initialized()
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

        analyze_request = AnalyzeDocumentRequest(bytes_source=document_bytes)

        poller = await self._client.begin_analyze_document(
            model_id=model_id,
            analyze_request=analyze_request,
            pages=pages,
        )
        result = await poller.result()

        return self._parse_result(result)

    @staticmethod
    def _parse_result(result: Any) -> dict[str, Any]:
        """Convert an AnalyzeResult into a plain Python dict."""
        # --- Full text ---
        text = result.content or ""

        # --- Tables ---
        tables: list[dict[str, Any]] = []
        for table in result.tables or []:
            cells: list[dict[str, Any]] = []
            for cell in table.cells or []:
                cells.append(
                    {
                        "row_index": cell.row_index,
                        "column_index": cell.column_index,
                        "content": cell.content or "",
                        "kind": cell.kind if hasattr(cell, "kind") else None,
                        "row_span": getattr(cell, "row_span", 1),
                        "column_span": getattr(cell, "column_span", 1),
                    }
                )
            tables.append(
                {
                    "row_count": table.row_count,
                    "column_count": table.column_count,
                    "cells": cells,
                }
            )

        # --- Key-value pairs ---
        key_value_pairs: list[dict[str, Any]] = []
        for kvp in result.key_value_pairs or []:
            key_value_pairs.append(
                {
                    "key": kvp.key.content if kvp.key else None,
                    "value": kvp.value.content if kvp.value else None,
                    "confidence": kvp.confidence if hasattr(kvp, "confidence") else None,
                }
            )

        # --- Layout (paragraphs) ---
        layout: list[dict[str, Any]] = []
        for paragraph in result.paragraphs or []:
            layout.append(
                {
                    "role": getattr(paragraph, "role", None),
                    "content": paragraph.content or "",
                }
            )

        # --- Page count ---
        page_count = len(result.pages) if result.pages else 0

        return {
            "text": text,
            "tables": tables,
            "key_value_pairs": key_value_pairs,
            "layout": layout,
            "page_count": page_count,
        }

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
        if self._credential is not None and hasattr(self._credential, "close"):
            await self._credential.close()
            self._credential = None

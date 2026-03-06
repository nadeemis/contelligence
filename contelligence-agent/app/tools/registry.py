from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.connectors import (
        BlobConnectorAdapter, 
        CosmosConnectorAdapter, 
        DocIntelligenceConnectorAdapter, 
        OpenAIConnectorAdapter, 
        SearchConnectorAdapter
    )

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def register(self, name: str, tool: Any) -> None:
        self._tools[name] = tool

    def get(self, name: str) -> Any:
        return self._tools[name]

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def register_all(
        self,
        *,
        blob_connector: BlobConnectorAdapter,
        search_connector: SearchConnectorAdapter,
        cosmos_connector: CosmosConnectorAdapter,
        doc_intelligence_connector: DocIntelligenceConnectorAdapter,
        openai_connector: OpenAIConnectorAdapter,
    ) -> None:
        pass

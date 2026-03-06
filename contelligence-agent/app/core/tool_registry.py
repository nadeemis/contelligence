"""Tool registry for the contelligence-agent.

Provides a central registry of tool definitions that can be exposed to the
LLM via function-calling and dispatched at runtime.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel


class ToolDefinition:
    """Represents a registered tool with its metadata."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters_model: type[BaseModel],
        handler: Callable[..., Any],
    ) -> None:
        self.name = name
        self.description = description
        self.parameters_model = parameters_model
        self.handler = handler

    def get_schema(self) -> dict[str, Any]:
        """Return JSON Schema for the tool parameters."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_model.model_json_schema(),
        }

    def to_openai_tool(self) -> dict[str, Any]:
        """Return the tool in OpenAI function-calling format.

        This produces the ``{"type": "function", "function": {...}}`` dict
        expected by the OpenAI chat completions API.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_model.model_json_schema(),
            },
        }

    def __repr__(self) -> str:
        return f"ToolDefinition(name={self.name!r})"


class ToolRegistry:
    """A container for all registered tools.

    Tools are stored by name and can be retrieved individually or as a batch
    for inclusion in an LLM request.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        self._tools[tool.name] = tool

    def get_all_tools(self) -> list[ToolDefinition]:
        """Return every registered tool."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Look up a tool by name, returning ``None`` if not found."""
        return self._tools.get(name)

    def get_tool_names(self) -> list[str]:
        """Return the names of all registered tools."""
        return list(self._tools.keys())

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return generic JSON schemas for every registered tool."""
        return [t.get_schema() for t in self._tools.values()]

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Return every tool in OpenAI function-calling format."""
        return [t.to_openai_tool() for t in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def filter_tools(self, names: list[str]) -> list[ToolDefinition]:
        """Return ``ToolDefinition`` instances matching *names*.

        Used by the delegation service to restrict the tool set for
        custom agents.  Unknown names are silently skipped.
        """
        return [self._tools[n] for n in names if n in self._tools]


# ---------------------------------------------------------------------------
# Decorator helper
# ---------------------------------------------------------------------------

def define_tool(
    name: str,
    description: str,
    parameters_model: type[BaseModel],
) -> Callable[[Callable[..., Any]], ToolDefinition]:
    """Decorator to define a tool from an async function.

    Usage::

        class SearchParams(BaseModel):
            query: str

        @define_tool("search", "Search the knowledge base", SearchParams)
        async def search_tool(params: SearchParams) -> dict:
            ...
    """

    def decorator(func: Callable[..., Any]) -> ToolDefinition:
        return ToolDefinition(
            name=name,
            description=description,
            parameters_model=parameters_model,
            handler=func,
        )

    return decorator

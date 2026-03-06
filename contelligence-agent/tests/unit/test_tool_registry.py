"""Tests for ToolRegistry and the define_tool decorator."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.core.tool_registry import ToolDefinition, ToolRegistry, define_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _DummyParams(BaseModel):
    query: str
    limit: int = 10


async def _dummy_handler(params: _DummyParams, context: dict) -> dict[str, Any]:
    return {"result": params.query}


def _make_tool(name: str = "dummy_tool") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="A dummy tool for testing.",
        parameters_model=_DummyParams,
        handler=_dummy_handler,
    )


# ---------------------------------------------------------------------------
# ToolDefinition tests
# ---------------------------------------------------------------------------

class TestToolDefinition:

    def test_get_schema(self) -> None:
        tool = _make_tool()
        schema = tool.get_schema()
        assert schema["name"] == "dummy_tool"
        assert schema["description"] == "A dummy tool for testing."
        assert "properties" in schema["parameters"]

    def test_to_openai_tool(self) -> None:
        tool = _make_tool()
        openai_tool = tool.to_openai_tool()
        assert openai_tool["type"] == "function"
        fn = openai_tool["function"]
        assert fn["name"] == "dummy_tool"
        assert fn["description"] == "A dummy tool for testing."
        assert "properties" in fn["parameters"]

    def test_repr(self) -> None:
        tool = _make_tool("my_tool")
        assert "my_tool" in repr(tool)


# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------

class TestToolRegistry:

    def test_register_and_get_tool(self) -> None:
        registry = ToolRegistry()
        tool = _make_tool()
        registry.register(tool)
        retrieved = registry.get_tool("dummy_tool")
        assert retrieved is tool

    def test_get_tool_returns_none_for_unknown(self) -> None:
        registry = ToolRegistry()
        assert registry.get_tool("nonexistent") is None

    def test_get_all_tools_empty(self) -> None:
        registry = ToolRegistry()
        assert registry.get_all_tools() == []

    def test_get_all_tools_returns_list(self) -> None:
        registry = ToolRegistry()
        registry.register(_make_tool("a"))
        registry.register(_make_tool("b"))
        assert len(registry.get_all_tools()) == 2

    def test_get_tool_names(self) -> None:
        registry = ToolRegistry()
        registry.register(_make_tool("alpha"))
        registry.register(_make_tool("beta"))
        names = registry.get_tool_names()
        assert set(names) == {"alpha", "beta"}

    def test_get_openai_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(_make_tool("x"))
        registry.register(_make_tool("y"))
        openai_tools = registry.get_openai_tools()
        assert len(openai_tools) == 2
        for ot in openai_tools:
            assert ot["type"] == "function"
            assert "name" in ot["function"]

    def test_len(self) -> None:
        registry = ToolRegistry()
        assert len(registry) == 0
        registry.register(_make_tool("one"))
        assert len(registry) == 1

    def test_contains(self) -> None:
        registry = ToolRegistry()
        registry.register(_make_tool("present"))
        assert "present" in registry
        assert "absent" not in registry

    def test_register_overwrites_same_name(self) -> None:
        """Registering a tool with the same name replaces the previous one."""
        registry = ToolRegistry()
        tool_a = _make_tool("dup")
        tool_b = _make_tool("dup")
        registry.register(tool_a)
        registry.register(tool_b)
        assert len(registry) == 1
        assert registry.get_tool("dup") is tool_b

    def test_get_tool_schemas(self) -> None:
        registry = ToolRegistry()
        registry.register(_make_tool("s1"))
        schemas = registry.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "s1"


# ---------------------------------------------------------------------------
# define_tool decorator tests
# ---------------------------------------------------------------------------

class TestDefineToolDecorator:

    def test_decorator_returns_tool_definition(self) -> None:
        @define_tool("dec_tool", "Decorated tool", _DummyParams)
        async def my_func(params: _DummyParams, context: dict) -> dict:
            return {}

        assert isinstance(my_func, ToolDefinition)
        assert my_func.name == "dec_tool"
        assert my_func.description == "Decorated tool"
        assert my_func.parameters_model is _DummyParams

    def test_decorator_handler_is_original_function(self) -> None:
        async def original(params: _DummyParams, context: dict) -> dict:
            return {"ok": True}

        tool = define_tool("orig", "Original", _DummyParams)(original)
        assert tool.handler is original

    def test_decorated_tool_can_be_registered(self) -> None:
        @define_tool("reg_test", "Registerable", _DummyParams)
        async def my_tool(params: _DummyParams, context: dict) -> dict:
            return {}

        registry = ToolRegistry()
        registry.register(my_tool)
        assert "reg_test" in registry

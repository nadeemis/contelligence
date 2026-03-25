"""Tests for ALL_TOOLS: validate count, shape, and basic invariants."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from app.core.tool_registry import ToolDefinition
from app.tools import ALL_TOOLS, EXTRACTION_TOOLS, STORAGE_TOOLS, AI_TOOLS, AGENT_TOOLS
from app.tools.skills import SKILL_TOOLS
from app.tools.devops import DEVOPS_TOOLS
from app.tools.powerbi import POWERBI_TOOLS
from app.tools.desktop import DESKTOP_TOOLS


class TestAllToolsCollection:
    """Verify the aggregated ALL_TOOLS list."""

    def test_total_tool_count(self) -> None:
        """ALL_TOOLS should contain exactly 27 tool definitions."""
        assert len(ALL_TOOLS) == 27

    def test_extraction_tools_count(self) -> None:
        assert len(EXTRACTION_TOOLS) == 7

    def test_storage_tools_count(self) -> None:
        assert len(STORAGE_TOOLS) == 6

    def test_ai_tools_count(self) -> None:
        assert len(AI_TOOLS) == 1

    def test_agent_tools_count(self) -> None:
        assert len(AGENT_TOOLS) == 1

    def test_all_tools_equals_sum_of_parts(self) -> None:
        assert len(ALL_TOOLS) == (
            len(EXTRACTION_TOOLS) + len(STORAGE_TOOLS) + len(AI_TOOLS)
            + len(SKILL_TOOLS) + len(DEVOPS_TOOLS) + len(POWERBI_TOOLS)
            + len(DESKTOP_TOOLS)
        )

    def test_all_tools_are_tool_definitions(self) -> None:
        """Every entry in ALL_TOOLS must be a ToolDefinition instance."""
        for tool in ALL_TOOLS:
            assert isinstance(tool, ToolDefinition), (
                f"Expected ToolDefinition, got {type(tool)} for {tool!r}"
            )


class TestToolDefinitionShape:
    """Each tool must have a non-empty name, description, a Pydantic
    parameters_model, and a callable handler."""

    def test_non_empty_names(self) -> None:
        for tool in ALL_TOOLS:
            assert isinstance(tool.name, str)
            assert len(tool.name) > 0, f"Tool has empty name: {tool!r}"

    def test_unique_names(self) -> None:
        names = [t.name for t in ALL_TOOLS]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    def test_non_empty_descriptions(self) -> None:
        for tool in ALL_TOOLS:
            assert isinstance(tool.description, str)
            assert len(tool.description) > 0, (
                f"Tool {tool.name!r} has empty description"
            )

    def test_parameters_model_is_pydantic(self) -> None:
        for tool in ALL_TOOLS:
            assert tool.parameters_model is not None, (
                f"Tool {tool.name!r} has no parameters_model"
            )
            assert issubclass(tool.parameters_model, BaseModel), (
                f"Tool {tool.name!r} parameters_model is not a Pydantic BaseModel"
            )

    def test_handler_is_callable(self) -> None:
        for tool in ALL_TOOLS:
            assert callable(tool.handler), (
                f"Tool {tool.name!r} handler is not callable"
            )

    def test_handler_is_coroutine_function(self) -> None:
        """All tool handlers are expected to be async functions."""
        for tool in ALL_TOOLS:
            assert inspect.iscoroutinefunction(tool.handler), (
                f"Tool {tool.name!r} handler is not an async function"
            )


class TestExpectedToolNames:
    """Make sure the expected tool names are present."""

    EXPECTED_NAMES: set[str] = {
        "extract_pdf",
        "extract_docx",
        "extract_xlsx",
        "extract_pptx",
        "call_doc_intelligence",
        "scrape_webpage",
        "transcribe_audio",
        "read_blob",
        "write_blob",
        "upload_to_search",
        "query_search_index",
        "upsert_cosmos",
        "query_cosmos",
        "generate_embeddings",
        "read_skill",
        "read_skill_file",
        "run_skill_script",
        "devops_get_work_item",
        "devops_list_work_items",
        "devops_query_work_items",
        "devops_get_iterations",
        "devops_get_project",
        "powerbi_execute_dax_query",
        "powerbi_get_dataset_tables",
        "powerbi_list_datasets",
        "powerbi_refresh_dataset",
        "local_files",
    }

    def test_expected_names_match(self) -> None:
        actual_names = {t.name for t in ALL_TOOLS}
        assert actual_names == self.EXPECTED_NAMES

"""Tests for the custom agent registry and agent definitions.

Validates:
- CUSTOM_AGENTS contains the three expected agents
- AgentDefinition Pydantic model validates correctly
- Each agent has non-empty prompts, valid tools, and MCP servers
"""

from __future__ import annotations

import pytest

from app.agents.models import AgentDefinition
from app.agents.registry import CUSTOM_AGENTS
from app.agents.prompts import (
    DATA_ANALYST_PROMPT,
    DOCUMENT_PROCESSOR_PROMPT,
    QA_REVIEWER_PROMPT,
)


# ===========================================================================
# Registry contents
# ===========================================================================

class TestAgentRegistry:

    EXPECTED_AGENTS = ["doc-processor", "data-analyst", "qa-reviewer"]

    def test_registry_has_all_agents(self) -> None:
        assert sorted(CUSTOM_AGENTS.keys()) == sorted(self.EXPECTED_AGENTS)

    def test_all_values_are_agent_definitions(self) -> None:
        for name, defn in CUSTOM_AGENTS.items():
            assert isinstance(defn, AgentDefinition), f"{name} is not AgentDefinition"

    @pytest.mark.parametrize("agent_name", EXPECTED_AGENTS)
    def test_agent_has_display_name(self, agent_name: str) -> None:
        defn = CUSTOM_AGENTS[agent_name]
        assert defn.display_name, f"{agent_name} missing display_name"

    @pytest.mark.parametrize("agent_name", EXPECTED_AGENTS)
    def test_agent_has_description(self, agent_name: str) -> None:
        defn = CUSTOM_AGENTS[agent_name]
        assert len(defn.description) > 10, f"{agent_name} description too short"

    @pytest.mark.parametrize("agent_name", EXPECTED_AGENTS)
    def test_agent_has_tools(self, agent_name: str) -> None:
        defn = CUSTOM_AGENTS[agent_name]
        assert len(defn.tools) >= 3, f"{agent_name} should have >=3 tools"

    @pytest.mark.parametrize("agent_name", EXPECTED_AGENTS)
    def test_agent_has_mcp_servers(self, agent_name: str) -> None:
        defn = CUSTOM_AGENTS[agent_name]
        assert "azure" in defn.mcp_servers

    @pytest.mark.parametrize("agent_name", EXPECTED_AGENTS)
    def test_agent_has_non_empty_prompt(self, agent_name: str) -> None:
        defn = CUSTOM_AGENTS[agent_name]
        assert len(defn.prompt) > 50, f"{agent_name} prompt too short"

    @pytest.mark.parametrize("agent_name", EXPECTED_AGENTS)
    def test_agent_has_reasonable_defaults(self, agent_name: str) -> None:
        defn = CUSTOM_AGENTS[agent_name]
        assert defn.model == "gpt-4.1"
        assert 10 <= defn.max_tool_calls <= 200
        assert 30 <= defn.timeout_seconds <= 600


# ===========================================================================
# AgentDefinition model
# ===========================================================================

class TestAgentDefinition:

    def test_valid_definition(self) -> None:
        defn = AgentDefinition(
            name="test-agent",
            display_name="Test Agent",
            description="A test agent for validation",
            tools=["read_blob", "write_blob"],
            mcp_servers=["azure"],
            prompt="You are a test agent.",
        )
        assert defn.name == "test-agent"
        assert defn.model == "gpt-4.1"
        assert defn.max_tool_calls == 50
        assert defn.timeout_seconds == 300

    def test_custom_fields(self) -> None:
        defn = AgentDefinition(
            name="custom",
            display_name="Custom",
            description="Custom agent",
            tools=["tool_a"],
            mcp_servers=["github"],
            prompt="Custom prompt",
            model="gpt-4o",
            max_tool_calls=100,
            timeout_seconds=600,
        )
        assert defn.model == "gpt-4o"
        assert defn.max_tool_calls == 100
        assert defn.timeout_seconds == 600

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(Exception):
            AgentDefinition(
                name="bad",
                display_name="Bad",
                # missing description, tools, mcp_servers, prompt
            )

    def test_serialization_roundtrip(self) -> None:
        defn = AgentDefinition(
            name="test",
            display_name="Test",
            description="Desc",
            tools=["a", "b"],
            mcp_servers=["azure"],
            prompt="Prompt text",
        )
        data = defn.model_dump()
        restored = AgentDefinition.model_validate(data)
        assert restored == defn


# ===========================================================================
# Prompt content
# ===========================================================================

class TestAgentPrompts:

    def test_document_processor_prompt_content(self) -> None:
        assert "extract" in DOCUMENT_PROCESSOR_PROMPT.lower()

    def test_data_analyst_prompt_content(self) -> None:
        assert "analy" in DATA_ANALYST_PROMPT.lower()

    def test_qa_reviewer_prompt_content(self) -> None:
        assert "review" in QA_REVIEWER_PROMPT.lower() or "quality" in QA_REVIEWER_PROMPT.lower()

    def test_prompts_are_unique(self) -> None:
        prompts = [DOCUMENT_PROCESSOR_PROMPT, DATA_ANALYST_PROMPT, QA_REVIEWER_PROMPT]
        # All distinct
        assert len(set(prompts)) == 3

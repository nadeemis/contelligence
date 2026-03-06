"""End-to-end Phase 3 workflow tests.

Validates the full Phase 3 scenario:
1. MCP configuration + health
2. Custom agent registry
3. Delegation flow
4. Approval flow with triggers
5. Vector search pipeline
6. System prompt integrity

Marked ``@pytest.mark.e2e``.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.models import AgentDefinition
from app.agents.registry import CUSTOM_AGENTS
from app.mcp.config import get_mcp_servers_config
from app.mcp.health import verify_mcp_servers
from app.models.approval_models import (
    ApprovalResponse,
    PendingOperation,
)
from app.prompts.system_prompt import (
    CONTELLIGENCE_AGENT_SYSTEM_PROMPT as SYSTEM_PROMPT,
    SYSTEM_PROMPT_VERSION,
)
from app.services.approval_helpers import describe_operation, summarize_params
from app.services.approval_manager import ApprovalManager
from app.services.approval_triggers import requires_approval
from app.tools.ai.generate_embeddings import GenerateEmbeddingsParams, generate_embeddings
from app.tools.ai.vector_utils import semantic_search
from app.tools.storage.query_search_index import QuerySearchIndexParams, query_search_index


pytestmark = pytest.mark.e2e


class TestPhase3SystemIntegrity:
    """Verify that all Phase 3 components are wired together correctly."""

    def test_system_prompt_version_3(self) -> None:
        """System prompt should be version 3.0.0 with Phase 3 sections."""
        assert SYSTEM_PROMPT_VERSION == "3.0.0"
        # Phase 3 sections
        assert "MCP" in SYSTEM_PROMPT or "mcp" in SYSTEM_PROMPT.lower()
        assert "delegate" in SYSTEM_PROMPT.lower() or "delegation" in SYSTEM_PROMPT.lower()
        assert "approval" in SYSTEM_PROMPT.lower()

    def test_custom_agents_complete(self) -> None:
        """All 3 custom agents are registered with valid definitions."""
        expected = {"doc-processor", "data-analyst", "qa-reviewer"}
        assert set(CUSTOM_AGENTS.keys()) == expected

        for name, defn in CUSTOM_AGENTS.items():
            assert isinstance(defn, AgentDefinition)
            assert len(defn.tools) >= 3
            assert "azure" in defn.mcp_servers
            assert len(defn.prompt) > 50

    def test_mcp_config_structure(self) -> None:
        """MCP configuration has both azure and github servers."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AZURE_MCP_SERVER_URL", None)
            cfg = get_mcp_servers_config()

        assert "azure" in cfg
        assert "github" in cfg
        assert cfg["azure"]["type"] in ("stdio", "http")
        assert cfg["github"]["type"] == "http"


class TestPhase3FullWorkflow:
    """End-to-end workflow simulating a complete Phase 3 interaction."""

    @pytest.mark.asyncio
    async def test_mcp_health_then_delegation_then_approval(self) -> None:
        """
        Scenario:
        1. Check MCP health
        2. Delegate to doc-processor
        3. Trigger approval for write operation
        4. User approves
        5. Verify pipeline complete
        """
        # ── Step 1: MCP Health ──
        config = {
            "azure": {"type": "stdio", "command": ["python", "--version"]},
        }
        health = await verify_mcp_servers(config, timeout=5.0)
        assert health["azure"]["status"] in ("ok", "degraded")

        # ── Step 2: Delegation setup ──
        # Verify agent exists and has proper config
        agent_def = CUSTOM_AGENTS["doc-processor"]
        assert "extract_pdf" in agent_def.tools
        assert "write_blob" in agent_def.tools  # can write results

        # ── Step 3: Approval trigger check ──
        # write_blob with overwrite should trigger approval
        assert requires_approval(
            "write_blob",
            {"overwrite": True, "path": "result.pdf", "container": "outputs"},
            {"require_approval": True},
        )

        # ── Step 4: Full approval lifecycle ──
        mgr = ApprovalManager(timeout_seconds=10)
        desc = describe_operation(
            "write_blob",
            {"path": "result.pdf", "container": "outputs", "overwrite": True},
        )
        ops = [
            PendingOperation(
                tool="write_blob",
                description=desc,
                risk="medium",
                parameters=summarize_params({
                    "path": "result.pdf",
                    "container": "outputs",
                    "overwrite": True,
                }),
            ),
        ]

        async def _user_approves():
            await asyncio.sleep(0.1)
            mgr.submit_response(
                "e2e-sess",
                ApprovalResponse(decision="approved", message="Go ahead"),
            )

        task = asyncio.create_task(_user_approves())
        response = await mgr.request_approval("e2e-sess", ops, desc)
        await task

        assert response.decision == "approved"

    @pytest.mark.asyncio
    async def test_vector_search_with_approval(self) -> None:
        """
        Scenario:
        1. Generate embeddings
        2. Upload to search (requires approval)
        3. Query with vector search
        """
        openai_mock = AsyncMock()
        openai_mock.generate_embeddings.return_value = {
            "model": "text-embedding-3-large",
            "count": 3,
            "embeddings": [[0.1] * 1536 for _ in range(3)],
            "dimensions": 1536,
            "total_tokens": 30,
        }

        search_mock = AsyncMock()
        search_mock.search.return_value = [
            {"id": "doc-1", "title": "Best match", "@search.score": 0.97},
        ]

        ctx = {"openai": openai_mock, "search": search_mock}

        # Step 1: Embed document chunks
        embed_params = GenerateEmbeddingsParams(
            texts=["chunk 1", "chunk 2", "chunk 3"],
            dimensions=1536,
        )
        embed_result = await generate_embeddings.handler(embed_params, ctx)
        assert embed_result["count"] == 3
        assert embed_result["total_tokens"] == 30

        # Step 2: Check upload_to_search requires approval
        assert requires_approval(
            "upload_to_search",
            {"index": "documents", "document_count": 3},
            {"require_approval": True},
        )

        # Step 3: Vector search with first embedding
        search_params = QuerySearchIndexParams(
            index="documents",
            query_type="vector",
            vector=embed_result["embeddings"][0],
            top=5,
        )
        search_result = await query_search_index.handler(search_params, ctx)
        assert search_result["count"] == 1
        assert search_result["results"][0]["@search.score"] == 0.97

    @pytest.mark.asyncio
    async def test_semantic_search_helper_workflow(self) -> None:
        """semantic_search helper as would be called from service code."""
        openai_mock = AsyncMock()
        openai_mock.generate_embeddings.return_value = {
            "embeddings": [[0.1, 0.2, 0.3] * 512],
            "total_tokens": 8,
        }

        search_mock = AsyncMock()
        search_mock.search.return_value = [
            {
                "id": "hit-1",
                "title": "Architecture",
                "@search.score": 0.92,
                "@search.reranker_score": 3.6,
            },
        ]

        results = await semantic_search(
            search_connector=search_mock,
            openai_connector=openai_mock,
            index="contelligence-documents",
            query_text="event-driven architecture patterns",
            top=10,
            semantic_configuration="default-semantic-config",
        )

        assert len(results) == 1
        assert results[0]["@search.reranker_score"] == 3.6

        # Verify semantic mode was used
        call_kwargs = search_mock.search.call_args.kwargs
        assert call_kwargs["query_type"] == "semantic"


class TestPhase3ReadWriteTriggerMatrix:
    """Comprehensive cross-check of all approval triggers."""

    SAFE_TOOLS = [
        "read_blob",
        "query_cosmos",
        "query_search_index",
        "extract_pdf",
        "extract_docx",
        "extract_xlsx",
        "extract_pptx",
        "call_doc_intelligence",
        "scrape_webpage",
        "transcribe_audio",
        "generate_embeddings",
        "delegate_task",
    ]

    DANGEROUS_TOOLS = [
        ("delete_blob", {}, True),
        ("upsert_cosmos", {}, True),
        ("upload_to_search", {}, True),
        ("write_blob", {"overwrite": True}, True),
        ("mcp_delete_resource", {}, True),
        ("mcp_delete_container", {}, True),
        ("mcp_update_schedule", {}, True),
        ("mcp_create_schedule", {}, True),
    ]

    @pytest.mark.parametrize("tool_name", SAFE_TOOLS)
    def test_safe_tools_no_approval(self, tool_name: str) -> None:
        assert not requires_approval(tool_name, {}, {"require_approval": True})

    @pytest.mark.parametrize("tool_name,params,expected", DANGEROUS_TOOLS)
    def test_dangerous_tools_require_approval(
        self,
        tool_name: str,
        params: dict,
        expected: bool,
    ) -> None:
        assert requires_approval(tool_name, params, {"require_approval": True}) == expected

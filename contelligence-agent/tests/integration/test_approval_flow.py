"""Integration tests for human-in-the-loop approval flow.

Tests the full approval lifecycle: approval_manager blocks → SSE event →
user responds via /reply → agent continues.

Marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.models.approval_models import (
    ApprovalResponse,
    PendingOperation,
)
from app.services.approval_manager import ApprovalManager
from app.services.approval_triggers import requires_approval
from app.services.approval_helpers import describe_operation, summarize_params


pytestmark = pytest.mark.integration


class TestApprovalFlowIntegration:

    @pytest.mark.asyncio
    async def test_full_approval_lifecycle(self) -> None:
        """Simulate: trigger → request → user approves → agent continues."""
        mgr = ApprovalManager(timeout_seconds=10)

        # 1. Check trigger
        tool_name = "delete_blob"
        params = {"container": "staging", "path": "old-data.csv"}
        assert requires_approval(tool_name, params, {"require_approval": True})

        # 2. Build operation description
        desc = describe_operation(tool_name, params)
        summary = summarize_params(params)
        assert "old-data.csv" in desc

        ops = [
            PendingOperation(
                tool=tool_name,
                description=desc,
                risk="high",
                parameters=summary,
            )
        ]

        # 3. Agent requests approval (blocks)
        async def _user_approves():
            await asyncio.sleep(0.1)
            assert mgr.has_pending("sess-flow")
            pending = mgr.get_pending("sess-flow")
            assert pending is not None
            assert len(pending.operations) == 1
            assert pending.operations[0].risk == "high"
            mgr.submit_response(
                "sess-flow",
                ApprovalResponse(decision="approved", message="Proceed"),
            )

        task = asyncio.create_task(_user_approves())
        response = await mgr.request_approval("sess-flow", ops, "About to delete file")
        await task

        assert response.decision == "approved"
        # After approval, no pending state
        assert not mgr.has_pending("sess-flow")

    @pytest.mark.asyncio
    async def test_rejection_flow(self) -> None:
        """User rejects → agent receives rejection."""
        mgr = ApprovalManager(timeout_seconds=10)

        ops = [
            PendingOperation(
                tool="upsert_cosmos",
                description="Upsert document",
                risk="medium",
                parameters={"container": "sessions"},
            )
        ]

        async def _user_rejects():
            await asyncio.sleep(0.05)
            mgr.submit_response(
                "sess-reject",
                ApprovalResponse(
                    decision="rejected",
                    message="Don't modify production data",
                ),
            )

        task = asyncio.create_task(_user_rejects())
        response = await mgr.request_approval("sess-reject", ops, "Upsert operation")
        await task

        assert response.decision == "rejected"
        assert "production" in response.message

    @pytest.mark.asyncio
    async def test_modification_flow(self) -> None:
        """User modifies instructions → agent receives modified response."""
        mgr = ApprovalManager(timeout_seconds=10)

        ops = [
            PendingOperation(
                tool="write_blob",
                description="Write report.pdf to container 'outputs'",
                risk="medium",
                parameters={"container": "outputs", "path": "report.pdf"},
            )
        ]

        async def _user_modifies():
            await asyncio.sleep(0.05)
            mgr.submit_response(
                "sess-modify",
                ApprovalResponse(
                    decision="modified",
                    message="Save to archive/ instead of outputs/",
                ),
            )

        task = asyncio.create_task(_user_modifies())
        response = await mgr.request_approval("sess-modify", ops, "Write file")
        await task

        assert response.decision == "modified"
        assert "archive" in response.message

    @pytest.mark.asyncio
    async def test_multi_operation_approval(self) -> None:
        """Multiple operations in a single approval request."""
        mgr = ApprovalManager(timeout_seconds=10)

        ops = [
            PendingOperation(
                tool="write_blob",
                description="Write file",
                risk="medium",
                parameters={"path": "a.txt"},
            ),
            PendingOperation(
                tool="delete_blob",
                description="Delete old file",
                risk="high",
                parameters={"path": "old.txt"},
            ),
            PendingOperation(
                tool="upload_to_search",
                description="Upload 10 documents",
                risk="medium",
                parameters={"count": 10},
            ),
        ]

        async def _approve_all():
            await asyncio.sleep(0.05)
            pending = mgr.get_pending("sess-multi")
            assert pending is not None
            assert len(pending.operations) == 3
            mgr.submit_response(
                "sess-multi",
                ApprovalResponse(decision="approved", message="All ok"),
            )

        task = asyncio.create_task(_approve_all())
        response = await mgr.request_approval("sess-multi", ops, "Batch operations")
        await task

        assert response.decision == "approved"

    @pytest.mark.asyncio
    async def test_timeout_with_cleanup(self) -> None:
        """Timeout should auto-reject and clean up state."""
        mgr = ApprovalManager(timeout_seconds=0.2)

        ops = [
            PendingOperation(
                tool="delete_blob",
                description="Delete file",
                risk="high",
                parameters={},
            )
        ]

        response = await mgr.request_approval("sess-timeout", ops, "Delete operation")

        assert response.decision == "rejected"
        assert "timed out" in response.message.lower()
        assert not mgr.has_pending("sess-timeout")


class TestApprovalTriggerIntegration:

    def test_read_write_trigger_matrix(self) -> None:
        """Verify the trigger matrix for common operations."""
        opts = {"require_approval": True}

        # Reads — no approval
        assert not requires_approval("read_blob", {}, opts)
        assert not requires_approval("query_cosmos", {}, opts)
        assert not requires_approval("query_search_index", {}, opts)
        assert not requires_approval("extract_pdf", {}, opts)
        assert not requires_approval("generate_embeddings", {}, opts)

        # Writes — need approval
        assert requires_approval("delete_blob", {}, opts)
        assert requires_approval("upsert_cosmos", {}, opts)
        assert requires_approval("upload_to_search", {}, opts)
        assert requires_approval("write_blob", {"overwrite": True}, opts)

        # write_blob without overwrite — no approval
        assert not requires_approval("write_blob", {"overwrite": False}, opts)
        assert not requires_approval("write_blob", {}, opts)

    def test_mcp_wildcards(self) -> None:
        opts = {"require_approval": True}
        assert requires_approval("mcp_delete_resource", {}, opts)
        assert requires_approval("mcp_delete_anything", {}, opts)
        assert requires_approval("mcp_update_schedule", {}, opts)
        assert requires_approval("mcp_create_schedule", {}, opts)

    def test_batch_edge_cases(self) -> None:
        opts = {"require_approval": True}
        # Exactly at threshold — no approval
        assert not requires_approval("custom", {"count": 50}, opts)
        # One over — approval needed
        assert requires_approval("custom", {"count": 51}, opts)

"""Tests for the ApprovalManager and approval workflow helpers.

Covers:
- ApprovalManager blocking and unblocking
- Timeout auto-rejection
- submit_response / has_pending / get_pending
- requires_approval trigger logic
- describe_operation / summarize_params helpers
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.models.approval_models import (
    ApprovalRequest,
    ApprovalResponse,
    PendingOperation,
)
from app.services.approval_manager import ApprovalManager
from app.services.approval_triggers import (
    APPROVAL_TRIGGERS,
    BATCH_THRESHOLD,
    get_risk_level,
    requires_approval,
)
from app.services.approval_helpers import describe_operation, summarize_params


# ===========================================================================
# ApprovalManager — blocking / unblocking
# ===========================================================================

class TestApprovalManagerBlocking:

    @pytest.mark.asyncio
    async def test_request_blocks_until_response(self) -> None:
        """request_approval should block until submit_response is called."""
        mgr = ApprovalManager(timeout_seconds=10)
        ops = [PendingOperation(
            tool="write_blob",
            description="Write file",
            risk="medium",
            parameters={"path": "test.txt"},
        )]

        async def _submit_after_delay():
            await asyncio.sleep(0.1)
            mgr.submit_response(
                "sess-1",
                ApprovalResponse(decision="approved", message="ok"),
            )

        task = asyncio.create_task(_submit_after_delay())
        response = await mgr.request_approval("sess-1", ops, "Write test.txt")
        await task

        assert response.decision == "approved"
        assert response.message == "ok"

    @pytest.mark.asyncio
    async def test_submit_unblocks_waiting_coroutine(self) -> None:
        mgr = ApprovalManager(timeout_seconds=10)
        ops = [PendingOperation(
            tool="delete_blob",
            description="Delete file",
            risk="high",
            parameters={},
        )]

        async def _approve():
            await asyncio.sleep(0.05)
            assert mgr.has_pending("sess-2")
            mgr.submit_response(
                "sess-2",
                ApprovalResponse(decision="rejected", message="no"),
            )

        task = asyncio.create_task(_approve())
        response = await mgr.request_approval("sess-2", ops, "Delete operation")
        await task

        assert response.decision == "rejected"

    @pytest.mark.asyncio
    async def test_modified_response(self) -> None:
        mgr = ApprovalManager(timeout_seconds=10)
        ops = [PendingOperation(
            tool="write_blob",
            description="Write",
            risk="medium",
            parameters={},
        )]

        async def _modify():
            await asyncio.sleep(0.05)
            mgr.submit_response(
                "sess-3",
                ApprovalResponse(
                    decision="modified",
                    message="Change destination to archive/",
                ),
            )

        task = asyncio.create_task(_modify())
        response = await mgr.request_approval("sess-3", ops, "Write file")
        await task

        assert response.decision == "modified"
        assert "archive" in response.message


# ===========================================================================
# ApprovalManager — timeout
# ===========================================================================

class TestApprovalManagerTimeout:

    @pytest.mark.asyncio
    async def test_timeout_auto_rejects(self) -> None:
        mgr = ApprovalManager(timeout_seconds=0.2)
        ops = [PendingOperation(
            tool="upsert_cosmos",
            description="Upsert doc",
            risk="medium",
            parameters={},
        )]

        response = await mgr.request_approval("sess-timeout", ops, "Upsert")

        assert response.decision == "rejected"
        assert "timed out" in response.message.lower()

    @pytest.mark.asyncio
    async def test_cleanup_after_timeout(self) -> None:
        mgr = ApprovalManager(timeout_seconds=0.1)
        ops = [PendingOperation(
            tool="write_blob",
            description="Write",
            risk="medium",
            parameters={},
        )]

        await mgr.request_approval("sess-cleanup", ops, "Write")

        assert not mgr.has_pending("sess-cleanup")
        assert mgr.get_pending("sess-cleanup") is None


# ===========================================================================
# ApprovalManager — state queries
# ===========================================================================

class TestApprovalManagerState:

    @pytest.mark.asyncio
    async def test_has_pending(self) -> None:
        mgr = ApprovalManager(timeout_seconds=10)
        assert not mgr.has_pending("nope")

        ops = [PendingOperation(
            tool="write_blob",
            description="Write",
            risk="medium",
            parameters={},
        )]

        async def _check_and_respond():
            await asyncio.sleep(0.05)
            assert mgr.has_pending("sess-check")
            pending = mgr.get_pending("sess-check")
            assert pending is not None
            assert pending.session_id == "sess-check"
            mgr.submit_response(
                "sess-check",
                ApprovalResponse(decision="approved"),
            )

        task = asyncio.create_task(_check_and_respond())
        await mgr.request_approval("sess-check", ops, "Test")
        await task

    def test_submit_response_no_pending_raises(self) -> None:
        mgr = ApprovalManager()
        with pytest.raises(KeyError, match="No pending approval"):
            mgr.submit_response(
                "nonexistent",
                ApprovalResponse(decision="approved"),
            )

    @pytest.mark.asyncio
    async def test_cleanup_removes_state(self) -> None:
        mgr = ApprovalManager(timeout_seconds=10)
        ops = [PendingOperation(
            tool="write_blob",
            description="Write",
            risk="medium",
            parameters={},
        )]

        async def _respond():
            await asyncio.sleep(0.05)
            mgr.submit_response("s1", ApprovalResponse(decision="approved"))

        task = asyncio.create_task(_respond())
        await mgr.request_approval("s1", ops, "Test")
        await task

        # After response processed, both pending and event should be cleaned
        assert not mgr.has_pending("s1")


# ===========================================================================
# ApprovalManager — concurrent sessions
# ===========================================================================

class TestApprovalManagerConcurrent:

    @pytest.mark.asyncio
    async def test_independent_sessions(self) -> None:
        """Two sessions can have concurrent pending approvals."""
        mgr = ApprovalManager(timeout_seconds=10)
        ops = [PendingOperation(
            tool="write_blob",
            description="Write",
            risk="medium",
            parameters={},
        )]

        async def _approve(sess_id: str, decision: str, delay: float):
            await asyncio.sleep(delay)
            mgr.submit_response(sess_id, ApprovalResponse(decision=decision))

        t1 = asyncio.create_task(_approve("a", "approved", 0.1))
        t2 = asyncio.create_task(_approve("b", "rejected", 0.15))

        r1, r2 = await asyncio.gather(
            mgr.request_approval("a", ops, "Op A"),
            mgr.request_approval("b", ops, "Op B"),
        )
        await asyncio.gather(t1, t2)

        assert r1.decision == "approved"
        assert r2.decision == "rejected"


# ===========================================================================
# requires_approval
# ===========================================================================

class TestRequiresApproval:

    def test_write_blob_no_overwrite(self) -> None:
        """write_blob without overwrite should NOT require approval."""
        result = requires_approval(
            "write_blob", {"overwrite": False}, {"require_approval": True}
        )
        assert result is False

    def test_write_blob_with_overwrite(self) -> None:
        result = requires_approval(
            "write_blob", {"overwrite": True}, {"require_approval": True}
        )
        assert result is True

    def test_delete_blob_always(self) -> None:
        result = requires_approval(
            "delete_blob", {}, {"require_approval": True}
        )
        assert result is True

    def test_upload_to_search_always(self) -> None:
        result = requires_approval(
            "upload_to_search", {}, {"require_approval": True}
        )
        assert result is True

    def test_upsert_cosmos_always(self) -> None:
        result = requires_approval(
            "upsert_cosmos", {}, {"require_approval": True}
        )
        assert result is True

    def test_mcp_delete_wildcard(self) -> None:
        result = requires_approval(
            "mcp_delete_resource", {}, {"require_approval": True}
        )
        assert result is True

    def test_mcp_update_wildcard(self) -> None:
        result = requires_approval(
            "mcp_update_schedule", {}, {"require_approval": True}
        )
        assert result is True

    def test_mcp_create_schedule(self) -> None:
        result = requires_approval(
            "mcp_create_schedule", {}, {"require_approval": True}
        )
        assert result is True

    def test_read_operations_no_approval(self) -> None:
        """Read-only operations should not trigger approval."""
        assert not requires_approval("read_blob", {}, {"require_approval": True})
        assert not requires_approval("query_cosmos", {}, {"require_approval": True})
        assert not requires_approval("query_search_index", {}, {"require_approval": True})

    def test_opt_out(self) -> None:
        """Sessions with require_approval=False bypass all checks."""
        result = requires_approval(
            "delete_blob", {}, {"require_approval": False}
        )
        assert result is False

    def test_batch_threshold(self) -> None:
        """Operations exceeding BATCH_THRESHOLD require approval."""
        result = requires_approval(
            "some_custom_tool",
            {"count": BATCH_THRESHOLD + 1},
            {"require_approval": True},
        )
        assert result is True

    def test_batch_list_threshold(self) -> None:
        result = requires_approval(
            "some_custom_tool",
            {"documents": list(range(BATCH_THRESHOLD + 1))},
            {"require_approval": True},
        )
        assert result is True

    def test_below_batch_threshold(self) -> None:
        result = requires_approval(
            "some_custom_tool",
            {"count": BATCH_THRESHOLD - 1},
            {"require_approval": True},
        )
        assert result is False


# ===========================================================================
# get_risk_level
# ===========================================================================

class TestGetRiskLevel:

    def test_delete_blob_high(self) -> None:
        assert get_risk_level("delete_blob") == "high"

    def test_write_blob_medium(self) -> None:
        assert get_risk_level("write_blob") == "medium"

    def test_mcp_delete_resource_high(self) -> None:
        assert get_risk_level("mcp_delete_resource") == "high"

    def test_unknown_tool_defaults_medium(self) -> None:
        assert get_risk_level("unknown_tool") == "medium"


# ===========================================================================
# describe_operation
# ===========================================================================

class TestDescribeOperation:

    def test_write_blob_description(self) -> None:
        desc = describe_operation(
            "write_blob",
            {"path": "output.pdf", "container": "docs", "overwrite": True},
        )
        assert "output.pdf" in desc
        assert "docs" in desc
        assert "overwrite" in desc.lower()

    def test_delete_blob_description(self) -> None:
        desc = describe_operation(
            "delete_blob",
            {"path": "old.csv", "container": "staging"},
        )
        assert "old.csv" in desc
        assert "staging" in desc

    def test_upsert_cosmos_description(self) -> None:
        desc = describe_operation(
            "upsert_cosmos",
            {"container": "sessions"},
        )
        assert "sessions" in desc

    def test_unknown_tool_fallback(self) -> None:
        desc = describe_operation("custom_tool", {"foo": "bar"})
        assert "custom_tool" in desc

    def test_upload_to_search_description(self) -> None:
        desc = describe_operation(
            "upload_to_search",
            {"index": "documents", "document_count": 10},
        )
        assert "10" in desc
        assert "documents" in desc


# ===========================================================================
# summarize_params
# ===========================================================================

class TestSummarizeParams:

    def test_extracts_key_params(self) -> None:
        summary = summarize_params({
            "container": "docs",
            "path": "file.pdf",
            "overwrite": True,
            "content": "a" * 10_000,  # should be ignored (not in summary keys)
        })
        assert summary["container"] == "docs"
        assert summary["path"] == "file.pdf"
        assert summary["overwrite"] is True
        assert "content" not in summary

    def test_truncates_long_strings(self) -> None:
        summary = summarize_params({
            "query": "x" * 300,
        })
        assert len(summary["query"]) <= 201  # 200 + "…"

    def test_summarizes_lists(self) -> None:
        summary = summarize_params({
            "filters": ["a", "b", "c"],
        })
        assert "3 items" in summary["filters"]

    def test_empty_params(self) -> None:
        assert summarize_params({}) == {}


# ===========================================================================
# Pydantic models
# ===========================================================================

class TestApprovalModels:

    def test_pending_operation(self) -> None:
        op = PendingOperation(
            tool="write_blob",
            description="Write file",
            risk="medium",
            parameters={"path": "f.txt"},
        )
        assert op.tool == "write_blob"
        assert op.risk == "medium"

    def test_approval_response_defaults(self) -> None:
        resp = ApprovalResponse(decision="approved")
        assert resp.message == ""
        assert resp.timestamp is not None

    def test_approval_request(self) -> None:
        req = ApprovalRequest(
            session_id="s1",
            operations=[],
            message="Test",
        )
        assert req.response is None
        assert req.requested_at is not None

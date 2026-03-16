"""Shared pytest fixtures for the contelligence-agent test suite."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.connectors.blob_connector import BlobInfo, BlobProperties
from app.core.tool_registry import ToolRegistry
from app.models.session_models import (
    ConversationTurn,
    OutputArtifact,
    SessionMetrics,
    SessionRecord,
    SessionStatus,
    ToolCallRecord,
)
from app.tools import ALL_TOOLS, register_all_tools


# ---------------------------------------------------------------------------
# Sample data factories (Phase 2)
# ---------------------------------------------------------------------------

def create_sample_session(
    *,
    session_id: str | None = None,
    status: SessionStatus = SessionStatus.COMPLETED,
    instruction: str = "Test instruction",
    model: str = "gpt-4.1",
    user_id: str | None = None,
) -> SessionRecord:
    """Build a ``SessionRecord`` suitable for testing."""
    now = datetime.now(timezone.utc)
    return SessionRecord(
        id=session_id or str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        status=status,
        model=model,
        instruction=instruction,
        user_id=user_id,
        metrics=SessionMetrics(),
    )


def create_sample_turns(
    session_id: str,
    count: int = 3,
) -> list[ConversationTurn]:
    """Build a list of ``ConversationTurn`` instances with sequential numbering."""
    now = datetime.now(timezone.utc)
    turns: list[ConversationTurn] = []
    for i in range(count):
        role = "user" if i % 2 == 0 else "assistant"
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            session_id=session_id,
            sequence=i,
            timestamp=now,
            role=role,
            prompt=f"Message {i}" if role == "user" else None,
            content=f"Response {i}" if role == "assistant" else None,
        )
        turns.append(turn)
    return turns


def create_sample_outputs(
    session_id: str,
    count: int = 2,
) -> list[OutputArtifact]:
    """Build a list of ``OutputArtifact`` instances for testing."""
    now = datetime.now(timezone.utc)
    return [
        OutputArtifact(
            id=str(uuid.uuid4()),
            session_id=session_id,
            name=f"output_{i}.json",
            description=f"Test output {i}",
            artifact_type="json",
            storage_type="blob",
            storage_location=f"agent-outputs/{session_id}/output_{i}.json",
            size_bytes=1024 * (i + 1),
            content_type="application/json",
            created_at=now,
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# MockSessionStore (in-memory SessionStore for tests)
# ---------------------------------------------------------------------------

class MockSessionStore:
    """In-memory implementation of ``SessionStore`` for unit/integration testing.

    Stores data in plain dicts so no Cosmos DB connection is needed.
    """

    def __init__(self) -> None:
        self.sessions: dict[str, SessionRecord] = {}
        self.turns: dict[str, list[ConversationTurn]] = {}
        self.outputs: dict[str, list[OutputArtifact]] = {}

    async def save_session(self, record: SessionRecord) -> None:
        self.sessions[record.id] = record

    async def get_session(self, session_id: str) -> SessionRecord:
        from app.models.exceptions import SessionNotFoundError
        if session_id not in self.sessions:
            raise SessionNotFoundError(session_id)
        return self.sessions[session_id]

    async def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        summary: str | None = None,
    ) -> None:
        record = await self.get_session(session_id)
        record.status = status
        record.updated_at = datetime.now(timezone.utc)
        if summary is not None:
            record.summary = summary
        self.sessions[session_id] = record

    async def update_session_metrics(
        self,
        session_id: str,
        **metric_updates: int | float,
    ) -> None:
        record = await self.get_session(session_id)
        for key, value in metric_updates.items():
            if hasattr(record.metrics, key):
                current = getattr(record.metrics, key)
                setattr(record.metrics, key, current + value)
        record.updated_at = datetime.now(timezone.utc)
        self.sessions[session_id] = record

    async def list_sessions(
        self,
        status: SessionStatus | None = None,
        user_id: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[SessionRecord]:
        records = list(self.sessions.values())
        if status is not None:
            records = [r for r in records if r.status == status]
        if user_id is not None:
            records = [r for r in records if r.user_id == user_id]
        if since is not None:
            records = [r for r in records if r.created_at >= since]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    async def save_turn(self, turn: ConversationTurn) -> None:
        if turn.session_id not in self.turns:
            self.turns[turn.session_id] = []
        # Upsert: replace if same id exists
        existing = [t for t in self.turns[turn.session_id] if t.id != turn.id]
        existing.append(turn)
        existing.sort(key=lambda t: t.sequence)
        self.turns[turn.session_id] = existing

    async def get_turns(self, session_id: str) -> list[ConversationTurn]:
        return sorted(
            self.turns.get(session_id, []),
            key=lambda t: t.sequence,
        )

    async def update_tool_call(
        self,
        session_id: str,
        tool_name: str,
        result: dict[str, Any] | None,
        result_blob_ref: str | None,
        completed_at: datetime,
        status: str,
        error: str | None = None,
    ) -> None:
        turns = self.turns.get(session_id, [])
        for turn in reversed(turns):
            if (
                turn.role == "tool"
                and turn.tool_call is not None
                and turn.tool_call.tool_name == tool_name
                and turn.tool_call.status == "running"
            ):
                turn.tool_call.result = result
                turn.tool_call.result_blob_ref = result_blob_ref
                turn.tool_call.completed_at = completed_at
                turn.tool_call.duration_ms = int(
                    (completed_at - turn.tool_call.started_at).total_seconds() * 1000
                )
                turn.tool_call.status = status
                if error is not None:
                    turn.tool_call.error = error
                break

    async def save_output(self, artifact: OutputArtifact) -> None:
        if artifact.session_id not in self.outputs:
            self.outputs[artifact.session_id] = []
        self.outputs[artifact.session_id].append(artifact)

    async def get_outputs(self, session_id: str) -> list[OutputArtifact]:
        return self.outputs.get(session_id, [])

    async def get_output(self, session_id: str, output_id: str) -> OutputArtifact:
        from app.models.exceptions import SessionNotFoundError
        for artifact in self.outputs.get(session_id, []):
            if artifact.id == output_id:
                return artifact
        raise SessionNotFoundError(f"Output {output_id} in session {session_id}")

    async def delete_turns(self, session_id: str) -> int:
        turns = self.turns.pop(session_id, [])
        return len(turns)

    async def delete_outputs(self, session_id: str) -> int:
        outputs = self.outputs.pop(session_id, [])
        return len(outputs)

    async def delete_events(self, session_id: str) -> int:
        return 0  # MockSessionStore does not track events

    async def delete_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Phase 2 fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_session_store() -> MockSessionStore:
    """Provide an in-memory ``MockSessionStore``."""
    return MockSessionStore()


@pytest.fixture()
def sample_session() -> SessionRecord:
    """A ready-made ``SessionRecord`` for tests."""
    return create_sample_session()


# ---------------------------------------------------------------------------
# Mock connector fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_blob_connector() -> AsyncMock:
    """AsyncMock that mimics BlobConnectorAdapter."""
    connector = AsyncMock()

    # list_blobs returns a list of BlobInfo dataclass instances.
    connector.list_blobs.return_value = [
        BlobInfo(name="doc1.pdf", size=1024, content_type="application/pdf"),
        BlobInfo(name="doc2.pdf", size=2048, content_type="application/pdf"),
    ]

    # download_blob returns raw bytes.
    connector.download_blob.return_value = b"fake-file-bytes"

    # upload_blob returns None (fire-and-forget).
    connector.upload_blob.return_value = None

    # get_blob_properties returns a BlobProperties dataclass.
    connector.get_blob_properties.return_value = BlobProperties(
        name="doc1.pdf",
        size=1024,
        content_type="application/pdf",
        metadata={"source": "test"},
    )

    return connector


@pytest.fixture()
def mock_search_connector() -> AsyncMock:
    """AsyncMock that mimics SearchConnectorAdapter."""
    connector = AsyncMock()

    # upload_documents returns a dict with succeeded/failed counts.
    connector.upload_documents.return_value = {"succeeded": 2, "failed": 0}

    # search returns a list of result dicts.
    connector.search.return_value = [
        {"id": "1", "title": "Result 1", "@search.score": 0.95},
        {"id": "2", "title": "Result 2", "@search.score": 0.85},
    ]

    return connector


@pytest.fixture()
def mock_cosmos_connector() -> AsyncMock:
    """AsyncMock that mimics CosmosConnectorAdapter."""
    connector = AsyncMock()

    # upsert returns the upserted document (with Cosmos system props).
    connector.upsert.return_value = {
        "id": "doc-123",
        "_etag": '"etag-value"',
        "_rid": "rid-value",
        "_ts": 1700000000,
    }

    # query returns a list of documents.
    connector.query.return_value = [
        {"id": "doc-1", "status": "active"},
        {"id": "doc-2", "status": "active"},
    ]

    return connector


@pytest.fixture()
def mock_doc_intelligence_connector() -> AsyncMock:
    """AsyncMock that mimics DocIntelligenceConnectorAdapter."""
    connector = AsyncMock()

    # analyze returns structured extraction results.
    connector.analyze.return_value = {
        "text": "Sample extracted text",
        "tables": [],
        "key_value_pairs": [],
        "layout": [{"role": "title", "content": "Document Title"}],
        "page_count": 1,
    }

    return connector


@pytest.fixture()
def mock_openai_connector() -> AsyncMock:
    """AsyncMock that mimics OpenAIConnectorAdapter."""
    connector = AsyncMock()

    # generate_embeddings returns a dict with flat embedding vectors (Phase 3 format).
    connector.generate_embeddings.return_value = {
        "model": "text-embedding-3-large",
        "count": 2,
        "embeddings": [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ],
        "dimensions": 3,
        "total_tokens": 12,
    }

    # get_client returns a mock AsyncAzureOpenAI client.
    mock_client = AsyncMock()
    connector.get_client.return_value = mock_client

    return connector


# ---------------------------------------------------------------------------
# Tool context fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def tool_context(
    mock_blob_connector: AsyncMock,
    mock_search_connector: AsyncMock,
    mock_cosmos_connector: AsyncMock,
    mock_doc_intelligence_connector: AsyncMock,
    mock_openai_connector: AsyncMock,
) -> dict[str, Any]:
    """Build the context dict passed to every tool handler."""
    return {
        "blob": mock_blob_connector,
        "search": mock_search_connector,
        "cosmos": mock_cosmos_connector,
        "doc_intelligence": mock_doc_intelligence_connector,
        "openai": mock_openai_connector,
        "settings": SimpleNamespace(
            COPILOT_MODEL="gpt-4.1",
            AZURE_OPENAI_ENDPOINT="https://test.openai.azure.com",
        ),
    }


# ---------------------------------------------------------------------------
# Tool registry fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def tool_registry() -> ToolRegistry:
    """Create a ToolRegistry populated with ALL_TOOLS."""
    registry = ToolRegistry()
    register_all_tools(registry)
    return registry


# ---------------------------------------------------------------------------
# Mock OpenAI client fixture (for agent session tests)
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_openai_client() -> AsyncMock:
    """AsyncMock that simulates chat.completions.create.

    Returns a response with a single choice whose message has content and
    no tool calls (i.e. a final text response).
    """
    client = AsyncMock()

    # Build a mock ChatCompletionMessage.
    mock_message = MagicMock()
    mock_message.role = "assistant"
    mock_message.content = "Here is my response."
    mock_message.tool_calls = None

    # Build one choice wrapping the message.
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"

    # The response object returned by chat.completions.create.
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    client.chat.completions.create.return_value = mock_response

    return client


# ===========================================================================
# Phase 3 fixtures
# ===========================================================================

@pytest.fixture()
def mock_mcp_config() -> dict[str, dict[str, Any]]:
    """MCP server configuration for testing (stdio + GitHub HTTP)."""
    return {
        "azure": {
            "type": "stdio",
            "command": ["azmcp", "server", "start"],
        },
        "github": {
            "type": "http",
            "url": "https://api.githubcopilot.com/mcp/",
            "auth": {
                "type": "token",
                "token_source": "keyvault",
                "secret_name": "github-copilot-token",
                "token": "ghp_test_token_12345",
            },
        },
    }


@pytest.fixture()
def mock_mcp_config_http() -> dict[str, dict[str, Any]]:
    """MCP server configuration with Azure in HTTP (sidecar) mode."""
    return {
        "azure": {
            "type": "http",
            "url": "http://azure-mcp:5008",
        },
        "github": {
            "type": "http",
            "url": "https://api.githubcopilot.com/mcp/",
            "auth": {
                "type": "token",
                "token_source": "keyvault",
                "secret_name": "github-copilot-token",
                "token": "ghp_test_token_12345",
            },
        },
    }


@pytest.fixture()
def mock_openai_embeddings() -> dict[str, Any]:
    """Phase 3 style embedding response (flat list[list[float]])."""
    return {
        "model": "text-embedding-3-large",
        "count": 2,
        "embeddings": [[0.1, 0.2, 0.3] * 512, [0.4, 0.5, 0.6] * 512],
        "dimensions": 1536,
        "total_tokens": 24,
    }


@pytest.fixture()
def mock_vector_search_results() -> list[dict[str, Any]]:
    """Typical search results with vector/reranker scores."""
    return [
        {
            "id": "chunk-001",
            "title": "Architecture Overview",
            "content": "Contelligence uses event-driven microservices...",
            "@search.score": 0.96,
            "@search.reranker_score": 3.85,
        },
        {
            "id": "chunk-002",
            "title": "Deployment Guide",
            "content": "Deploy using Azure Container Apps...",
            "@search.score": 0.91,
            "@search.reranker_score": 3.42,
        },
    ]


@pytest.fixture()
def test_agent_definitions() -> dict[str, Any]:
    """Expected custom agent names and properties for validation."""
    return {
        "expected_agents": ["doc-processor", "data-analyst", "qa-reviewer"],
        "expected_tools_minimum": 3,
        "expected_mcp_servers": ["azure"],
    }


@pytest.fixture()
def approval_manager():
    """Fresh ApprovalManager instance for testing."""
    from app.services.approval_manager import ApprovalManager
    return ApprovalManager(timeout_seconds=5)


@pytest.fixture()
def sample_pending_operations() -> list[dict[str, Any]]:
    """Pending operations for approval testing."""
    return [
        {
            "tool": "write_blob",
            "description": "Write 'report.pdf' to container 'outputs' (overwrite)",
            "risk": "medium",
            "parameters": {
                "container": "outputs",
                "path": "report.pdf",
                "overwrite": True,
            },
        },
        {
            "tool": "delete_blob",
            "description": "Delete 'old-data.csv' from container 'staging'",
            "risk": "high",
            "parameters": {
                "container": "staging",
                "path": "old-data.csv",
            },
        },
    ]

"""AC-10: GET /sessions/{id}/outputs/{output_id}/download.

Integration tests for the download endpoint — verifies behaviour for
blob, cosmos, and search_index storage types.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import (
    get_agent_service,
    get_blob_connector,
    get_cosmos_connector,
    get_session_store,
)
from app.models.session_models import OutputArtifact
from tests.conftest import MockSessionStore, create_sample_session


def _create_test_app(
    store: MockSessionStore,
    blob: AsyncMock | None = None,
    cosmos: AsyncMock | None = None,
) -> FastAPI:
    from app.routers import agent, health

    app = FastAPI()
    app.include_router(agent.router, prefix="/api/agent")
    app.include_router(health.router)
    app.dependency_overrides[get_session_store] = lambda: store
    svc = MagicMock()
    app.dependency_overrides[get_agent_service] = lambda: svc
    # Always override both connectors — the download endpoint depends on both
    app.dependency_overrides[get_blob_connector] = lambda: (blob or AsyncMock())
    app.dependency_overrides[get_cosmos_connector] = lambda: (cosmos or AsyncMock())
    return app


class TestDownloadBlobOutput:
    @pytest.fixture(autouse=True)
    async def setup(self) -> None:
        self.store = MockSessionStore()
        session = create_sample_session(session_id="s-dl-1")
        await self.store.save_session(session)

        self.artifact_id = str(uuid.uuid4())
        artifact = OutputArtifact(
            id=self.artifact_id,
            session_id="s-dl-1",
            name="result.json",
            description="Blob output",
            artifact_type="json",
            storage_type="blob",
            storage_location="agent-outputs/result.json",
            size_bytes=128,
            content_type="application/json",
            created_at=datetime.now(timezone.utc),
        )
        await self.store.save_output(artifact)

        self.blob_mock = AsyncMock()
        self.blob_mock.download_blob.return_value = b'{"key": "value"}'

        self.app = _create_test_app(self.store, blob=self.blob_mock)
        self.client = TestClient(self.app)

    def test_blob_download_returns_bytes(self) -> None:
        url = f"/api/agent/sessions/s-dl-1/outputs/{self.artifact_id}/download"
        resp = self.client.get(url)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert b"key" in resp.content

    def test_blob_download_has_content_disposition(self) -> None:
        url = f"/api/agent/sessions/s-dl-1/outputs/{self.artifact_id}/download"
        resp = self.client.get(url)
        assert "content-disposition" in resp.headers
        assert "result.json" in resp.headers["content-disposition"]


class TestDownloadCosmosOutput:
    @pytest.fixture(autouse=True)
    async def setup(self) -> None:
        self.store = MockSessionStore()
        session = create_sample_session(session_id="s-dl-cosmos")
        await self.store.save_session(session)

        self.artifact_id = str(uuid.uuid4())
        artifact = OutputArtifact(
            id=self.artifact_id,
            session_id="s-dl-cosmos",
            name="cosmos_doc",
            description="Cosmos output",
            artifact_type="json",
            storage_type="cosmos",
            storage_location="db/collection/doc-1",
            created_at=datetime.now(timezone.utc),
        )
        await self.store.save_output(artifact)

        self.app = _create_test_app(self.store)
        self.client = TestClient(self.app)

    def test_cosmos_download_returns_json(self) -> None:
        url = f"/api/agent/sessions/s-dl-cosmos/outputs/{self.artifact_id}/download"
        resp = self.client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == self.artifact_id
        assert body["storage_type"] == "cosmos"


class TestDownloadSearchIndexOutput:
    @pytest.fixture(autouse=True)
    async def setup(self) -> None:
        self.store = MockSessionStore()
        session = create_sample_session(session_id="s-dl-search")
        await self.store.save_session(session)

        self.artifact_id = str(uuid.uuid4())
        artifact = OutputArtifact(
            id=self.artifact_id,
            session_id="s-dl-search",
            name="index upload",
            description="Search index upload",
            artifact_type="search_index",
            storage_type="search_index",
            storage_location="my-index",
            record_count=50,
            created_at=datetime.now(timezone.utc),
        )
        await self.store.save_output(artifact)

        self.app = _create_test_app(self.store)
        self.client = TestClient(self.app)

    def test_search_index_returns_metadata_json(self) -> None:
        url = f"/api/agent/sessions/s-dl-search/outputs/{self.artifact_id}/download"
        resp = self.client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        assert body["storage_type"] == "search_index"
        assert body["record_count"] == 50
        assert "message" in body

    def test_search_index_not_directly_downloadable(self) -> None:
        url = f"/api/agent/sessions/s-dl-search/outputs/{self.artifact_id}/download"
        resp = self.client.get(url)
        body = resp.json()
        assert "cannot be downloaded directly" in body["message"]


class TestDownloadErrors:
    @pytest.fixture(autouse=True)
    async def setup(self) -> None:
        self.store = MockSessionStore()
        session = create_sample_session(session_id="s-dl-err")
        await self.store.save_session(session)
        self.app = _create_test_app(self.store)
        self.client = TestClient(self.app)

    def test_404_for_unknown_output(self) -> None:
        resp = self.client.get(
            "/api/agent/sessions/s-dl-err/outputs/does-not-exist/download"
        )
        assert resp.status_code == 404

    def test_404_for_unknown_session(self) -> None:
        resp = self.client.get(
            "/api/agent/sessions/nope/outputs/nope/download"
        )
        assert resp.status_code == 404

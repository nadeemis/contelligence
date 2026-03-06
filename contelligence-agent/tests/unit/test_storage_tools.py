"""Tests for storage tools: read_blob, write_blob, upload_to_search,
query_search_index, upsert_cosmos, query_cosmos."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.connectors.blob_connector import BlobInfo, BlobProperties
from app.tools.storage.read_blob import ReadBlobParams, read_blob
from app.tools.storage.write_blob import WriteBlobParams, write_blob
from app.tools.storage.upload_to_search import UploadToSearchParams, upload_to_search
from app.tools.storage.query_search_index import QuerySearchIndexParams, query_search_index
from app.tools.storage.upsert_cosmos import UpsertCosmosParams, upsert_cosmos
from app.tools.storage.query_cosmos import QueryCosmosParams, query_cosmos


# ===================================================================
# read_blob
# ===================================================================

class TestReadBlob:
    """Tests for the read_blob tool (list, read, metadata actions)."""

    @pytest.mark.asyncio
    async def test_list_action(self, tool_context: dict[str, Any]) -> None:
        params = ReadBlobParams(container="mycontainer", action="list")
        result = await read_blob.handler(params, tool_context)

        assert result["count"] == 2
        assert len(result["blobs"]) == 2
        assert result["blobs"][0]["name"] == "doc1.pdf"
        tool_context["blob"].list_blobs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_with_prefix(self, tool_context: dict[str, Any]) -> None:
        params = ReadBlobParams(
            container="mycontainer", action="list", prefix="docs/", max_results=50
        )
        await read_blob.handler(params, tool_context)
        tool_context["blob"].list_blobs.assert_awaited_once_with(
            container="mycontainer", prefix="docs/", max_results=50,
        )

    @pytest.mark.asyncio
    async def test_read_action(self, tool_context: dict[str, Any]) -> None:
        tool_context["blob"].download_blob.return_value = b"file content here"

        params = ReadBlobParams(
            container="mycontainer", action="read", path="data/file.txt"
        )
        result = await read_blob.handler(params, tool_context)

        assert result["path"] == "data/file.txt"
        assert result["content"] == "file content here"
        assert result["size"] == len(b"file content here")

    @pytest.mark.asyncio
    async def test_read_action_requires_path(self, tool_context: dict[str, Any]) -> None:
        params = ReadBlobParams(container="mycontainer", action="read")
        result = await read_blob.handler(params, tool_context)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_metadata_action(self, tool_context: dict[str, Any]) -> None:
        params = ReadBlobParams(
            container="mycontainer", action="metadata", path="doc1.pdf"
        )
        result = await read_blob.handler(params, tool_context)

        assert result["path"] == "doc1.pdf"
        assert result["size"] == 1024
        assert result["content_type"] == "application/pdf"
        assert result["metadata"] == {"source": "test"}

    @pytest.mark.asyncio
    async def test_metadata_action_requires_path(self, tool_context: dict[str, Any]) -> None:
        params = ReadBlobParams(container="mycontainer", action="metadata")
        result = await read_blob.handler(params, tool_context)
        assert "error" in result


# ===================================================================
# write_blob
# ===================================================================

class TestWriteBlob:

    @pytest.mark.asyncio
    async def test_write_blob_success(self, tool_context: dict[str, Any]) -> None:
        params = WriteBlobParams(
            container="out",
            path="results/output.json",
            content='{"key": "value"}',
            content_type="application/json",
        )
        result = await write_blob.handler(params, tool_context)

        assert result["status"] == "written"
        assert result["path"] == "out/results/output.json"
        tool_context["blob"].upload_blob.assert_awaited_once_with(
            container="out",
            path="results/output.json",
            data=b'{"key": "value"}',
            content_type="application/json",
        )

    @pytest.mark.asyncio
    async def test_write_blob_default_content_type(self, tool_context: dict[str, Any]) -> None:
        params = WriteBlobParams(
            container="c",
            path="data.json",
            content="{}",
        )
        result = await write_blob.handler(params, tool_context)
        assert result["status"] == "written"
        # Default content_type is application/json.
        call_kwargs = tool_context["blob"].upload_blob.call_args.kwargs
        assert call_kwargs["content_type"] == "application/json"


# ===================================================================
# upload_to_search
# ===================================================================

class TestUploadToSearch:

    @pytest.mark.asyncio
    async def test_success(self, tool_context: dict[str, Any]) -> None:
        params = UploadToSearchParams(
            index="my-index",
            documents=[
                {"id": "1", "title": "Doc 1"},
                {"id": "2", "title": "Doc 2"},
            ],
        )
        result = await upload_to_search.handler(params, tool_context)

        assert result["index"] == "my-index"
        assert result["uploaded"] == 2
        assert result["failed"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_missing_id_field(self, tool_context: dict[str, Any]) -> None:
        """Documents missing the required 'id' field should be flagged."""
        params = UploadToSearchParams(
            index="idx",
            documents=[{"title": "No ID"}],
        )
        result = await upload_to_search.handler(params, tool_context)

        assert result["uploaded"] == 0
        assert result["failed"] == 1
        assert len(result["errors"]) == 1
        assert "id" in result["errors"][0].lower()

    @pytest.mark.asyncio
    async def test_partial_missing_ids(self, tool_context: dict[str, Any]) -> None:
        """If some docs have id and some don't, validation catches them all."""
        params = UploadToSearchParams(
            index="idx",
            documents=[
                {"id": "ok", "text": "good"},
                {"text": "bad"},
            ],
        )
        result = await upload_to_search.handler(params, tool_context)
        # Validation runs on ALL documents before uploading.
        assert result["failed"] == 2
        assert len(result["errors"]) == 1  # only the invalid one is flagged


# ===================================================================
# query_search_index
# ===================================================================

class TestQuerySearchIndex:

    @pytest.mark.asyncio
    async def test_basic_query(self, tool_context: dict[str, Any]) -> None:
        params = QuerySearchIndexParams(
            index="my-index",
            query="azure storage",
        )
        result = await query_search_index.handler(params, tool_context)

        assert result["index"] == "my-index"
        assert result["count"] == 2
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_query_with_filters_and_select(self, tool_context: dict[str, Any]) -> None:
        params = QuerySearchIndexParams(
            index="idx",
            query="test",
            top=5,
            filters="status eq 'active'",
            select=["id", "title"],
        )
        await query_search_index.handler(params, tool_context)
        tool_context["search"].search.assert_awaited_once_with(
            index="idx",
            query="test",
            top=5,
            filters="status eq 'active'",
            select=["id", "title"],
            vector=None,
            vector_fields="contentVector",
            query_type="keyword",
            semantic_configuration=None,
        )


# ===================================================================
# upsert_cosmos
# ===================================================================

class TestUpsertCosmos:

    @pytest.mark.asyncio
    async def test_upsert_success(self, tool_context: dict[str, Any]) -> None:
        params = UpsertCosmosParams(
            database="testdb",
            container="items",
            document={"id": "doc-123", "status": "active"},
            partition_key="doc-123",
        )
        result = await upsert_cosmos.handler(params, tool_context)

        assert result["status"] == "upserted"
        assert result["id"] == "doc-123"
        assert result["etag"] == '"etag-value"'

    @pytest.mark.asyncio
    async def test_upsert_missing_id(self, tool_context: dict[str, Any]) -> None:
        """Document without 'id' should return an error."""
        params = UpsertCosmosParams(
            database="db",
            container="c",
            document={"status": "draft"},
            partition_key="pk",
        )
        result = await upsert_cosmos.handler(params, tool_context)

        assert "error" in result
        assert "id" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_upsert_calls_connector(self, tool_context: dict[str, Any]) -> None:
        params = UpsertCosmosParams(
            database="mydb",
            container="stuff",
            document={"id": "x", "name": "test"},
            partition_key="x",
        )
        await upsert_cosmos.handler(params, tool_context)
        tool_context["cosmos"].upsert.assert_awaited_once_with(
            container="stuff",
            document={"id": "x", "name": "test"},
            database="mydb",
            partition_key="x",
        )


# ===================================================================
# query_cosmos
# ===================================================================

class TestQueryCosmos:

    @pytest.mark.asyncio
    async def test_basic_query(self, tool_context: dict[str, Any]) -> None:
        params = QueryCosmosParams(
            database="testdb",
            container="items",
            query="SELECT * FROM c",
        )
        result = await query_cosmos.handler(params, tool_context)

        assert result["count"] == 2
        assert len(result["documents"]) == 2

    @pytest.mark.asyncio
    async def test_query_with_parameters(self, tool_context: dict[str, Any]) -> None:
        params = QueryCosmosParams(
            database="db",
            container="c",
            query="SELECT * FROM c WHERE c.status = @status",
            parameters=[{"name": "@status", "value": "active"}],
        )
        await query_cosmos.handler(params, tool_context)
        tool_context["cosmos"].query.assert_awaited_once_with(
            container="c",
            query_str="SELECT * FROM c WHERE c.status = @status",
            parameters=[{"name": "@status", "value": "active"}],
            database="db",
        )

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_context: dict[str, Any]) -> None:
        tool_context["cosmos"].query.return_value = []

        params = QueryCosmosParams(
            database="db", container="c", query="SELECT * FROM c WHERE 1=0"
        )
        result = await query_cosmos.handler(params, tool_context)

        assert result["count"] == 0
        assert result["documents"] == []

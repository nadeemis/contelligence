"""Tests for SharePoint tools: list_document_libraries, list_items, download_file."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.tools.sharepoint.list_document_libraries import (
    ListDocumentLibrariesParams,
    list_document_libraries,
)
from app.tools.sharepoint.list_items import ListItemsParams, list_items
from app.tools.sharepoint.download_file import DownloadFileParams, download_file


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def sp_context() -> dict[str, Any]:
    """Build a tool context with SharePoint settings populated."""
    return {
        "settings": SimpleNamespace(
            SHAREPOINT_SITE_URL="https://contoso.sharepoint.com/sites/team",
            SHAREPOINT_ACCESS_TOKEN="test-token",
            MSGRAPH_TENANT_ID="tenant-id",
            MSGRAPH_CLIENT_ID="client-id",
            MSGRAPH_CLIENT_SECRET="client-secret",
        ),
    }


# ===================================================================
# list_document_libraries
# ===================================================================

class TestListDocumentLibraries:
    """Tests for the sharepoint_list_document_libraries tool."""

    @pytest.mark.asyncio
    async def test_success(self, sp_context: dict[str, Any]) -> None:
        mock_response = {
            "value": [
                {
                    "Id": "lib-1",
                    "Title": "Documents",
                    "ItemCount": 42,
                    "Created": "2024-01-01T00:00:00Z",
                    "LastItemModifiedDate": "2024-06-15T12:00:00Z",
                    "RootFolder": {
                        "ServerRelativeUrl": "/sites/team/Shared Documents",
                    },
                },
                {
                    "Id": "lib-2",
                    "Title": "Reports",
                    "ItemCount": 5,
                    "Created": "2024-02-01T00:00:00Z",
                    "LastItemModifiedDate": "2024-06-10T08:00:00Z",
                    "RootFolder": {
                        "ServerRelativeUrl": "/sites/team/Reports",
                    },
                },
            ]
        }

        with patch(
            "app.tools.sharepoint.list_document_libraries.sharepoint_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            params = ListDocumentLibrariesParams()
            result = await list_document_libraries.handler(params, sp_context)

            assert result["count"] == 2
            assert result["libraries"][0]["title"] == "Documents"
            assert result["libraries"][0]["itemCount"] == 42
            assert result["libraries"][1]["title"] == "Reports"
            assert "error" not in result
            mock_req.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_custom_site_url(self, sp_context: dict[str, Any]) -> None:
        mock_response = {"value": []}

        with patch(
            "app.tools.sharepoint.list_document_libraries.sharepoint_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            params = ListDocumentLibrariesParams(
                site_url="https://other.sharepoint.com/sites/project",
            )
            result = await list_document_libraries.handler(params, sp_context)

            assert result["count"] == 0
            assert result["libraries"] == []
            call_kwargs = mock_req.call_args
            assert call_kwargs.kwargs["site_url"] == "https://other.sharepoint.com/sites/project"

    @pytest.mark.asyncio
    async def test_error_handling(self, sp_context: dict[str, Any]) -> None:
        with patch(
            "app.tools.sharepoint.list_document_libraries.sharepoint_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection failed"),
        ):
            params = ListDocumentLibrariesParams()
            result = await list_document_libraries.handler(params, sp_context)

            assert "error" in result
            assert "connection failed" in result["error"]


# ===================================================================
# list_items
# ===================================================================

class TestListItems:
    """Tests for the sharepoint_list_items tool."""

    @pytest.mark.asyncio
    async def test_list_root(self, sp_context: dict[str, Any]) -> None:
        folders_resp = {
            "value": [
                {
                    "Name": "Quarterly",
                    "ServerRelativeUrl": "/sites/team/Shared Documents/Quarterly",
                    "ItemCount": 3,
                    "TimeCreated": "2024-01-15T00:00:00Z",
                    "TimeLastModified": "2024-06-01T00:00:00Z",
                },
                {
                    "Name": "Forms",
                    "ServerRelativeUrl": "/sites/team/Shared Documents/Forms",
                    "ItemCount": 0,
                    "TimeCreated": "2024-01-01T00:00:00Z",
                    "TimeLastModified": "2024-01-01T00:00:00Z",
                },
            ]
        }
        files_resp = {
            "value": [
                {
                    "Name": "readme.txt",
                    "ServerRelativeUrl": "/sites/team/Shared Documents/readme.txt",
                    "Length": "1024",
                    "TimeCreated": "2024-03-01T00:00:00Z",
                    "TimeLastModified": "2024-05-20T00:00:00Z",
                    "MajorVersion": 2,
                    "MinorVersion": 0,
                },
            ]
        }

        with patch(
            "app.tools.sharepoint.list_items.sharepoint_request",
            new_callable=AsyncMock,
            side_effect=[folders_resp, files_resp],
        ):
            params = ListItemsParams(library_title="Shared Documents")
            result = await list_items.handler(params, sp_context)

            # "Forms" folder should be filtered out
            assert result["folderCount"] == 1
            assert result["fileCount"] == 1
            assert result["items"][0]["name"] == "Quarterly"
            assert result["items"][0]["type"] == "folder"
            assert result["items"][1]["name"] == "readme.txt"
            assert result["items"][1]["type"] == "file"
            assert result["items"][1]["sizeBytes"] == 1024
            assert result["items"][1]["version"] == "2.0"

    @pytest.mark.asyncio
    async def test_list_subfolder(self, sp_context: dict[str, Any]) -> None:
        folders_resp = {"value": []}
        files_resp = {
            "value": [
                {
                    "Name": "Q1.xlsx",
                    "ServerRelativeUrl": "/sites/team/Shared Documents/Quarterly/Q1.xlsx",
                    "Length": "5000",
                    "TimeCreated": "2024-02-01T00:00:00Z",
                    "TimeLastModified": "2024-02-15T00:00:00Z",
                    "MajorVersion": 1,
                    "MinorVersion": 1,
                },
            ]
        }

        with patch(
            "app.tools.sharepoint.list_items.sharepoint_request",
            new_callable=AsyncMock,
            side_effect=[folders_resp, files_resp],
        ) as mock_req:
            params = ListItemsParams(
                library_title="Shared Documents",
                folder_path="/sites/team/Shared Documents/Quarterly",
            )
            result = await list_items.handler(params, sp_context)

            assert result["folderCount"] == 0
            assert result["fileCount"] == 1
            assert result["items"][0]["name"] == "Q1.xlsx"
            # Verify the folder-based URL path was used (not library root)
            first_call_path = mock_req.call_args_list[0][0][1]
            assert "GetFolderByServerRelativeUrl" in first_call_path

    @pytest.mark.asyncio
    async def test_error_handling(self, sp_context: dict[str, Any]) -> None:
        with patch(
            "app.tools.sharepoint.list_items.sharepoint_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("not found"),
        ):
            params = ListItemsParams(library_title="Missing")
            result = await list_items.handler(params, sp_context)

            assert "error" in result


# ===================================================================
# download_file
# ===================================================================

class TestDownloadFile:
    """Tests for the sharepoint_download_file tool."""

    @pytest.mark.asyncio
    async def test_download_with_content(self, sp_context: dict[str, Any]) -> None:
        mock_metadata = {
            "Name": "report.pdf",
            "ServerRelativeUrl": "/sites/team/Shared Documents/report.pdf",
            "Length": "2048",
            "TimeCreated": "2024-03-01T00:00:00Z",
            "TimeLastModified": "2024-06-01T00:00:00Z",
            "UIVersionLabel": "3.0",
        }
        mock_content = b"fake-pdf-bytes"

        with (
            patch(
                "app.tools.sharepoint.download_file.sharepoint_request",
                new_callable=AsyncMock,
                return_value=mock_metadata,
            ),
            patch(
                "app.tools.sharepoint.download_file.sharepoint_download",
                new_callable=AsyncMock,
                return_value=mock_content,
            ),
        ):
            params = DownloadFileParams(
                server_relative_url="/sites/team/Shared Documents/report.pdf",
            )
            result = await download_file.handler(params, sp_context)

            assert result["name"] == "report.pdf"
            assert result["sizeBytes"] == 2048
            assert result["version"] == "3.0"
            assert result["downloadedBytes"] == len(mock_content)
            decoded = base64.b64decode(result["contentBase64"])
            assert decoded == mock_content
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_metadata_only(self, sp_context: dict[str, Any]) -> None:
        mock_metadata = {
            "Name": "report.pdf",
            "ServerRelativeUrl": "/sites/team/Shared Documents/report.pdf",
            "Length": "2048",
            "TimeCreated": "2024-03-01T00:00:00Z",
            "TimeLastModified": "2024-06-01T00:00:00Z",
            "UIVersionLabel": "1.0",
        }

        with patch(
            "app.tools.sharepoint.download_file.sharepoint_request",
            new_callable=AsyncMock,
            return_value=mock_metadata,
        ):
            params = DownloadFileParams(
                server_relative_url="/sites/team/Shared Documents/report.pdf",
                include_content=False,
            )
            result = await download_file.handler(params, sp_context)

            assert result["name"] == "report.pdf"
            assert "contentBase64" not in result
            assert "downloadedBytes" not in result
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_error_handling(self, sp_context: dict[str, Any]) -> None:
        with patch(
            "app.tools.sharepoint.download_file.sharepoint_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("403 forbidden"),
        ):
            params = DownloadFileParams(
                server_relative_url="/sites/team/Docs/secret.docx",
            )
            result = await download_file.handler(params, sp_context)

            assert "error" in result
            assert "403 forbidden" in result["error"]

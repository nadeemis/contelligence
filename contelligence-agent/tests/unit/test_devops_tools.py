"""Tests for Azure DevOps tools: get_work_item, list_work_items,
query_work_items, get_iterations, get_project."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.tools.devops.get_work_item import GetWorkItemParams, get_work_item
from app.tools.devops.list_work_items import ListWorkItemsParams, list_work_items
from app.tools.devops.query_work_items import QueryWorkItemsParams, query_work_items
from app.tools.devops.get_iterations import GetIterationsParams, get_iterations
from app.tools.devops.get_project import GetProjectParams, get_project


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def devops_context() -> dict[str, Any]:
    """Build a tool context with Azure DevOps settings populated."""
    return {
        "settings": SimpleNamespace(
            AZURE_DEVOPS_ORG="test-org",
            AZURE_DEVOPS_DEFAULT_PROJECT="TestProject",
        ),
    }


# ===================================================================
# get_work_item
# ===================================================================

class TestGetWorkItem:
    """Tests for the devops_get_work_item tool."""

    @pytest.mark.asyncio
    async def test_get_work_item_success(self, devops_context: dict[str, Any]) -> None:
        mock_response = {
            "id": 42,
            "rev": 3,
            "url": "https://dev.azure.com/test-org/_apis/wit/workItems/42",
            "fields": {
                "System.Title": "Implement login feature",
                "System.State": "Active",
                "System.WorkItemType": "Task",
            },
        }

        with patch(
            "app.tools.devops.get_work_item.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            params = GetWorkItemParams(work_item_id=42)
            result = await get_work_item.handler(params, devops_context)

            assert result["id"] == 42
            assert result["rev"] == 3
            assert result["fields"]["System.Title"] == "Implement login feature"
            assert result["fields"]["System.State"] == "Active"
            assert "error" not in result
            mock_req.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_work_item_with_fields_and_expand(
        self, devops_context: dict[str, Any],
    ) -> None:
        mock_response = {
            "id": 10,
            "rev": 1,
            "url": "https://dev.azure.com/test-org/_apis/wit/workItems/10",
            "fields": {"System.Title": "Bug fix"},
            "relations": [{"rel": "System.LinkTypes.Hierarchy-Forward", "url": "..."}],
        }

        with patch(
            "app.tools.devops.get_work_item.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            params = GetWorkItemParams(
                work_item_id=10,
                fields="System.Title",
                expand="Relations",
                project="MyProject",
            )
            result = await get_work_item.handler(params, devops_context)

            assert result["id"] == 10
            assert result["relations"] is not None
            # Verify params passed through
            call_kwargs = mock_req.call_args
            assert call_kwargs.kwargs["project"] == "MyProject"

    @pytest.mark.asyncio
    async def test_get_work_item_error(self, devops_context: dict[str, Any]) -> None:
        with patch(
            "app.tools.devops.get_work_item.devops_request",
            new_callable=AsyncMock,
            side_effect=Exception("Not found"),
        ):
            params = GetWorkItemParams(work_item_id=999)
            result = await get_work_item.handler(params, devops_context)

            assert "error" in result
            assert result["work_item_id"] == 999

    @pytest.mark.asyncio
    async def test_get_work_item_missing_settings(self) -> None:
        context: dict[str, Any] = {"settings": SimpleNamespace()}
        params = GetWorkItemParams(work_item_id=1)
        result = await get_work_item.handler(params, context)
        assert "error" in result


# ===================================================================
# list_work_items
# ===================================================================

class TestListWorkItems:
    """Tests for the devops_list_work_items tool."""

    @pytest.mark.asyncio
    async def test_list_work_items_success(
        self, devops_context: dict[str, Any],
    ) -> None:
        mock_response = {
            "count": 2,
            "value": [
                {
                    "id": 101,
                    "rev": 1,
                    "url": "https://dev.azure.com/test-org/_apis/wit/workItems/101",
                    "fields": {"System.Title": "Task A", "System.State": "New"},
                },
                {
                    "id": 102,
                    "rev": 2,
                    "url": "https://dev.azure.com/test-org/_apis/wit/workItems/102",
                    "fields": {"System.Title": "Task B", "System.State": "Active"},
                },
            ],
        }

        with patch(
            "app.tools.devops.list_work_items.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            params = ListWorkItemsParams(ids=[101, 102])
            result = await list_work_items.handler(params, devops_context)

            assert result["count"] == 2
            assert len(result["work_items"]) == 2
            assert result["work_items"][0]["id"] == 101
            assert result["work_items"][1]["fields"]["System.State"] == "Active"
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_list_work_items_empty_ids(
        self, devops_context: dict[str, Any],
    ) -> None:
        params = ListWorkItemsParams(ids=[])
        result = await list_work_items.handler(params, devops_context)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_work_items_with_fields(
        self, devops_context: dict[str, Any],
    ) -> None:
        mock_response = {
            "count": 1,
            "value": [
                {
                    "id": 50,
                    "rev": 1,
                    "url": "...",
                    "fields": {"System.Title": "Item"},
                },
            ],
        }

        with patch(
            "app.tools.devops.list_work_items.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            params = ListWorkItemsParams(
                ids=[50],
                fields="System.Title,System.State",
                expand="All",
            )
            result = await list_work_items.handler(params, devops_context)

            assert result["count"] == 1
            call_args = mock_req.call_args
            assert "fields" in str(call_args)

    @pytest.mark.asyncio
    async def test_list_work_items_error(
        self, devops_context: dict[str, Any],
    ) -> None:
        with patch(
            "app.tools.devops.list_work_items.devops_request",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            params = ListWorkItemsParams(ids=[1, 2])
            result = await list_work_items.handler(params, devops_context)

            assert "error" in result
            assert result["ids"] == [1, 2]


# ===================================================================
# query_work_items
# ===================================================================

class TestQueryWorkItems:
    """Tests for the devops_query_work_items tool."""

    @pytest.mark.asyncio
    async def test_flat_query_success(
        self, devops_context: dict[str, Any],
    ) -> None:
        mock_response = {
            "queryType": "flat",
            "asOf": "2024-01-15T10:00:00Z",
            "columns": [
                {"referenceName": "System.Id", "name": "ID"},
                {"referenceName": "System.Title", "name": "Title"},
            ],
            "workItems": [
                {"id": 10, "url": "https://dev.azure.com/test-org/_apis/wit/workItems/10"},
                {"id": 11, "url": "https://dev.azure.com/test-org/_apis/wit/workItems/11"},
            ],
        }

        with patch(
            "app.tools.devops.query_work_items.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            params = QueryWorkItemsParams(
                query="Select [System.Id] From WorkItems Where [System.State] = 'Active'",
            )
            result = await query_work_items.handler(params, devops_context)

            assert result["query_type"] == "flat"
            assert result["count"] == 2
            assert result["work_items"][0]["id"] == 10
            assert len(result["columns"]) == 2
            assert "error" not in result

            # Verify the POST body
            call_kwargs = mock_req.call_args
            assert call_kwargs.kwargs["json_body"]["query"].startswith("Select")

    @pytest.mark.asyncio
    async def test_query_with_top(
        self, devops_context: dict[str, Any],
    ) -> None:
        mock_response = {
            "queryType": "flat",
            "asOf": "2024-01-15T10:00:00Z",
            "columns": [],
            "workItems": [{"id": 1, "url": "..."}],
        }

        with patch(
            "app.tools.devops.query_work_items.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            params = QueryWorkItemsParams(
                query="Select [System.Id] From WorkItems",
                top=5,
            )
            result = await query_work_items.handler(params, devops_context)

            assert result["count"] == 1
            call_kwargs = mock_req.call_args
            assert call_kwargs.kwargs["params"]["$top"] == 5

    @pytest.mark.asyncio
    async def test_query_with_relations(
        self, devops_context: dict[str, Any],
    ) -> None:
        mock_response = {
            "queryType": "tree",
            "asOf": "2024-01-15T10:00:00Z",
            "columns": [],
            "workItemRelations": [
                {"rel": None, "source": None, "target": {"id": 100, "url": "..."}},
                {
                    "rel": "System.LinkTypes.Hierarchy-Forward",
                    "source": {"id": 100, "url": "..."},
                    "target": {"id": 101, "url": "..."},
                },
            ],
        }

        with patch(
            "app.tools.devops.query_work_items.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            params = QueryWorkItemsParams(
                query="Select [System.Id] From WorkItemLinks",
            )
            result = await query_work_items.handler(params, devops_context)

            assert result["query_type"] == "tree"
            assert result["count"] == 2
            assert "work_item_relations" in result

    @pytest.mark.asyncio
    async def test_query_error(
        self, devops_context: dict[str, Any],
    ) -> None:
        with patch(
            "app.tools.devops.query_work_items.devops_request",
            new_callable=AsyncMock,
            side_effect=Exception("Bad WIQL"),
        ):
            params = QueryWorkItemsParams(query="invalid query")
            result = await query_work_items.handler(params, devops_context)

            assert "error" in result


# ===================================================================
# get_iterations
# ===================================================================

class TestGetIterations:
    """Tests for the devops_get_iterations tool."""

    @pytest.mark.asyncio
    async def test_team_iterations(
        self, devops_context: dict[str, Any],
    ) -> None:
        mock_response = {
            "value": [
                {
                    "id": "iter-1",
                    "name": "Sprint 1",
                    "path": "TestProject\\Sprint 1",
                    "attributes": {
                        "startDate": "2024-01-01T00:00:00Z",
                        "finishDate": "2024-01-14T00:00:00Z",
                        "timeFrame": "past",
                    },
                    "url": "https://dev.azure.com/test-org/...",
                },
                {
                    "id": "iter-2",
                    "name": "Sprint 2",
                    "path": "TestProject\\Sprint 2",
                    "attributes": {
                        "startDate": "2024-01-15T00:00:00Z",
                        "finishDate": "2024-01-28T00:00:00Z",
                        "timeFrame": "current",
                    },
                    "url": "https://dev.azure.com/test-org/...",
                },
            ],
        }

        with patch(
            "app.tools.devops.get_iterations.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            params = GetIterationsParams(team="TeamAlpha")
            result = await get_iterations.handler(params, devops_context)

            assert result["count"] == 2
            assert result["iterations"][0]["name"] == "Sprint 1"
            assert result["iterations"][1]["timeframe"] == "current"
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_classification_node_iterations(
        self, devops_context: dict[str, Any],
    ) -> None:
        # Classification-node tree (no team specified)
        mock_response = {
            "id": 1,
            "name": "TestProject",
            "path": "\\TestProject\\Iteration",
            "url": "...",
            "attributes": {},
            "children": [
                {
                    "id": 2,
                    "name": "Sprint 1",
                    "path": "\\TestProject\\Iteration\\Sprint 1",
                    "url": "...",
                    "attributes": {
                        "startDate": "2024-01-01T00:00:00Z",
                        "finishDate": "2024-01-14T00:00:00Z",
                    },
                },
            ],
        }

        with patch(
            "app.tools.devops.get_iterations.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            params = GetIterationsParams()
            result = await get_iterations.handler(params, devops_context)

            # Root + 1 child = 2
            assert result["count"] == 2
            assert result["iterations"][1]["name"] == "Sprint 1"

    @pytest.mark.asyncio
    async def test_get_iterations_error(
        self, devops_context: dict[str, Any],
    ) -> None:
        with patch(
            "app.tools.devops.get_iterations.devops_request",
            new_callable=AsyncMock,
            side_effect=Exception("Forbidden"),
        ):
            params = GetIterationsParams()
            result = await get_iterations.handler(params, devops_context)

            assert "error" in result


# ===================================================================
# get_project
# ===================================================================

class TestGetProject:
    """Tests for the devops_get_project tool."""

    @pytest.mark.asyncio
    async def test_get_single_project(
        self, devops_context: dict[str, Any],
    ) -> None:
        mock_response = {
            "id": "proj-123",
            "name": "TestProject",
            "description": "A test project",
            "state": "wellFormed",
            "visibility": "private",
            "defaultTeam": {
                "id": "team-1",
                "name": "TestProject Team",
            },
            "url": "https://dev.azure.com/test-org/_apis/projects/proj-123",
        }

        with patch(
            "app.tools.devops.get_project.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            params = GetProjectParams()
            result = await get_project.handler(params, devops_context)

            assert result["id"] == "proj-123"
            assert result["name"] == "TestProject"
            assert result["default_team"]["name"] == "TestProject Team"
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_list_all_projects(
        self, devops_context: dict[str, Any],
    ) -> None:
        mock_response = {
            "count": 2,
            "value": [
                {
                    "id": "p1",
                    "name": "ProjectA",
                    "description": "First",
                    "state": "wellFormed",
                    "visibility": "private",
                    "url": "...",
                },
                {
                    "id": "p2",
                    "name": "ProjectB",
                    "description": "Second",
                    "state": "wellFormed",
                    "visibility": "public",
                    "url": "...",
                },
            ],
        }

        with patch(
            "app.tools.devops.get_project.devops_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            params = GetProjectParams(project="*")
            result = await get_project.handler(params, devops_context)

            assert result["count"] == 2
            assert result["projects"][0]["name"] == "ProjectA"
            assert result["projects"][1]["visibility"] == "public"

    @pytest.mark.asyncio
    async def test_get_project_no_project_configured(self) -> None:
        context: dict[str, Any] = {
            "settings": SimpleNamespace(
                AZURE_DEVOPS_ORG="org",
                AZURE_DEVOPS_DEFAULT_PROJECT="",
            ),
        }
        params = GetProjectParams()
        result = await get_project.handler(params, context)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_project_error(
        self, devops_context: dict[str, Any],
    ) -> None:
        with patch(
            "app.tools.devops.get_project.devops_request",
            new_callable=AsyncMock,
            side_effect=Exception("Not found"),
        ):
            params = GetProjectParams(project="NoSuchProject")
            result = await get_project.handler(params, devops_context)

            assert "error" in result


# ===================================================================
# Client helper tests
# ===================================================================

class TestDevOpsClient:
    """Tests for the _client.py helper functions."""

    def test_base_url(self) -> None:
        from app.tools.devops._client import _base_url

        assert _base_url("myorg") == "https://dev.azure.com/myorg"

    def test_get_devops_settings_missing_org(self) -> None:
        from app.tools.devops._client import _get_devops_settings

        context: dict[str, Any] = {
            "settings": SimpleNamespace(AZURE_DEVOPS_ORG=""),
        }
        with pytest.raises(ValueError, match="AZURE_DEVOPS_ORG"):
            _get_devops_settings(context)

    def test_get_devops_settings_success(self) -> None:
        from app.tools.devops._client import _get_devops_settings

        context: dict[str, Any] = {
            "settings": SimpleNamespace(
                AZURE_DEVOPS_ORG="myorg",
                AZURE_DEVOPS_DEFAULT_PROJECT="proj",
                AZURE_DEVOPS_PAT="my-pat",
            ),
        }
        org, project, pat = _get_devops_settings(context)
        assert org == "myorg"
        assert project == "proj"
        assert pat == "my-pat"

    def test_get_devops_settings_no_pat(self) -> None:
        from app.tools.devops._client import _get_devops_settings

        context: dict[str, Any] = {
            "settings": SimpleNamespace(
                AZURE_DEVOPS_ORG="myorg",
                AZURE_DEVOPS_DEFAULT_PROJECT="proj",
            ),
        }
        org, project, pat = _get_devops_settings(context)
        assert org == "myorg"
        assert pat == ""

    @pytest.mark.asyncio
    async def test_get_auth_header_with_pat(self) -> None:
        """When PAT is provided, return Basic auth without touching DefaultAzureCredential."""
        from app.tools.devops._client import _get_auth_header
        import base64

        header = await _get_auth_header(pat="my-pat")
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header.split(" ")[1]).decode()
        assert decoded == ":my-pat"

    @pytest.mark.asyncio
    async def test_get_auth_header_entra_id_fallback(self) -> None:
        """When PAT is empty, fall back to DefaultAzureCredential bearer token."""
        from app.tools.devops._client import _get_auth_header

        mock_token = SimpleNamespace(token="fake-bearer-token")
        mock_credential = AsyncMock()
        mock_credential.get_token = AsyncMock(return_value=mock_token)
        mock_credential.close = AsyncMock()

        with patch(
            "app.tools.devops._client.DefaultAzureCredential",
            return_value=mock_credential,
        ):
            header = await _get_auth_header()
            assert header == "Bearer fake-bearer-token"
            mock_credential.get_token.assert_awaited_once()
            mock_credential.close.assert_awaited_once()

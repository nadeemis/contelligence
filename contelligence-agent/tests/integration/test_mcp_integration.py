"""Integration tests for MCP server connectivity.

These tests verify MCP server health checking with real/mock probes.
Marked with ``@pytest.mark.integration`` — skipped unless
``--run-integration`` is passed to pytest.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.mcp.config import get_mcp_servers_config
from app.mcp.health import verify_mcp_servers


pytestmark = pytest.mark.integration


class TestMcpConnectivity:

    @pytest.mark.asyncio
    async def test_verify_all_servers(
        self,
        mock_mcp_config: dict[str, dict[str, Any]],
    ) -> None:
        """Verify that verify_mcp_servers returns status for all configured servers."""
        results = await verify_mcp_servers(mock_mcp_config, timeout=3.0)

        for name in mock_mcp_config:
            assert name in results
            assert "status" in results[name]
            assert results[name]["status"] in ("ok", "degraded", "unavailable")

    @pytest.mark.asyncio
    async def test_stdio_health_check(self) -> None:
        """Stdio health check for a known binary (python)."""
        config = {
            "test-stdio": {
                "type": "stdio",
                "command": ["python", "--version"],
            }
        }
        results = await verify_mcp_servers(config, timeout=5.0)
        assert results["test-stdio"]["status"] in ("ok", "degraded")

    @pytest.mark.asyncio
    async def test_http_health_with_mock_server(self) -> None:
        """HTTP health check with a mocked httpx response."""
        config = {
            "test-http": {
                "type": "http",
                "url": "http://localhost:5008",
            }
        }

        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await verify_mcp_servers(config, timeout=3.0)

        assert results["test-http"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_reports_transport_type(
        self,
        mock_mcp_config: dict[str, dict[str, Any]],
    ) -> None:
        results = await verify_mcp_servers(mock_mcp_config, timeout=3.0)

        assert results["azure"]["transport"] == "stdio"
        assert results["github"]["transport"] == "http"

    @pytest.mark.asyncio
    async def test_config_http_mode(
        self,
        mock_mcp_config_http: dict[str, dict[str, Any]],
    ) -> None:
        """HTTP Azure MCP config should report http transport."""
        results = await verify_mcp_servers(mock_mcp_config_http, timeout=2.0)
        assert results["azure"]["transport"] == "http"

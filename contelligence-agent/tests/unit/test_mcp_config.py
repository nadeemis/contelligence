"""Tests for MCP server configuration and health checking.

Covers:
- get_mcp_servers_config for stdio and HTTP modes
- resolve_github_token (mocked Key Vault)
- verify_mcp_servers health probes
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.config import get_mcp_servers_config, resolve_github_token
from app.mcp.health import verify_mcp_servers


# ===========================================================================
# get_mcp_servers_config
# ===========================================================================

class TestGetMcpServersConfig:
    """Test MCP server configuration generation."""

    def test_stdio_mode_when_no_url(self) -> None:
        """Without AZURE_MCP_SERVER_URL the Azure MCP uses stdio transport."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AZURE_MCP_SERVER_URL", None)
            cfg = get_mcp_servers_config()

        assert cfg["azure"]["type"] == "stdio"
        assert cfg["azure"]["command"] == ["azmcp", "server", "start"]

    def test_http_mode_when_url_set(self) -> None:
        """Setting AZURE_MCP_SERVER_URL switches Azure MCP to HTTP."""
        with patch.dict(os.environ, {"AZURE_MCP_SERVER_URL": "http://mcp:5008"}):
            cfg = get_mcp_servers_config()

        assert cfg["azure"]["type"] == "http"
        assert cfg["azure"]["url"] == "http://mcp:5008"

    def test_http_mode_trims_whitespace(self) -> None:
        with patch.dict(os.environ, {"AZURE_MCP_SERVER_URL": "  http://mcp:5008  "}):
            cfg = get_mcp_servers_config()

        assert cfg["azure"]["url"] == "http://mcp:5008"

    def test_empty_url_falls_back_to_stdio(self) -> None:
        with patch.dict(os.environ, {"AZURE_MCP_SERVER_URL": "   "}):
            cfg = get_mcp_servers_config()

        assert cfg["azure"]["type"] == "stdio"

    def test_github_config_always_http(self) -> None:
        """GitHub MCP is always HTTP / Copilot API proxy."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AZURE_MCP_SERVER_URL", None)
            cfg = get_mcp_servers_config()

        gh = cfg["github"]
        assert gh["type"] == "http"
        assert "githubcopilot" in gh["url"]
        assert gh["auth"]["type"] == "token"

    def test_github_token_initially_empty(self) -> None:
        """Token should be empty before startup resolves it."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AZURE_MCP_SERVER_URL", None)
            cfg = get_mcp_servers_config()

        assert cfg["github"]["auth"]["token"] == ""

    def test_config_is_mutable(self) -> None:
        """Callers should be able to inject tokens at runtime."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AZURE_MCP_SERVER_URL", None)
            cfg = get_mcp_servers_config()

        cfg["github"]["auth"]["token"] = "ghp_test"
        assert cfg["github"]["auth"]["token"] == "ghp_test"

    def test_both_servers_present(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AZURE_MCP_SERVER_URL", None)
            cfg = get_mcp_servers_config()

        assert "azure" in cfg
        assert "github" in cfg


# ===========================================================================
# resolve_github_token
# ===========================================================================

class TestResolveGithubToken:

    @pytest.mark.asyncio
    async def test_resolves_from_keyvault(self) -> None:
        mock_secret = MagicMock()
        mock_secret.value = "ghp_resolved_token"

        mock_client = AsyncMock()
        mock_client.get_secret.return_value = mock_secret
        mock_client.close = AsyncMock()

        mock_credential = AsyncMock()
        mock_credential.close = AsyncMock()

        with (
            patch("azure.identity.aio.DefaultAzureCredential", return_value=mock_credential),
            patch("azure.keyvault.secrets.aio.SecretClient", return_value=mock_client),
        ):
            token = await resolve_github_token("https://test-vault.vault.azure.net/")

        assert token == "ghp_resolved_token"
        mock_client.get_secret.assert_awaited_once_with("github-copilot-token")
        mock_client.close.assert_awaited_once()
        mock_credential.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_on_failure(self) -> None:
        """Re-raises are suppressed; returns empty string."""
        with patch(
            "azure.identity.aio.DefaultAzureCredential",
            side_effect=Exception("No credentials"),
        ):
            token = await resolve_github_token("https://test-vault.vault.azure.net/")

        assert token == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_secret_value_none(self) -> None:
        mock_secret = MagicMock()
        mock_secret.value = None

        mock_client = AsyncMock()
        mock_client.get_secret.return_value = mock_secret
        mock_client.close = AsyncMock()

        mock_credential = AsyncMock()
        mock_credential.close = AsyncMock()

        with (
            patch("azure.identity.aio.DefaultAzureCredential", return_value=mock_credential),
            patch("azure.keyvault.secrets.aio.SecretClient", return_value=mock_client),
        ):
            token = await resolve_github_token("https://test-vault.vault.azure.net/")

        assert token == ""


# ===========================================================================
# verify_mcp_servers
# ===========================================================================

class TestVerifyMcpServers:

    @pytest.mark.asyncio
    async def test_stdio_ok_when_binary_exists(self) -> None:
        config = {
            "azure": {"type": "stdio", "command": ["python", "--version"]},
        }
        result = await verify_mcp_servers(config, timeout=5.0)

        assert result["azure"]["transport"] == "stdio"
        assert result["azure"]["status"] in ("ok", "degraded")

    @pytest.mark.asyncio
    async def test_stdio_unavailable_when_binary_missing(self) -> None:
        config = {
            "azure": {"type": "stdio", "command": ["nonexistent_binary_xyz"]},
        }
        result = await verify_mcp_servers(config, timeout=2.0)

        assert result["azure"]["status"] == "unavailable"
        assert "not found" in result["azure"]["detail"]

    @pytest.mark.asyncio
    async def test_stdio_unavailable_when_no_command(self) -> None:
        config = {"azure": {"type": "stdio", "command": []}}
        result = await verify_mcp_servers(config, timeout=2.0)

        assert result["azure"]["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_http_degraded_when_token_missing(self) -> None:
        config = {
            "github": {
                "type": "http",
                "url": "https://api.githubcopilot.com/mcp/",
                "auth": {"type": "token", "token": ""},
            },
        }
        result = await verify_mcp_servers(config, timeout=2.0)

        assert result["github"]["transport"] == "http"
        assert result["github"]["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_http_unavailable_when_no_url(self) -> None:
        config = {"test": {"type": "http", "url": ""}}
        result = await verify_mcp_servers(config, timeout=2.0)

        assert result["test"]["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_unknown_transport(self) -> None:
        config = {"custom": {"type": "websocket"}}
        result = await verify_mcp_servers(config, timeout=2.0)

        assert result["custom"]["status"] == "unavailable"
        assert "Unknown transport" in result["custom"]["detail"]

    @pytest.mark.asyncio
    async def test_multiple_servers(
        self,
        mock_mcp_config: dict[str, dict[str, Any]],
    ) -> None:
        """Both azure and github servers are checked."""
        result = await verify_mcp_servers(mock_mcp_config, timeout=2.0)

        assert "azure" in result
        assert "github" in result
        for name in result:
            assert "status" in result[name]
            assert "transport" in result[name]

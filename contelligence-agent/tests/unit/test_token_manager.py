"""Unit tests for Phase 4 — Token Manager (Key Vault secret refresh)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.token_manager import TokenManager


@pytest.fixture
def mock_secret_client() -> AsyncMock:
    """Create a mock Azure Key Vault SecretClient."""
    client = AsyncMock()
    secret = MagicMock()
    secret.value = "test-token-value"
    client.get_secret.return_value = secret
    return client


class TestTokenManager:
    """Test the Key Vault token manager."""

    @pytest.mark.asyncio
    async def test_initial_state(self) -> None:
        tm = TokenManager(
            vault_url="https://test.vault.azure.net",
            secret_name="test-secret",
            refresh_interval_seconds=300,
        )
        assert tm.get_token() is None
        status = tm.health_status()
        assert status["healthy"] is False

    @pytest.mark.asyncio
    async def test_force_refresh(self, mock_secret_client: AsyncMock) -> None:
        tm = TokenManager(
            vault_url="https://test.vault.azure.net",
            secret_name="test-secret",
            refresh_interval_seconds=300,
        )
        tm._client = mock_secret_client

        await tm.force_refresh()
        assert tm.get_token() == "test-token-value"
        status = tm.health_status()
        assert status["healthy"] is True

    @pytest.mark.asyncio
    async def test_force_refresh_failure(self) -> None:
        tm = TokenManager(
            vault_url="https://test.vault.azure.net",
            secret_name="test-secret",
            refresh_interval_seconds=300,
        )
        client = AsyncMock()
        client.get_secret.side_effect = Exception("Key Vault unreachable")
        tm._client = client

        await tm.force_refresh()
        assert tm.get_token() is None
        status = tm.health_status()
        assert status["healthy"] is False

    def test_health_status_format(self) -> None:
        tm = TokenManager(
            vault_url="https://test.vault.azure.net",
            secret_name="test-secret",
            refresh_interval_seconds=300,
        )
        status = tm.health_status()
        assert "healthy" in status
        assert "last_refresh" in status
        assert "secret_name" in status
        assert status["secret_name"] == "test-secret"

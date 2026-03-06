"""Key Vault token manager — stores and auto-refreshes the GitHub
Copilot SDK token in Azure Key Vault.

Implements a background loop that checks token expiry and refreshes
from the Key Vault secret, plus a health monitor that reports token
status to the health endpoint.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from azure.keyvault.secrets.aio import SecretClient

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# Default token refresh interval — 5 minutes
_DEFAULT_REFRESH_INTERVAL = 300


class TokenManager:
    """Manages the GitHub Copilot token lifecycle via Key Vault.

    The token is stored as a Key Vault secret named
    ``github-copilot-token``.  The manager periodically reads the
    secret and keeps a local in-memory copy that the SDK client uses.
    """

    def __init__(
        self,
        secret_client: SecretClient,
        secret_name: str = "github-copilot-token",
        refresh_interval_seconds: int = _DEFAULT_REFRESH_INTERVAL,
    ) -> None:
        self._secret_client = secret_client
        self._secret_name = secret_name
        self._refresh_interval = refresh_interval_seconds
        self._current_token: str | None = None
        self._last_refresh: datetime | None = None
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._healthy = True
        self._error: str | None = None

    @property
    def token(self) -> str | None:
        """Return the current cached token value."""
        return self._current_token

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    async def start(self) -> None:
        """Start the background token refresh loop."""
        self._running = True
        # Fetch immediately on start
        await self._refresh_token()
        self._task = asyncio.create_task(
            self._refresh_loop(), name="token-refresh-loop"
        )
        logger.info(
            "Token manager started (refresh every %ds, secret=%s)",
            self._refresh_interval,
            self._secret_name,
        )

    async def stop(self) -> None:
        """Stop the background loop and close the Key Vault client."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._secret_client.close()
        logger.info("Token manager stopped.")

    async def _refresh_loop(self) -> None:
        """Background loop that refreshes the token periodically."""
        while self._running:
            try:
                await asyncio.sleep(self._refresh_interval)
                await self._refresh_token()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Token refresh loop error — will retry")
                await asyncio.sleep(30)

    async def _refresh_token(self) -> None:
        """Fetch the token from Key Vault."""
        try:
            secret = await self._secret_client.get_secret(self._secret_name)
            if secret.value:
                self._current_token = secret.value
                self._last_refresh = datetime.now(timezone.utc)
                self._healthy = True
                self._error = None
                logger.debug("Token refreshed from Key Vault.")
            else:
                self._healthy = False
                self._error = "Secret value is empty"
                logger.warning("Key Vault secret '%s' is empty.", self._secret_name)
        except Exception as exc:
            self._healthy = False
            self._error = str(exc)
            logger.error("Failed to refresh token from Key Vault: %s", exc)

    async def force_refresh(self) -> bool:
        """Manually trigger a token refresh.  Returns ``True`` on success."""
        try:
            await self._refresh_token()
            return self._healthy
        except Exception:
            return False

    def health_status(self) -> dict[str, Any]:
        """Return token health for the ``/api/health`` endpoint."""
        return {
            "healthy": self._healthy,
            "last_refresh": (
                self._last_refresh.isoformat() if self._last_refresh else None
            ),
            "secret_name": self._secret_name,
            "error": self._error,
        }

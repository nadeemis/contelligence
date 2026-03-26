"""Factory for creating and managing CopilotClient instances.

Encapsulates CopilotClient lifecycle (create, start, reset) so that:
- Multiple clients can be created for future scenarios.
- The active client can be reset when credentials change (e.g. Key Vault
  token rotation via the web UI settings page).
- The ``SessionFactory`` depends only on the factory and obtains the
  current client via ``client_factory.client``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from copilot import CopilotClient, ExternalServerConfig, SubprocessConfig

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class CopilotClientFactory:
    """Creates, manages, and resets ``CopilotClient`` instances.

    Parameters
    ----------
    base_options:
        Static options (``cli_path``, ``cli_url``, ``log_level``, etc.)
        that do not change across resets.
    github_token:
        Initial GitHub token.  Can be updated later via :meth:`reset`.
    """

    def __init__(
        self,
        base_options: dict[str, Any] | None = None,
        github_token: str | None = None,
    ) -> None:
        self._base_options: dict[str, Any] = base_options or {}
        self._github_token: str | None = github_token
        self._client: CopilotClient | None = None
        self._lock = asyncio.Lock()
        
    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def client(self) -> CopilotClient:
        """Return the current active ``CopilotClient``.

        Raises ``RuntimeError`` if the factory has not been started yet.
        """
        if self._client is None:
            raise RuntimeError(
                "CopilotClientFactory has not been started. "
                "Call 'await factory.start()' first."
            )
        return self._client

    @property
    def github_token(self) -> str | None:
        """The GitHub token currently configured on the factory."""
        return self._github_token

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_client(self) -> CopilotClient:
        """
            Create a new ``CopilotClient`` instance with the current options.
            Note: The client is not started here; it is the caller's responsibility to call `start()` on the client after building it.
        """
        
        opts = {**self._base_options}
        if self._github_token:
            opts["github_token"] = self._github_token

        if opts.get("cli_url") in [None, ""]:
            client = CopilotClient(
                config=SubprocessConfig(
                    cli_path=opts.get("cli_path"),
                    log_level=opts.get("log_level", "info"),
                    cwd=opts.get("cli_cwd"),
                    github_token=opts.get("github_token"),
                    use_logged_in_user=opts.get("use_logged_in_user"),
                ),
                auto_start=opts.get("auto_start", True),
            )
        else:
            client = CopilotClient(
                config=ExternalServerConfig(
                    url=opts["cli_url"]
                ),
                auto_start=opts.get("auto_start", True),
            )
        
        return client

    async def start(self) -> CopilotClient:
        """Create and start a new ``CopilotClient``.

        If a client already exists it will be stopped first.
        """
        async with self._lock:
            await self._stop_current()
            self._client = self._build_client()
            await self._client.start()
            logger.info("CopilotClient started via factory.")
            return self._client

    async def stop(self) -> None:
        """Stop the current client (if any)."""
        async with self._lock:
            await self._stop_current()

    async def reset(
        self,
        *,
        github_token: str | None = None,
    ) -> CopilotClient:
        """Stop the current client and start a fresh one.

        Optionally update the GitHub token before restarting.  This is
        the entry-point for credential rotation triggered from the web
        UI settings page.

        Parameters
        ----------
        github_token:
            If provided, replaces the stored token before the new client
            is created.  Pass ``None`` to keep the existing token.

        Returns
        -------
        CopilotClient
            The newly started client instance.
        """
        async with self._lock:
            if github_token is not None:
                self._github_token = github_token
                logger.info("GitHub token updated on CopilotClientFactory.")
            await self._stop_current()
            self._client = self._build_client()
            await self._client.start()
            logger.info("CopilotClient reset and restarted via factory.")
            return self._client

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _stop_current(self) -> None:
        """Stop and discard the current client, swallowing errors."""
        if self._client is not None:
            try:
                await self._client.stop()
                logger.debug("Previous CopilotClient stopped.")
            except Exception:
                logger.debug(
                    "Error stopping CopilotClient during reset.",
                    exc_info=True,
                )
            self._client = None

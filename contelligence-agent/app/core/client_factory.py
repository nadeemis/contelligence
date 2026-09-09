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
from datetime import datetime, timezone
from typing import Any

from copilot import CopilotClient, RuntimeConnection
from copilot.client import PingResponse

logger = logging.getLogger(f"contelligence-agent.{__name__}")


# ---------------------------------------------------------------------------
# Monkey-patch: SDK >= 0.x returns ISO-8601 timestamp strings from the CLI
# ping response instead of integer milliseconds.  The SDK's from_dict does
# int(timestamp) which raises ValueError on an ISO string.  Patch it here
# so the app starts cleanly until the SDK ships a fix.
# ---------------------------------------------------------------------------

_original_ping_from_dict = PingResponse.from_dict


@staticmethod  # type: ignore[misc]
def _patched_ping_from_dict(obj: Any) -> PingResponse:
    """PingResponse.from_dict that tolerates ISO-8601 timestamp strings."""
    assert isinstance(obj, dict)
    message = obj.get("message")
    timestamp = obj.get("timestamp")
    protocol_version = obj.get("protocolVersion")

    if message is None or timestamp is None or protocol_version is None:
        raise ValueError(
            f"Missing required fields in PingResponse: message={message}, "
            f"timestamp={timestamp}, protocolVersion={protocol_version}"
        )

    # Handle ISO-8601 timestamp strings from newer CLI versions
    if isinstance(timestamp, str):
        try:
            ts_int = int(timestamp)
        except ValueError:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            ts_int = int(dt.timestamp() * 1000)
    else:
        ts_int = int(timestamp)

    return PingResponse(str(message), ts_int, int(protocol_version))


PingResponse.from_dict = _patched_ping_from_dict  # type: ignore[assignment]


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
                connection=RuntimeConnection.for_stdio(
                    path=opts.get("cli_path"),
                    args=opts.get("cli_args", []),
                ),
                working_directory=opts.get("cli_cwd"),
                log_level=opts.get("log_level", "info"),
                github_token=opts.get("github_token"),
                use_logged_in_user=opts.get("use_logged_in_user"),
            )
        else:
            client = CopilotClient(
                connection=RuntimeConnection.for_uri(opts["cli_url"]),
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

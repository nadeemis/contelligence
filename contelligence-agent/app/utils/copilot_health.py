"""Quick preflight check for the Copilot SDK client.

Call :func:`verify_copilot_client` after ``CopilotClient.start()`` to confirm
the client is authenticated and can successfully complete a round-trip to the
model provider.  This catches misconfiguration (wrong token, bad BYOK
endpoint, expired credentials) *before* any real session is created.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from copilot import CopilotClient
from copilot.session import PermissionHandler

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# Lightweight prompt that burns minimal tokens.
_PROBE_PROMPT = "Reply with only the word: OK"
_PROBE_TIMEOUT_SECONDS = 30.0


@dataclass
class CopilotHealthResult:
    """Outcome of a Copilot SDK preflight check."""

    healthy: bool
    auth_type: str | None = None
    auth_host: str | None = None
    login: str | None = None
    cli_version: str | None = None
    probe_response: str | None = None
    error: str | None = None

    def summary(self) -> str:
        if self.healthy:
            return (
                f"Copilot SDK OK — auth={self.auth_type}, "
                f"host={self.auth_host}, cli={self.cli_version}"
            )
        return f"Copilot SDK UNHEALTHY — {self.error}"


class CopilotClientUnhealthyError(RuntimeError):
    """Raised when the Copilot SDK client fails the preflight health check."""

    def __init__(self, result: CopilotHealthResult) -> None:
        self.result = result
        super().__init__(result.summary())


async def verify_copilot_client(
    client: CopilotClient,
    *,
    provider_config: dict[str, Any] | None = None,
    model: str | None = None,
    full_probe: bool = True,
    timeout: float = _PROBE_TIMEOUT_SECONDS,
) -> CopilotHealthResult:
    """Run a preflight check on the Copilot SDK client.

    The check has two stages:

    1. **Auth check** — calls ``client.get_auth_status()`` to verify the
       token / login is valid.
    2. **Probe session** *(optional, ``full_probe=True``)* — creates a
       minimal session with the target model and provider config, sends a
       trivial prompt, and waits for the assistant reply.  This catches
       provider-level errors (e.g. bad Azure OpenAI endpoint) that the
       auth check alone cannot detect.

    Parameters
    ----------
    client:
        An already-started ``CopilotClient``.
    provider_config:
        The BYOK provider dict to test (same format passed to
        ``SessionFactory``).  Pass ``None`` to test the default GitHub
        Copilot provider.
    model:
        Model name to use for the probe session.  If ``None``, the SDK
        picks its default.
    full_probe:
        If ``True`` (default), run the probe session in addition to the
        auth check.  Set to ``False`` for a faster, auth-only check.
    timeout:
        Maximum seconds to wait for the probe session to complete.

    Returns
    -------
    CopilotHealthResult
        Always returned — inspect ``.healthy`` or call ``.summary()``.
    """
    result = CopilotHealthResult(healthy=False)

    # ------------------------------------------------------------------
    # Stage 1 — Auth status
    # ------------------------------------------------------------------
    try:
        auth = await client.get_auth_status()
        result.auth_type = auth.authType
        result.auth_host = auth.host
        result.login = auth.login
        if not auth.isAuthenticated:
            result.error = (
                f"Not authenticated (authType={auth.authType}, "
                f"status={auth.statusMessage})"
            )
            return result
    except Exception as exc:
        result.error = f"Auth status check failed: {exc}"
        return result

    # ------------------------------------------------------------------
    # Stage 1b — CLI version (best-effort)
    # ------------------------------------------------------------------
    try:
        status = await client.get_status()
        result.cli_version = status.version
    except Exception:
        pass  # non-fatal

    if not full_probe:
        result.healthy = True
        return result

    # ------------------------------------------------------------------
    # Stage 2 — Probe session (catches provider/model errors)
    # ------------------------------------------------------------------
    session = None
    try:
        session = await client.create_session(
                                                on_permission_request=PermissionHandler.approve_all,
                                                streaming=True,
                                                model=model,
                                                provider=provider_config,
                                             )

        done = asyncio.Event()
        probe_error: str | None = None
        probe_reply: str | None = None

        def _on_event(event: Any) -> None:
            nonlocal probe_error, probe_reply
            etype = event.type.value

            if etype == "session.error":
                error_msg = getattr(event.data, "message", None) or "Unknown error"
                error_type = getattr(event.data, "error_type", None) or "unknown"
                status_code = getattr(event.data, "status_code", None)
                probe_error = f"[{error_type}] {error_msg} (status={status_code})"
            elif etype == "assistant.message":
                probe_reply = getattr(event.data, "content", "")
            elif etype == "session.idle":
                done.set()

        session.on(_on_event)
        await session.send(prompt=_PROBE_PROMPT)
        await asyncio.wait_for(done.wait(), timeout=timeout)

        if probe_error:
            # Detect tenant mismatch: a token issued for one Azure AD tenant was
            # presented to a resource owned by a different tenant.  The message
            # and fix differ depending on whether a BYOK provider is configured.
            if "does not match resource tenant" in (probe_error or ""):
                import re as _re
                tenant_hint = ""
                m = _re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", probe_error)
                if m:
                    tenant_hint = f" (token is from tenant {m.group(0)})"
                if provider_config:
                    # BYOK mode: the Azure OpenAI credential is wrong.
                    result.error = (
                        f"Probe session failed: {probe_error}. "
                        f"TENANT MISMATCH — the credential used to authenticate against the "
                        f"configured Azure OpenAI endpoint belongs to the wrong Azure AD tenant{tenant_hint}. "
                        "Fix: set AZURE_OPENAI_KEY in your .env to use API-key auth, or run "
                        "'az login --tenant <your-tenant-id>' so the correct organisation "
                        "credential is active, or set AZURE_AD_TENANT_ID in your .env."
                    )
                else:
                    # Default GitHub Copilot path: the model may route through
                    # Azure AI infrastructure in a tenant the Copilot CLI token
                    # cannot access.  Most commonly seen on Windows with a
                    # model name that maps to an Azure-hosted backend.
                    result.error = (
                        f"Probe session failed: {probe_error}. "
                        f"TENANT MISMATCH — the model requested may route through Azure AI "
                        f"infrastructure that requires a different Azure AD tenant{tenant_hint}. "
                        "Fix: try a different COPILOT_MODEL (e.g. 'gpt-4o' or 'claude-3.5-sonnet'), "
                        "or re-authenticate the Copilot CLI with 'gh auth login'."
                    )
            else:
                result.error = f"Probe session failed: {probe_error}"
            return result

        result.probe_response = probe_reply
        result.healthy = True

    except asyncio.TimeoutError:
        result.error = f"Probe session timed out after {timeout}s"
    except Exception as exc:
        result.error = f"Probe session error: {exc}"
    finally:
        if session is not None:
            try:
                await session.destroy()
            except Exception:
                pass

    return result

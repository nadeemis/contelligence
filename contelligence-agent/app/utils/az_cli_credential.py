"""Acquire Azure access tokens by shelling out to the ``az`` CLI.

This is useful as a fallback when ``DefaultAzureCredential`` cannot resolve
a credential (e.g. inside VS Code MCP servers or restricted-PATH
environments where the Azure CLI is installed but the SDK chain cannot
discover it automatically).

The implementation mirrors the Node.js ``createAuthService`` helper:
it locates the ``az`` binary, spawns ``az account get-access-token``,
caches the result, and transparently refreshes when the token is near
expiry.

Usage::

    from app.utils.az_cli_credential import AzCliCredential

    credential = AzCliCredential(resource="https://contoso.sharepoint.com")
    token = await credential.get_token()   # AccessTokenInfo
    await credential.close()               # no-op, provided for parity

Or as an async context manager::

    async with AzCliCredential(resource="https://graph.microsoft.com") as cred:
        tok = await cred.get_token()
        print(tok.token)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import platform
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(f"contelligence-agent.{__name__}")

_DEFAULT_TIMEOUT_S = 30


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AccessTokenInfo:
    """Minimal mirror of ``azure.core.credentials.AccessToken``."""

    token: str
    expires_on: int  # UTC epoch seconds


@dataclass
class TokenMetadata:
    """Decoded JWT metadata (best-effort, non-validated)."""

    user_name: str | None = None
    audience: str | None = None
    expires_at: float | None = None  # UTC epoch seconds
    is_expired: bool = True


# ---------------------------------------------------------------------------
# JWT helpers (decode-only, **no** signature verification)
# ---------------------------------------------------------------------------

def _base64url_decode(value: str) -> bytes:
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(padded)


def parse_token_metadata(token: str) -> TokenMetadata:
    """Decode the JWT payload and return best-effort metadata."""
    try:
        _, payload_b64, *_ = token.split(".")
        payload = json.loads(_base64url_decode(payload_b64))
        exp = payload.get("exp")
        expires_at = float(exp) if exp is not None else None
        is_expired = (expires_at <= time.time()) if expires_at else True
        return TokenMetadata(
            user_name=payload.get("name")
            or payload.get("unique_name")
            or payload.get("upn"),
            audience=payload.get("aud"),
            expires_at=expires_at,
            is_expired=is_expired,
        )
    except Exception:
        return TokenMetadata()


# ---------------------------------------------------------------------------
# Locate the ``az`` binary
# ---------------------------------------------------------------------------

_az_cli_path: str | None = None


def _find_az_cli() -> str:
    """Resolve the ``az`` CLI executable path.

    Checks common install locations first to avoid spawning a shell,
    then falls back to the user's login shell ``command -v az``.
    """
    global _az_cli_path
    if _az_cli_path is not None:
        return _az_cli_path

    if platform.system() == "Windows":
        _az_cli_path = "az.cmd"
        return _az_cli_path

    home = Path.home()

    # 1. Fast filesystem probes
    candidates = [
        home / "miniconda3" / "bin" / "az",
        home / "anaconda3" / "bin" / "az",
        Path("/opt/homebrew/bin/az"),
        Path("/usr/local/bin/az"),
        Path("/usr/bin/az"),
    ]
    for candidate in candidates:
        if candidate.exists():
            _az_cli_path = str(candidate)
            return _az_cli_path

    # 2. shutil.which — respects current PATH
    which_result = shutil.which("az")
    if which_result:
        _az_cli_path = which_result
        return _az_cli_path

    # 3. Login-shell discovery (conda, brew, pyenv, etc.)
    shells = list(
        dict.fromkeys(
            filter(None, [os.environ.get("SHELL"), "/bin/zsh", "/bin/bash"])
        )
    )
    for sh in shells:
        if not Path(sh).exists():
            continue
        try:
            import subprocess

            result = subprocess.run(
                [sh, "-ilc", "command -v az"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            resolved = result.stdout.strip()
            if resolved and Path(resolved).exists():
                _az_cli_path = resolved
                return _az_cli_path
        except Exception:
            continue

    # 4. Last resort — will produce a clear FileNotFoundError downstream
    _az_cli_path = "az"
    return _az_cli_path


# ---------------------------------------------------------------------------
# Core: spawn ``az account get-access-token``
# ---------------------------------------------------------------------------

async def _run_az_get_token(
    scope: str,
    tenant: str | None = None,
    *,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> str:
    """Run ``az account get-access-token`` and return the raw token string."""

    az = _find_az_cli()
    args = [
        az,
        "account",
        "get-access-token",
        "--scope",
        scope,
        "--query",
        "accessToken",
        "-o",
        "tsv",
    ]
    if tenant:
        args.extend(["--tenant", tenant])

    logger.debug("Spawning: %s", " ".join(args))

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Azure CLI not found. Install it from "
            "https://learn.microsoft.com/cli/azure/install-azure-cli"
        ) from None
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(
            f"Azure CLI command timed out after {timeout}s."
        ) from None

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        _raise_cli_error(err, tenant)

    token = stdout.decode().strip()
    if not token:
        raise RuntimeError("Azure CLI returned an empty token.")
    return token


def _raise_cli_error(stderr: str, tenant: str | None) -> None:
    """Translate common ``az`` error patterns into actionable messages."""
    tenant_hint = f' --tenant {tenant}' if tenant else ''
    if "AADSTS" in stderr or "login" in stderr.lower():
        raise RuntimeError(
            f'Azure CLI session expired. Run "az login{tenant_hint}" '
            "in your terminal, then retry."
        )
    if "tenant" in stderr.lower():
        raise RuntimeError(
            f'Invalid tenant or no access. Run "az login{tenant_hint}" '
            "to re-authenticate."
        )
    raise RuntimeError(f"Azure CLI error: {stderr or 'Unknown error'}")


# ---------------------------------------------------------------------------
# Public credential class
# ---------------------------------------------------------------------------

class AzCliCredential:
    """Async credential that acquires tokens via the Azure CLI.

    Implements ``get_token()`` / ``close()`` so it can be used as a
    drop-in replacement for ``DefaultAzureCredential`` where only
    ``get_token(*scopes)`` is required.

    Parameters
    ----------
    scope:
        The OAuth2 scope to request a token for,
        e.g. ``"https://graph.microsoft.com/.default"`` or
        ``"https://contoso.sharepoint.com/.default"``.
    tenant:
        Optional tenant ID.  When *None*, ``az`` uses whatever
        tenant the user last logged in to.
    """

    _REFRESH_MARGIN_S = 120  # refresh when < 2 min remaining

    def __init__(
        self,
        scope: str,
        tenant: str | None = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._scope = scope
        self._tenant = tenant
        self._timeout = timeout
        self._cached: AccessTokenInfo | None = None

    # -- async context-manager support --------------------------------------

    async def __aenter__(self) -> AzCliCredential:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -- public API ---------------------------------------------------------

    async def get_token(self, *scopes: str) -> AccessTokenInfo:
        """Return a cached or freshly-acquired access token.

        *scopes* is accepted for API compatibility with
        ``azure.identity`` credentials but is **ignored** — the
        ``scope`` passed at construction time is always used.
        """
        if self._cached and not self._is_near_expiry(self._cached):
            return self._cached

        raw = await _run_az_get_token(
            self._scope, self._tenant, timeout=self._timeout
        )
        meta = parse_token_metadata(raw)
        expires_on = int(meta.expires_at) if meta.expires_at else int(time.time()) + 3600
        self._cached = AccessTokenInfo(token=raw, expires_on=expires_on)
        return self._cached

    async def close(self) -> None:
        """No-op — provided for interface parity with SDK credentials."""

    # -- internals ----------------------------------------------------------

    def _is_near_expiry(self, tok: AccessTokenInfo) -> bool:
        return (tok.expires_on - time.time()) < self._REFRESH_MARGIN_S

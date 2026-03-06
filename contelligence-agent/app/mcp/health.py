"""MCP server health verification.

Provides ``verify_mcp_servers`` which checks whether each configured MCP
server is reachable and returns a typed health payload suitable for
``/api/health`` and startup diagnostics.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")

async def verify_mcp_servers(
    mcp_config: dict[str, dict[str, Any]],
    *,
    timeout: float = 5.0,
) -> dict[str, dict[str, Any]]:
    """Ping each configured MCP server and report health status.

    Parameters
    ----------
    mcp_config:
        The dict returned by ``get_mcp_servers_config()``.
    timeout:
        Maximum seconds to wait for each server probe.

    Returns
    -------
    dict
        ``{ server_name: { "status": "ok"|"degraded"|"unavailable",
                           "transport": "stdio"|"http",
                           "detail": "..." } }``
    """
    results: dict[str, dict[str, Any]] = {}

    for name, cfg in mcp_config.items():
        transport = cfg.get("type", "unknown")
        try:
            if transport == "stdio":
                result = await _check_stdio(cfg, timeout=timeout)
            elif transport == "http":
                result = await _check_http(cfg, timeout=timeout)
            else:
                result = {"status": "unavailable", "detail": f"Unknown transport: {transport}"}
            result["transport"] = transport
            results[name] = result
        except Exception as exc:
            results[name] = {
                "status": "unavailable",
                "transport": transport,
                "detail": str(exc),
            }

    return results


# ── Internal probes ──────────────────────────────────────────────────────

async def _check_stdio(
    cfg: dict[str, Any],
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Check a stdio-based MCP server by verifying the binary exists."""
    command = cfg.get("command", [])
    if not command:
        return {"status": "unavailable", "detail": "No command specified"}

    binary = command[0]
    path = shutil.which(binary)
    if path is None:
        return {
            "status": "unavailable",
            "detail": f"Binary '{binary}' not found on PATH",
        }

    # Optionally run `<binary> --version` for a deeper check
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                binary, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=timeout,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        version = stdout.decode().strip() if stdout else "unknown"
        return {"status": "ok", "detail": f"v{version}" if version else "ok"}
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as exc:
        return {"status": "degraded", "detail": f"Binary found but version check failed: {exc}"}


async def _check_http(
    cfg: dict[str, Any],
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Check an HTTP-based MCP server with a lightweight GET probe."""
    url = cfg.get("url", "")
    if not url:
        return {"status": "unavailable", "detail": "No URL configured"}

    # Check if token is needed but missing
    auth = cfg.get("auth", {})
    if auth and auth.get("type") == "token" and not auth.get("token"):
        return {
            "status": "degraded",
            "detail": "Token not resolved — server may be unreachable",
        }

    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code < 500:
                return {"status": "ok", "detail": f"HTTP {resp.status_code}"}
            return {"status": "degraded", "detail": f"HTTP {resp.status_code}"}
    except ImportError:
        # httpx not available — degrade gracefully
        return {"status": "degraded", "detail": "httpx not installed — cannot probe HTTP server"}
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}

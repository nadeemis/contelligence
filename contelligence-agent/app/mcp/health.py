"""MCP server health verification.

Provides ``verify_mcp_servers`` which checks whether each configured MCP
server is reachable and returns a typed health payload suitable for
``/api/health`` and startup diagnostics.
"""

from __future__ import annotations

import asyncio
import json
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
                           "transport": "stdio"|"http"|"sse"|"local"|"unknown",
                           "detail": "..." } }``
    """
    results: dict[str, dict[str, Any]] = {}

    for name, cfg in mcp_config.items():
        mcp_type = cfg.get("type", "unknown")
        try:
            if mcp_type in ("stdio", "local"):
                result = await _check_stdio(cfg, timeout=timeout)
            elif mcp_type in ("http", "sse"):
                result = await _check_http(cfg, timeout=timeout)
            else:
                result = {"status": "unavailable", "detail": f"Unknown transport: {mcp_type}"}
            result["transport"] = mcp_type
            results[name] = result
        except Exception as exc:
            results[name] = {
                "status": "unavailable",
                "transport": mcp_type,
                "detail": str(exc),
            }

    return results


# ── Internal probes ──────────────────────────────────────────────────────

async def _check_stdio(
    cfg: dict[str, Any],
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Check a stdio-based MCP server by starting it with full command + args.

    Launches the server process, sends an MCP ``initialize`` JSON-RPC message
    over stdin, and waits for a valid response on stdout.  The process is
    always terminated after the probe completes.
    """
    command = cfg.get("command", [])
    if not command:
        return {"status": "unavailable", "detail": "No command specified"}

    # Normalise command to a list and resolve the binary
    if isinstance(command, list):
        cmd_parts = list(command)
    else:
        cmd_parts = [str(command)]

    binary = cmd_parts[0]
    path = shutil.which(binary)
    if path is None:
        return {
            "status": "unavailable",
            "detail": f"Binary '{binary}' not found on PATH",
        }

    # Append args from config (the standard MCP config shape)
    args = cfg.get("args", [])
    if isinstance(args, list):
        cmd_parts.extend(str(a) for a in args)

    # Build an MCP initialize request (JSON-RPC 2.0)
    init_request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "contelligence-health-check", "version": "1.0.0"},
        },
    })

    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *cmd_parts,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=timeout,
        )

        # Send the initialize message followed by a newline (Content-Length
        # framing varies; most stdio MCP servers accept newline-delimited JSON)
        assert proc.stdin is not None
        proc.stdin.write((init_request + "\n").encode())
        await proc.stdin.drain()

        # Read the first line of response within the timeout
        assert proc.stdout is not None
        raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
        response_text = raw.decode().strip() if raw else ""

        if not response_text:
            # No output but process is still alive — partial success
            if proc.returncode is None:
                return {"status": "degraded", "detail": "Server started but returned no initialize response"}
            return {"status": "unavailable", "detail": f"Server exited immediately (code {proc.returncode})"}

        logger.debug(f"Received response from MCP server '{binary}': {response_text}")
        
        # Try to parse the response as JSON-RPC
        try:
            resp = json.loads(response_text)
            if isinstance(resp, dict) and ("result" in resp or "id" in resp):
                server_info = ""
                result = resp.get("result", {})
                if isinstance(result, dict):
                    si = result.get("serverInfo", {})
                    if isinstance(si, dict):
                        name = si.get("name", "")
                        version = si.get("version", "")
                        server_info = f"{name} {version}".strip()
                detail = f"MCP initialize OK"
                if server_info:
                    detail += f" ({server_info})"
                return {"status": "ok", "detail": detail}
            elif isinstance(resp, dict) and "error" in resp:
                err = resp["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                return {"status": "degraded", "detail": f"MCP initialize error: {msg}"}
        except json.JSONDecodeError:
            pass

        # Got some output but not valid JSON-RPC — server started at least
        return {"status": "degraded", "detail": f"Server started but unexpected response: {response_text[:120]}"}

    except asyncio.TimeoutError:
        # Timeout during startup or waiting for response — but process may
        # still be alive (just slow), which still counts as "started"
        if proc and proc.returncode is None:
            return {"status": "degraded", "detail": "Server started but initialize response timed out"}
        return {"status": "unavailable", "detail": "Server failed to start within timeout"}
    except FileNotFoundError:
        return {"status": "unavailable", "detail": f"Command not found: {' '.join(cmd_parts)}"}
    except OSError as exc:
        return {"status": "unavailable", "detail": f"Failed to start server: {exc}"}
    finally:
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                proc.kill()


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


# ── Tool listing ─────────────────────────────────────────────────────────

async def list_server_tools(
    cfg: dict[str, Any],
    *,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """Connect to an MCP server and return its advertised tools.

    Sends ``initialize`` followed by ``tools/list`` using the appropriate
    transport (stdio or HTTP) and returns the tool descriptors.
    """
    mcp_type = cfg.get("type", "unknown")
    if mcp_type in ("stdio", "local"):
        return await _list_tools_stdio(cfg, timeout=timeout)
    elif mcp_type in ("http", "sse"):
        return await _list_tools_http(cfg, timeout=timeout)
    else:
        raise ValueError(f"Unknown transport: {mcp_type}")


async def _list_tools_stdio(
    cfg: dict[str, Any],
    *,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """Start a stdio MCP server, initialize, and request tools/list."""
    command = cfg.get("command", [])
    if not command:
        raise ValueError("No command specified")

    cmd_parts = list(command) if isinstance(command, list) else [str(command)]
    binary = cmd_parts[0]
    path = shutil.which(binary)
    if path is None:
        raise FileNotFoundError(f"Binary '{binary}' not found on PATH")

    args = cfg.get("args", [])
    if isinstance(args, list):
        cmd_parts.extend(str(a) for a in args)

    init_request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "contelligence-tool-list", "version": "1.0.0"},
        },
    })
    initialized_notification = json.dumps({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    })
    tools_request = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    })

    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *cmd_parts,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=timeout,
        )
        assert proc.stdin is not None and proc.stdout is not None

        # 1. Send initialize
        proc.stdin.write((init_request + "\n").encode())
        await proc.stdin.drain()
        raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
        resp_text = raw.decode().strip() if raw else ""
        if not resp_text:
            raise RuntimeError("Server returned no initialize response")
        init_resp = json.loads(resp_text)
        if "error" in init_resp:
            raise RuntimeError(f"Initialize error: {init_resp['error']}")

        # 2. Send initialized notification
        proc.stdin.write((initialized_notification + "\n").encode())
        await proc.stdin.drain()

        # 3. Send tools/list
        proc.stdin.write((tools_request + "\n").encode())
        await proc.stdin.drain()
        raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
        resp_text = raw.decode().strip() if raw else ""
        if not resp_text:
            raise RuntimeError("Server returned no tools/list response")
        tools_resp = json.loads(resp_text)
        if "error" in tools_resp:
            raise RuntimeError(f"tools/list error: {tools_resp['error']}")

        result = tools_resp.get("result", {})
        return result.get("tools", []) if isinstance(result, dict) else []

    finally:
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                proc.kill()


def _parse_json_or_sse(text: str) -> dict[str, Any]:
    """Parse a response body that may be plain JSON or SSE-wrapped JSON.

    SSE responses look like::

        event: message
        data: {"jsonrpc": "2.0", ...}

    This extracts the JSON from the ``data:`` line(s) and parses it.
    Falls back to plain ``json.loads`` for non-SSE bodies.
    """
    stripped = text.strip()
    # Try plain JSON first
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Parse as SSE: collect all "data:" lines and join them
    data_parts: list[str] = []
    for line in stripped.splitlines():
        if line.startswith("data:"):
            data_parts.append(line[len("data:"):].strip())
    if data_parts:
        return json.loads("\n".join(data_parts))

    raise ValueError(f"Response is neither valid JSON nor SSE: {stripped[:200]}")


async def _list_tools_http(
    cfg: dict[str, Any],
    *,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """Send JSON-RPC tools/list to an HTTP-based MCP server."""
    import httpx

    url = cfg.get("url", "")
    if not url:
        raise ValueError("No URL configured")

    headers: dict[str, str] = {"Content-Type": "application/json"}
    auth = cfg.get("auth", {})
    if auth and auth.get("type") == "token" and auth.get("token"):
        headers["Authorization"] = f"Bearer {auth['token']}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        # 1. Initialize
        init_resp = await client.post(url, headers=headers, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "contelligence-tool-list", "version": "1.0.0"},
            },
        })
        
        logger.debug(f"Received response from MCP server at '{url}': {init_resp.text}")
        
        init_resp.raise_for_status()
        init_data = _parse_json_or_sse(init_resp.text)
        if "error" in init_data:
            raise RuntimeError(f"Initialize error: {init_data['error']}")

        # 2. Initialized notification
        await client.post(url, headers=headers, json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

        # 3. tools/list
        tools_resp = await client.post(url, headers=headers, json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        })
        tools_resp.raise_for_status()
        tools_data = _parse_json_or_sse(tools_resp.text)
        if "error" in tools_data:
            raise RuntimeError(f"tools/list error: {tools_data['error']}")

        result = tools_data.get("result", {})
        return result.get("tools", []) if isinstance(result, dict) else []

"""MCP Servers Router — CRUD and health-testing for MCP server configs.

Provides REST endpoints for listing, adding, removing, disabling/enabling,
and testing MCP servers.  All mutations persist to
``~/.contelligence/mcp-config.json``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.mcp.config import get_mcp_servers_config
from app.mcp.file_config import (
    add_server,
    load_file_based_servers,
    remove_server,
    set_server_disabled,
)
from app.mcp.health import list_server_tools, verify_mcp_servers

logger = logging.getLogger(f"contelligence-agent.{__name__}")

router = APIRouter(prefix="/mcp-servers", tags=["MCP Servers"])


# ── Models ─────────────────────────────────────────────────────


class McpServerEntry(BaseModel):
    """A single MCP server as returned by the list endpoint."""

    name: str
    disabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class McpServerHealth(BaseModel):
    """Health probe result for one server."""

    key: str
    status: str
    transport: str = "unknown"
    detail: str = ""


class AddServerRequest(BaseModel):
    """Payload for adding a new MCP server."""

    name: str = Field(
        description="Unique identifier (e.g. 'azure', 'my-server')",
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$",
    )
    config: dict[str, Any] = Field(
        description="Server config dict, must include 'type' ('stdio' or 'http')",
    )


class SetDisabledRequest(BaseModel):
    """Toggle a server's disabled state."""

    disabled: bool


class McpToolEntry(BaseModel):
    """A single tool exposed by an MCP server."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict, alias="inputSchema")

    model_config = {"populate_by_name": True}


# ── Helpers ────────────────────────────────────────────────────


def _build_entry(name: str, cfg: dict[str, Any], exclude: list[str]) -> McpServerEntry:
    return McpServerEntry(
        name=name,
        disabled=name in exclude,
        config=cfg,
    )


# ── Endpoints ──────────────────────────────────────────────────

@router.get("", response_model=list[McpServerEntry])
async def list_mcp_servers() -> list[McpServerEntry]:
    """List all MCP servers from merged config (including disabled ones)."""
    try:
        servers, exclude, _ = load_file_based_servers()
        return [_build_entry(name, cfg, exclude) for name, cfg in servers.items()]
    except Exception as e:
        logger.error(f"Failed to load MCP servers: {e}")
        raise HTTPException(500, "Failed to load MCP servers")
    
    
@router.post("", response_model=McpServerEntry, status_code=201)
async def add_mcp_server(body: AddServerRequest) -> McpServerEntry:
    """Add or update an MCP server in the app config."""
    mcp_type = body.config.get("type", "")
    if mcp_type not in ("stdio", "http", "sse", "local"):
        raise HTTPException(400, "config.type must be 'stdio', 'http', 'sse', or 'local'")
    if mcp_type in ("stdio", "local") and not body.config.get("command"):
        raise HTTPException(400, "stdio/local servers require a 'command' in config")
    if mcp_type in ("http", "sse") and not body.config.get("url"):
        raise HTTPException(400, "http/sse servers require a 'url' in config")

    try:
        add_server(body.name, body.config)
        return McpServerEntry(
            name=body.name,
            disabled=False,
            config=body.config,
        )
    except Exception as e:
        logger.error(f"Failed to add MCP server: {e}")
        raise HTTPException(500, "Failed to add MCP server")


@router.delete("/{key}", status_code=204)
async def delete_mcp_server(key: str) -> None:
    """Remove an MCP server from the app config."""
    try:
        remove_server(key)
    except Exception as e:
        logger.error(f"Failed to remove MCP server: {e}")
        raise HTTPException(500, "Failed to remove MCP server")


@router.patch("/{key}/disabled", response_model=McpServerEntry)
async def toggle_mcp_server(key: str, body: SetDisabledRequest) -> McpServerEntry:
    """Enable or disable an MCP server (adds/removes from exclude list)."""
    try:
        set_server_disabled(key, body.disabled)
        # Re-read to return current state.
        servers, exclude, _ = load_file_based_servers()
        cfg = servers.get(key, {})
        return _build_entry(key, cfg, exclude)
    except Exception as e:
        logger.error(f"Failed to toggle MCP server: {e}")
        raise HTTPException(500, "Failed to toggle MCP server")


@router.get("/{key}/tools", response_model=list[McpToolEntry])
async def show_tools(key: str) -> list[McpToolEntry]:
    """Connect to an MCP server and list the tools it exposes."""
    config = get_mcp_servers_config()
    if key not in config:
        servers, _, _ = load_file_based_servers()
        if key not in servers:
            raise HTTPException(404, f"MCP server '{key}' not found")
        config = servers

    try:
        raw_tools = await list_server_tools(config[key])
        return [
            McpToolEntry(
                name=t.get("name", "unknown"),
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {}),
            )
            for t in raw_tools
        ]
    except Exception as e:
        logger.error(f"Failed to list tools for MCP server '{key}': {e}", exc_info=True)
        raise HTTPException(502, f"Failed to retrieve tools from MCP server '{key}': {e}")


@router.post("/{key}/test", response_model=McpServerHealth)
async def test_mcp_server(key: str) -> McpServerHealth:
    """Run a health probe against a single MCP server."""
    config = get_mcp_servers_config()
    if key not in config:
        # Also check unfiltered (may be disabled).
        servers, _, _ = load_file_based_servers()
        if key not in servers:
            raise HTTPException(404, f"MCP server '{key}' not found")
        config = servers

    try:
        results = await verify_mcp_servers({key: config[key]})
        result = results.get(key, {"status": "unavailable", "detail": "No result"})
        return McpServerHealth(
            key=key,
            status=result.get("status", "unavailable"),
            transport=result.get("transport", "unknown"),
            detail=result.get("detail", ""),
        )
    except Exception as e:
        logger.error(f"Failed to test MCP server: {e}")
        raise HTTPException(500, "Failed to test MCP server")

"""Tests for the MCP Servers CRUD router.

Covers:
- GET /mcp-servers — list servers
- POST /mcp-servers — add a server
- DELETE /mcp-servers/{key} — remove a server
- PATCH /mcp-servers/{key}/disabled — toggle enable/disable
- POST /mcp-servers/{key}/test — health probe
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.mcp_servers import router


# ── Test app fixture ──────────────────────────────────────────────────────


@pytest.fixture()
def tmp_configs(tmp_path: Path):
    """Create temp config paths and patch file_config to use them."""
    app_path = tmp_path / "app-config.json"
    shared_path = tmp_path / "shared-config.json"
    return app_path, shared_path


@pytest.fixture()
def client(tmp_configs) -> TestClient:
    """TestClient wired to the MCP router with temp config paths."""
    app_path, shared_path = tmp_configs
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    # Patch file paths used by file_config module
    with (
        patch("app.mcp.file_config.APP_CONFIG_PATH", app_path),
        patch("app.mcp.file_config.SHARED_CONFIG_PATH", shared_path),
    ):
        yield TestClient(test_app)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── GET /mcp-servers ──────────────────────────────────────────────────────


class TestListServers:
    def test_empty_config(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"mcpServers": {}})
        resp = client.get("/api/v1/mcp-servers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_servers(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {
            "mcpServers": {
                "azure": {"type": "stdio", "command": ["npx", "azure-mcp"]},
                "my-http": {"type": "http", "url": "http://localhost:3000"},
            }
        })
        resp = client.get("/api/v1/mcp-servers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {s["name"] for s in data}
        assert names == {"azure", "my-http"}
        # Each entry should have name, disabled, config
        for entry in data:
            assert set(entry.keys()) == {"name", "disabled", "config"}

    def test_disabled_flag(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {
            "exclude": ["azure"],
            "mcpServers": {
                "azure": {"type": "stdio", "command": ["npx", "azure-mcp"]},
            }
        })
        resp = client.get("/api/v1/mcp-servers")
        data = resp.json()
        assert data[0]["disabled"] is True


# ── POST /mcp-servers ─────────────────────────────────────────────────────


class TestAddServer:
    def test_add_stdio_server(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"mcpServers": {}})
        resp = client.post("/api/v1/mcp-servers", json={
            "name": "new-srv",
            "config": {"type": "stdio", "command": ["npx", "my-mcp-server"]},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "new-srv"
        assert data["config"]["type"] == "stdio"

    def test_add_http_server(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"mcpServers": {}})
        resp = client.post("/api/v1/mcp-servers", json={
            "name": "remote",
            "config": {"type": "http", "url": "http://localhost:5000"},
        })
        assert resp.status_code == 201
        assert resp.json()["config"]["type"] == "http"

    def test_add_stdio_without_command_fails(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"mcpServers": {}})
        resp = client.post("/api/v1/mcp-servers", json={
            "name": "bad",
            "config": {"type": "stdio"},
        })
        assert resp.status_code == 400

    def test_add_http_without_url_fails(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"mcpServers": {}})
        resp = client.post("/api/v1/mcp-servers", json={
            "name": "bad",
            "config": {"type": "http"},
        })
        assert resp.status_code == 400

    def test_add_persists_to_file(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"mcpServers": {}})
        client.post("/api/v1/mcp-servers", json={
            "name": "persisted",
            "config": {"type": "http", "url": "http://x"},
        })
        loaded = json.loads(app_path.read_text(encoding="utf-8"))
        assert "persisted" in loaded["mcpServers"]


# ── DELETE /mcp-servers/{key} ─────────────────────────────────────────────


class TestDeleteServer:
    def test_delete_existing(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"mcpServers": {"rm-me": {"type": "http", "url": "http://x"}}})
        resp = client.delete("/api/v1/mcp-servers/rm-me")
        assert resp.status_code == 204
        loaded = json.loads(app_path.read_text(encoding="utf-8"))
        assert "rm-me" not in loaded["mcpServers"]

    def test_delete_nonexistent_is_noop(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"mcpServers": {"keep": {"type": "http"}}})
        resp = client.delete("/api/v1/mcp-servers/nope")
        assert resp.status_code == 204


# ── PATCH /mcp-servers/{key}/disabled ─────────────────────────────────────


class TestToggleDisabled:
    def test_disable_server(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"exclude": [], "mcpServers": {"s": {"type": "http", "url": "http://s"}}})
        resp = client.patch("/api/v1/mcp-servers/s/disabled", json={"disabled": True})
        assert resp.status_code == 200
        assert resp.json()["disabled"] is True

    def test_enable_server(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"exclude": ["s"], "mcpServers": {"s": {"type": "http", "url": "http://s"}}})
        resp = client.patch("/api/v1/mcp-servers/s/disabled", json={"disabled": False})
        assert resp.status_code == 200
        assert resp.json()["disabled"] is False


# ── POST /mcp-servers/{key}/test ──────────────────────────────────────────


class TestHealthProbe:
    def test_test_known_server(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"mcpServers": {"s": {"type": "http", "url": "http://s"}}})
        with patch("app.routers.mcp_servers.verify_mcp_servers", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"s": {"status": "ok", "transport": "http", "detail": "HTTP 200"}}
            resp = client.post("/api/v1/mcp-servers/s/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["key"] == "s"

    def test_test_unknown_server_404(self, client: TestClient, tmp_configs) -> None:
        app_path, _ = tmp_configs
        _write_json(app_path, {"mcpServers": {}})
        resp = client.post("/api/v1/mcp-servers/nope/test")
        assert resp.status_code == 404

"""Tests for file-based MCP server configuration loading.

Covers:
- Missing config files (no-op)
- Only shared config
- Only app config
- Both configs with and without overlap
- importSharedConfig: false
- exclude list
- Malformed JSON
- Invalid server definitions
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.mcp.file_config import (
    _extract_servers,
    _read_mcp_json,
    add_server,
    ensure_default_config,
    load_file_based_servers,
    remove_server,
    save_app_config,
    set_server_disabled,
)


# ── Helpers ───────────────────────────────────────────────────────────────


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ── _read_mcp_json ───────────────────────────────────────────────────────


class TestReadMcpJson:

    def test_returns_empty_when_missing(self, tmp_path: Path) -> None:
        result = _read_mcp_json(tmp_path / "nope.json")
        assert result == {}

    def test_returns_parsed_dict(self, tmp_path: Path) -> None:
        p = tmp_path / "conf.json"
        _write_json(p, {"mcpServers": {"a": {"type": "http", "url": "http://x"}}})
        result = _read_mcp_json(p)
        assert "mcpServers" in result

    def test_returns_empty_on_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{invalid", encoding="utf-8")
        result = _read_mcp_json(p)
        assert result == {}

    def test_returns_empty_when_root_is_not_dict(self, tmp_path: Path) -> None:
        p = tmp_path / "arr.json"
        p.write_text("[1,2,3]", encoding="utf-8")
        result = _read_mcp_json(p)
        assert result == {}


# ── _extract_servers ─────────────────────────────────────────────────────


class TestExtractServers:

    def test_extracts_valid_servers(self) -> None:
        data = {
            "mcpServers": {
                "a": {"type": "http", "url": "http://x"},
                "b": {"type": "stdio", "command": ["node", "server.js"]},
            }
        }
        result = _extract_servers(data)
        assert set(result.keys()) == {"a", "b"}

    def test_skips_non_dict_server(self) -> None:
        data = {"mcpServers": {"bad": "string_value"}}
        result = _extract_servers(data)
        assert result == {}

    def test_skips_unsupported_type(self) -> None:
        data = {"mcpServers": {"ws": {"type": "websocket", "url": "ws://x"}}}
        result = _extract_servers(data)
        assert result == {}

    def test_returns_empty_when_no_mcpServers_key(self) -> None:
        result = _extract_servers({"other": "stuff"})
        assert result == {}

    def test_returns_empty_when_mcpServers_not_dict(self) -> None:
        result = _extract_servers({"mcpServers": [1, 2]})
        assert result == {}


# ── load_file_based_servers ──────────────────────────────────────────────


class TestLoadFileBasedServers:

    def test_no_files_returns_empty(self, tmp_path: Path) -> None:
        servers, exclude, imported = load_file_based_servers(
            shared_path=tmp_path / "shared.json",
            app_path=tmp_path / "app.json",
        )
        assert servers == {}
        assert exclude == []
        assert imported is False

    def test_only_shared_file(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared.json"
        _write_json(shared, {
            "mcpServers": {
                "ext-tool": {"type": "stdio", "command": ["ext-tool"]},
            }
        })
        servers, exclude, imported = load_file_based_servers(
            shared_path=shared,
            app_path=tmp_path / "app.json",
        )
        assert "ext-tool" in servers
        assert imported is True

    def test_only_app_file(self, tmp_path: Path) -> None:
        app = tmp_path / "app.json"
        _write_json(app, {
            "mcpServers": {
                "my-server": {"type": "http", "url": "http://localhost:9000"},
            }
        })
        servers, exclude, imported = load_file_based_servers(
            shared_path=tmp_path / "shared.json",
            app_path=app,
        )
        assert "my-server" in servers
        assert imported is False

    def test_both_files_no_overlap(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared.json"
        app = tmp_path / "app.json"
        _write_json(shared, {
            "mcpServers": {"s1": {"type": "http", "url": "http://s1"}},
        })
        _write_json(app, {
            "mcpServers": {"a1": {"type": "stdio", "command": ["a1"]}},
        })
        servers, _, imported = load_file_based_servers(
            shared_path=shared, app_path=app,
        )
        assert set(servers.keys()) == {"s1", "a1"}
        assert imported is True

    def test_app_overrides_shared_same_name(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared.json"
        app = tmp_path / "app.json"
        _write_json(shared, {
            "mcpServers": {"srv": {"type": "http", "url": "http://shared"}},
        })
        _write_json(app, {
            "mcpServers": {"srv": {"type": "http", "url": "http://app-override"}},
        })
        servers, _, _ = load_file_based_servers(
            shared_path=shared, app_path=app,
        )
        assert servers["srv"]["url"] == "http://app-override"

    def test_import_shared_false_skips_shared(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared.json"
        app = tmp_path / "app.json"
        _write_json(shared, {
            "mcpServers": {"shared-only": {"type": "http", "url": "http://s"}},
        })
        _write_json(app, {
            "importSharedConfig": False,
            "mcpServers": {"app-only": {"type": "stdio", "command": ["x"]}},
        })
        servers, _, imported = load_file_based_servers(
            shared_path=shared, app_path=app,
        )
        assert "shared-only" not in servers
        assert "app-only" in servers
        assert imported is False

    def test_exclude_list(self, tmp_path: Path) -> None:
        app = tmp_path / "app.json"
        _write_json(app, {
            "exclude": ["noisy"],
            "mcpServers": {},
        })
        servers, exclude, _ = load_file_based_servers(
            shared_path=tmp_path / "shared.json",
            app_path=app,
        )
        assert exclude == ["noisy"]

    def test_malformed_shared_file_skipped(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared.json"
        shared.parent.mkdir(parents=True, exist_ok=True)
        shared.write_text("{bad json", encoding="utf-8")
        app = tmp_path / "app.json"
        _write_json(app, {
            "mcpServers": {"ok": {"type": "http", "url": "http://ok"}},
        })
        servers, _, imported = load_file_based_servers(
            shared_path=shared, app_path=app,
        )
        assert "ok" in servers
        assert imported is False

    def test_malformed_app_file_skipped(self, tmp_path: Path) -> None:
        app = tmp_path / "app.json"
        app.parent.mkdir(parents=True, exist_ok=True)
        app.write_text("not json!", encoding="utf-8")
        shared = tmp_path / "shared.json"
        _write_json(shared, {
            "mcpServers": {"s": {"type": "http", "url": "http://s"}},
        })
        servers, exclude, imported = load_file_based_servers(
            shared_path=shared, app_path=app,
        )
        # Shared should still be imported since app file is broken
        # (importSharedConfig defaults to True when app data is empty)
        assert "s" in servers
        assert imported is True
        assert exclude == []

    def test_exclude_not_a_list_ignored(self, tmp_path: Path) -> None:
        app = tmp_path / "app.json"
        _write_json(app, {
            "exclude": "should-be-a-list",
            "mcpServers": {},
        })
        _, exclude, _ = load_file_based_servers(
            shared_path=tmp_path / "shared.json",
            app_path=app,
        )
        assert exclude == []


# ── Integration with get_mcp_servers_config ──────────────────────────────


class TestConfigIntegration:
    """Verify that file-based servers merge into get_mcp_servers_config."""

    def test_file_servers_returned(self, tmp_path: Path) -> None:
        with patch("app.mcp.config.load_file_based_servers") as mock_load:
            mock_load.return_value = (
                {"custom-tool": {"type": "stdio", "command": ["custom-tool"]}},
                [],
                True,
            )
            from app.mcp.config import get_mcp_servers_config
            cfg = get_mcp_servers_config()

        assert "custom-tool" in cfg

    def test_exclude_removes_server(self, tmp_path: Path) -> None:
        with patch("app.mcp.config.load_file_based_servers") as mock_load:
            mock_load.return_value = (
                {"azure": {"type": "stdio", "command": ["az-mcp"]}, "github": {"type": "stdio", "command": ["gh-mcp"]}},
                ["azure"],
                True,
            )
            from app.mcp.config import get_mcp_servers_config
            cfg = get_mcp_servers_config()

        assert "azure" not in cfg
        assert "github" in cfg

    def test_file_server_overrides_shared(self) -> None:
        with patch("app.mcp.config.load_file_based_servers") as mock_load:
            mock_load.return_value = (
                {"azure": {"type": "http", "url": "http://custom-azure:5008"}},
                [],
                False,
            )
            from app.mcp.config import get_mcp_servers_config
            cfg = get_mcp_servers_config()

        assert cfg["azure"]["type"] == "http"
        assert cfg["azure"]["url"] == "http://custom-azure:5008"


# ── Write operations ─────────────────────────────────────────────────────


class TestSaveAppConfig:
    """Tests for save_app_config."""

    def test_creates_file(self, tmp_path: Path) -> None:
        app = tmp_path / "sub" / "config.json"
        data = {"importSharedConfig": True, "exclude": [], "mcpServers": {"s": {"type": "http", "url": "http://s"}}}
        save_app_config(data, app_path=app)
        assert app.is_file()
        loaded = json.loads(app.read_text(encoding="utf-8"))
        assert loaded["mcpServers"]["s"]["url"] == "http://s"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        app = tmp_path / "config.json"
        _write_json(app, {"mcpServers": {"old": {}}})
        save_app_config({"mcpServers": {"new": {}}}, app_path=app)
        loaded = json.loads(app.read_text(encoding="utf-8"))
        assert "new" in loaded["mcpServers"]
        assert "old" not in loaded["mcpServers"]


class TestAddServer:
    """Tests for add_server."""

    def test_add_new(self, tmp_path: Path) -> None:
        app = tmp_path / "config.json"
        _write_json(app, {"mcpServers": {}})
        result = add_server("test-srv", {"type": "http", "url": "http://x"}, app_path=app)
        assert "test-srv" in result["mcpServers"]
        # Verify persisted
        loaded = json.loads(app.read_text(encoding="utf-8"))
        assert "test-srv" in loaded["mcpServers"]

    def test_add_creates_file_if_missing(self, tmp_path: Path) -> None:
        app = tmp_path / "new" / "config.json"
        result = add_server("s", {"type": "stdio", "command": ["s"]}, app_path=app)
        assert "s" in result["mcpServers"]

    def test_add_removes_from_exclude(self, tmp_path: Path) -> None:
        app = tmp_path / "config.json"
        _write_json(app, {"exclude": ["srv-a"], "mcpServers": {}})
        result = add_server("srv-a", {"type": "http", "url": "http://a"}, app_path=app)
        assert "srv-a" not in result.get("exclude", [])

    def test_add_replaces_existing(self, tmp_path: Path) -> None:
        app = tmp_path / "config.json"
        _write_json(app, {"mcpServers": {"s": {"type": "http", "url": "http://old"}}})
        add_server("s", {"type": "http", "url": "http://new"}, app_path=app)
        loaded = json.loads(app.read_text(encoding="utf-8"))
        assert loaded["mcpServers"]["s"]["url"] == "http://new"


class TestRemoveServer:
    """Tests for remove_server."""

    def test_remove_existing(self, tmp_path: Path) -> None:
        app = tmp_path / "config.json"
        _write_json(app, {"mcpServers": {"a": {"type": "http"}, "b": {"type": "http"}}})
        result = remove_server("a", app_path=app)
        assert "a" not in result["mcpServers"]
        assert "b" in result["mcpServers"]

    def test_remove_nonexistent_is_noop(self, tmp_path: Path) -> None:
        app = tmp_path / "config.json"
        _write_json(app, {"mcpServers": {"a": {"type": "http"}}})
        result = remove_server("nope", app_path=app)
        assert "a" in result["mcpServers"]


class TestSetServerDisabled:
    """Tests for set_server_disabled."""

    def test_disable_adds_to_exclude(self, tmp_path: Path) -> None:
        app = tmp_path / "config.json"
        _write_json(app, {"exclude": [], "mcpServers": {"s": {"type": "http"}}})
        result = set_server_disabled("s", True, app_path=app)
        assert "s" in result["exclude"]

    def test_enable_removes_from_exclude(self, tmp_path: Path) -> None:
        app = tmp_path / "config.json"
        _write_json(app, {"exclude": ["s"], "mcpServers": {"s": {"type": "http"}}})
        result = set_server_disabled("s", False, app_path=app)
        assert "s" not in result["exclude"]

    def test_disable_idempotent(self, tmp_path: Path) -> None:
        app = tmp_path / "config.json"
        _write_json(app, {"exclude": ["s"], "mcpServers": {"s": {"type": "http"}}})
        result = set_server_disabled("s", True, app_path=app)
        assert result["exclude"].count("s") == 1

    def test_enable_idempotent(self, tmp_path: Path) -> None:
        app = tmp_path / "config.json"
        _write_json(app, {"exclude": [], "mcpServers": {"s": {"type": "http"}}})
        result = set_server_disabled("s", False, app_path=app)
        assert "s" not in result["exclude"]


# ── ensure_default_config ─────────────────────────────────────────────────


class TestEnsureDefaultConfig:
    """Tests for ensure_default_config."""

    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        app = tmp_path / "sub" / "mcp-config.json"
        created = ensure_default_config(app_path=app)
        assert created is True
        assert app.is_file()
        data = json.loads(app.read_text(encoding="utf-8"))
        assert isinstance(data["mcpServers"], dict)
        assert data["importSharedConfig"] is True
        assert data["exclude"] == []

    def test_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        app = tmp_path / "mcp-config.json"
        _write_json(app, {"mcpServers": {"custom": {"type": "http", "url": "http://x"}}})
        created = ensure_default_config(app_path=app)
        assert created is False
        data = json.loads(app.read_text(encoding="utf-8"))
        assert "custom" in data["mcpServers"]
        assert "azure" not in data["mcpServers"]

    def test_default_servers_are_valid(self, tmp_path: Path) -> None:
        app = tmp_path / "mcp-config.json"
        ensure_default_config(app_path=app)
        data = json.loads(app.read_text(encoding="utf-8"))
        for name, cfg in data["mcpServers"].items():
            assert cfg["type"] in ("stdio", "http"), f"{name} has invalid type"

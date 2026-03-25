"""File-based MCP server configuration loader.

Reads user-defined MCP servers from:
- ``~/.contelligence/mcp-config.json``  (app-specific, highest priority)
- ``~/.copilot/mcp-config.json``        (shared ecosystem config)

and merges them with the built-in programmatic servers from ``config.py``.

See ``docs/gitignore/MCP_CONFIG_LAYERED_LOADING.md`` for the full design.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# ── Well-known config paths ───────────────────────────────────────────────

_HOME = Path.home()
SHARED_CONFIG_PATH = _HOME / ".copilot" / "mcp-config.json"
APP_CONFIG_PATH = _HOME / ".contelligence" / "mcp-config.json"


# ── Helpers ───────────────────────────────────────────────────────────────


def _read_mcp_json(path: Path) -> dict[str, Any]:
    """Read and parse an MCP config JSON file.

    Returns an empty dict if the file is missing or malformed.
    """
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            logger.warning("MCP config %s: root is not an object — skipping", path)
            return {}
        return data
    except json.JSONDecodeError as exc:
        logger.warning("MCP config %s: invalid JSON — %s", path, exc)
        return {}
    except OSError as exc:
        logger.warning("MCP config %s: read error — %s", path, exc)
        return {}


def _extract_servers(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Pull the ``mcpServers`` dict from a parsed config, with validation."""
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        logger.warning("mcpServers is not an object — ignoring")
        return {}

    validated: dict[str, dict[str, Any]] = {}
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            logger.warning("MCP server '%s' config is not an object — skipping", name)
            continue
        transport = cfg.get("type", "")
        if transport not in ("stdio", "http"):
            logger.warning(
                "MCP server '%s' has unsupported type '%s' — skipping",
                name,
                transport,
            )
            continue
        validated[name] = cfg
    return validated


# ── Public API ────────────────────────────────────────────────────────────


def load_file_based_servers(
    *,
    shared_path: Path | None = None,
    app_path: Path | None = None,
) -> tuple[
    dict[str, dict[str, Any]],  # merged file-based servers
    list[str],                   # exclude list
    bool,                        # whether shared config was imported
]:
    """Load and merge file-based MCP server configs.

    Parameters
    ----------
    shared_path:
        Override for the shared config path (useful for testing).
    app_path:
        Override for the app config path (useful for testing).

    Returns
    -------
    servers
        Merged server configs (shared underneath, app on top).
    exclude
        Server names to remove from the final config.
    imported_shared
        ``True`` if the shared config was read and merged.
    """
    _shared_path = shared_path or SHARED_CONFIG_PATH
    _app_path = app_path or APP_CONFIG_PATH

    # --- App-specific config (controls merge behaviour) ----------------
    app_data = _read_mcp_json(_app_path)
    import_shared: bool = app_data.get("importSharedConfig", True)
    exclude: list[str] = app_data.get("exclude", [])
    if not isinstance(exclude, list):
        exclude = []
    app_servers = _extract_servers(app_data)

    # --- Shared ecosystem config ---------------------------------------
    shared_servers: dict[str, dict[str, Any]] = {}
    imported_shared = False
    if import_shared:
        shared_data = _read_mcp_json(_shared_path)
        shared_servers = _extract_servers(shared_data)
        if shared_servers:
            imported_shared = True
            logger.info(
                "Imported %d server(s) from shared config: %s",
                len(shared_servers),
                _shared_path,
            )

    # --- Merge: shared underneath, app on top --------------------------
    merged = {**shared_servers, **app_servers}

    if app_servers:
        logger.info(
            "Loaded %d server(s) from app config: %s",
            len(app_servers),
            _app_path,
        )

    return merged, exclude, imported_shared


# ── Default config scaffolding ─────────────────────────────────────────────

#: Servers written to a fresh ``~/.contelligence/mcp-config.json`` on first run.
_DEFAULT_MCP_SERVERS: dict[str, dict[str, Any]] = {
    "microsoft-learn": {
      "type": "http",
      "url": "https://learn.microsoft.com/api/mcp",
      "tools": [
        "*"
      ]
    },
    "deepwiki": {
      "type": "http",
      "url": "https://mcp.deepwiki.com/mcp",
      "tools": [
        "*"
      ]
    }
  }


def ensure_default_config(
    *,
    app_path: Path | None = None,
) -> bool:
    """Create the app-specific MCP config with sensible defaults if absent.

    Returns ``True`` when a new file was written, ``False`` when one already
    existed (no overwrite).
    """
    _app_path = app_path or APP_CONFIG_PATH
    if _app_path.is_file():
        return False

    data = {
        "importSharedConfig": True,
        "exclude": [],
        "mcpServers": _DEFAULT_MCP_SERVERS,
    }
    save_app_config(data, app_path=_app_path)
    logger.info("Created default MCP config at %s", _app_path)
    return True


# ── Write operations ──────────────────────────────────────────────────────


def save_app_config(
    data: dict[str, Any],
    *,
    app_path: Path | None = None,
) -> None:
    """Write the app-specific MCP config file atomically.

    Parameters
    ----------
    data:
        Full config dict (must include ``mcpServers``, optionally
        ``importSharedConfig`` and ``exclude``).
    app_path:
        Override for the config path (useful for testing).
    """
    _app_path = app_path or APP_CONFIG_PATH
    _app_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    _app_path.write_text(text, encoding="utf-8")
    logger.info("Saved app MCP config to %s", _app_path)


def add_server(
    name: str,
    cfg: dict[str, Any],
    *,
    app_path: Path | None = None,
) -> dict[str, Any]:
    """Add or update a server entry in the app config and return the full config."""
    _app_path = app_path or APP_CONFIG_PATH
    data = _read_mcp_json(_app_path)
    if not data:
        data = {"importSharedConfig": True, "exclude": [], "mcpServers": {}}
    if "mcpServers" not in data:
        data["mcpServers"] = {}
    data["mcpServers"][name] = cfg
    # If the server was previously excluded, remove it from exclude
    if isinstance(data.get("exclude"), list) and name in data["exclude"]:
        data["exclude"].remove(name)
    save_app_config(data, app_path=_app_path)
    return data


def remove_server(
    name: str,
    *,
    app_path: Path | None = None,
) -> dict[str, Any]:
    """Remove a server from the app config and return the full config."""
    _app_path = app_path or APP_CONFIG_PATH
    data = _read_mcp_json(_app_path)
    if not data:
        data = {"importSharedConfig": True, "exclude": [], "mcpServers": {}}
    if "mcpServers" in data:
        data["mcpServers"].pop(name, None)
    save_app_config(data, app_path=_app_path)
    return data


def set_server_disabled(
    name: str,
    disabled: bool,
    *,
    app_path: Path | None = None,
) -> dict[str, Any]:
    """Add or remove a server from the exclude list."""
    _app_path = app_path or APP_CONFIG_PATH
    data = _read_mcp_json(_app_path)
    if not data:
        data = {"importSharedConfig": True, "exclude": [], "mcpServers": {}}
    exclude = data.get("exclude", [])
    if not isinstance(exclude, list):
        exclude = []

    if disabled and name not in exclude:
        exclude.append(name)
    elif not disabled and name in exclude:
        exclude.remove(name)

    data["exclude"] = exclude
    save_app_config(data, app_path=_app_path)
    return data

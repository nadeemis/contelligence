#!/usr/bin/env python3
"""Verify Azure MCP Server installation and basic connectivity.

Run from the project root::

    python scripts/verify_mcp.py

Prerequisites:
    pip install msmcp-azure
    az login          # for DefaultAzureCredential in development
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys


def _header(text: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {text}")
    print(f"{'─'*60}")


def check_binary() -> bool:
    """Ensure the ``azmcp`` binary is on PATH."""
    _header("1. Checking azmcp binary")
    path = shutil.which("azmcp")
    if path is None:
        print("  ✗ 'azmcp' not found on PATH.")
        print("  → Install with: pip install msmcp-azure")
        return False
    print(f"  ✓ Found: {path}")
    return True


def check_version() -> bool:
    """Print ``azmcp --version``."""
    _header("2. Version check")
    try:
        result = subprocess.run(
            ["azmcp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        print(f"  ✓ {version}")
        return True
    except Exception as exc:
        print(f"  ✗ Could not determine version: {exc}")
        return False


def check_tool_list() -> bool:
    """Run ``azmcp tool list`` and report available tools."""
    _header("3. Listing available MCP tools")
    try:
        result = subprocess.run(
            ["azmcp", "tool", "list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"  ✗ azmcp tool list failed (exit {result.returncode})")
            print(f"    stderr: {result.stderr.strip()}")
            return False
        lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
        print(f"  ✓ {len(lines)} tools available")
        # Show first 10
        for line in lines[:10]:
            print(f"    - {line.strip()}")
        if len(lines) > 10:
            print(f"    ... and {len(lines) - 10} more")
        return True
    except Exception as exc:
        print(f"  ✗ Could not list tools: {exc}")
        return False


def check_azure_cli() -> bool:
    """Verify ``az`` CLI is logged in for DefaultAzureCredential."""
    _header("4. Azure CLI authentication")
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "name", "-o", "tsv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            print(f"  ✓ Logged in to subscription: {result.stdout.strip()}")
            return True
        print("  ✗ Azure CLI not logged in. Run: az login")
        return False
    except FileNotFoundError:
        print("  ✗ Azure CLI not installed.")
        return False
    except Exception as exc:
        print(f"  ✗ Error: {exc}")
        return False


def main() -> None:
    print("Azure MCP Server Verification")
    print("=" * 60)

    results = {
        "binary": check_binary(),
        "version": check_version(),
        "tools": check_tool_list(),
        "azure_cli": check_azure_cli(),
    }

    _header("Summary")
    all_ok = all(results.values())
    for name, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")

    if all_ok:
        print("\n  All checks passed — MCP server is ready for development.")
    else:
        print("\n  Some checks failed — review the output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

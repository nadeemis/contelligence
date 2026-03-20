# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Contelligence backend (one-folder bundle).

Usage:
    cd contelligence-agent
    pyinstaller contelligence-agent.spec

The resulting 'dist/contelligence-agent/' directory contains the standalone
backend binary plus all runtime dependencies. Electron Forge copies this
directory into the app resources via extraResource.
"""

import sys
from pathlib import Path

block_cipher = None
here = Path(SPECPATH)  # noqa: F821 — SPECPATH injected by PyInstaller

a = Analysis(
    [str(here / "main.py")],
    pathex=[str(here)],
    binaries=[],
    datas=[
        # Built-in skills (Markdown + config files)
        (str(here / "skills"), "skills"),
        # Prompt templates
        (str(here / "app" / "prompts"), "app/prompts"),
    ],
    hiddenimports=[
        # FastAPI + Uvicorn
        "fastapi",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # Pydantic
        "pydantic",
        "pydantic_settings",
        # SQLite shim
        "aiosqlite",
        # Azure SDK (needed for exception classes even in local mode)
        "azure.cosmos",
        "azure.cosmos.aio",
        "azure.cosmos.exceptions",
        "azure.identity",
        "azure.identity.aio",
        # Copilot SDK
        "github_copilot_sdk",
        # OpenTelemetry
        "opentelemetry",
        "opentelemetry.trace",
        "opentelemetry.metrics",
        # Scheduling
        "apscheduler",
        "croniter",
        # Document parsing
        "pymupdf",
        "docx",
        "openpyxl",
        "pptx",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Development-only
        "pytest",
        "mypy",
        "black",
        "ruff",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="contelligence-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Keep console for log output
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="contelligence-agent",
)

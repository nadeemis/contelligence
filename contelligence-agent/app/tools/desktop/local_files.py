"""Tool for reading, listing, and writing files on the local desktop filesystem."""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool, ToolDefinition

logger = logging.getLogger(__name__)

# Allowed base directories — restricts access to user-visible locations only.
# Expandable via settings if needed in the future.
_ALLOWED_ROOTS: tuple[str, ...] = (
    str(Path.home()),
)


def _is_safe_path(target: Path) -> bool:
    """Return True if *target* is inside one of the allowed root directories."""
    resolved = target.resolve()
    return any(
        str(resolved).startswith(str(Path(root).resolve()))
        for root in _ALLOWED_ROOTS
    )


class LocalFilesParams(BaseModel):
    """Parameters for the local_files tool."""

    action: Literal["list", "read", "write"] = Field(
        description=(
            "Action to perform: 'list' to enumerate files/directories, "
            "'read' to read file content as text, "
            "'write' to write text content to a file."
        )
    )
    path: str = Field(
        description=(
            "Absolute or ~-relative path on the local filesystem. "
            "For 'list': a directory to enumerate. "
            "For 'read': a file to read. "
            "For 'write': a file to write to (parent directories are created automatically)."
        )
    )
    content: str | None = Field(
        default=None,
        description="Text content to write. Required when action='write'.",
    )
    max_results: int = Field(
        default=200,
        description="Maximum entries to return when listing a directory.",
    )
    recursive: bool = Field(
        default=False,
        description="If True, list directory contents recursively (only for action='list').",
    )


@define_tool(
    name="local_files",
    description=(
        "Read, list, or write files on the local desktop filesystem. "
        "Use action='list' to enumerate a directory (optionally recursive), "
        "action='read' to get file content as text, or "
        "action='write' to create/overwrite a file with text content. "
        "Paths must be inside the user's home directory."
    ),
    parameters_model=LocalFilesParams,
)
async def local_files(params: LocalFilesParams, context: dict) -> dict:
    """Handle local_files tool invocations."""
    target = Path(params.path).expanduser()

    if not _is_safe_path(target):
        return {"error": f"Access denied — path must be under the user's home directory."}

    if params.action == "list":
        return await _list_dir(target, params.max_results, params.recursive)

    if params.action == "read":
        return await _read_file(target)

    if params.action == "write":
        if params.content is None:
            return {"error": "The 'content' parameter is required for action='write'."}
        return await _write_file(target, params.content)

    return {"error": f"Unknown action: {params.action}"}


async def _list_dir(directory: Path, max_results: int, recursive: bool) -> dict:
    """List directory contents."""
    if not directory.exists():
        return {"error": f"Directory not found: {directory}"}
    if not directory.is_dir():
        return {"error": f"Not a directory: {directory}"}

    entries: list[dict] = []
    try:
        iterator = directory.rglob("*") if recursive else directory.iterdir()
        for item in sorted(iterator):
            if not _is_safe_path(item):
                continue
            ct, _ = mimetypes.guess_type(str(item))
            entries.append({
                "name": str(item.relative_to(directory)),
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
                "content_type": ct,
            })
            if len(entries) >= max_results:
                break
    except PermissionError:
        return {"error": f"Permission denied: {directory}"}

    logger.debug("local_files list path=%s returned %d entries", directory, len(entries))
    return {
        "path": str(directory),
        "count": len(entries),
        "entries": entries,
    }


async def _read_file(file_path: Path) -> dict:
    """Read a file as text."""
    if not file_path.exists():
        return {"error": f"File not found: {file_path}"}
    if not file_path.is_file():
        return {"error": f"Not a file: {file_path}"}

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return {"error": f"Permission denied: {file_path}"}

    logger.debug("local_files read path=%s size=%d", file_path, len(content))
    return {
        "path": str(file_path),
        "content": content,
        "size": len(content),
    }


async def _write_file(file_path: Path, content: str) -> dict:
    """Write text content to a file."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except PermissionError:
        return {"error": f"Permission denied: {file_path}"}

    logger.info("local_files write path=%s size=%d", file_path, len(content))
    return {
        "status": "written",
        "path": str(file_path),
        "size": len(content),
    }

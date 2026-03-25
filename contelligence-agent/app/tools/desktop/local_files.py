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
    offset: int = Field(
        default=0,
        description=(
            "Byte offset to start reading from (only for action='read'). "
            "Defaults to 0 (beginning of file)."
        ),
    )
    length: int | None = Field(
        default=None,
        description=(
            "Maximum number of bytes to read (only for action='read'). "
            "Defaults to None (read to end of file from offset)."
        ),
    )
    append: bool = Field(
        default=False,
        description=(
            "If True, append content to the file instead of overwriting "
            "(only for action='write'). Defaults to False."
        ),
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
        "action='read' to get file content as text (supports chunked reads via "
        "offset/length for large files), or "
        "action='write' to create/overwrite a file with text content (supports "
        "append mode for chunked writes). "
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
        return await _read_file(target, params.offset, params.length)

    if params.action == "write":
        if params.content is None:
            return {"error": "The 'content' parameter is required for action='write'."}
        return await _write_file(target, params.content, params.append)

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


async def _read_file(file_path: Path, offset: int = 0, length: int | None = None) -> dict:
    """Read a file as text, optionally from *offset* for up to *length* bytes."""
    if not file_path.exists():
        return {"error": f"File not found: {file_path}"}
    if not file_path.is_file():
        return {"error": f"Not a file: {file_path}"}

    total_size = file_path.stat().st_size

    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as fh:
            if offset > 0:
                fh.seek(offset)
            content = fh.read(length) if length is not None else fh.read()
            end_offset = fh.tell()
    except PermissionError:
        return {"error": f"Permission denied: {file_path}"}

    logger.debug(
        "local_files read path=%s offset=%d length=%s chunk=%d",
        file_path, offset, length, len(content),
    )
    return {
        "path": str(file_path),
        "content": content,
        "size": len(content),
        "total_size": total_size,
        "offset": offset,
        "end_offset": end_offset,
        "has_more": end_offset < total_size,
    }


async def _write_file(file_path: Path, content: str, append: bool = False) -> dict:
    """Write text content to a file. Appends if *append* is True."""
    mode = "a" if append else "w"
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open(mode, encoding="utf-8") as fh:
            fh.write(content)
    except PermissionError:
        return {"error": f"Permission denied: {file_path}"}

    total_size = file_path.stat().st_size
    logger.info(
        "local_files write path=%s append=%s chunk=%d total=%d",
        file_path, append, len(content), total_size,
    )
    return {
        "status": "appended" if append else "written",
        "path": str(file_path),
        "size": len(content),
        "total_size": total_size,
    }

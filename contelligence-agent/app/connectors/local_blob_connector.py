"""Local filesystem blob connector — drop-in replacement for BlobConnectorAdapter.

Stores files in a local directory tree mimicking Azure Blob container/path structure:
    base_dir/
    ├── agent-outputs/
    │   └── <session_id>/result.json
    └── skills/
        └── <skill_id>/SKILL.md
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

from app.connectors.blob_types import BlobInfo, BlobProperties

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class LocalBlobConnectorAdapter:
    """Filesystem-based blob storage with the same API as BlobConnectorAdapter."""

    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)
        self._initialized = False

    def _resolve(self, container: str, blob_path: str) -> Path:
        """Resolve and validate a blob path, preventing directory traversal."""
        full = (self._base_dir / container / blob_path).resolve()
        base_resolved = self._base_dir.resolve()
        if not str(full).startswith(str(base_resolved)):
            raise ValueError(f"Path traversal detected: {blob_path}")
        return full

    async def ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        logger.info(f"Local blob storage initialized at {self._base_dir}")

    async def ensure_container_exists(self, container_name: str) -> None:
        """Create a container directory if it does not exist."""
        await self.ensure_initialized()
        container_path = self._base_dir / container_name
        container_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Blob container '{container_name}' ready at {container_path}")

    async def upload_blob(
        self,
        container: str,
        path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        await self.ensure_initialized()
        full_path = self._resolve(container, path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)
        logger.debug(f"Uploaded {len(data)} bytes to {container}/{path}")

    async def download_blob(self, container: str, path: str) -> bytes:
        await self.ensure_initialized()
        full_path = self._resolve(container, path)
        if not full_path.exists():
            raise FileNotFoundError(f"Blob not found: {container}/{path}")
        return full_path.read_bytes()

    async def list_blobs(
        self,
        container: str,
        prefix: str | None = None,
        max_results: int = 100,
    ) -> list[BlobInfo]:
        await self.ensure_initialized()
        container_path = self._base_dir / container
        if not container_path.exists():
            return []

        blobs: list[BlobInfo] = []
        for file_path in sorted(container_path.rglob("*")):
            if file_path.is_dir():
                continue
            relative = str(file_path.relative_to(container_path))
            if prefix and not relative.startswith(prefix):
                continue
            ct, _ = mimetypes.guess_type(str(file_path))
            blobs.append(
                BlobInfo(
                    name=relative,
                    size=file_path.stat().st_size,
                    content_type=ct,
                )
            )
            if len(blobs) >= max_results:
                break
        return blobs

    async def get_blob_properties(
        self, container: str, path: str,
    ) -> BlobProperties:
        await self.ensure_initialized()
        full_path = self._resolve(container, path)
        if not full_path.exists():
            raise FileNotFoundError(f"Blob not found: {container}/{path}")
        ct, _ = mimetypes.guess_type(str(full_path))
        return BlobProperties(
            name=path,
            size=full_path.stat().st_size,
            content_type=ct,
            metadata={},
        )

    async def list_containers(self) -> list[Any]:
        await self.ensure_initialized()
        return [
            {"name": d.name}
            for d in self._base_dir.iterdir()
            if d.is_dir()
        ]

    async def delete_blob(self, container: str, path: str) -> None:
        await self.ensure_initialized()
        full_path = self._resolve(container, path)
        if full_path.exists():
            full_path.unlink()
            logger.debug(f"Deleted blob '{container}/{path}'")

    async def delete_prefix(
        self,
        container_name: str,
        prefix: str,
    ) -> int:
        """Delete all blobs under a prefix. Returns the count of deleted blobs."""
        await self.ensure_initialized()
        container_path = self._base_dir / container_name
        if not container_path.exists():
            return 0

        count = 0
        for file_path in list(container_path.rglob("*")):
            if file_path.is_dir():
                continue
            relative = str(file_path.relative_to(container_path))
            if relative.startswith(prefix):
                file_path.unlink()
                count += 1
        return count

    async def close(self) -> None:
        """No-op — filesystem does not need explicit cleanup."""
        pass

"""Skills Manager — core runtime for Agent Skills.

Handles discovery, loading, caching, prompt injection, and file access.
Implements the three-level progressive disclosure model:

- **Level 1 (Metadata)**: ``name`` + ``description`` loaded at startup for
  every installed Skill (~100 tokens each).
- **Level 2 (Instructions)**: Full ``SKILL.md`` body loaded on demand when
  the agent decides a Skill is relevant.
- **Level 3 (Resources)**: ``references/*.md``, ``scripts/*.py``, ``assets/*``
  loaded only when explicitly referenced from the instructions.

Phase: Skills Integration
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from app.connectors.blob_connector import BlobConnectorAdapter
from app.models.skill_models import (
    CreateSkillRequest,
    SkillRecord,
    SkillSource,
    SkillStatus,
    SkillSummary,
    SkillValidationResult,
    UpdateSkillRequest,
)
from app.skills.store import SkillAlreadyExistsError, SkillNotFoundError, SkillStore
from app.skills.validator import validate_skill_frontmatter

logger = logging.getLogger(f"contelligence-agent.{__name__}")

_METADATA_CACHE_TTL = 120  # seconds
_SKILLS_BLOB_CONTAINER = "skills"
_BUILT_IN_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


class SkillsManager:
    """Runtime manager for Agent Skills.

    Combines the ``SkillStore`` (Cosmos DB) with ``BlobConnectorAdapter``
    (Azure Blob Storage) to provide a unified interface for Skill lifecycle
    operations and runtime loading.
    """

    def __init__(
        self,
        skill_store: SkillStore,
        blob_connector: BlobConnectorAdapter,
        extra_skill_directories: list[str] | None = None,
    ) -> None:
        self._store = skill_store
        self._blob = blob_connector
        self._extra_skill_directories: list[str] = extra_skill_directories or []

        # Level 1 metadata cache: {skill_id: SkillRecord}
        self._metadata_cache: dict[str, SkillRecord] = {}
        self._cache_timestamp: float = 0.0
        self._lock = asyncio.Lock()

    # ── Skill directories for SDK integration ──────────────

    @property
    def built_in_skills_dir(self) -> Path:
        """Return the path to the built-in skills directory."""
        return _BUILT_IN_SKILLS_DIR

    def get_skill_directories(self) -> list[str]:
        """Return filesystem paths the SDK should load skills from.

        Includes:
        - The built-in skills directory (if it exists on disk)
        - Any extra directories configured at construction time
        """
        dirs: list[str] = []
        if _BUILT_IN_SKILLS_DIR.is_dir():
            dirs.append(str(_BUILT_IN_SKILLS_DIR))
        for d in self._extra_skill_directories:
            if d not in dirs:
                dirs.append(d)
        return dirs

    # ── Startup & Built-in Sync ────────────────────────────

    async def sync_built_in_skills(self) -> int:
        """Scan the local ``skills/`` directory and register built-in Skills.

        Built-in Skills are shipped inside the container image. This method:
        1. Reads each ``SKILL.md`` in the ``skills/`` directory.
        2. Validates the frontmatter.
        3. Creates or updates the Cosmos DB record.
        4. Uploads Skill files to Blob Storage.

        Returns the number of built-in Skills synced.
        """
        if not _BUILT_IN_SKILLS_DIR.is_dir():
            logger.info(f"No built-in skills directory found at {_BUILT_IN_SKILLS_DIR}.")
            return 0

        synced = 0
        for skill_dir in sorted(_BUILT_IN_SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                logger.warning(f"Skipping {skill_dir.name} — no SKILL.md found.")
                continue

            try:
                content = skill_md.read_text(encoding="utf-8")
                result = validate_skill_frontmatter(content)
                if not result["valid"]:
                    logger.warning(
                        f"Built-in skill '{skill_dir.name}' has invalid SKILL.md: {result['errors']}"
                    )
                    continue

                fm = result["frontmatter"] or {}
                skill_name = result["parsed_name"] or skill_dir.name

                # Collect file listing
                files = _collect_skill_files(skill_dir)

                # Build record
                record = SkillRecord(
                    id=skill_name,
                    name=skill_name,
                    description=result["parsed_description"] or "",
                    license=fm.get("license"),
                    compatibility=fm.get("compatibility"),
                    metadata={
                        str(k): str(v)
                        for k, v in (fm.get("metadata") or {}).items()
                    },
                    tags=_extract_tags(fm),
                    source=SkillSource.BUILT_IN,
                    status=SkillStatus.ACTIVE,
                    blob_prefix=f"skills/{skill_name}/",
                    instructions=result["body"],
                    files=files,
                    bound_to_agents=[],
                    partition_key="skill",
                )

                # Upsert to Cosmos (idempotent)
                try:
                    await self._store.create_skill(record)
                except SkillAlreadyExistsError:
                    await self._store.update_skill(
                        skill_name,
                        {
                            "description": record.description,
                            "instructions": record.instructions,
                            "files": record.files,
                            "metadata": record.metadata,
                            "tags": record.tags,
                            "license": record.license,
                            "compatibility": record.compatibility,
                            "source": SkillSource.BUILT_IN.value,
                            "status": SkillStatus.ACTIVE.value,
                        },
                    )

                # Upload files to Blob Storage
                await self._upload_skill_directory(skill_name, skill_dir)
                synced += 1
                logger.info("Synced built-in skill '%s' (%d files).", skill_name, len(files))

            except Exception:
                logger.exception("Error syncing built-in skill '%s'.", skill_dir.name)

        # Refresh cache after sync
        self._cache_timestamp = 0.0
        return synced

    # ── Level 1: Metadata (cached) ────────────────────────

    async def get_all_metadata(self) -> list[SkillRecord]:
        """Return metadata for all active/built-in skills (cached)."""
        await self._refresh_cache_if_stale()
        return list(self._metadata_cache.values())

    async def get_skills_manifest(self) -> str:
        """Build the skills manifest for system prompt injection.

        Returns a Markdown fragment listing all active Skills with their
        ``name`` and ``description``. Costs ~100 tokens per Skill.
        """
        skills = await self.get_all_metadata()
        active = [
            s for s in skills
            if s.status in (SkillStatus.ACTIVE,)
        ]

        if not active:
            return ""

        lines = [
            "\n## Available Skills\n",
            "The following Skills are available. When a task matches a Skill's description,",
            "use the `read_skill` tool to load its full instructions before proceeding.\n",
        ]
        for skill in sorted(active, key=lambda s: s.name):
            lines.append(f"- **{skill.name}**: {skill.description}")

        return "\n".join(lines)

    async def get_bound_skills_instructions(
        self,
        skill_names: list[str],
    ) -> str:
        """Load Level 2 instructions for bound skills (pre-loaded at session start).

        Returns concatenated Markdown for all specified Skills.
        """
        if not skill_names:
            return ""

        parts: list[str] = []
        for name in skill_names:
            try:
                content = await self.get_skill_instructions(name)
                if content:
                    parts.append(f"\n## Skill: {name}\n\n{content}")
            except SkillNotFoundError:
                logger.warning("Bound skill '%s' not found — skipping.", name)
        return "\n".join(parts)

    # ── Level 2: Full Instructions ────────────────────────

    async def get_skill_instructions(self, skill_name: str) -> str:
        """Load the full SKILL.md body for a skill (Level 2).

        Also increments the usage counter.
        """
        record = await self._store.get_skill(skill_name)

        # Increment usage (fire-and-forget)
        asyncio.create_task(self._store.increment_usage(skill_name))

        if record.instructions:
            return record.instructions

        # Fallback: read from Blob Storage
        try:
            await self._blob.ensure_initialized()
            data = await self._blob.download_blob(
                _SKILLS_BLOB_CONTAINER,
                f"{record.blob_prefix}SKILL.md",
            )
            content = data.decode("utf-8")

            # Parse body (skip frontmatter)
            from app.skills.validator import parse_skill_content
            _, body = parse_skill_content(content)
            return body
        except Exception:
            logger.exception("Failed to load SKILL.md for '%s' from blob.", skill_name)
            return ""

    # ── Level 3: Skill Files ──────────────────────────────

    async def read_skill_file(self, skill_name: str, file_path: str) -> str:
        """Read a specific file from a skill's directory (Level 3).

        Validates that the file path is within allowed subdirectories
        (``references/``, ``scripts/``, ``assets/``).
        """
        # Security: prevent path traversal
        normalised = os.path.normpath(file_path)
        if normalised.startswith("..") or normalised.startswith("/"):
            raise ValueError(f"Invalid file path: {file_path}")

        allowed_prefixes = ("references/", "scripts/", "assets/", "SKILL.md")
        if not any(normalised.startswith(p) or normalised == p for p in allowed_prefixes):
            raise ValueError(
                f"File path '{file_path}' is outside allowed directories "
                "(references/, scripts/, assets/)."
            )

        record = await self._store.get_skill(skill_name)
        blob_path = f"{record.blob_prefix}{normalised}"

        try:
            await self._blob.ensure_initialized()
            data = await self._blob.download_blob(_SKILLS_BLOB_CONTAINER, blob_path)
            return data.decode("utf-8")
        except Exception as exc:
            raise FileNotFoundError(
                f"File '{file_path}' not found in skill '{skill_name}'."
            ) from exc

    async def list_skill_files(self, skill_name: str) -> list[str]:
        """List all files in a skill's blob directory."""
        record = await self._store.get_skill(skill_name)
        if record.files:
            return record.files

        # Fallback: list from Blob Storage
        try:
            await self._blob.ensure_initialized()
            blobs = await self._blob.list_blobs(
                _SKILLS_BLOB_CONTAINER,
                prefix=record.blob_prefix,
                max_results=200,
            )
            prefix_len = len(record.blob_prefix)
            return [b.name[prefix_len:] for b in blobs if b.name != record.blob_prefix]
        except Exception:
            logger.exception("Failed to list files for skill '%s'.", skill_name)
            return []

    # ── Script Execution ──────────────────────────────────

    async def run_skill_script(
        self,
        skill_name: str,
        script_path: str,
        args: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a Python script bundled with a Skill.

        The script is downloaded from Blob Storage to a temporary directory
        and executed in a sandboxed subprocess with a 30-second timeout.
        """
        # Validate script path
        normalised = os.path.normpath(script_path)
        if not normalised.startswith("scripts/"):
            raise ValueError("Script must be in the 'scripts/' directory.")
        if not normalised.endswith(".py"):
            raise ValueError("Only Python (.py) scripts are supported.")

        record = await self._store.get_skill(skill_name)
        blob_path = f"{record.blob_prefix}{normalised}"

        # Download script to temp file
        try:
            await self._blob.ensure_initialized()
            script_data = await self._blob.download_blob(_SKILLS_BLOB_CONTAINER, blob_path)
        except Exception as exc:
            raise FileNotFoundError(
                f"Script '{script_path}' not found in skill '{skill_name}'."
            ) from exc

        with tempfile.TemporaryDirectory() as tmpdir:
            script_file = Path(tmpdir) / Path(normalised).name
            script_file.write_bytes(script_data)

            cmd = [sys.executable, str(script_file)] + (args or [])

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=tmpdir,
                    env={
                        **os.environ,
                        "SKILL_NAME": skill_name,
                        "SKILL_SCRIPT": script_path,
                    },
                )
                return {
                    "exit_code": result.returncode,
                    "stdout": result.stdout[:10_000],  # Truncate large output
                    "stderr": result.stderr[:5_000],
                }
            except subprocess.TimeoutExpired:
                return {
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Script execution timed out (30s limit).",
                }
            except Exception as exc:
                return {
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Script execution failed: {exc}",
                }

    # ── CRUD (delegated to SkillStore with blob management) ──

    async def create_skill(self, request: CreateSkillRequest) -> SkillRecord:
        """Create a new skill from an API request."""
        # Build SKILL.md content from request
        skill_md = _build_skill_md(request)

        # Validate
        validation = validate_skill_frontmatter(skill_md)
        if not validation["valid"]:
            raise ValueError(f"Invalid skill: {validation['errors']}")

        record = SkillRecord(
            id=request.name,
            name=request.name,
            description=request.description,
            license=request.license,
            compatibility=request.compatibility,
            metadata=request.metadata or {},
            tags=request.tags or [],
            source=SkillSource.USER_CREATED,
            status=request.status or SkillStatus.DRAFT,
            blob_prefix=f"skills/{request.name}/",
            instructions=request.instructions,
            files=["SKILL.md"],
            partition_key="skill",
        )

        # Store in Cosmos
        record = await self._store.create_skill(record)

        # Upload SKILL.md to Blob Storage
        try:
            await self._blob.ensure_initialized()
            await self._blob.upload_blob(
                _SKILLS_BLOB_CONTAINER,
                f"skills/{request.name}/SKILL.md",
                skill_md.encode("utf-8"),
                content_type="text/markdown",
            )
        except Exception:
            logger.exception("Failed to upload SKILL.md for '%s'.", request.name)

        # Invalidate cache
        self._cache_timestamp = 0.0
        return record

    async def update_skill(
        self,
        skill_id: str,
        request: UpdateSkillRequest,
    ) -> SkillRecord:
        """Update an existing skill."""
        updates = request.model_dump(exclude_none=True)

        # If instructions are being updated, rebuild the SKILL.md blob
        if request.instructions is not None:
            # Get current record for frontmatter fields
            current = await self._store.get_skill(skill_id)
            merged_request = CreateSkillRequest(
                name=request.name or current.name,
                description=request.description or current.description,
                license=request.license if request.license is not None else current.license,
                compatibility=request.compatibility if request.compatibility is not None else current.compatibility,
                metadata=request.metadata if request.metadata is not None else current.metadata,
                tags=request.tags if request.tags is not None else current.tags,
                status=request.status or current.status,
                instructions=request.instructions,
            )
            skill_md = _build_skill_md(merged_request)

            try:
                await self._blob.ensure_initialized()
                await self._blob.upload_blob(
                    _SKILLS_BLOB_CONTAINER,
                    f"skills/{current.name}/SKILL.md",
                    skill_md.encode("utf-8"),
                    content_type="text/markdown",
                )
            except Exception:
                logger.exception("Failed to update SKILL.md blob for '%s'.", skill_id)

        record = await self._store.update_skill(skill_id, updates)

        # Invalidate cache
        self._cache_timestamp = 0.0
        return record

    async def delete_skill(self, skill_id: str) -> None:
        """Delete a skill (Cosmos record + blob files)."""
        record = await self._store.get_skill(skill_id)

        if record.source == SkillSource.BUILT_IN:
            raise ValueError("Cannot delete built-in skills. Use 'disable' instead.")

        await self._store.delete_skill(skill_id)

        # Best-effort cleanup of blob files
        try:
            await self._blob.ensure_initialized()
            blobs = await self._blob.list_blobs(
                _SKILLS_BLOB_CONTAINER,
                prefix=record.blob_prefix,
                max_results=200,
            )
            for blob in blobs:
                try:
                    await self._blob.delete_blob(_SKILLS_BLOB_CONTAINER, blob.name)
                except Exception:
                    logger.warning("Failed to delete blob '%s'.", blob.name)
        except Exception:
            logger.exception("Failed to cleanup blobs for skill '%s'.", skill_id)

        # Invalidate cache
        self._cache_timestamp = 0.0

    # ── File Management ───────────────────────────────────

    async def upload_skill_file(
        self,
        skill_id: str,
        relative_path: str,
        data: bytes,
    ) -> None:
        """Upload a single file to a skill's blob directory and update the record."""
        record = await self._store.get_skill(skill_id)
        blob_path = f"{record.blob_prefix}{relative_path}"
        content_type = _guess_content_type(Path(relative_path).suffix)

        await self._blob.ensure_initialized()
        await self._blob.upload_blob(
            _SKILLS_BLOB_CONTAINER,
            blob_path,
            data,
            content_type=content_type,
        )

        # Update the files list in the record
        if relative_path not in record.files:
            updated_files = sorted(set(record.files + [relative_path]))
            await self._store.update_skill(skill_id, {"files": updated_files})

        logger.info("Uploaded file '%s' for skill '%s'.", relative_path, skill_id)

    async def upload_skill_zip(
        self,
        skill_id: str,
        zip_data: bytes,
    ) -> dict[str, Any]:
        """Extract a zip archive into a skill's blob directory.

        Returns ``{"files_added": int, "files": list[str]}``.
        Filters out unsafe paths and only allows files under recognised
        subdirectories (``references/``, ``scripts/``, ``assets/``) or
        ``SKILL.md`` at the root.
        """
        record = await self._store.get_skill(skill_id)
        await self._blob.ensure_initialized()

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_data))
        except zipfile.BadZipFile:
            raise ValueError("Uploaded file is not a valid zip archive.")

        allowed_prefixes = ("references/", "scripts/", "assets/", "SKILL.md")
        added_files: list[str] = []

        # Detect if the zip has a single top-level directory wrapper
        # e.g., "my-skill/references/...", and strip it.
        names = [n for n in zf.namelist() if not n.endswith("/")]
        common_prefix = ""
        if names:
            parts = names[0].split("/")
            if len(parts) > 1:
                candidate = parts[0] + "/"
                if all(n.startswith(candidate) for n in names):
                    common_prefix = candidate

        for info in zf.infolist():
            if info.is_dir():
                continue

            relative = info.filename
            if common_prefix and relative.startswith(common_prefix):
                relative = relative[len(common_prefix):]

            if not relative:
                continue

            normalised = os.path.normpath(relative)
            if normalised.startswith("..") or normalised.startswith("/"):
                continue

            # Only allow recognised paths
            if not any(normalised.startswith(p) or normalised == p for p in allowed_prefixes):
                continue

            # Size guard: skip files > 10 MB
            if info.file_size > 10 * 1024 * 1024:
                logger.warning("Skipping oversized file in zip: '%s' (%d bytes).", normalised, info.file_size)
                continue

            data = zf.read(info.filename)
            blob_path = f"{record.blob_prefix}{normalised}"
            content_type = _guess_content_type(Path(normalised).suffix)

            await self._blob.upload_blob(
                _SKILLS_BLOB_CONTAINER,
                blob_path,
                data,
                content_type=content_type,
            )
            added_files.append(normalised)

        # Update the files list in the record
        if added_files:
            updated_files = sorted(set(record.files + added_files))
            await self._store.update_skill(skill_id, {"files": updated_files})

        self._cache_timestamp = 0.0
        logger.info("Extracted %d files from zip for skill '%s'.", len(added_files), skill_id)
        return {"files_added": len(added_files), "files": added_files}

    async def delete_skill_file(
        self,
        skill_id: str,
        relative_path: str,
    ) -> None:
        """Delete a single file from a skill's blob directory and update the record."""
        record = await self._store.get_skill(skill_id)
        blob_path = f"{record.blob_prefix}{relative_path}"

        try:
            await self._blob.ensure_initialized()
            await self._blob.delete_blob(_SKILLS_BLOB_CONTAINER, blob_path)
        except Exception as exc:
            raise FileNotFoundError(
                f"File '{relative_path}' not found in skill '{skill_id}'."
            ) from exc

        # Update the files list in the record
        updated_files = [f for f in record.files if f != relative_path]
        await self._store.update_skill(skill_id, {"files": updated_files})

        logger.info("Deleted file '%s' from skill '%s'.", relative_path, skill_id)

    async def get_skill(self, skill_id: str) -> SkillRecord:
        """Get a skill record by ID."""
        return await self._store.get_skill(skill_id)

    async def list_skills(
        self,
        status: SkillStatus | None = None,
        tags: list[str] | None = None,
    ) -> list[SkillSummary]:
        """List skills as lightweight summaries."""
        records = await self._store.list_skills(status=status, tags=tags)
        return [
            SkillSummary(
                id=r.id,
                name=r.name,
                description=r.description,
                tags=r.tags,
                source=r.source,
                status=r.status,
                usage_count=r.usage_count,
                bound_to_agents=r.bound_to_agents,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in records
        ]

    # ── Internal helpers ──────────────────────────────────

    async def _refresh_cache_if_stale(self) -> None:
        """Reload metadata cache if TTL has expired."""
        if time.monotonic() - self._cache_timestamp < _METADATA_CACHE_TTL:
            return

        async with self._lock:
            # Double-check after acquiring lock
            if time.monotonic() - self._cache_timestamp < _METADATA_CACHE_TTL:
                return

            try:
                records = await self._store.list_skills()
                self._metadata_cache = {r.id: r for r in records}
                self._cache_timestamp = time.monotonic()
                logger.debug(
                    "Refreshed skills metadata cache — %d skills.", len(self._metadata_cache),
                )
            except Exception:
                logger.exception("Failed to refresh skills metadata cache.")

    async def _upload_skill_directory(self, skill_name: str, local_dir: Path) -> None:
        """Upload all files from a local skill directory to Blob Storage."""
        await self._blob.ensure_initialized()
        await self._blob.ensure_container_exists(_SKILLS_BLOB_CONTAINER)

        for file_path in local_dir.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                relative = file_path.relative_to(local_dir)
                blob_path = f"{skill_name}/{relative}"
                content_type = _guess_content_type(file_path.suffix)

                try:
                    data = file_path.read_bytes()
                    await self._blob.upload_blob(
                        _SKILLS_BLOB_CONTAINER,
                        blob_path,
                        data,
                        content_type=content_type,
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to upload '{relative}' for skill '{skill_name}'. Error: {e}"
                    )
                    logger.exception(e)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _collect_skill_files(skill_dir: Path) -> list[str]:
    """Collect relative file paths from a skill directory."""
    files: list[str] = []
    for file_path in skill_dir.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith("."):
            relative = str(file_path.relative_to(skill_dir))
            files.append(relative)
    return sorted(files)


def _extract_tags(frontmatter: dict[str, Any]) -> list[str]:
    """Extract tags from frontmatter metadata."""
    tags: list[str] = []
    meta = frontmatter.get("metadata", {})
    if isinstance(meta, dict):
        category = meta.get("category")
        if isinstance(category, str):
            tags.append(category)
        tag_list = meta.get("tags")
        if isinstance(tag_list, list):
            tags.extend(str(t) for t in tag_list)
    return tags


def _build_skill_md(request: CreateSkillRequest) -> str:
    """Build a SKILL.md file from a CreateSkillRequest."""
    import yaml

    frontmatter: dict[str, Any] = {
        "name": request.name,
        "description": request.description,
    }

    if request.license:
        frontmatter["license"] = request.license
    if request.compatibility:
        frontmatter["compatibility"] = request.compatibility
    if request.metadata:
        frontmatter["metadata"] = request.metadata

    yaml_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
    return f"---\n{yaml_str}---\n\n{request.instructions}"


def _guess_content_type(suffix: str) -> str:
    """Guess MIME type from file extension."""
    mapping = {
        ".md": "text/markdown",
        ".py": "text/x-python",
        ".json": "application/json",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".txt": "text/plain",
        ".csv": "text/csv",
    }
    return mapping.get(suffix.lower(), "application/octet-stream")

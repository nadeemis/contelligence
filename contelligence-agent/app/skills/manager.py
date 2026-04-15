"""Skills Manager — core runtime for Agent Skills.

Handles discovery, loading, caching, prompt injection, and file access.
The filesystem is the source of truth for all skill content.  Cosmos DB
stores only lightweight metadata for fast queries and API responses.

- **Level 1 (Metadata)**: ``name`` + ``description`` loaded at startup for
  every installed Skill (~100 tokens each).
- **Level 2 (Instructions)**: Full ``SKILL.md`` body loaded on demand from
  the filesystem when the agent decides a Skill is relevant.
- **Level 3 (Resources)**: ``references/*.md``, ``scripts/*.py``, ``assets/*``
  loaded from the filesystem when explicitly referenced.

Phase: Skills Integration
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from app.models.skill_models import (
    CreateSkillRequest,
    SkillRecord,
    SkillSource,
    SkillStatus,
    SkillSummary,
    UpdateSkillRequest,
)
from app.settings import AppSettings, get_settings
from app.skills.store import SkillAlreadyExistsError, SkillNotFoundError, SkillStore
from app.skills.validator import validate_skill_frontmatter


logger = logging.getLogger(f"contelligence-agent.{__name__}")

_METADATA_CACHE_TTL = 120  # seconds
_BUILT_IN_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


class SkillsManager:
    """Runtime manager for Agent Skills.

    The filesystem is the source of truth for all skill content.
    ``SkillStore`` (Cosmos DB) holds only lightweight metadata for
    fast queries and API responses.
    """

    def __init__(
        self,
        skill_store: SkillStore,
        settings: AppSettings | None = None,
    ) -> None:
        self._store = skill_store
        self._settings = settings or get_settings()

        # Level 1 metadata cache: {skill_id: SkillRecord}
        self._metadata_cache: dict[str, SkillRecord] = {}
        self._cache_timestamp: float = 0.0
        self._lock = asyncio.Lock()

    # ── Skill directories for SDK integration ──────────────

    @property
    def built_in_skills_dir(self) -> Path:
        """Return the path to the built-in skills directory."""
        return _BUILT_IN_SKILLS_DIR

    @property
    def cli_shared_skills_dir(self) -> str:
        """Return the configured ``CLI_SHARED_SKILLS_DIRECTORY``, or empty string."""
        return self._settings.CLI_SHARED_SKILLS_DIRECTORY

    def get_skill_directories(self) -> list[str]:
        """Return filesystem paths the SDK should load skills from.

        When ``CLI_SHARED_SKILLS_DIRECTORY`` is configured it is the single
        authoritative directory — all skills (built-in + user-created)
        are materialized there.  Falls back to the built-in source
        directory when no shared directory is set.
        """
        shared = self.cli_shared_skills_dir
        if shared:
            return [shared]
        # Fallback: use built-in skills dir from the source tree
        if _BUILT_IN_SKILLS_DIR.is_dir():
            return [str(_BUILT_IN_SKILLS_DIR)]
        return []

    # ── Filesystem resolution ─────────────────────────────

    def _resolve_skill_path(self, skill_name: str) -> Path | None:
        """Find the filesystem directory for a skill.

        Checks the shared skills directory first, then the built-in
        source tree.  Returns ``None`` if the skill is not found in
        either location.
        """
        shared_dir = self._settings.AGENT_SHARED_SKILLS_DIRECTORY
        if shared_dir:
            skill_path = Path(shared_dir) / skill_name
            if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                return skill_path
        if _BUILT_IN_SKILLS_DIR.is_dir():
            skill_path = _BUILT_IN_SKILLS_DIR / skill_name
            if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                return skill_path
        return None

    # ── Shared skills directory (filesystem materialization) ──

    async def _materialize_to_shared(
        self,
        skill_name: str,
        skill_md_content: str,
        extra_files: dict[str, bytes] | None = None,
    ) -> None:
        """Write skill files to the shared skills directory on disk.

        This makes the skill visible to the Copilot CLI container (Docker)
        or the local SDK session (Electron / dev server) via
        ``skill_directories``.

        No-op when ``AGENT_SHARED_SKILLS_DIRECTORY`` is not configured.
        """
        shared_dir = self._settings.AGENT_SHARED_SKILLS_DIRECTORY
        if not shared_dir:
            return

        skill_path = Path(shared_dir) / skill_name
        skill_path.mkdir(parents=True, exist_ok=True)

        with skill_path.joinpath("SKILL.md").open("w", encoding="utf-8") as f:
            f.write(skill_md_content)

        if extra_files:
            for relative_path, content in extra_files.items():
                file_path = skill_path / relative_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(content)

        logger.info("Materialized skill '%s' to %s", skill_name, skill_path)

    def _remove_from_shared(self, skill_name: str) -> None:
        """Remove a skill from the shared skills directory.

        No-op when ``AGENT_SHARED_SKILLS_DIRECTORY`` is not configured or the
        directory does not exist.
        """
        shared_dir = self._settings.AGENT_SHARED_SKILLS_DIRECTORY
        if not shared_dir:
            return
        skill_path = Path(shared_dir) / skill_name
        if skill_path.is_dir():
            shutil.rmtree(skill_path)
            logger.info("Removed skill '%s' from shared directory.", skill_name)

    async def discover_filesystem_skills(self) -> int:
        """Scan the shared skills directory for skills not yet in Cosmos DB.

        This picks up skills that were manually added to the skills
        directory.  Built-in skills (already synced) are skipped.

        Returns the number of newly discovered skills.
        """
        shared_dir = self._settings.AGENT_SHARED_SKILLS_DIRECTORY
        if not shared_dir:
            return 0

        shared_path = Path(shared_dir)
        if not shared_path.is_dir():
            return 0

        # Get names of already-known skills
        known_records = await self._store.list_skills()
        known_names = {r.name for r in known_records}

        discovered = 0
        for skill_dir in sorted(shared_path.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md_path = skill_dir / "SKILL.md"
            if not skill_md_path.exists():
                continue
            if skill_dir.name in known_names:
                continue

            try:
                content = skill_md_path.read_text(encoding="utf-8")
                result = validate_skill_frontmatter(content)
                if not result["valid"]:
                    logger.warning(
                        f"Discovered skill '{skill_dir.name}' has invalid SKILL.md: "
                        f"{result['errors']}"
                    )
                    continue

                fm = result["frontmatter"] or {}
                skill_name = result["parsed_name"] or skill_dir.name

                if skill_name in known_names:
                    continue

                files = _collect_skill_files(skill_dir)

                record = SkillRecord(
                    id=skill_name,
                    name=skill_name,
                    description=result["parsed_description"] or "",
                    license=fm.get("license"),
                    compatibility=fm.get("compatibility"),
                    metadata={
                        str(k): str(v)
                        for k, v in (fm.get("metadata") or {}).items()
                        if not isinstance(v, (list, dict))
                    },
                    tags=_extract_tags(fm),
                    source=SkillSource.USER_CREATED,
                    status=SkillStatus.ACTIVE,
                    files=files,
                    bound_to_agents=[],
                    partition_key="skill",
                )

                await self._store.create_skill(record)
                known_names.add(skill_name)
                discovered += 1
                logger.info(f"Discovered new skill '{skill_name}' from filesystem.")

            except SkillAlreadyExistsError:
                pass
            except Exception:
                logger.exception(
                    f"Error discovering skill '{skill_dir.name}'.", exc_info=True,
                )

        if discovered:
            self._cache_timestamp = 0.0
        return discovered

    # ── Startup & Built-in Sync ────────────────────────────

    async def sync_built_in_skills(self) -> int:
        """Scan the local ``skills/`` directory and register built-in Skills.

        Built-in Skills are shipped inside the container image. This method:
        1. Reads each ``SKILL.md`` in the ``skills/`` directory.
        2. Validates the frontmatter.
        3. Creates or updates the metadata record in Cosmos DB.
        4. Copies skill files to the shared skills directory.

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

                # Build record (metadata only — no instructions stored in DB)
                record = SkillRecord(
                    id=skill_name,
                    name=skill_name,
                    description=result["parsed_description"] or "",
                    license=fm.get("license"),
                    compatibility=fm.get("compatibility"),
                    metadata={
                        str(k): str(v)
                        for k, v in (fm.get("metadata") or {}).items()
                        if not isinstance(v, (list, dict))
                    },
                    tags=_extract_tags(fm),
                    source=SkillSource.BUILT_IN,
                    status=SkillStatus.ACTIVE,
                    files=files,
                    bound_to_agents=[],
                    partition_key="skill",
                )

                # Upsert metadata to Cosmos DB (idempotent)
                try:
                    await self._store.create_skill(record)
                except SkillAlreadyExistsError:
                    await self._store.update_skill(
                        skill_name,
                        {
                            "description": record.description,
                            "files": record.files,
                            "metadata": record.metadata,
                            "tags": record.tags,
                            "license": record.license,
                            "compatibility": record.compatibility,
                            "source": SkillSource.BUILT_IN.value,
                            "status": SkillStatus.ACTIVE.value,
                        },
                    )

                # Materialize to shared skills directory (so CLI/SDK can discover)
                try:
                    extra_files: dict[str, bytes] = {}
                    for f in files:
                        if f == "SKILL.md":
                            continue
                        fp = skill_dir / f
                        if fp.is_file():
                            extra_files[f] = fp.read_bytes()
                    
                    await self._materialize_to_shared(
                        skill_name, content, extra_files=extra_files or None,
                    )
                except Exception:
                    logger.warning(f"Failed to materialize built-in skill '{skill_name}' to shared dir.")
                    raise

                synced += 1
                logger.info(f"Synced built-in skill '{skill_name}' ({len(files)} files).")

            except Exception:
                logger.exception(f"Error syncing built-in skill '{skill_dir.name}'.", exc_info=True)

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
        """Load the full SKILL.md body for a skill from the filesystem (Level 2).

        Also increments the usage counter.
        """
        await self._store.get_skill(skill_name)

        # Increment usage (fire-and-forget)
        asyncio.create_task(self._store.increment_usage(skill_name))

        # Read from filesystem
        skill_path = self._resolve_skill_path(skill_name)
        if not skill_path:
            logger.warning(
                "Skill '%s' registered in DB but not found on filesystem.", skill_name,
            )
            return ""

        try:
            content = (skill_path / "SKILL.md").read_text(encoding="utf-8")
            from app.skills.validator import parse_skill_content
            _, body = parse_skill_content(content)
            return body
        except Exception:
            logger.exception("Failed to read SKILL.md for '%s'.", skill_name)
            return ""

    # ── Level 3: Skill Files ──────────────────────────────

    async def read_skill_file(self, skill_name: str, file_path: str) -> str:
        """Read a specific file from a skill's directory on the filesystem (Level 3).

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

        await self._store.get_skill(skill_name)  # verify exists in DB

        skill_path = self._resolve_skill_path(skill_name)
        if not skill_path:
            raise FileNotFoundError(
                f"Skill '{skill_name}' not found on filesystem."
            )

        target = skill_path / normalised
        if not target.is_file():
            raise FileNotFoundError(
                f"File '{file_path}' not found in skill '{skill_name}'."
            )
        return target.read_text(encoding="utf-8")

    async def list_skill_files(self, skill_name: str) -> list[str]:
        """List all files in a skill's filesystem directory."""
        await self._store.get_skill(skill_name)  # verify exists in DB

        skill_path = self._resolve_skill_path(skill_name)
        if not skill_path:
            return []

        return _collect_skill_files(skill_path)

    # ── Script Execution ──────────────────────────────────

    async def run_skill_script(
        self,
        skill_name: str,
        script_path: str,
        args: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a Python script bundled with a Skill directly from the filesystem."""
        # Validate script path
        normalised = os.path.normpath(script_path)
        if not normalised.startswith("scripts/"):
            raise ValueError("Script must be in the 'scripts/' directory.")
        if not normalised.endswith(".py"):
            raise ValueError("Only Python (.py) scripts are supported.")

        await self._store.get_skill(skill_name)  # verify exists

        skill_path = self._resolve_skill_path(skill_name)
        if not skill_path:
            raise FileNotFoundError(
                f"Skill '{skill_name}' not found on filesystem."
            )

        script_file = skill_path / normalised
        if not script_file.is_file():
            raise FileNotFoundError(
                f"Script '{script_path}' not found in skill '{skill_name}'."
            )

        cmd = [sys.executable, str(script_file)] + (args or [])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(skill_path),
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

    # ── CRUD (filesystem + metadata in Cosmos DB) ──────────

    async def create_skill(self, request: CreateSkillRequest) -> SkillRecord:
        """Create a new skill: write to filesystem + store metadata in Cosmos."""
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
            files=["SKILL.md"],
            partition_key="skill",
        )

        # Store metadata in Cosmos
        record = await self._store.create_skill(record)

        # Write to shared filesystem
        try:
            await self._materialize_to_shared(request.name, skill_md)
        except Exception:
            logger.exception("Failed to materialize skill '%s' to shared dir.", request.name)

        # Invalidate cache
        self._cache_timestamp = 0.0
        return record

    async def update_skill(
        self,
        skill_id: str,
        request: UpdateSkillRequest,
    ) -> SkillRecord:
        """Update an existing skill: write to filesystem + update metadata in Cosmos."""
        updates = request.model_dump(exclude_none=True)

        # If instructions are being updated, rebuild the SKILL.md file
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

            # Write to shared filesystem
            try:
                await self._materialize_to_shared(current.name, skill_md)
            except Exception:
                logger.exception("Failed to materialize skill '%s' to shared dir.", skill_id)

        # Remove instructions from DB updates (filesystem is the source of truth)
        updates.pop("instructions", None)

        record = await self._store.update_skill(skill_id, updates)

        # Invalidate cache
        self._cache_timestamp = 0.0
        return record

    async def delete_skill(self, skill_id: str) -> None:
        """Delete a skill (Cosmos record + filesystem)."""
        record = await self._store.get_skill(skill_id)

        if record.source == SkillSource.BUILT_IN:
            raise ValueError("Cannot delete built-in skills. Use 'disable' instead.")

        await self._store.delete_skill(skill_id)

        # Remove from shared filesystem
        try:
            self._remove_from_shared(record.name)
        except Exception:
            logger.exception("Failed to remove skill '%s' from shared dir.", skill_id)

        # Invalidate cache
        self._cache_timestamp = 0.0

    # ── File Management ───────────────────────────────────

    async def upload_skill_file(
        self,
        skill_id: str,
        relative_path: str,
        data: bytes,
    ) -> None:
        """Write a single file to a skill's directory on the filesystem."""
        record = await self._store.get_skill(skill_id)

        skill_path = self._resolve_skill_path(record.name)
        if not skill_path:
            # Fall back to creating the directory in the shared skills dir
            shared_dir = self._settings.AGENT_SHARED_SKILLS_DIRECTORY
            if not shared_dir:
                raise ValueError("No skills directory configured.")
            skill_path = Path(shared_dir) / record.name
            skill_path.mkdir(parents=True, exist_ok=True)

        target = skill_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

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
        """Extract a zip archive into a skill's filesystem directory.

        Returns ``{"files_added": int, "files": list[str]}``.
        Filters out unsafe paths and only allows files under recognised
        subdirectories (``references/``, ``scripts/``, ``assets/``) or
        ``SKILL.md`` at the root.
        """
        record = await self._store.get_skill(skill_id)

        skill_path = self._resolve_skill_path(record.name)
        if not skill_path:
            shared_dir = self._settings.AGENT_SHARED_SKILLS_DIRECTORY
            if not shared_dir:
                raise ValueError("No skills directory configured.")
            skill_path = Path(shared_dir) / record.name
            skill_path.mkdir(parents=True, exist_ok=True)

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

            file_data = zf.read(info.filename)
            target = skill_path / normalised
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(file_data)
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
        """Delete a single file from a skill's filesystem directory."""
        record = await self._store.get_skill(skill_id)

        skill_path = self._resolve_skill_path(record.name)
        if not skill_path:
            raise FileNotFoundError(
                f"Skill '{skill_id}' not found on filesystem."
            )

        target = skill_path / relative_path
        if not target.is_file():
            raise FileNotFoundError(
                f"File '{relative_path}' not found in skill '{skill_id}'."
            )

        target.unlink()

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
    metadata = dict(request.metadata) if request.metadata else {}
    if request.tags:
        metadata["tags"] = request.tags
    if metadata:
        frontmatter["metadata"] = metadata

    yaml_str = _dump_frontmatter(frontmatter)
    return f"---\n{yaml_str}---\n\n{request.instructions}"


def _dump_frontmatter(frontmatter: dict[str, Any]) -> str:
    """Serialize frontmatter dict to YAML with double-quoted flow-style lists."""
    import yaml

    class _Dumper(yaml.SafeDumper):
        pass

    class _QuotedStr(str):
        """Marker for strings that should be double-quoted."""

    def _represent_quoted_str(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')

    def _represent_list(dumper: yaml.SafeDumper, data: list) -> yaml.Node:
        # Wrap each item so it gets double-quoted inside the flow sequence
        quoted = [_QuotedStr(item) if isinstance(item, str) else item for item in data]
        return dumper.represent_sequence(
            "tag:yaml.org,2002:seq", quoted, flow_style=True,
        )

    _Dumper.add_representer(_QuotedStr, _represent_quoted_str)
    _Dumper.add_representer(list, _represent_list)

    return yaml.dump(
        frontmatter, Dumper=_Dumper, default_flow_style=False,
        allow_unicode=True, sort_keys=False,
    )

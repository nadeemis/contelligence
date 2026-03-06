"""Skills API router — CRUD and management endpoints for Agent Skills.

Provides the REST API consumed by the Web UI's Skills Library page,
Skill Editor, and ChatSkillPicker component.

Phase: Skills Integration
"""

from __future__ import annotations

import io
import logging
import os
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.dependencies import get_skills_manager
from app.models.skill_models import (
    CreateSkillRequest,
    SkillRecord,
    SkillStatus,
    SkillSummary,
    SkillValidationResult,
    UpdateSkillRequest,
)
from app.skills.manager import SkillsManager
from app.skills.store import SkillAlreadyExistsError, SkillNotFoundError
from app.skills.validator import validate_skill_frontmatter

logger = logging.getLogger(f"contelligence-agent.{__name__}")
router = APIRouter(prefix="/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# Validation request model (JSON body with content string)
# ---------------------------------------------------------------------------


class ValidateSkillBody(BaseModel):
    """Request body for SKILL.md content validation."""
    content: str = Field(description="Full SKILL.md content to validate")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[SkillSummary])
async def list_skills(
    status: str | None = Query(None, description="Filter by status: active, disabled, draft, built-in"),
    tag: str | None = Query(None, description="Filter by tag"),
    manager: SkillsManager = Depends(get_skills_manager),
) -> list[SkillSummary]:
    """List all installed skills with optional filters."""
    # Map 'built-in' status filter to source-based filtering
    skill_status: SkillStatus | None = None
    if status and status != "built-in":
        try:
            skill_status = SkillStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Must be one of: active, disabled, draft",
            )

    tags = [tag] if tag else None
    summaries = await manager.list_skills(status=skill_status, tags=tags)

    # If status filter is 'built-in', filter by source
    if status == "built-in":
        summaries = [s for s in summaries if s.source == "built-in"]

    return summaries


@router.post("", response_model=SkillRecord, status_code=201)
async def create_skill(
    request: CreateSkillRequest,
    manager: SkillsManager = Depends(get_skills_manager),
) -> SkillRecord:
    """Create a new skill from JSON payload.

    The ``instructions`` field contains the SKILL.md body (Markdown).
    Frontmatter is generated automatically from the other fields.
    """
    try:
        return await manager.create_skill(request)
    except SkillAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail=f"Skill '{request.name}' already exists.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{skill_id}", response_model=SkillRecord)
async def get_skill(
    skill_id: str,
    manager: SkillsManager = Depends(get_skills_manager),
) -> SkillRecord:
    """Get full details of a skill."""
    try:
        return await manager.get_skill(skill_id)
    except SkillNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")


@router.put("/{skill_id}", response_model=SkillRecord)
async def update_skill(
    skill_id: str,
    request: UpdateSkillRequest,
    manager: SkillsManager = Depends(get_skills_manager),
) -> SkillRecord:
    """Update an existing skill.

    Built-in skills can have their ``status`` changed (e.g., disabled)
    but not their content.
    """
    try:
        current = await manager.get_skill(skill_id)
    except SkillNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    # Built-in skills: only allow status changes
    if current.source == "built-in":
        allowed_updates = UpdateSkillRequest(status=request.status)
        if request.model_dump(exclude_none=True).keys() - {"status"}:
            logger.info(
                "Ignoring non-status updates for built-in skill '%s'.", skill_id,
            )
        request = allowed_updates

    try:
        return await manager.update_skill(skill_id, request)
    except SkillNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    manager: SkillsManager = Depends(get_skills_manager),
) -> None:
    """Remove a skill and its stored files.

    Built-in skills cannot be deleted — disable them instead.
    """
    try:
        await manager.delete_skill(skill_id)
    except SkillNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{skill_id}/files", response_model=list[str])
async def list_skill_files(
    skill_id: str,
    manager: SkillsManager = Depends(get_skills_manager),
) -> list[str]:
    """List all files in a skill's directory."""
    try:
        return await manager.list_skill_files(skill_id)
    except SkillNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")


@router.post("/validate", response_model=SkillValidationResult)
async def validate_skill(
    body: ValidateSkillBody,
) -> SkillValidationResult:
    """Validate SKILL.md content against the Agent Skills specification.

    Accepts a JSON body with a ``content`` field containing the full
    SKILL.md text (frontmatter + body).
    """
    result = validate_skill_frontmatter(body.content)
    return SkillValidationResult(
        valid=result["valid"],
        errors=result["errors"],
        warnings=result["warnings"],
        parsed_name=result["parsed_name"],
        parsed_description=result["parsed_description"],
    )


# ---------------------------------------------------------------------------
# File management endpoints
# ---------------------------------------------------------------------------


@router.post("/{skill_id}/files")
async def upload_skill_file(
    skill_id: str,
    file: UploadFile = File(...),
    path: str = Form(...),
    manager: SkillsManager = Depends(get_skills_manager),
) -> dict[str, Any]:
    """Upload a single file to a skill's directory.

    The ``path`` form field specifies the relative path within the skill
    directory (e.g., ``references/schema.md``, ``scripts/validate.py``).
    """
    try:
        await manager.get_skill(skill_id)
    except SkillNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    # Security: prevent path traversal
    normalised = os.path.normpath(path)
    if normalised.startswith("..") or normalised.startswith("/"):
        raise HTTPException(status_code=400, detail=f"Invalid file path: {path}")

    allowed_prefixes = ("references/", "scripts/", "assets/")
    if not any(normalised.startswith(p) for p in allowed_prefixes):
        raise HTTPException(
            status_code=400,
            detail=f"File path must start with references/, scripts/, or assets/.",
        )

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:  # 10 MB limit per file
        raise HTTPException(status_code=400, detail="File too large (max 10 MB).")

    await manager.upload_skill_file(skill_id, normalised, data)
    return {"path": normalised, "size": len(data)}


@router.post("/{skill_id}/upload-zip")
async def upload_skill_zip(
    skill_id: str,
    file: UploadFile = File(...),
    manager: SkillsManager = Depends(get_skills_manager),
) -> dict[str, Any]:
    """Upload a .zip archive and extract its contents into the skill directory.

    The zip may contain any of the standard skill subdirectories
    (``references/``, ``scripts/``, ``assets/``).  If the archive contains
    a ``SKILL.md`` at the root, it is uploaded but does **not** overwrite
    the stored instructions — use the update endpoint for that.
    """
    try:
        await manager.get_skill(skill_id)
    except SkillNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    data = await file.read()
    if len(data) > 50 * 1024 * 1024:  # 50 MB limit for zip
        raise HTTPException(status_code=400, detail="Zip file too large (max 50 MB).")

    try:
        result = await manager.upload_skill_zip(skill_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return result


@router.delete("/{skill_id}/files/{file_path:path}", status_code=204)
async def delete_skill_file(
    skill_id: str,
    file_path: str,
    manager: SkillsManager = Depends(get_skills_manager),
) -> None:
    """Delete a specific file from a skill's directory.

    The ``SKILL.md`` file cannot be deleted directly.
    """
    try:
        await manager.get_skill(skill_id)
    except SkillNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    normalised = os.path.normpath(file_path)
    if normalised == "SKILL.md":
        raise HTTPException(status_code=400, detail="Cannot delete the SKILL.md file.")
    if normalised.startswith("..") or normalised.startswith("/"):
        raise HTTPException(status_code=400, detail=f"Invalid file path: {file_path}")

    try:
        await manager.delete_skill_file(skill_id, normalised)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File '{file_path}' not found.")

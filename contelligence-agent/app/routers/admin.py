"""Admin router — operational endpoints (health deep-check, cache clear, prompt management, etc.).

Mounted at ``/api/admin`` with appropriate auth guards added in WS-9.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_settings
from app.models.prompt_models import (
    PromptListResponse,
    PromptResponse,
    PromptUpdateRequest,
)
from app.settings import AppSettings

logger = logging.getLogger(f"contelligence-agent.{__name__}")

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


@router.get("/cache/stats")
async def cache_stats(settings: AppSettings = Depends(get_settings)) -> dict:
    """Return extraction cache statistics."""
    from app.startup import _extraction_cache

    if _extraction_cache is None:
        return {"enabled": False}

    return _extraction_cache.get_stats()


@router.post("/cache/clear")
async def cache_clear(settings: AppSettings = Depends(get_settings)) -> dict:
    """Clear the extraction cache."""
    from app.startup import _extraction_cache

    if _extraction_cache is None:
        return {"cleared": False, "reason": "cache not enabled"}

    await _extraction_cache.clear()
    logger.info("Extraction cache cleared by admin request.")
    return {"cleared": True}


@router.get("/rate-limits")
async def rate_limit_status() -> dict:
    """Return current rate limiter status."""
    from app.rate_limiting import rate_limiter

    return rate_limiter.get_status()


# ---------------------------------------------------------------------------
# Prompt management
# ---------------------------------------------------------------------------


def _get_prompt_store(request: Request):
    """Retrieve the PromptStore from app state."""
    store = getattr(request.app.state, "prompt_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Prompt store not initialised")
    return store


@router.get("/prompts", response_model=PromptListResponse)
async def list_prompts(request: Request) -> PromptListResponse:
    """List all prompts (system + built-in agents) with their current state."""
    store = _get_prompt_store(request)
    prompts = await store.list_prompts()
    return PromptListResponse(prompts=prompts)


@router.get("/prompts/{prompt_id:path}", response_model=PromptResponse)
async def get_prompt(prompt_id: str, request: Request) -> PromptResponse:
    """Get a single prompt by ID (``system-prompt`` or ``agent:<name>``)."""
    store = _get_prompt_store(request)
    try:
        if prompt_id == "system-prompt":
            return await store.get_system_prompt()
        elif prompt_id.startswith("agent:"):
            agent_name = prompt_id[len("agent:"):]
            return await store.get_agent_prompt(agent_name)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prompt ID format: {prompt_id}. Use 'system-prompt' or 'agent:<name>'.",
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/prompts/{prompt_id:path}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: str,
    body: PromptUpdateRequest,
    request: Request,
) -> PromptResponse:
    """Update a prompt's content."""
    store = _get_prompt_store(request)
    try:
        if prompt_id == "system-prompt":
            result = await store.update_system_prompt(body.content)
            # Refresh the in-memory system prompt on the agent service
            agent_svc = getattr(request.app.state, "agent_service", None)
            if agent_svc is not None:
                agent_svc.system_prompt = body.content
            return result
        elif prompt_id.startswith("agent:"):
            agent_name = prompt_id[len("agent:"):]
            return await store.update_agent_prompt(agent_name, body.content)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prompt ID format: {prompt_id}. Use 'system-prompt' or 'agent:<name>'.",
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/prompts/{prompt_id:path}/reset", response_model=PromptResponse)
async def reset_prompt(prompt_id: str, request: Request) -> PromptResponse:
    """Reset a prompt to its built-in default."""
    store = _get_prompt_store(request)
    try:
        if prompt_id == "system-prompt":
            result = await store.reset_system_prompt()
            # Refresh the in-memory system prompt on the agent service
            agent_svc = getattr(request.app.state, "agent_service", None)
            if agent_svc is not None:
                agent_svc.system_prompt = result.content
            return result
        elif prompt_id.startswith("agent:"):
            agent_name = prompt_id[len("agent:"):]
            return await store.reset_agent_prompt(agent_name)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prompt ID format: {prompt_id}. Use 'system-prompt' or 'agent:<name>'.",
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

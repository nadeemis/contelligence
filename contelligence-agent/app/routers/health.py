from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_settings
from app.settings import AppSettings
from app.utils.instance import get_instance_id

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check(request: Request):
    """Health check with optional MCP server status."""
    mcp_config = getattr(request.app.state, "mcp_config", None)
    mcp_status: dict | None = None

    if mcp_config:
        from app.mcp.health import verify_mcp_servers

        mcp_status = await verify_mcp_servers(mcp_config, timeout=3.0)

    # Overall status: degraded if any MCP server is unavailable
    overall = "healthy"
    if mcp_status:
        for info in mcp_status.values():
            if info.get("status") == "unavailable":
                overall = "degraded"
                break

    response: dict = {
        "status": overall,
        "service": "contelligence-agent",
        "version": "1.0.0",
        "instance_id": get_instance_id(),
    }

    # Scheduler leader status
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        response["is_scheduler_leader"] = scheduler.is_leader if hasattr(scheduler, "is_leader") else False

    # Token manager health
    token_manager = getattr(request.app.state, "token_manager", None)
    if token_manager is not None:
        response["token_health"] = token_manager.health_status()

    if mcp_status is not None:
        response["mcp_servers"] = mcp_status

    return response


@router.get("/environment")
async def environment_info(
    request: Request,
    settings: AppSettings = Depends(get_settings),
) -> dict:
    """Return non-sensitive system environment and configuration values."""

    # Storage paths
    storage = {
        "storage_mode": settings.STORAGE_MODE,
        "local_data_dir": settings.app_data_dir(),
        "agent_shared_skills_dir": settings.AGENT_SHARED_SKILLS_DIRECTORY or "(not set)",
        "cli_shared_skills_dir": settings.CLI_SHARED_SKILLS_DIRECTORY or "(not set)",
        "cli_working_directory": settings.CLI_WORKING_DIRECTORY or "(not set)",
    }

    # Server / runtime
    server = {
        "api_version": settings.API_VERSION,
        "api_host": settings.API_HOST,
        "api_port": settings.API_PORT,
        "log_level": settings.LOG_LEVEL,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
    }

    # Session quotas
    quotas = {
        "session_timeout_minutes": settings.SESSION_TIMEOUT_MINUTES,
        "session_max_tool_calls": settings.SESSION_MAX_TOOL_CALLS,
        "session_max_documents": settings.SESSION_MAX_DOCUMENTS,
        "session_max_tokens": settings.SESSION_MAX_TOKENS,
        "approval_timeout_seconds": settings.APPROVAL_TIMEOUT_SECONDS,
    }

    # Rate limiting
    rate_limits = {
        "openai_rpm": settings.RATE_LIMIT_OPENAI_RPM,
        "doc_intel_rpm": settings.RATE_LIMIT_DOC_INTEL_RPM,
    }

    # Caching & retention
    cache_retention = {
        "cache_enabled": settings.CACHE_ENABLED,
        "cache_ttl_days": settings.CACHE_TTL_DAYS,
        "session_retention_days": settings.SESSION_RETENTION_DAYS,
        "blob_archive_days": settings.BLOB_ARCHIVE_DAYS,
        "blob_delete_days": settings.BLOB_DELETE_DAYS,
    }

    # Scaling
    scaling = {
        "max_replicas": settings.MAX_REPLICAS,
        "scheduler_misfire_grace_time": settings.SCHEDULER_MISFIRE_GRACE_TIME,
        "schedule_auto_pause_threshold": settings.SCHEDULE_AUTO_PAUSE_THRESHOLD,
    }

    return {
        "storage": storage,
        "server": server,
        "quotas": quotas,
        "rate_limits": rate_limits,
        "cache_retention": cache_retention,
        "scaling": scaling,
    }

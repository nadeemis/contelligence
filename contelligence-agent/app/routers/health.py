from __future__ import annotations

from fastapi import APIRouter, Request

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

    # Phase 4 — active session count
    agent_service = getattr(request.app.state, "agent_service", None)
    if agent_service is not None:
        response["active_sessions"] = len(
            getattr(agent_service, "active_sessions", {}),
        )

    # Phase 4 — scheduler leader status
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        response["is_scheduler_leader"] = scheduler.is_leader if hasattr(scheduler, "is_leader") else False

    # Phase 4 — token manager health
    token_manager = getattr(request.app.state, "token_manager", None)
    if token_manager is not None:
        response["token_health"] = token_manager.health_status()

    if mcp_status is not None:
        response["mcp_servers"] = mcp_status

    return response

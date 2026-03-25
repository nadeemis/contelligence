from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sse_starlette.sse import EventSourceResponse

from app.agents import CUSTOM_AGENTS
from app.auth.middleware import get_current_user
from app.auth.models import User
from app.connectors.blob_connector import BlobConnectorAdapter
from app.dependencies import (
    get_agent_service,
    get_approval_manager,
    get_blob_connector,
    get_client_factory,
    get_session_store,
)
from app.models.agent_models import InstructRequest, InstructResponse, ReplyRequest
from app.models.approval_models import ApprovalResponse
from app.models.api_models import SessionListItem, SessionLogsResponse, SessionOutputsResponse
from app.models.exceptions import SessionNotActiveError, SessionNotFoundError
from app.models.session_models import SessionStatus
from app.services.persistent_agent_service import PersistentAgentService
from app.store.session_store import SessionStore

logger = logging.getLogger(f"contelligence-agent.{__name__}")

router = APIRouter(prefix="/agent", tags=["Agent"])


# ---------------------------------------------------------------------------
# POST /instruct -- start a new agent session
# ---------------------------------------------------------------------------


@router.post("/instruct", response_model=InstructResponse)
async def instruct(
    body: InstructRequest,
    agent_service: PersistentAgentService = Depends(get_agent_service),
    user: User = Depends(get_current_user),
) -> InstructResponse:
    """Accept an instruction and start a new agent session, or resume an existing one."""
    try:
        if body.session_id:
            # Resume existing session
            session_id = await agent_service.resume_session(
                body.session_id, body.instruction, body.options,
            )
        else:
            # Create new session — attach user identity
            session_id = await agent_service.create_and_run(
                session_id=f"{user.oid}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                instruction=body.instruction,
                options=body.options,
                metadata={"user_id": user.oid},
            )
        return InstructResponse(session_id=session_id, status="processing")
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SessionNotActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in /instruct")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}/stream -- SSE event stream
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/stream")
async def stream_session(
    session_id: str,
    request: Request,
    agent_service: PersistentAgentService = Depends(get_agent_service),
    user: User = Depends(get_current_user),
) -> EventSourceResponse:
    """Stream server-sent events for an active agent session.

    Supports reconnection via the ``Last-Event-ID`` header — events
    already delivered are skipped on reconnect.
    """
    last_event_id = request.headers.get("Last-Event-ID")
    try:
        return EventSourceResponse(
            agent_service.stream_events(
                session_id, 
            ),
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SessionNotActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in /sessions/%s/stream", session_id)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /sessions/{session_id}/reply -- send a follow-up message
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/reply")
async def reply_to_session(
    session_id: str,
    body: ReplyRequest,
    agent_service: PersistentAgentService = Depends(get_agent_service),
    approval_manager=Depends(get_approval_manager),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Send a reply message to an active agent session.

    If a pending approval request exists for this session, the reply is
    treated as an approval response (approved / rejected / modified).
    Otherwise it is forwarded to the agent as a regular follow-up message.
    """
    try:
        # --- Phase 3: check for pending approval first ---
        if approval_manager is not None and approval_manager.has_pending(session_id):
            decision = _classify_approval_response(body.message)
            approval_manager.submit_response(
                session_id,
                ApprovalResponse(decision=decision, message=body.message),
            )
            return {"status": "approval_response_submitted", "decision": decision}

        # --- Regular reply (Phase 2 behaviour) ---
        await agent_service.send_reply(session_id=session_id, message=body.message)
        return {"status": "sent"}
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SessionNotActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in /sessions/%s/reply", session_id)
        raise HTTPException(status_code=500, detail=str(exc))


def _classify_approval_response(message: str) -> str:
    """Classify the user's free-text reply as an approval decision.

    Simple heuristic: look for signal words.  A richer implementation
    could use an LLM classifier.
    """
    lower = message.strip().lower()
    reject_signals = ("reject", "no", "deny", "cancel", "stop", "abort", "don't", "do not")
    modify_signals = ("modify", "change", "adjust", "update", "instead", "but", "however")

    if any(lower.startswith(s) or s in lower for s in reject_signals):
        return "rejected"
    if any(s in lower for s in modify_signals):
        return "modified"
    return "approved"


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id}/cancel -- cancel a session
# ---------------------------------------------------------------------------


@router.delete("/sessions/{session_id}/cancel")
async def cancel_session(
    session_id: str,
    agent_service: PersistentAgentService = Depends(get_agent_service),
) -> dict[str, str]:
    """Cancel an active agent session."""
    try:
        await agent_service.cancel(session_id=session_id)
        return {"status": "cancelled"}
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SessionNotActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error cancelling session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id} -- permanently delete a session
# ---------------------------------------------------------------------------


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    agent_service: PersistentAgentService = Depends(get_agent_service),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Permanently delete a session and all related data.

    Removes the session record, conversation turns, output artifacts,
    events, and any associated blobs from storage. If the session is
    currently active it will be cancelled first.

    Requires authentication. Non-admin users may only delete their own
    sessions.
    """
    try:
        # RBAC: non-admin users can only delete their own sessions
        if not user.is_admin:
            record = await agent_service.store.get_session(session_id)
            if record.user_id and record.user_id != user.oid:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have permission to delete this session",
                )

        summary = await agent_service.delete_session(session_id=session_id)
        return {"status": "deleted", **summary}
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error deleting session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}/status -- check session status
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/status")
async def get_session_status(
    session_id: str,
    agent_service: PersistentAgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    """Return the current status of a session."""
    try:
        return await agent_service.get_session_status(session_id=session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SessionNotActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error getting status for session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /sessions -- list sessions with optional filters
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    status: SessionStatus | None = Query(None, description="Filter by session status"),
    user_id: str | None = Query(None, description="Filter by user ID"),
    since: datetime | None = Query(None, description="Only sessions created after this ISO timestamp"),
    limit: int = Query(50, ge=1, le=200, description="Max results to return"),
    store: SessionStore = Depends(get_session_store),
    user: User = Depends(get_current_user),
) -> list[SessionListItem]:
    """List sessions with optional filters, newest first.

    Non-admin users can only see their own sessions.
    """
    try:
        # Phase 4 — RBAC: non-admin callers are restricted to their own sessions
        effective_user_id = user_id
        if user is not None and not user.is_admin:
            effective_user_id = user.oid

        records = await store.list_sessions(
            status=status,
            user_id=effective_user_id,
            since=since,
            limit=limit,
        )
        return [
            SessionListItem(
                id=r.id,
                created_at=r.created_at,
                status=r.status.value,
                instruction=r.instruction,
                model=r.model,
                metrics=r.metrics,
                summary=r.summary,
            )
            for r in records
        ]
    except Exception as exc:
        logger.exception("Unexpected error listing sessions")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /sessions/{session_id} -- full session record
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> dict[str, Any]:
    """Return the full session record."""
    try:
        record = await store.get_session(session_id)
        return record.model_dump(mode="json")
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error getting session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}/logs -- conversation turns
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/logs", response_model=SessionLogsResponse)
async def get_session_logs(
    session_id: str,
    include_tool_results: bool = Query(
        False,
        description="Include full tool call results (may be large)",
    ),
    store: SessionStore = Depends(get_session_store),
) -> SessionLogsResponse:
    """Return conversation turns for a session, optionally including tool results."""
    try:
        # Verify session exists
        await store.get_session(session_id)
        turns = await store.get_turns(session_id)

        turn_dicts = []
        for t in turns:
            d = t.model_dump(mode="json")
            # Strip large tool results unless explicitly requested
            if (
                not include_tool_results
                and d.get("tool_call")
                and d["tool_call"].get("result") is not None
            ):
                d["tool_call"]["result"] = {"_truncated": True}
            turn_dicts.append(d)

        return SessionLogsResponse(session_id=session_id, turns=turn_dicts)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error getting logs for session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))



# ---------------------------------------------------------------------------
# GET /models -- list available models
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models(
    client_factory=Depends(get_client_factory),
) -> dict[str, Any]:
    """Return the available models from the Copilot CLI."""
    try:
        client = client_factory.client
        models = await client.list_models()
        return {
            "models": [m.to_dict() for m in models],
        }
    except Exception as exc:
        logger.exception("Error listing models")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /agents -- list available custom agents (Phase 3)
# ---------------------------------------------------------------------------


@router.get("/agents")
async def list_agents() -> dict[str, Any]:
    """Return the available custom agents and their capabilities.

    System prompts are deliberately excluded from the response for security.
    """
    return {
        "agents": [
            {
                "name": a.name,
                "display_name": a.display_name,
                "description": a.description,
                "tools": a.tools,
                "mcp_servers": a.mcp_servers,
            }
            for a in CUSTOM_AGENTS.values()
        ]
    }

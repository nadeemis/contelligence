"""ApprovalManager — blocks the agent loop until the user confirms or rejects
destructive / high-stakes operations.

The manager uses per-session ``asyncio.Event`` objects so that a session can
be paused independently without affecting other sessions.

Timeout behaviour:
    If the user does not respond within ``timeout_seconds`` the pending
    request is automatically rejected and the agent is informed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.models.approval_models import ApprovalRequest, ApprovalResponse, PendingOperation

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class ApprovalManager:
    """In-memory approval gatekeeper.

    *Not* horizontally scalable — in a multi-replica deployment the caller
    must ensure the request and response arrive at the same replica (e.g.
    via sticky sessions or an external queue).
    """

    def __init__(self, timeout_seconds: int = 300) -> None:
        self._timeout = timeout_seconds
        self._pending: dict[str, ApprovalRequest] = {}
        self._events: dict[str, asyncio.Event] = {}

    # -- public API -----------------------------------------------------------

    async def request_approval(
        self,
        session_id: str,
        operations: list[PendingOperation],
        message: str,
    ) -> ApprovalResponse:
        """Block until the user submits a response or the request times out.

        Returns the user's ``ApprovalResponse``.  On timeout the response
        will have ``decision="rejected"`` with an explanatory message.
        """
        request = ApprovalRequest(
            session_id=session_id,
            operations=operations,
            message=message,
            requested_at=datetime.now(timezone.utc),
        )
        event = asyncio.Event()
        self._pending[session_id] = request
        self._events[session_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "Approval timed out after %ds for session %s",
                self._timeout,
                session_id,
            )
            self._cleanup(session_id)
            return ApprovalResponse(
                decision="rejected",
                message=(
                    f"Approval timed out after {self._timeout}s — "
                    "operations were not executed."
                ),
            )

        # The user submitted a response — retrieve and clean up.
        response = self._pending[session_id].response
        self._cleanup(session_id)

        if response is None:
            # Defensive: should never happen
            return ApprovalResponse(
                decision="rejected",
                message="No approval response received.",
            )
        return response

    def submit_response(
        self,
        session_id: str,
        response: ApprovalResponse,
    ) -> None:
        """Submit the user's decision, unblocking the waiting coroutine.

        Raises ``KeyError`` if there is no pending request for the session.
        """
        if session_id not in self._pending:
            raise KeyError(f"No pending approval for session {session_id}")

        self._pending[session_id].response = response
        self._events[session_id].set()

    def has_pending(self, session_id: str) -> bool:
        """Return ``True`` if a session has an outstanding approval request."""
        return session_id in self._pending

    def get_pending(self, session_id: str) -> ApprovalRequest | None:
        """Return the pending approval request for *session_id*, if any."""
        return self._pending.get(session_id)

    # -- internals ------------------------------------------------------------

    def _cleanup(self, session_id: str) -> None:
        self._pending.pop(session_id, None)
        self._events.pop(session_id, None)

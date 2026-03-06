"""Custom exceptions for the contelligence-agent."""

from __future__ import annotations


class SessionNotFoundError(Exception):
    """Raised when a session cannot be found by its ID."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class SessionNotActiveError(Exception):
    """Raised when an operation is attempted on a session that is not active."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session is not active: {session_id}")


class ScheduleNotFoundError(Exception):
    """Raised when a schedule cannot be found by its ID."""

    def __init__(self, schedule_id: str) -> None:
        self.schedule_id = schedule_id
        super().__init__(f"Schedule not found: {schedule_id}")


class QuotaExceededError(Exception):
    """Raised when a per-session resource quota is exceeded."""

    def __init__(
        self, session_id: str, resource: str, remaining: int | None,
    ) -> None:
        self.session_id = session_id
        self.resource = resource
        self.remaining = remaining
        super().__init__(
            f"Session '{session_id}' exceeded quota for '{resource}'. "
            f"Remaining: {remaining}"
        )

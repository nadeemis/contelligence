"""Session Manager — high-level lifecycle operations on sessions.

Consolidates rename / tag / pin / duplicate operations so routers stay
thin.  Enforces per-operation RBAC (owner-or-admin) and input validation
(tag length / tag count / title length).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from app.models.exceptions import SessionNotFoundError
from app.models.session_models import (
    ConversationTurn,
    SessionMetrics,
    SessionRecord,
    SessionStatus,
)
from app.settings import AppSettings
from app.store.session_store import SessionStore
from app.utils.cosmos_helpers import to_cosmos_dict

if TYPE_CHECKING:  # pragma: no cover — typing only
    from app.auth.models import User
    from app.services.session_titler import SessionTitler

logger = logging.getLogger(f"contelligence-agent.{__name__}")


_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]*$")


class SessionManager:
    """High-level lifecycle operations on sessions."""

    def __init__(
        self,
        store: SessionStore,
        titler: "SessionTitler | None",
        settings: AppSettings,
    ) -> None:
        self._store = store
        self._titler = titler
        self._settings = settings

    # ------------------------------------------------------------------
    # Authorisation
    # ------------------------------------------------------------------

    @staticmethod
    def _authorize(user: "User | None", record: SessionRecord) -> None:
        """Raise ``403`` if *user* cannot modify *record*."""
        if user is None:
            return  # Auth disabled — allow
        if getattr(user, "is_admin", False):
            return
        if record.user_id and record.user_id != user.oid:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to modify this session",
            )

    # ------------------------------------------------------------------
    # Rename (auto / manual)
    # ------------------------------------------------------------------

    async def rename(
        self,
        session_id: str,
        *,
        title: str | None,
        auto: bool,
        user: "User | None",
    ) -> SessionRecord:
        """Set the session title.

        When *auto* is true, invokes :class:`SessionTitler` and marks the
        result as ``title_source="auto"``.  Otherwise persists *title* as
        ``title_source="manual"``.
        """
        record = await self._store.get_session(session_id)
        self._authorize(user, record)

        if auto:
            if not self._settings.ENABLE_SESSION_AUTO_RENAME:
                raise HTTPException(
                    status_code=409,
                    detail="Auto-rename is disabled",
                )
            if self._titler is None:
                raise HTTPException(
                    status_code=503,
                    detail="Session titler is not configured",
                )
            turns = await self._store.get_turns(session_id)
            new_title = await self._titler.generate_title(
                record.instruction,
                turns=turns,
                summary=record.summary,
            )
            source = "auto"
        else:
            if title is None or not title.strip():
                raise HTTPException(
                    status_code=400,
                    detail="title is required for manual rename",
                )
            new_title = self._validate_title(title)
            source = "manual"

        return await self._store.update_session_fields(
            session_id,
            title=new_title,
            title_source=source,
        )

    def _validate_title(self, title: str) -> str:
        cleaned = re.sub(r"\s+", " ", title.strip().replace("\n", " "))
        max_len = 120
        if len(cleaned) > max_len:
            cleaned = cleaned[: max_len - 1].rstrip() + "…"
        if not cleaned:
            raise HTTPException(status_code=400, detail="title cannot be empty")
        return cleaned

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    async def set_tags(
        self,
        session_id: str,
        tags: list[str],
        user: "User | None",
    ) -> SessionRecord:
        """Replace the full tag list for a session."""
        record = await self._store.get_session(session_id)
        self._authorize(user, record)
        normalised = self._normalise_tags(tags)
        return await self._store.update_session_fields(session_id, tags=normalised)

    async def add_tags(
        self,
        session_id: str,
        tags: list[str],
        user: "User | None",
    ) -> SessionRecord:
        """Add tags, preserving existing ones (idempotent)."""
        record = await self._store.get_session(session_id)
        self._authorize(user, record)
        merged = list(record.tags or [])
        for tag in self._normalise_tags(tags):
            if tag not in merged:
                merged.append(tag)
        merged = self._normalise_tags(merged)  # re-validate count cap
        return await self._store.update_session_fields(session_id, tags=merged)

    async def remove_tags(
        self,
        session_id: str,
        tags: list[str],
        user: "User | None",
    ) -> SessionRecord:
        """Remove tags (idempotent)."""
        record = await self._store.get_session(session_id)
        self._authorize(user, record)
        to_remove = {self._normalise_single_tag(t) for t in tags}
        remaining = [t for t in (record.tags or []) if t not in to_remove]
        return await self._store.update_session_fields(session_id, tags=remaining)

    def _normalise_single_tag(self, tag: str) -> str:
        cleaned = (tag or "").strip().lower()
        if not cleaned:
            raise HTTPException(status_code=400, detail="Empty tag is not allowed")
        if len(cleaned) > self._settings.SESSION_MAX_TAG_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Tag '{cleaned[:20]}...' exceeds max length "
                    f"{self._settings.SESSION_MAX_TAG_LENGTH}"
                ),
            )
        if not _TAG_RE.match(cleaned):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Tag '{cleaned}' is invalid — use lowercase letters, "
                    "digits, hyphens or underscores (must start with a letter or digit)"
                ),
            )
        return cleaned

    def _normalise_tags(self, tags: list[str]) -> list[str]:
        seen: list[str] = []
        for tag in tags or []:
            norm = self._normalise_single_tag(tag)
            if norm not in seen:
                seen.append(norm)
        if len(seen) > self._settings.SESSION_MAX_TAGS:
            raise HTTPException(
                status_code=400,
                detail=f"At most {self._settings.SESSION_MAX_TAGS} tags per session",
            )
        return seen

    # ------------------------------------------------------------------
    # Pin
    # ------------------------------------------------------------------

    async def set_pinned(
        self,
        session_id: str,
        pinned: bool,
        user: "User | None",
    ) -> SessionRecord:
        record = await self._store.get_session(session_id)
        self._authorize(user, record)
        return await self._store.update_session_fields(session_id, pinned=pinned)

    # ------------------------------------------------------------------
    # Duplicate
    # ------------------------------------------------------------------

    async def duplicate(
        self,
        session_id: str,
        *,
        include_turns: bool = False,
        new_title: str | None = None,
        user: "User | None",
    ) -> SessionRecord:
        """Create a copy of a session.

        The duplicate starts in :class:`SessionStatus.COMPLETED` status so
        that it does not auto-run.  Users can kick it off via
        ``POST /agent/instruct`` with ``session_id`` set to the new ID.
        """
        original = await self._store.get_session(session_id)
        self._authorize(user, original)

        now = datetime.now(timezone.utc)
        new_id = str(uuid.uuid4())
        title_for_copy: str | None
        if new_title is not None:
            title_for_copy = self._validate_title(new_title)
            title_source = "manual"
        elif original.title:
            title_for_copy = self._validate_title(f"{original.title} (copy)")
            title_source = original.title_source
        else:
            title_for_copy = None
            title_source = None

        copy = SessionRecord(
            id=new_id,
            created_at=now,
            updated_at=now,
            status=SessionStatus.COMPLETED,
            model=original.model,
            instruction=original.instruction,
            user_id=user.oid if user is not None else original.user_id,
            options=dict(original.options or {}),
            schedule_id=None,
            trigger_reason=None,
            summary=original.summary,
            title=title_for_copy,
            title_source=title_source,
            tags=list(original.tags or []),
            pinned=False,
            parent_session_id=original.id,
            metrics=SessionMetrics(),
            allowed_agents=list(original.allowed_agents or []),
            active_skill_ids=list(original.active_skill_ids or []),
        )
        await self._store.save_session(copy)

        if include_turns:
            turns = await self._store.get_turns(session_id)
            for t in turns:
                dup_turn = ConversationTurn(
                    id=str(uuid.uuid4()),
                    session_id=new_id,
                    sequence=t.sequence,
                    timestamp=t.timestamp,
                    role=t.role,
                    prompt=t.prompt,
                    content=t.content,
                    reasoning=t.reasoning,
                    tool_call=t.tool_call,
                    metadata=t.metadata,
                )
                await self._store.save_turn(dup_turn)

        logger.info(
            "Duplicated session %s -> %s (include_turns=%s)",
            session_id, new_id, include_turns,
        )
        return copy


__all__ = ["SessionManager"]

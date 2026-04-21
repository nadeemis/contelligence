"""Unit tests for SessionManager — lifecycle, tags, pin, duplicate."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.session_models import SessionStatus
from app.services.session_manager import SessionManager
from app.settings import AppSettings
from tests.conftest import MockSessionStore, create_sample_session


def _settings(**overrides) -> AppSettings:
    base = {
        "ENABLE_SESSION_AUTO_RENAME": True,
        "SESSION_MAX_TAGS": 8,
        "SESSION_MAX_TAG_LENGTH": 32,
    }
    base.update(overrides)
    return AppSettings(_env_file=None, **base)


def _manager(store: MockSessionStore, *, titler=None, **settings_overrides) -> SessionManager:
    return SessionManager(
        store=store,
        titler=titler,
        settings=_settings(**settings_overrides),
    )


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


class TestRename:
    @pytest.mark.asyncio
    async def test_manual_rename_sets_title_and_source(self) -> None:
        store = MockSessionStore()
        record = create_sample_session(session_id="s-1")
        await store.save_session(record)

        mgr = _manager(store)
        updated = await mgr.rename("s-1", title="My Custom Title", auto=False, user=None)
        assert updated.title == "My Custom Title"
        assert updated.title_source == "manual"

    @pytest.mark.asyncio
    async def test_manual_rename_without_title_raises(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        mgr = _manager(store)
        with pytest.raises(HTTPException) as exc:
            await mgr.rename("s-1", title=None, auto=False, user=None)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_auto_rename_uses_titler(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(
            session_id="s-1", instruction="summarise Q3 report",
        ))

        class _StubTitler:
            async def generate_title(self, *a, **kw):
                return "Q3 Summary"

        mgr = _manager(store, titler=_StubTitler())
        updated = await mgr.rename("s-1", title=None, auto=True, user=None)
        assert updated.title == "Q3 Summary"
        assert updated.title_source == "auto"

    @pytest.mark.asyncio
    async def test_auto_rename_disabled_flag_raises_409(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        mgr = _manager(store, titler=object(), ENABLE_SESSION_AUTO_RENAME=False)
        with pytest.raises(HTTPException) as exc:
            await mgr.rename("s-1", title=None, auto=True, user=None)
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_title_truncation(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        mgr = _manager(store)
        long = "x" * 300
        updated = await mgr.rename("s-1", title=long, auto=False, user=None)
        assert len(updated.title) <= 120


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class TestTags:
    @pytest.mark.asyncio
    async def test_set_tags_normalises_and_deduplicates(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        mgr = _manager(store)
        updated = await mgr.set_tags("s-1", ["Finance", "finance", "Q3-report"], user=None)
        assert updated.tags == ["finance", "q3-report"]

    @pytest.mark.asyncio
    async def test_add_tags_is_idempotent(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        mgr = _manager(store)
        await mgr.add_tags("s-1", ["alpha"], user=None)
        updated = await mgr.add_tags("s-1", ["alpha", "beta"], user=None)
        assert updated.tags == ["alpha", "beta"]

    @pytest.mark.asyncio
    async def test_remove_tags(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        mgr = _manager(store)
        await mgr.set_tags("s-1", ["alpha", "beta", "gamma"], user=None)
        updated = await mgr.remove_tags("s-1", ["beta"], user=None)
        assert updated.tags == ["alpha", "gamma"]

    @pytest.mark.asyncio
    async def test_invalid_tag_format_raises(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        mgr = _manager(store)
        with pytest.raises(HTTPException) as exc:
            await mgr.set_tags("s-1", ["Has Space"], user=None)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_tag_count_cap(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        mgr = _manager(store, SESSION_MAX_TAGS=3)
        with pytest.raises(HTTPException) as exc:
            await mgr.set_tags("s-1", ["a", "b", "c", "d"], user=None)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Pin
# ---------------------------------------------------------------------------


class TestPin:
    @pytest.mark.asyncio
    async def test_pin_toggles(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        mgr = _manager(store)
        updated = await mgr.set_pinned("s-1", True, user=None)
        assert updated.pinned is True
        updated = await mgr.set_pinned("s-1", False, user=None)
        assert updated.pinned is False


# ---------------------------------------------------------------------------
# Duplicate
# ---------------------------------------------------------------------------


class TestDuplicate:
    @pytest.mark.asyncio
    async def test_duplicate_without_turns(self) -> None:
        store = MockSessionStore()
        orig = create_sample_session(session_id="s-1", instruction="do the thing")
        orig.tags = ["alpha"]
        orig.title = "Original"
        orig.allowed_agents = ["a1"]
        orig.active_skill_ids = ["sk1"]
        await store.save_session(orig)

        mgr = _manager(store)
        dup = await mgr.duplicate("s-1", include_turns=False, user=None)

        assert dup.id != "s-1"
        assert dup.parent_session_id == "s-1"
        assert dup.instruction == "do the thing"
        assert dup.tags == ["alpha"]
        assert dup.allowed_agents == ["a1"]
        assert dup.active_skill_ids == ["sk1"]
        assert dup.pinned is False
        assert dup.status == SessionStatus.COMPLETED
        assert dup.title == "Original (copy)"

    @pytest.mark.asyncio
    async def test_duplicate_with_new_title(self) -> None:
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        mgr = _manager(store)
        dup = await mgr.duplicate("s-1", new_title="Fresh Run", user=None)
        assert dup.title == "Fresh Run"

    @pytest.mark.asyncio
    async def test_duplicate_with_turns_copies_sequence(self) -> None:
        from tests.conftest import create_sample_turns
        store = MockSessionStore()
        await store.save_session(create_sample_session(session_id="s-1"))
        for t in create_sample_turns("s-1", count=3):
            await store.save_turn(t)

        mgr = _manager(store)
        dup = await mgr.duplicate("s-1", include_turns=True, user=None)

        dup_turns = await store.get_turns(dup.id)
        assert len(dup_turns) == 3
        # Sequences preserved.
        assert [t.sequence for t in dup_turns] == [0, 1, 2]
        # Turn IDs are new.
        orig_turns = await store.get_turns("s-1")
        assert {t.id for t in dup_turns}.isdisjoint({t.id for t in orig_turns})


# ---------------------------------------------------------------------------
# Authorisation
# ---------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, oid: str, is_admin: bool = False) -> None:
        self.oid = oid
        self.is_admin = is_admin


class TestAuthorisation:
    @pytest.mark.asyncio
    async def test_non_owner_non_admin_blocked(self) -> None:
        store = MockSessionStore()
        record = create_sample_session(session_id="s-1", user_id="owner-1")
        await store.save_session(record)
        mgr = _manager(store)
        with pytest.raises(HTTPException) as exc:
            await mgr.set_tags("s-1", ["x"], user=_FakeUser("other-1"))
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self) -> None:
        store = MockSessionStore()
        record = create_sample_session(session_id="s-1", user_id="owner-1")
        await store.save_session(record)
        mgr = _manager(store)
        updated = await mgr.set_tags("s-1", ["x"], user=_FakeUser("owner-1"))
        assert updated.tags == ["x"]

    @pytest.mark.asyncio
    async def test_admin_allowed(self) -> None:
        store = MockSessionStore()
        record = create_sample_session(session_id="s-1", user_id="owner-1")
        await store.save_session(record)
        mgr = _manager(store)
        updated = await mgr.set_tags("s-1", ["x"], user=_FakeUser("admin", is_admin=True))
        assert updated.tags == ["x"]

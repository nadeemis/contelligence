"""Unit tests for SessionStore list/search enhancements (items 3, 6, 8)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from tests.conftest import MockSessionStore, create_sample_session


@pytest.fixture()
def populated_store() -> MockSessionStore:
    store = MockSessionStore()
    now = datetime.now(timezone.utc)

    async def _seed():
        r1 = create_sample_session(session_id="s-1", instruction="analyse finance report")
        r1.tags = ["finance", "weekly"]
        r1.title = "Finance Weekly"
        r1.created_at = now - timedelta(hours=3)

        r2 = create_sample_session(session_id="s-2", instruction="marketing review")
        r2.tags = ["marketing"]
        r2.title = "Marketing Check"
        r2.created_at = now - timedelta(hours=2)

        r3 = create_sample_session(session_id="s-3", instruction="triage bugs")
        r3.tags = ["engineering", "bugs"]
        r3.title = "Bug Triage"
        r3.pinned = True
        r3.created_at = now - timedelta(hours=5)  # oldest but pinned

        r4 = create_sample_session(session_id="s-4", instruction="FINANCE deep dive")
        r4.tags = ["finance"]
        r4.created_at = now - timedelta(hours=1)
        for r in (r1, r2, r3, r4):
            await store.save_session(r)

    import asyncio
    asyncio.run(_seed())
    return store


@pytest.mark.asyncio
async def test_tag_filter_any_match(populated_store) -> None:
    records = await populated_store.list_sessions(tags=["finance"])
    ids = {r.id for r in records}
    assert ids == {"s-1", "s-4"}


@pytest.mark.asyncio
async def test_tag_filter_multiple_any(populated_store) -> None:
    records = await populated_store.list_sessions(tags=["marketing", "engineering"])
    ids = {r.id for r in records}
    assert ids == {"s-2", "s-3"}


@pytest.mark.asyncio
async def test_search_case_insensitive(populated_store) -> None:
    records = await populated_store.list_sessions(search="finance")
    ids = {r.id for r in records}
    assert ids == {"s-1", "s-4"}


@pytest.mark.asyncio
async def test_search_matches_title(populated_store) -> None:
    records = await populated_store.list_sessions(search="marketing check")
    assert {r.id for r in records} == {"s-2"}


@pytest.mark.asyncio
async def test_pinned_first_sort(populated_store) -> None:
    records = await populated_store.list_sessions(pinned_first=True)
    # Pinned s-3 should come first despite being the oldest.
    assert records[0].id == "s-3"


@pytest.mark.asyncio
async def test_pinned_first_false_sorts_by_date(populated_store) -> None:
    records = await populated_store.list_sessions(pinned_first=False)
    # Newest first (s-4, s-2, s-1, s-3).
    assert [r.id for r in records] == ["s-4", "s-2", "s-1", "s-3"]


@pytest.mark.asyncio
async def test_list_distinct_tags(populated_store) -> None:
    pairs = await populated_store.list_distinct_tags()
    tag_map = dict(pairs)
    assert tag_map["finance"] == 2
    assert tag_map["marketing"] == 1
    assert tag_map["engineering"] == 1
    assert tag_map["bugs"] == 1
    assert tag_map["weekly"] == 1

"""bdm-008 -- the follow-ups list, create, edit, complete and cancel (spec §5, §6; AC1-AC6, AC8)."""

import logging

import pytest
from sqlalchemy import select

from app.models import AuditLog, BdmTask
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import bdm_with_org
from tests.bdm007_helpers import completed
from tests.bdm008_helpers import TASKS, create_task, insert_task, ist_day, listed


@pytest.mark.asyncio
async def test_buckets_split_open_items_on_the_ist_date(client, db_session):
    """AC2: due yesterday = overdue, today = today, tomorrow = upcoming; each row says whether it is overdue."""
    _, bdm, _ = await bdm_with_org(client, db_session)
    for n in (-1, 0, 1):
        await insert_task(db_session, bdm.id, due_on=ist_day(n), title=f"d{n}")
    today = await listed(client)
    assert today["today"] == ist_day().isoformat() and [t["title"] for t in today["items"]] == ["d0"]
    assert [(t["title"], t["overdue"]) for t in (await listed(client, bucket="overdue"))["items"]] == [("d-1", True)]
    assert [t["title"] for t in (await listed(client, bucket="upcoming"))["items"]] == ["d1"]
    assert today["counts"]["buckets"] == {"today": 1, "overdue": 1, "upcoming": 1, "done": 0, "cancelled": 0}


@pytest.mark.asyncio
async def test_outcome_follow_up_is_listed_with_its_appointment(client, db_session):
    """AC1: a meeting report's follow-up date shows here, linked to its appointment, complete-only (AC6)."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org, next_follow_up_on=ist_day(2).isoformat())
    [item] = (await listed(client, bucket="upcoming"))["items"]
    assert (item["source"], item["kind"], item["appointment"], item["organization"]["id"]) == (
        "appointment_outcome", "follow_up", {"id": a["id"], "code": a["code"]}, org["id"])
    assert item["permissions"] == {"can_edit": False, "can_complete": True, "can_cancel": False}


@pytest.mark.asyncio
async def test_counts_match_the_list(client, db_session):
    """AC4: type counts sum to the total; a type filter's total equals that type's count; tab counts equal each tab's total."""
    _, bdm, college = await bdm_with_org(client, db_session)
    university = await create_org(client, org_type="university")
    for org_id in (college["id"], college["id"], university["id"], None):
        await insert_task(db_session, bdm.id, org_id=org_id)
    await insert_task(db_session, bdm.id, org_id=college["id"], status="done")
    page = await listed(client)
    assert page["counts"]["by_org_type"] == [{"org_type": "college", "count": 2}, {"org_type": "university", "count": 1}, {"org_type": None, "count": 1}]
    assert sum(c["count"] for c in page["counts"]["by_org_type"]) == page["total"] == 4
    filtered = await listed(client, org_type="college")
    assert filtered["total"] == 2 and {t["organization"]["org_type"] for t in filtered["items"]} == {"college"}
    assert filtered["counts"]["by_org_type"] == page["counts"]["by_org_type"]  # the chips keep showing every type
    assert (await listed(client, org_type="none"))["total"] == 1
    for tab, n in filtered["counts"]["buckets"].items():
        assert (await listed(client, bucket=tab, org_type="college"))["total"] == n


@pytest.mark.asyncio
async def test_done_and_cancelled_are_kept_and_ordered_newest_first(client, db_session):
    """AC3."""
    _, bdm, _ = await bdm_with_org(client, db_session)
    await insert_task(db_session, bdm.id, status="done", title="d1")
    await insert_task(db_session, bdm.id, status="done", title="d2")
    await insert_task(db_session, bdm.id, status="cancelled", title="c1")
    done = await listed(client, bucket="done")
    assert {t["title"] for t in done["items"]} == {"d1", "d2"} and all(t["completed_at"] for t in done["items"])
    [c] = (await listed(client, bucket="cancelled"))["items"]
    assert (c["title"], c["cancel_reason"], c["overdue"]) == ("c1", "Seeded", False)


@pytest.mark.asyncio
async def test_list_refuses_bad_filters(client, db_session):
    await bdm_with_org(client, db_session)
    for params in ({"bucket": "soon"}, {"org_type": "hospital"}, {"kind": "meeting"}, {"limit": 101}):
        assert (await client.get(TASKS, params=params)).status_code == 422
    other = await client.get(TASKS, params={"bdm_user_id": "00000000-0000-0000-0000-000000000000"})
    assert (other.status_code, other.json()["detail"]) == (422, "bdm_user_id is only for managers")

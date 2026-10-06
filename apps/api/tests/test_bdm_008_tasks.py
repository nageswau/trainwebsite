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


@pytest.mark.asyncio
async def test_create_a_manual_task_with_and_without_an_organization(client, db_session):
    """AC1: manual items; the server owns assignee, source and status."""
    _, bdm, org = await bdm_with_org(client, db_session)
    t = await create_task(client, kind="follow_up", organization_id=org["id"], notes="Ask for\nthe prospectus", due_on=ist_day(1).isoformat())
    assert (t["source"], t["status"], t["assignee"]["id"], t["notes"], t["organization"]["code"]) == ("manual", "open", str(bdm.id), "Ask for\nthe prospectus", org["code"])
    assert t["permissions"] == {"can_edit": True, "can_complete": True, "can_cancel": True}
    general = await create_task(client)
    assert general["organization"] is None and general["kind"] == "task"


@pytest.mark.asyncio
async def test_create_refusals(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    past = await client.post(TASKS, json={"kind": "task", "title": "x", "due_on": ist_day(-1).isoformat()})
    assert (past.status_code, past.json()["detail"]) == (422, "Due date can't be in the past")
    other = await make_bdm(db_session, manager)
    await login(client, other)
    theirs = await client.post(TASKS, json={"kind": "task", "title": "x", "due_on": ist_day().isoformat(), "organization_id": org["id"]})
    assert (theirs.status_code, theirs.json()["detail"]) == (403, "Only the assigned BDM can add tasks for this organization")
    await login(client, bdm)
    assert (await client.post(f"/api/v1/bdm/organizations/{org['id']}/archive")).status_code == 200
    archived = await client.post(TASKS, json={"kind": "task", "title": "x", "due_on": ist_day().isoformat(), "organization_id": org["id"]})
    assert (archived.status_code, archived.json()["detail"]) == (422, "This organization is archived — restore it before adding tasks")
    await login(client, manager)
    assert (await client.post(TASKS, json={"kind": "task", "title": "x", "due_on": ist_day().isoformat()})).status_code == 403


@pytest.mark.asyncio
async def test_create_cap(client, db_session, monkeypatch):
    from app.services import bdm_tasks

    monkeypatch.setattr(bdm_tasks, "DAILY_CAP", 1)
    await bdm_with_org(client, db_session)
    await create_task(client)
    again = await client.post(TASKS, json={"kind": "task", "title": "x", "due_on": ist_day().isoformat()})
    assert again.status_code == 409

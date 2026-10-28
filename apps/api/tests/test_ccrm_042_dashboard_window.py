"""ccrm-042 (DEC-SCOPE-313; AC1-AC7): the counselor dashboard's follow-ups and tasks sections cover overdue + today + the next 7 days
(India time), soonest first, overdue flagged -- so a follow-up added now (always future-dated) shows on the next load. Backlog:
docs/delivery/COUNSELOR_CRM_BACKLOG_2.md `ccrm-042`."""

from datetime import UTC, datetime, time, timedelta

import pytest

from app.models import CounselorTask, LeadFollowUp
from app.services.bdm_travel import INDIA
from tests.agn001_helpers import client_for, mk_user, uniq
from tests.ccrm012_helpers import mk_lead
from tests.test_ccrm_032_dashboard import URL, add, at, day, follow_up, ids, task


async def sections(user) -> dict:
    async with client_for(user.email) as c:
        r = await c.get(URL)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_a_follow_up_added_for_tomorrow_shows_at_once_and_leaves_when_done(db_session):
    """AC1 + positive scenario: create through the API, see it, complete it, it is gone."""
    a = await mk_user(db_session, role="counselor", full_name=f"Win A {uniq()}")
    lead = await mk_lead(db_session, a, status="qualified", next_action="Send brochure", next_action_due=day(1))
    async with client_for(a.email) as c:
        created = await c.post(f"/api/v1/counselor/leads/{lead.id}/follow-ups", json={"due_at": at(1).isoformat(), "reason": "counselor_call", "next_action": "Call about intake"})
        assert created.status_code == 201, created.text
        fu_id = created.json()["id"]
        body = (await c.get(URL)).json()
        item = next(i for i in body["sections"]["follow_ups"]["items"] if i["id"] == fu_id)
        assert item["overdue"] is False and item["detail"] == "Call about intake"
        assert (await c.post(f"/api/v1/counselor/follow-ups/{fu_id}/complete", json={})).status_code in (200, 201)
        assert fu_id not in ids((await c.get(URL)).json(), "follow_ups")


@pytest.mark.asyncio
async def test_follow_ups_cover_overdue_today_and_the_next_seven_days_soonest_first(db_session):
    """AC2-AC4, AC6 and the start+8d boundary (exclusive)."""
    a = await mk_user(db_session, role="counselor", full_name=f"Win B {uniq()}")
    lead = await mk_lead(db_session, a, status="qualified", next_action="Call", next_action_due=day(1))
    late = await follow_up(db_session, lead, a, -4)
    soon = await follow_up(db_session, lead, a, 3)
    last = await add(db_session, LeadFollowUp(lead_id=lead.id, due_at=datetime.combine(day(8), time.min, INDIA) - timedelta(minutes=1), reason="counselor_call", created_by_user_id=a.id))
    edge = await add(db_session, LeadFollowUp(lead_id=lead.id, due_at=datetime.combine(day(8), time.min, INDIA), reason="counselor_call", created_by_user_id=a.id))
    await follow_up(db_session, lead, a, 8)
    await follow_up(db_session, lead, a, 1, status="done")
    await add(
        db_session, LeadFollowUp(lead_id=lead.id, due_at=at(1), reason="counselor_call", status="cancelled", cancelled_at=datetime.now(UTC), cancel_reason="Lead closed", created_by_user_id=a.id)
    )
    s = (await sections(a))["sections"]["follow_ups"]
    assert [i["id"] for i in s["items"]] == [str(late.id), str(soon.id), str(last.id)]
    assert [i["overdue"] for i in s["items"]] == [True, False, False]
    assert s["count"] == 3 and str(edge.id) not in {i["id"] for i in s["items"]}


@pytest.mark.asyncio
async def test_tasks_follow_the_same_window_with_overdue_flagged(db_session):
    """AC5 + AC6: open tasks due up to today + 7, soonest first; done/cancelled and later ones are left out."""
    a = await mk_user(db_session, role="counselor", full_name=f"Win C {uniq()}")
    late, today_, week = await task(db_session, a, day(-3)), await task(db_session, a, day(0)), await task(db_session, a, day(7))
    await task(db_session, a, day(8))
    await task(db_session, a, day(2), status="done")
    await add(
        db_session,
        CounselorTask(
            title=f"Gone {uniq()}", due_on=day(1), priority="low", status="cancelled", cancelled_at=datetime.now(UTC), counselor_user_id=a.id, created_by_user_id=a.id, updated_by_user_id=a.id
        ),
    )
    s = (await sections(a))["sections"]["overdue_tasks"]
    assert [i["id"] for i in s["items"]] == [str(late.id), str(today_.id), str(week.id)]
    assert [i["overdue"] for i in s["items"]] == [True, False, False]
    assert s["items"][1]["href"] == "/overseas/counselor/tasks"


@pytest.mark.asyncio
async def test_another_counselors_and_handed_over_leads_follow_ups_never_show(db_session):
    """AC7 + negative scenario: scope stays the lead owner."""
    a = await mk_user(db_session, role="counselor", full_name=f"Win D {uniq()}")
    b = await mk_user(db_session, role="counselor", full_name=f"Win E {uniq()}")
    theirs = await follow_up(db_session, await mk_lead(db_session, b, status="qualified"), b, 1)
    moved_lead = await mk_lead(db_session, a, status="qualified")
    moved = await follow_up(db_session, moved_lead, a, 2)
    await task(db_session, b, day(1))
    moved_lead.owner_id = b.id
    await db_session.commit()
    body = await sections(a)
    assert body["sections"]["follow_ups"]["count"] == 0 and body["sections"]["overdue_tasks"]["count"] == 0
    assert {str(theirs.id), str(moved.id)} <= ids(await sections(b), "follow_ups")


@pytest.mark.asyncio
async def test_more_than_ten_follow_ups_in_the_window_keep_the_full_count(db_session):
    a = await mk_user(db_session, role="counselor", full_name=f"Win F {uniq()}")
    lead = await mk_lead(db_session, a, status="qualified")
    for offset in range(1, 8):
        await follow_up(db_session, lead, a, offset)
        await follow_up(db_session, lead, a, offset)
    s = (await sections(a))["sections"]["follow_ups"]
    assert s["count"] == 14 and len(s["items"]) == 10 and s["more"] is True

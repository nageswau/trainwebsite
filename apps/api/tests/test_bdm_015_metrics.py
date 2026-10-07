"""bdm-015 -- the daily metric catalogue (spec §3; AC1). Each count is exact for the BDM's IST day: records of the day before, the day
after and of another BDM never count; counts that need unbuilt sources are "not tracked", never 0."""

import uuid

import pytest
from sqlalchemy import event

from app.models import SchoolStudent
from app.services import bdm_metrics as metrics
from tests.bdm001_helpers import make_manager
from tests.bdm002_helpers import make_bdm
from tests.bdm015_helpers import (
    a_past_day,
    activity,
    after,
    appointment,
    before,
    by_key,
    follow_up,
    inside,
    lead,
    mou_event,
    org_row,
    trip,
)

COLLEGE_KEYS = [
    "calls_made",
    "colleges_contacted",
    "agents_contacted",
    "meetings_completed",
    "appointments_fixed",
    "travel_completed",
    "proposals_sent",
    "mous_discussed",
    "mous_signed",
    "student_leads",
    "follow_ups_completed",
]
AGENT_KEYS = [
    "calls_made",
    "agents_contacted",
    "meetings_completed",
    "new_prospects",
    "new_agents",
    "mous_signed",
    "agent_training",
    "follow_ups_completed",
    "student_leads",
    "applications_generated",
    "enrollments_generated",
]
SCHOOL_KEYS = [
    "schools_contacted",
    "calls_made",
    "meetings_completed",
    "school_visits",
    "presentations",
    "proposals_sent",
    "mous_signed",
    "follow_ups_completed",
    "students_generated",
    "career_guidance_sessions",
    "psychometric_sessions",
]


async def _pair(db, bdm_type: str):
    manager = await make_manager(db)
    return await make_bdm(db, manager, bdm_type), await make_bdm(db, manager, bdm_type)


def test_each_type_lists_exactly_its_source_counts_in_order():
    assert [k for k, _ in metrics.DAILY_REPORTS["college"]] == COLLEGE_KEYS
    assert [k for k, _ in metrics.DAILY_REPORTS["agent"]] == AGENT_KEYS
    assert [k for k, _ in metrics.DAILY_REPORTS["school"]] == SCHOOL_KEYS
    assert dict(metrics.DAILY_REPORTS["agent"])["mous_signed"] == "Agreements"
    assert dict(metrics.DAILY_REPORTS["school"])["calls_made"] == "Calls"


@pytest.mark.asyncio
async def test_an_empty_day_is_all_zero_except_not_tracked(db_session):
    bdm, _ = await _pair(db_session, "agent")
    items = await metrics.daily_counts(db_session, bdm.id, "agent", a_past_day())
    assert [i["key"] for i in items] == AGENT_KEYS
    assert all(i["definition"] for i in items)
    counts = by_key(items)
    assert {k for k, v in counts.items() if v == "not tracked"} == {"new_agents", "applications_generated", "enrollments_generated"}
    assert all(v == 0 for v in counts.values() if v != "not tracked")
    assert all(i["count"] is None for i in items if not i["tracked"])


@pytest.mark.asyncio
async def test_college_counts_are_exact_for_the_ist_day(db_session):
    bdm, other = await _pair(db_session, "college")
    day = a_past_day()
    college = await org_row(db_session, bdm.id, "college")
    college2 = await org_row(db_session, bdm.id, "college")
    agent_org = await org_row(db_session, bdm.id, "agent")
    # M-01: outbound calls only, in the day, own
    await activity(db_session, bdm.id, college.id, inside(day))
    await activity(db_session, bdm.id, college.id, inside(day, 11))
    await activity(db_session, bdm.id, college.id, inside(day), direction="inbound")
    await activity(db_session, bdm.id, college.id, before(day))
    await activity(db_session, bdm.id, college.id, after(day))
    await activity(db_session, other.id, college.id, inside(day))
    await activity(db_session, bdm.id, agent_org.id, inside(day), channel="email")
    # M-05/M-06: college2 is contacted only through a completed appointment; a scheduled one never counts
    await appointment(db_session, bdm.id, college2.id, inside(day, 12))
    await appointment(db_session, bdm.id, college2.id, inside(day, 13), status="scheduled")
    await appointment(db_session, bdm.id, college2.id, before(day))
    await appointment(db_session, other.id, college2.id, inside(day))
    # M-07: two fixed today, one of them cancelled the same day; one cancelled later still counts
    await appointment(db_session, bdm.id, college.id, after(day), status="scheduled", created_at=inside(day))
    await appointment(db_session, bdm.id, college.id, after(day), status="cancelled", created_at=inside(day), cancelled_at=inside(day, 14))
    await appointment(db_session, bdm.id, college.id, after(day), status="cancelled", created_at=inside(day), cancelled_at=after(day))
    # M-10: completed MoU discussion
    await appointment(db_session, bdm.id, college.id, inside(day, 15), appointment_type="mou_discussion")
    # M-08
    await trip(db_session, bdm.id, inside(day))
    await trip(db_session, bdm.id, before(day))
    await trip(db_session, other.id, inside(day))
    # M-09 / M-11: transitions only (a no-change event does not count)
    await mou_event(db_session, bdm.id, college.id, "proposal_sent", inside(day))
    await mou_event(db_session, bdm.id, college.id, "proposal_sent", inside(day), from_status="proposal_sent")
    await mou_event(db_session, bdm.id, college.id, "signed", inside(day), from_status=None)
    await mou_event(db_session, other.id, college.id, "signed", inside(day))
    await mou_event(db_session, bdm.id, college.id, "signed", after(day))
    # M-12
    await lead(db_session, bdm.id, college.id, inside(day))
    await lead(db_session, bdm.id, college.id, before(day))
    await lead(db_session, other.id, college.id, inside(day))
    # M-13: done follow-ups; a done task or a cancelled follow-up never counts
    await follow_up(db_session, bdm.id, inside(day))
    await follow_up(db_session, bdm.id, inside(day), kind="task")
    await follow_up(db_session, bdm.id, inside(day), status="cancelled")
    await follow_up(db_session, other.id, inside(day))

    counts = by_key(await metrics.daily_counts(db_session, bdm.id, "college", day))
    assert counts == {
        "calls_made": 2,
        "colleges_contacted": 2,
        "agents_contacted": 1,
        "meetings_completed": 2,
        "appointments_fixed": 2,
        "travel_completed": 1,
        "proposals_sent": 1,
        "mous_discussed": 1,
        "mous_signed": 1,
        "student_leads": 1,
        "follow_ups_completed": 1,
    }


@pytest.mark.asyncio
async def test_agent_counts_prospects_and_training(db_session):
    bdm, other = await _pair(db_session, "agent")
    day = a_past_day(3)
    agent_org = await org_row(db_session, bdm.id, "agent", "agent", created_at=inside(day))
    await org_row(db_session, bdm.id, "agent", "agent", created_at=before(day))
    await org_row(db_session, bdm.id, "university", "agent", created_at=inside(day))  # not an agent: not a "new prospect"
    await org_row(db_session, other.id, "agent", "agent", created_at=inside(day))
    await appointment(db_session, bdm.id, agent_org.id, inside(day), appointment_type="product_training")
    await appointment(db_session, bdm.id, agent_org.id, inside(day, 11), appointment_type="agreement_discussion")
    await mou_event(db_session, bdm.id, agent_org.id, "signed", inside(day))
    counts = by_key(await metrics.daily_counts(db_session, bdm.id, "agent", day))
    assert counts["new_prospects"] == 1
    assert counts["agent_training"] == 1
    assert counts["meetings_completed"] == 2
    assert counts["agents_contacted"] == 1
    assert counts["mous_signed"] == 1


@pytest.mark.asyncio
async def test_school_counts_sessions_presentations_and_students(client, db_session):
    from tests.test_bdm_020_school_activity import _linked

    w = await _linked(client, db_session)
    bdm_id, school_id = w["ids"]["owner"], uuid.UUID(w["school"]["id"])
    org_id = uuid.UUID(w["org"]["id"])
    day = a_past_day(1)
    for kind in ("career_guidance_presentation", "career_guidance_presentation", "psychometric_presentation", "profile_building_presentation"):
        await appointment(db_session, bdm_id, org_id, inside(day), appointment_type=kind)
    await appointment(db_session, bdm_id, org_id, inside(day), appointment_type="psychometric_presentation", status="cancelled")
    await activity(db_session, bdm_id, org_id, inside(day), channel="visit", direction=None)
    for at in (inside(day), inside(day, 12), before(day)):
        student = SchoolStudent(school_id=school_id, student_code=uuid.uuid4().hex[:8].upper(), full_name="Priya Student", created_by_user_id=w["ids"]["admin"])
        student.created_at = at
        db_session.add(student)
    await db_session.commit()
    counts = by_key(await metrics.daily_counts(db_session, bdm_id, "school", day))
    assert counts["career_guidance_sessions"] == 2
    assert counts["psychometric_sessions"] == 1
    assert counts["presentations"] == 4
    assert counts["meetings_completed"] == 4
    assert counts["school_visits"] == 1
    assert counts["schools_contacted"] == 1
    assert counts["students_generated"] == 2


@pytest.mark.asyncio
async def test_one_query_whatever_the_type(db_session):
    bdm, _ = await _pair(db_session, "school")
    statements: list[str] = []
    engine = db_session.bind.sync_engine if hasattr(db_session.bind, "sync_engine") else db_session.bind
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        await metrics.daily_counts(db_session, bdm.id, "school", a_past_day())
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len(statements) == 1

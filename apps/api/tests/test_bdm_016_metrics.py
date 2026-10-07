"""bdm-016 -- the monthly KPI catalogue and its achieved counts (spec §3; AC1, AC3). Each count is exact for the IST month: records of the
month before, the month after and of another BDM never count; KPIs that need unbuilt sources are "not tracked", never 0."""

from datetime import timedelta

import pytest
from sqlalchemy import event

from app.models import User
from app.services import bdm_metrics as metrics
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm015_helpers import activity, appointment, mou_event, org_row
from tests.bdm016_helpers import (
    after,
    before,
    by_key,
    career,
    converted_lead,
    enroll,
    inside,
    placement,
    psychometric,
    school,
    school_student,
    shift,
    this_month,
)

AGENT = ["new_agent_leads", "agent_meetings", "new_agents", "agreements_signed", "active_agents", "agent_students", "applications", "enrollments",
         "college_meetings", "new_colleges", "appointments", "mous", "student_leads"]
SCHOOL = ["schools_contacted", "school_meetings", "school_presentations", "proposals", "mous", "active_schools", "students_onboarded", "career_guidance",
          "psychometric_tests", "college_meetings", "agent_meetings", "new_colleges", "new_agents", "appointments", "student_leads"]
COLLEGE = ["colleges_contacted", "meetings", "college_presentations", "mous", "course_promotions", "student_leads", "training_registrations",
           "internship_students", "placement_candidates", "college_meetings", "agent_meetings", "new_colleges", "new_agents", "appointments"]
PAST = shift(this_month(), -1)  # a fully elapsed IST month


async def _pair(db, bdm_type: str) -> tuple[User, User]:
    manager = await make_manager(db)
    return await make_bdm(db, manager, bdm_type), await make_bdm(db, manager, bdm_type)


def test_each_type_offers_its_own_kpis_then_the_common_list_once():
    assert list(metrics.TARGET_KPIS["agent"]) == AGENT
    assert list(metrics.TARGET_KPIS["school"]) == SCHOOL
    assert list(metrics.TARGET_KPIS["college"]) == COLLEGE
    for keys in metrics.TARGET_KPIS.values():
        assert all(k in metrics.TARGET_METRICS for k in keys)
    assert metrics.TARGET_METRICS["mous"][0] == "MoUs" and metrics.TARGET_METRICS["college_presentations"][0] == "Presentations"


def test_the_month_is_the_ist_calendar_month():
    start, end = metrics.month_range(PAST)
    assert start.tzinfo == IST and start.utcoffset() == timedelta(hours=5, minutes=30) and (start.date(), start.hour) == (PAST, 0)
    assert end == metrics.month_range(shift(PAST, 1))[0]


@pytest.mark.asyncio
async def test_an_empty_month_is_all_zero_except_not_tracked(db_session):
    bdm, _ = await _pair(db_session, "agent")
    items = await metrics.monthly_counts(db_session, bdm.id, "agent", PAST)
    assert [i["key"] for i in items] == AGENT and all(i["label"] and i["definition"] for i in items)
    counts = by_key(items)
    assert {k for k, v in counts.items() if v == "not tracked"} == {"new_agents", "active_agents", "agent_students", "applications", "enrollments"}
    assert all(v == 0 for v in counts.values() if v != "not tracked")


@pytest.mark.asyncio
async def test_college_kpis_are_exact_for_the_month(db_session):
    bdm, other = await _pair(db_session, "college")
    college = await org_row(db_session, bdm.id, "college", created_at=inside(PAST))
    await org_row(db_session, bdm.id, "college", created_at=before(PAST))  # created last month: not new
    agent_org = await org_row(db_session, bdm.id, "agent", "college")
    for at, kind in ((inside(PAST), "college_meeting"), (inside(PAST, 20), "it_training_presentation"), (inside(PAST, 3), "course_promotion"),
                     (before(PAST), "college_meeting"), (after(PAST), "college_meeting")):
        await appointment(db_session, bdm.id, college.id, at, appointment_type=kind)
    await appointment(db_session, bdm.id, agent_org.id, inside(PAST), appointment_type="agent_meeting")
    await appointment(db_session, bdm.id, college.id, inside(PAST), status="scheduled")
    await appointment(db_session, other.id, college.id, inside(PAST))
    await activity(db_session, bdm.id, agent_org.id, inside(PAST))
    await mou_event(db_session, bdm.id, college.id, "signed", inside(PAST))
    await mou_event(db_session, bdm.id, agent_org.id, "signed", inside(PAST, 1))
    await mou_event(db_session, bdm.id, college.id, "signed", before(PAST))
    registered, placed = await converted_lead(db_session, bdm.id, college.id), await converted_lead(db_session, bdm.id, college.id)
    await enroll(db_session, registered.id, inside(PAST))
    await enroll(db_session, registered.id, inside(PAST, 2))  # a second enrollment: the same student once
    await enroll(db_session, placed.id, before(PAST))
    await placement(db_session, placed.id, inside(PAST))
    theirs = await converted_lead(db_session, other.id, college.id)
    await enroll(db_session, theirs.id, inside(PAST))
    counts = by_key(await metrics.monthly_counts(db_session, bdm.id, "college", PAST))
    assert counts["meetings"] == 4  # three typed at the college + one agent meeting; not scheduled, other months or the other BDM
    assert counts["college_meetings"] == 3 and counts["agent_meetings"] == 1
    assert counts["college_presentations"] == 1 and counts["course_promotions"] == 1
    assert counts["colleges_contacted"] == 1
    assert counts["new_colleges"] == 1
    assert counts["mous"] == 2
    assert counts["student_leads"] == 0  # the converted leads were entered this month, not in PAST
    assert counts["training_registrations"] == 1 and counts["placement_candidates"] == 1
    assert counts["internship_students"] == "not tracked"


@pytest.mark.asyncio
async def test_agent_kpis_filter_agreements_and_new_leads_to_agent_organizations(db_session):
    bdm, _ = await _pair(db_session, "agent")
    agent_org = await org_row(db_session, bdm.id, "agent", "agent", created_at=inside(PAST))
    college = await org_row(db_session, bdm.id, "college", "agent", created_at=inside(PAST))
    await mou_event(db_session, bdm.id, agent_org.id, "signed", inside(PAST))
    await mou_event(db_session, bdm.id, college.id, "signed", inside(PAST))
    await mou_event(db_session, bdm.id, agent_org.id, "signed", inside(PAST), from_status="signed")  # stayed signed: not a transition
    counts = by_key(await metrics.monthly_counts(db_session, bdm.id, "agent", PAST))
    assert counts["agreements_signed"] == 1 and counts["mous"] == 2
    assert counts["new_agent_leads"] == 1 and counts["new_colleges"] == 1


@pytest.mark.asyncio
async def test_school_kpis_count_students_served_in_the_linked_schools(db_session):
    bdm, other = await _pair(db_session, "school")
    admin = await make_user(db_session, "overseas_admin", "overseas")
    counselor = await make_user(db_session, "career_counselor", "overseas")
    team = await make_user(db_session, "psychometric_team", "overseas")
    last_day = shift(PAST, 1) - timedelta(days=1)
    linked = await school(db_session, admin.id, valid_until=last_day)
    expired = await school(db_session, admin.id, valid_until=last_day - timedelta(days=1))
    unlinked = await school(db_session, admin.id)
    for s in (linked, expired):
        await org_row(db_session, bdm.id, "school", "school", school_id=s.id)
    await org_row(db_session, other.id, "school", "school", school_id=unlinked.id)
    a = await school_student(db_session, linked.id, admin.id, inside(PAST))
    b = await school_student(db_session, linked.id, admin.id, before(PAST))
    c = await school_student(db_session, unlinked.id, admin.id, inside(PAST))
    await career(db_session, a.id, counselor.id, completed_on=PAST + timedelta(days=4))
    await career(db_session, a.id, counselor.id, status="follow_up_required", completed_on=PAST + timedelta(days=5))  # same student once
    await career(db_session, b.id, counselor.id, status=None, created_at=inside(PAST))  # legacy row: dated by created_at
    await career(db_session, b.id, counselor.id, status="scheduled", completed_on=PAST)  # not delivered
    await career(db_session, b.id, counselor.id, completed_on=last_day + timedelta(days=1))  # next month
    await career(db_session, c.id, counselor.id, completed_on=PAST)  # another BDM's school
    await career(db_session, a.id, counselor.id, completed_on=PAST, record_type="counselling_note")  # not a guidance session
    await psychometric(db_session, a.id, team.id, test_date=PAST + timedelta(days=2))
    await psychometric(db_session, b.id, team.id, created_at=inside(PAST))  # no test date: dated by created_at
    await psychometric(db_session, b.id, team.id, status="assigned", test_date=PAST)
    await psychometric(db_session, c.id, team.id, test_date=PAST)
    counts = by_key(await metrics.monthly_counts(db_session, bdm.id, "school", PAST))
    assert counts["active_schools"] == 1  # valid until the month's last day; the other expired the day before
    assert counts["students_onboarded"] == 1
    assert counts["career_guidance"] == 2
    assert counts["psychometric_tests"] == 2


@pytest.mark.asyncio
async def test_one_query_whatever_the_type_and_none_for_a_future_month(db_session):
    bdm, _ = await _pair(db_session, "school")
    statements: list[str] = []
    engine = db_session.bind.sync_engine if hasattr(db_session.bind, "sync_engine") else db_session.bind
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        await metrics.monthly_counts(db_session, bdm.id, "school", PAST)
        assert len(statements) == 1
        future = await metrics.monthly_counts(db_session, bdm.id, "school", shift(this_month(), 1), future=True)
        assert len(statements) == 1 and all(i["achieved"] is None for i in future)
    finally:
        event.remove(engine, "before_cursor_execute", listener)

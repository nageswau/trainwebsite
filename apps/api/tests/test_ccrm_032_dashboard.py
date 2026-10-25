"""ccrm-032 (DEC-SCOPE-277, D1-D10): the overseas counselor's action dashboard -- one read-only aggregate of their own leads, tasks,
follow-ups, appointments, calls, students and applications. Every counselor here is fresh, so the counts are exact. Spec:
docs/superpowers/specs/2026-10-25-ccrm-032-counselor-action-dashboard-design.md."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
import pytest_asyncio

from app.models import (
    ApplicationDepositRecord,
    ApplicationOffer,
    ApplicationOfferCondition,
    Appointment,
    CounselorTask,
    DocumentRequest,
    LeadCall,
    LeadFollowUp,
    OverseasStudentArchive,
    VisaCase,
)
from app.services.bdm_travel import INDIA, india_today
from tests.agn001_helpers import client_for, mk_user, uniq
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import mk_doc
from tests.ccrm012_helpers import mk_lead, mk_university

URL = "/api/v1/counselor/dashboard"


def day(offset: int = 0) -> date:
    return india_today() + timedelta(days=offset)


def at(offset: int, hour: int = 11) -> datetime:
    return datetime.combine(day(offset), time(hour), INDIA)


async def add(db, row):
    db.add(row)
    await db.commit()
    return row


def ids(body: dict, key: str) -> set[str]:
    return {i["id"] for i in body["sections"][key]["items"]}


async def task(db, counselor, due: date, status: str = "open") -> CounselorTask:
    return await add(
        db, CounselorTask(title=f"Task {uniq()}", due_on=due, priority="medium", status=status, counselor_user_id=counselor.id, created_by_user_id=counselor.id, updated_by_user_id=counselor.id)
    )


async def follow_up(db, lead, counselor, offset: int, status: str = "open") -> LeadFollowUp:
    done = {"completed_at": datetime.now(UTC), "completed_by_user_id": counselor.id} if status == "done" else {}
    return await add(db, LeadFollowUp(lead_id=lead.id, due_at=at(offset), reason="counselor_call", status=status, created_by_user_id=counselor.id, **done))


@pytest_asyncio.fixture
async def world(db_session):
    db = db_session
    w: dict = {"a": await mk_user(db, role="counselor", full_name=f"Dash A {uniq()}"), "b": await mk_user(db, role="counselor", full_name=f"Dash B {uniq()}")}
    a, b = w["a"], w["b"]
    uni = await mk_university(db, "Dashland")
    # leads
    w["new"] = await mk_lead(db, a, status="new")
    w["pending"] = await mk_lead(db, a, status="first_call_pending", next_action="Call", next_action_due=day(1))
    w["bare"] = await mk_lead(db, a, status="follow_up")  # no next action
    w["planned"] = await mk_lead(db, a, status="qualified", next_action="Send brochure", next_action_due=day(2))
    w["lost"] = await mk_lead(db, a, status="lost")
    w["linked"] = await mk_lead(db, a, status="application_enrollment")
    w["b_lead"] = await mk_lead(db, b, status="new")
    # follow-ups, tasks, calls, appointments
    w["fu_today"] = await follow_up(db, w["planned"], a, 0)
    w["fu_late"] = await follow_up(db, w["planned"], a, -3)
    w["fu_later"] = await follow_up(db, w["planned"], a, 2)
    w["fu_done"] = await follow_up(db, w["planned"], a, -1, status="done")
    w["fu_b"] = await follow_up(db, w["b_lead"], b, 0)
    w["late_task"] = await task(db, a, day(-2))
    w["today_task"] = await task(db, a, day(0))
    w["done_task"] = await task(db, a, day(-5), status="done")
    w["b_task"] = await task(db, b, day(-2))
    w["call"] = await add(db, LeadCall(lead_id=w["planned"].id, caller_user_id=a.id, call_type="outgoing", outcome="interested", duration_seconds=60, occurred_at=datetime.now(UTC)))
    w["old_call"] = await add(db, LeadCall(lead_id=w["planned"].id, caller_user_id=a.id, call_type="outgoing", outcome="interested", duration_seconds=60, occurred_at=at(-2)))
    w["s1"] = await mk_user(db, role="overseas_student", full_name=f"Dash Student {uniq()}")
    w["s2"] = await mk_user(db, role="overseas_student", full_name=f"Dash Docs {uniq()}")
    w["gone"] = await mk_user(db, role="overseas_student", full_name=f"Dash Archived {uniq()}")
    w["appt"] = await add(
        db, Appointment(division="overseas", lead_id=w["planned"].id, staff_id=a.id, scheduled_at=at(0, 15), appointment_type="career_counselling", mode="online", status="scheduled")
    )
    w["student_appt"] = await add(db, Appointment(division="overseas", student_id=w["s1"].id, staff_id=a.id, scheduled_at=at(0, 10), appointment_type="Counselling", mode="online", status="scheduled"))
    w["cancelled_appt"] = await add(
        db, Appointment(division="overseas", student_id=w["s1"].id, staff_id=a.id, scheduled_at=at(0, 12), appointment_type="Counselling", mode="online", status="cancelled")
    )
    w["tomorrow_appt"] = await add(db, Appointment(division="overseas", student_id=w["s1"].id, staff_id=a.id, scheduled_at=at(1), appointment_type="Counselling", mode="online", status="scheduled"))
    # applications
    app = lambda student, **f: mk_application(db, agent=None, university=uni, student=student, counselor_id=f.pop("counselor_id", a.id), **f)  # noqa: E731
    w["not_ready"] = await app(w["s1"], status="university_selection", application_deadline=day(10))
    w["ready"] = await app(w["s1"], status="university_selection", documents_completed_on=day(-1))
    w["submitted"] = await app(w["s1"], status="university_selection", submitted_on=day(-20), decision_due_on=day(-1))
    w["offer"] = await app(w["s1"], status="offer")
    w["visa"] = await app(w["s1"], status="visa_documentation")
    w["pending_visa"] = await app(w["s1"], status="status_tracking")
    w["approved"] = await app(w["s1"], status="status_tracking", sub_status="visa_approved")
    w["enrolled"] = await app(w["s1"], status="enrolled", enrollment_confirmed_at=datetime.now(UTC))
    w["withdrawn"] = await app(w["s1"], status="withdrawn")
    w["held"] = await app(w["s1"], status="university_selection", outcome="on_hold")
    w["archived_app"] = await app(w["gone"], status="university_selection")
    w["b_app"] = await app(w["s2"], status="university_selection", counselor_id=b.id)
    await add(db, OverseasStudentArchive(student_user_id=w["gone"].id, reason="Moved on", archived_by_user_id=a.id))
    offer = await add(db, ApplicationOffer(application_id=w["offer"].id, offer_type="conditional", issue_date=day(-5), offer_deadline=day(5)))
    w["offer_row"] = offer
    await add(db, ApplicationOffer(application_id=w["withdrawn"].id, offer_type="conditional", issue_date=day(-5), offer_deadline=day(3)))
    w["condition"] = await add(db, ApplicationOfferCondition(offer_id=offer.id, description="Final transcript", owner="student", due_date=day(3), status="open"))
    w["far_condition"] = await add(db, ApplicationOfferCondition(offer_id=offer.id, description="IELTS", owner="student", due_date=day(40), status="open"))
    w["deposit"] = await add(
        db, ApplicationDepositRecord(application_id=w["offer"].id, required=True, amount=500, currency="GBP", payment_status="pending", due_date=day(7), recorded_by_id=a.id, updated_by_id=a.id)
    )
    w["visa_appt"] = await add(db, VisaCase(application_id=w["visa"].id, status="interview_prep", visa_status="appointment_booked", appointment_date=day(4), checklist=[]))
    w["visa_wait"] = await add(db, VisaCase(application_id=w["pending_visa"].id, status="tracking", visa_status="decision_pending", checklist=[]))
    w["visa_ok"] = await add(db, VisaCase(application_id=w["approved"].id, status="decision", visa_status="approved", decision="approved", checklist=[]))
    # students' documents (D2: csc-001 visible students -- s2 is visible to A only through the link below)
    from app.models import OverseasStudentCounselor

    await add(db, OverseasStudentCounselor(student_user_id=w["s2"].id, counselor_user_id=a.id, assigned_by_user_id=a.id))
    w["request"] = await add(db, DocumentRequest(student_user_id=w["s2"].id, document_type="Passport", due_date=day(2), status="open", requested_by_user_id=a.id))
    await mk_doc(db, student=w["s1"], status="pending")
    await mk_doc(db, student=w["gone"], status="pending")
    return w


@pytest.mark.asyncio
async def test_only_the_overseas_counselor_reads_a_dashboard(db_session):
    for role, division in (("counselor", "it"), ("overseas_admin", "overseas"), ("overseas_student", "overseas"), ("telecaller", "overseas")):
        user = await mk_user(db_session, role=role, division=division)
        async with client_for(user.email, division) as c:
            assert (await c.get(URL)).status_code == 403, role


@pytest.mark.asyncio
async def test_a_fresh_counselor_sees_every_section_empty(db_session):
    fresh = await mk_user(db_session, role="counselor")
    async with client_for(fresh.email) as c:
        r = await c.get(URL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["today"] == day(0).isoformat() and body["window_days"] == 14
    assert set(body["sections"]) == {
        "new_leads",
        "appointments_today",
        "calls_today",
        "follow_ups",
        "overdue_tasks",
        "no_next_action",
        "pending_documents",
        "not_ready",
        "awaiting_decision",
        "offers_due",
        "visa",
        "enrolment",
    }
    assert all(s == {"count": 0, "more": False, "items": []} for s in body["sections"].values())


@pytest.mark.asyncio
async def test_every_section_lists_only_the_counselors_own_live_work(db_session, world):
    w = world
    async with client_for(w["a"].email) as c:
        r = await c.get(URL)
    assert r.status_code == 200, r.text
    body = r.json()
    s = body["sections"]
    assert ids(body, "new_leads") == {str(w["new"].id), str(w["pending"].id)}
    assert ids(body, "no_next_action") == {str(w["bare"].id)}  # not-contacted leads show above, closed and linked ones never
    assert ids(body, "follow_ups") == {str(w["fu_today"].id), str(w["fu_late"].id)}
    late = next(i for i in s["follow_ups"]["items"] if i["id"] == str(w["fu_late"].id))
    assert late["overdue"] is True and late["href"] == f"/overseas/counselor/leads/{w['planned'].id}"
    assert [i["id"] for i in s["follow_ups"]["items"]] == [str(w["fu_late"].id), str(w["fu_today"].id)]  # soonest first
    assert ids(body, "overdue_tasks") == {str(w["late_task"].id)}
    assert ids(body, "calls_today") == {str(w["call"].id)}
    assert [i["id"] for i in s["appointments_today"]["items"]] == [str(w["student_appt"].id), str(w["appt"].id)]  # by time
    assert s["appointments_today"]["items"][0]["href"] == f"/overseas/counselor/students/{w['s1'].id}"
    assert ids(body, "pending_documents") == {str(w["s1"].id), str(w["s2"].id)}  # the archived student is left out
    assert ids(body, "not_ready") == {str(w["not_ready"].id)}  # ready, on-hold, archived and B's are not
    assert ids(body, "awaiting_decision") == {str(w["submitted"].id)}
    assert s["awaiting_decision"]["items"][0]["overdue"] is True
    assert ids(body, "offers_due") == {str(w["offer_row"].id), str(w["condition"].id), str(w["deposit"].id)}  # the withdrawn app's offer is not
    assert ids(body, "visa") == {str(w["visa_appt"].id), str(w["visa_wait"].id)}
    assert ids(body, "enrolment") == {str(w["approved"].id), str(w["enrolled"].id)}
    details = {i["id"]: i["detail"] for i in s["enrolment"]["items"]}
    assert details[str(w["approved"].id)].startswith("Confirm enrolment") and details[str(w["enrolled"].id)].startswith("Confirm arrival")
    for key in ("new_leads", "follow_ups", "overdue_tasks", "not_ready", "offers_due", "visa"):
        assert s[key]["count"] == len(s[key]["items"]) and s[key]["more"] is False


@pytest.mark.asyncio
async def test_a_confirmed_arrival_leaves_the_enrolment_section(db_session, world):
    w = world
    w["enrolled"].arrival_date, w["enrolled"].arrival_confirmed_at = day(-1), datetime.now(UTC)
    await db_session.commit()
    async with client_for(w["a"].email) as c:
        body = (await c.get(URL)).json()
    assert ids(body, "enrolment") == {str(w["approved"].id)}


@pytest.mark.asyncio
async def test_a_section_caps_its_items_and_keeps_the_full_count(db_session):
    a = await mk_user(db_session, role="counselor")
    for _ in range(12):
        await task(db_session, a, day(-1))
    async with client_for(a.email) as c:
        section = (await c.get(URL)).json()["sections"]["overdue_tasks"]
    assert section["count"] == 12 and len(section["items"]) == 10 and section["more"] is True

"""itc-030 (DEC-SCOPE-367) -- the IT counselor dashboard, GET /counselor/it/dashboard (spec docs/superpowers/specs/2026-11-03-itc-030-it-
counselor-dashboard-design.md). Nine widgets over the caller's lead book and student book; every figure is the count of the same
statement its list reads (AC1); course, batch, date range, stage and (IT Admin) owner filters apply to every widget by one rule each
(AC2). The test database is shared and never truncated: counselor-scoped tests use fresh counselors, admin tests use the owner filter."""

import datetime
import uuid

import pytest
from sqlalchemy import event

from app.models import Batch, Enquiry, Enrollment, HrReviewTask, ItStudentCounselor, LeadFollowUp, Payment, Program, StudentRiskFlag, TelProduct
from tests.bdm001_helpers import make_user
from tests.tel026_helpers import headers

pytestmark = pytest.mark.asyncio
URL = "/api/v1/counselor/it/dashboard"
UTC = datetime.UTC
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
WIDGETS = {"assigned_leads", "follow_ups", "pipeline", "conversions", "enrolled_students", "outstanding_fees", "at_risk", "pending_hr", "ready_to_convert"}


def _now() -> datetime.datetime:
    return datetime.datetime.now(UTC)


async def _course(db) -> tuple[Program, Batch, TelProduct]:
    tag = uuid.uuid4().hex[:8]
    program = Program(slug=f"i030-{tag}", title=f"I030 Course {tag}", category="Testing", summary="-", duration="3 months", eligibility="-",
                      fees=1000, certification="-", placement_assistance="-", trainer_name="-")  # fmt: skip
    db.add(program)
    await db.flush()
    batch = Batch(program_id=program.id, name=f"I030-{tag}", start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 1), schedule="-", status="active")
    product = TelProduct(product_group="it", name=f"I030 Product {tag}", team="it", program_id=program.id)
    db.add_all([batch, product])
    await db.commit()
    return program, batch, product


async def _lead(db, owner, *, status: str = "assigned", product=None, created_at=None, converted_to=None, merged: bool = False) -> Enquiry:
    row = Enquiry(division="it", name=f"Lead {uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:8]}@example.local", subject="Python", message="-",
                  source="website", status=status, owner_id=owner.id if owner else None, product_id=product.id if product else None)  # fmt: skip
    if created_at:
        row.created_at = created_at
    if converted_to:
        row.converted_user_id, row.converted_at, row.converted_by_user_id = converted_to.id, _now(), owner.id
    db.add(row)
    await db.flush()
    if merged:
        survivor = await _lead(db, owner)
        row.status, row.duplicate_of_id, row.merged_at, row.merged_by_user_id = "duplicate", survivor.id, _now(), owner.id
    await db.commit()
    return row


async def _follow_up(db, lead, due_at, *, status: str = "open") -> LeadFollowUp:
    row = LeadFollowUp(lead_id=lead.id, due_at=due_at, reason="course_details", status=status, created_by_user_id=lead.owner_id)
    if status == "done":
        row.completed_at, row.completed_by_user_id = _now(), lead.owner_id
    db.add(row)
    await db.commit()
    return row


async def _student(db, counselor, batch=None, *, status: str = "active", fee: float | None = None, enrolled_on=None):
    student = await make_user(db, "it_student", "it")
    db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    seat = None
    if batch:
        seat = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"I030-{uuid.uuid4().hex[:10]}", status=status,
                          enrolled_on=enrolled_on or datetime.date.today())  # fmt: skip
        db.add(seat)
        await db.flush()
        if fee:
            db.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=seat.id, amount=fee, status="pending", is_manual=True))
    await db.commit()
    return student, seat


async def _flag(db, seat, *, cleared: bool = False) -> StudentRiskFlag:
    row = StudentRiskFlag(enrollment_id=seat.id, student_id=seat.student_id, batch_id=seat.batch_id, reasons=["attendance"], raised_at=_now(),
                          cleared_at=_now() if cleared else None, clear_reason="recovered" if cleared else None)  # fmt: skip
    db.add(row)
    await db.commit()
    return row


async def _hr_task(db, student, stage: str) -> HrReviewTask:
    row = HrReviewTask(student_user_id=student.id, stage=stage, resume_version=1, closed_at=_now() if stage in ("completed", "withdrawn") else None)
    db.add(row)
    await db.commit()
    return row


async def _get(client, user, **params):
    return await client.get(URL, headers=headers(user), params={k: str(v) for k, v in params.items() if v is not None})


async def _board(client, user, **params) -> dict:
    response = await _get(client, user, **params)
    assert response.status_code == 200, response.text
    return response.json()


def _ids(widget: dict) -> set[str]:
    return {item["id"] for item in widget["items"]}


# --- access -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("trainer", "it"), ("hr_team", "it"), ("it_student", "it"), ("overseas_admin", "overseas")])
async def test_anyone_but_an_it_counselor_or_the_it_admin_is_403(client, db_session, role, division):
    response = await _get(client, await make_user(db_session, role, division))
    assert response.status_code == 403
    assert response.json()["detail"] == "Only an IT counselor or the IT Admin has this dashboard"


async def test_signed_out_is_401(client):
    assert (await client.get(URL)).status_code == 401


async def test_a_counselor_with_nothing_gets_every_widget_empty(client, db_session):
    body = await _board(client, await make_user(db_session, "counselor", "it"))
    assert set(body["widgets"]) == WIDGETS
    for key, widget in body["widgets"].items():
        assert widget["count"] == 0, key
    assert body["widgets"]["outstanding_fees"]["total"] == 0
    assert body["options"]["owners"] == []  # the owner picker is the IT Admin's


async def test_the_response_is_never_cached(client, db_session):
    response = await _get(client, await make_user(db_session, "counselor", "it"))
    assert response.headers["cache-control"] == "private, no-store"


# --- the lead widgets ---------------------------------------------------------------------------------------------------------------


async def test_lead_widgets_cover_only_the_counselors_own_open_unmerged_leads(client, db_session):
    me, other = await make_user(db_session, "counselor", "it"), await make_user(db_session, "counselor", "it")
    assigned = await _lead(db_session, me, status="assigned")
    qualified = await _lead(db_session, me, status="qualified")
    await _lead(db_session, me, status="not_eligible")  # closed
    await _lead(db_session, me, merged=True)  # merged: never counted (the survivor is)
    await _lead(db_session, other, status="assigned")  # someone else's
    body = (await _board(client, me))["widgets"]
    leads = body["assigned_leads"]
    assert {str(assigned.id), str(qualified.id)} <= _ids(leads)
    assert leads["count"] == 3 == len(leads["items"])  # the two plus the merged lead's survivor
    assert body["pipeline"]["count"] == 3
    assert {s["stage"]: s["count"] for s in body["pipeline"]["stages"]}["qualified"] == 1
    assert sum(s["count"] for s in body["pipeline"]["stages"]) == body["pipeline"]["count"]
    assert body["ready_to_convert"]["count"] == 1 and _ids(body["ready_to_convert"]) == {str(qualified.id)}
    assert body["ready_to_convert"]["items"][0]["href"] == f"/it/counselor/leads/{qualified.id}"


async def test_follow_ups_are_open_ones_due_today_or_overdue(client, db_session):
    me = await make_user(db_session, "counselor", "it")
    lead = await _lead(db_session, me)
    today_ist = _now().astimezone(IST).date()
    tomorrow = datetime.datetime.combine(today_ist + datetime.timedelta(days=1), datetime.time(), IST)
    overdue = await _follow_up(db_session, lead, _now() - datetime.timedelta(days=2))
    later_today = await _follow_up(db_session, lead, tomorrow - datetime.timedelta(minutes=1))
    await _follow_up(db_session, lead, tomorrow)  # 00:00 IST tomorrow: not today
    await _follow_up(db_session, lead, _now() - datetime.timedelta(hours=1), status="done")
    widget = (await _board(client, me))["widgets"]["follow_ups"]
    assert widget["count"] == 2 and widget["overdue"] == 1
    assert [i["id"] for i in widget["items"]] == [str(overdue.id), str(later_today.id)]  # soonest first
    assert [i["overdue"] for i in widget["items"]] == [True, False]
    assert widget["items"][0]["href"] == f"/it/counselor/leads/{lead.id}"


async def test_conversions_count_the_converted_leads(client, db_session):
    me = await make_user(db_session, "counselor", "it")
    student, _ = await _student(db_session, me)
    converted = await _lead(db_session, me, status="application_enrollment", converted_to=student)
    await _lead(db_session, me, status="qualified")
    widget = (await _board(client, me))["widgets"]["conversions"]
    assert widget["count"] == 1 and _ids(widget) == {str(converted.id)}


async def test_a_long_list_shows_ten_and_the_full_count(client, db_session):
    me = await make_user(db_session, "counselor", "it")
    for _ in range(12):
        await _lead(db_session, me)
    widget = (await _board(client, me))["widgets"]["assigned_leads"]
    assert widget["count"] == 12 and len(widget["items"]) == 10 and widget["more"] is True


# --- the student widgets -------------------------------------------------------------------------------------------------------------


async def test_student_widgets_cover_the_linked_students(client, db_session):
    me, other = await make_user(db_session, "counselor", "it"), await make_user(db_session, "counselor", "it")
    _, batch, _ = await _course(db_session)
    owing, owing_seat = await _student(db_session, me, batch, fee=5000)
    paid, _ = await _student(db_session, me, batch)
    await _student(db_session, me, batch, status="withdrawn", fee=900)  # not active: neither enrolled nor outstanding
    await _student(db_session, other, batch, fee=700)  # someone else's
    await _flag(db_session, owing_seat)
    await _flag(db_session, (await _student(db_session, me, batch))[1], cleared=True)
    await _hr_task(db_session, paid, "changes_requested")
    await _hr_task(db_session, owing, "under_review")
    body = (await _board(client, me))["widgets"]
    assert body["enrolled_students"]["count"] == 3  # owing, paid, the cleared-flag student
    assert body["outstanding_fees"]["count"] == 1 and body["outstanding_fees"]["total"] == 5000
    assert body["outstanding_fees"]["items"][0]["href"] == f"/it/counselor/students/{owing.id}"
    assert body["at_risk"]["count"] == 1 and body["at_risk"]["items"][0]["href"] == f"/it/counselor/students/{owing.id}"
    assert body["pending_hr"]["count"] == 1 and body["pending_hr"]["items"][0]["href"] == f"/it/counselor/students/{paid.id}"


async def test_a_student_with_two_active_enrolments_counts_once(client, db_session):
    me = await make_user(db_session, "counselor", "it")
    (_, batch, _), (_, batch2, _) = await _course(db_session), await _course(db_session)
    student, _ = await _student(db_session, me, batch)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch2.id, enrollment_code=f"I030-{uuid.uuid4().hex[:10]}", status="active"))
    await db_session.commit()
    widget = (await _board(client, me))["widgets"]["enrolled_students"]
    assert widget["count"] == 1 == len(widget["items"])


# --- filters (AC2) -------------------------------------------------------------------------------------------------------------------


async def _two_courses(db, me):
    (p1, b1, prod1), (p2, b2, prod2) = await _course(db), await _course(db)
    world = {"p1": p1, "b1": b1, "p2": p2, "b2": b2}
    world["lead1"], world["lead2"] = await _lead(db, me, product=prod1), await _lead(db, me, product=prod2)
    world["s1"], world["seat1"] = await _student(db, me, b1, fee=100)
    world["s2"], world["seat2"] = await _student(db, me, b2, fee=200)
    for seat in (world["seat1"], world["seat2"]):
        await _flag(db, seat)
    await _hr_task(db, world["s1"], "changes_requested")
    await _hr_task(db, world["s2"], "changes_requested")
    return world


@pytest.mark.parametrize("by", ["program", "batch"])
async def test_course_and_batch_narrow_every_widget(client, db_session, by):
    me = await make_user(db_session, "counselor", "it")
    w = await _two_courses(db_session, me)
    body = await _board(client, me, **{by: w["p1"].id if by == "program" else w["b1"].id})
    widgets = body["widgets"]
    assert _ids(widgets["assigned_leads"]) == {str(w["lead1"].id)}  # a batch narrows leads to its course
    assert widgets["pipeline"]["count"] == 1
    for key in ("enrolled_students", "outstanding_fees", "at_risk", "pending_hr"):
        assert widgets[key]["count"] == 1, key
    assert widgets["outstanding_fees"]["total"] == 100
    assert body["filters"][by] == str(w["p1"].id if by == "program" else w["b1"].id)


async def test_the_date_range_narrows_by_each_widgets_own_date(client, db_session):
    me = await make_user(db_session, "counselor", "it")
    _, batch, _ = await _course(db_session)
    old = await _lead(db_session, me, created_at=datetime.datetime(2026, 1, 10, 12, tzinfo=UTC))
    new = await _lead(db_session, me, created_at=datetime.datetime(2026, 3, 10, 12, tzinfo=UTC))
    await _student(db_session, me, batch, enrolled_on=datetime.date(2026, 1, 5))
    recent, _ = await _student(db_session, me, batch, enrolled_on=datetime.date(2026, 3, 5))
    widgets = (await _board(client, me, **{"from": "2026-03-01", "to": "2026-03-31"}))["widgets"]
    assert _ids(widgets["assigned_leads"]) == {str(new.id)} and str(old.id) not in _ids(widgets["assigned_leads"])
    assert _ids(widgets["enrolled_students"]) == {str(recent.id)}


async def test_the_stage_filter_narrows_the_lead_widgets_only(client, db_session):
    me = await make_user(db_session, "counselor", "it")
    _, batch, _ = await _course(db_session)
    qualified = await _lead(db_session, me, status="qualified")
    await _lead(db_session, me, status="assigned")
    await _student(db_session, me, batch)
    widgets = (await _board(client, me, stage="qualified"))["widgets"]
    assert _ids(widgets["assigned_leads"]) == {str(qualified.id)}
    assert [s["stage"] for s in widgets["pipeline"]["stages"]] == ["qualified"]
    assert widgets["enrolled_students"]["count"] == 1  # student widgets have no lead stage


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"program": "nope"}, "Unknown filter value"),
        ({"program": uuid.uuid4()}, "Unknown filter value"),
        ({"batch": uuid.uuid4()}, "Unknown filter value"),
        ({"stage": "bogus"}, "Unknown filter value"),
        ({"from": "2026-13-01"}, "Unknown filter value"),
        ({"from": "2026-03-02", "to": "2026-03-01"}, "The start date must be on or before the end date"),
        ({"owner": uuid.uuid4()}, "The owner filter is for the IT Admin"),
    ],
)
async def test_a_bad_filter_is_422(client, db_session, params, message):
    response = await _get(client, await make_user(db_session, "counselor", "it"), **params)
    assert response.status_code == 422 and response.json()["detail"] == message


async def test_a_batch_outside_the_chosen_course_is_422(client, db_session):
    (p1, _, _), (_, b2, _) = await _course(db_session), await _course(db_session)
    response = await _get(client, await make_user(db_session, "counselor", "it"), program=p1.id, batch=b2.id)
    assert response.status_code == 422 and response.json()["detail"] == "The batch is not in that course"


# --- the IT Admin ---------------------------------------------------------------------------------------------------------------------


async def test_the_it_admin_sees_every_counselor_and_narrows_by_owner(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    me, other = await make_user(db_session, "counselor", "it"), await make_user(db_session, "counselor", "it")
    mine, theirs = await _lead(db_session, me), await _lead(db_session, other)
    _, batch, _ = await _course(db_session)
    student, _ = await _student(db_session, me, batch)
    everyone = await _board(client, admin)
    assert everyone["widgets"]["assigned_leads"]["count"] >= 2
    assert str(me.id) in {o["value"] for o in everyone["options"]["owners"]}
    narrowed = await _board(client, admin, owner=me.id)
    assert _ids(narrowed["widgets"]["assigned_leads"]) == {str(mine.id)} and str(theirs.id) not in _ids(narrowed["widgets"]["assigned_leads"])
    assert narrowed["widgets"]["assigned_leads"]["items"][0]["href"] == "/it/admin/leads"
    assert narrowed["widgets"]["enrolled_students"]["items"][0]["href"] == f"/it/admin/students/{student.id}"
    assert narrowed["filters"]["owner"] == str(me.id)


@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("trainer", "it")])
async def test_an_owner_who_is_not_an_it_counselor_is_422(client, db_session, role, division):
    admin = await make_user(db_session, "it_admin", "it")
    response = await _get(client, admin, owner=(await make_user(db_session, role, division)).id)
    assert response.status_code == 422 and response.json()["detail"] == "Choose an IT counselor"


async def test_the_admin_portal_section_is_header_only(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    response = await client.get("/api/v1/portal/it/admin/counselor-dashboard", headers=headers(admin))
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Counselor Dashboard" and response.json()["rows"] == []


# --- query count ----------------------------------------------------------------------------------------------------------------------


async def _count(client, db, user) -> int:
    queries = []
    engine = db.bind.sync_engine
    listener = lambda *_: queries.append(1)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        await _board(client, user)
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(queries)


async def test_the_query_count_is_fixed_whatever_the_book(client, db_session):
    me = await make_user(db_session, "counselor", "it")
    await _two_courses(db_session, me)
    one = await _count(client, db_session, me)
    await _two_courses(db_session, me)
    assert await _count(client, db_session, me) == one
    assert one <= 30

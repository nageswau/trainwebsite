"""itc-032 (DEC-SCOPE-369) -- the management IT reports: lead funnel by course and source, conversions by course, revenue / collections /
outstanding, attendance and completion, placement outcomes and team activity, each with the same five filters (course, batch, owner,
date range, status), written definitions, and figures that tie out to their drill-down rows (AC1, AC2). Spec:
docs/superpowers/specs/2026-11-03-itc-032-management-it-reports-design.md."""

import csv
import datetime
import io
import uuid

import pytest
from sqlalchemy import select

from app.models import Attendance, AuditLog, Batch, Enquiry, Enrollment, ItStudentCounselor, LeadCall, LeadFollowUp, Payment, Program, TelProduct
from tests.bdm001_helpers import make_user
from tests.test_itc_013_fee_account import API, enrolled
from tests.test_itc_031_lifecycle import application
from tests.upc001_helpers import login

BASE = f"{API}/management/it/reports"
UTC = datetime.UTC
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
OCT = {"date_from": "2026-10-01", "date_to": "2026-10-31"}
REPORTS = ("funnel", "conversions", "revenue", "training", "placement", "activity")
OPERATIONAL = ("funnel", "conversions", "training", "placement", "activity")


def url(report: str) -> str:
    return f"{BASE}/{report}"


def at(day: int, hour: int = 10) -> datetime.datetime:
    return datetime.datetime(2026, 10, day, hour, 0, tzinfo=IST)


async def as_role(client, db, role="partner", division="global"):
    user = await make_user(db, role, division)
    await login(client, user)
    return user


async def course(db) -> tuple[Program, TelProduct]:
    tag = uuid.uuid4().hex[:8]
    program = Program(slug=f"i032-{tag}", title=f"I032 Course {tag}", category="Testing", summary="-", duration="3 months", eligibility="-",
                      fees=0, certification="-", placement_assistance="-", trainer_name="-")  # fmt: skip
    db.add(program)
    await db.flush()
    product = TelProduct(product_group="it", name=f"I032 {tag}", program_id=program.id)
    db.add(product)
    await db.commit()
    return program, product


async def lead(db, product, *, owner=None, source="website", status="new", created=None, converted=None, converted_by=None, merged_into=None) -> Enquiry:
    row = Enquiry(division="it", name="Hidden Name", email=f"{uuid.uuid4().hex[:8]}@example.com", subject="IT", message="-", source=source, status=status,
                  owner_id=owner.id if owner else None, product_id=product.id if product else None)  # fmt: skip
    if converted:  # ck_enquiries_conversion: the student, the time and the converter are recorded together
        converted_by = converted_by or owner or await make_user(db, "counselor", "it")
        row.converted_user_id, row.converted_at, row.converted_by_user_id = (await make_user(db, "it_student", "it")).id, converted, converted_by.id
    if merged_into is not None:  # ccrm-006 / itc-007: a merged lead is closed as a duplicate of the surviving one
        row.status, row.duplicate_of_id = "duplicate", merged_into.id
    db.add(row)
    await db.flush()
    row.created_at = created or at(10)
    if merged_into is not None:
        row.merged_at, row.merged_by_user_id = at(11), owner.id
    await db.commit()
    return row


async def seat(db, program=None, *, fee=30000, on=datetime.date(2026, 10, 5), status="active", counselor=None, starts=None):
    """An IT enrolment in a batch of `program` (a fresh course when None), enrolled on `on`, optionally linked to an IT counselor."""
    student, enrollment = await enrolled(db, fee)
    batch = await db.get(Batch, enrollment.batch_id)
    if program is not None:
        batch.program_id = program.id
    enrollment.enrolled_on, enrollment.status = on, status
    if starts is not None:  # a batch not started yet: the lifecycle stage reads the fee track
        batch.start_date, batch.end_date = starts, starts + datetime.timedelta(days=90)
    if counselor is not None:
        db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()
    return student, enrollment, batch


async def settle(db, enrollment, amount, *, due=None):
    """A confirmed payment of `amount` taken off the enrolment's pending bill (as recording a payment does); `due` dates what is left."""
    bill = (await db.scalars(select(Payment).where(Payment.reference_id == enrollment.id, Payment.status == "pending"))).one()
    bill.amount, bill.due_date = float(bill.amount) - amount, due
    db.add(Payment(user_id=enrollment.student_id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=amount, status="paid",
                   paid_at=at(6), provider="manual", is_manual=True, payment_mode="cash"))  # fmt: skip
    await db.commit()


# --- who may read (R4) -------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("partner", "global"), ("super_admin", "global"), ("it_admin", "it")])
async def test_management_and_the_it_admin_open_every_report(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    listed = (await client.get(BASE)).json()["reports"]
    assert [r["key"] for r in listed] == list(REPORTS)
    for report in REPORTS:
        response = await client.get(url(report))
        assert response.status_code == 200, (report, response.text)
        assert {"filters", "options", "definitions", "totals", "groups", "items", "total", "limit", "offset"} <= set(response.json())


@pytest.mark.asyncio
async def test_the_accountant_reads_revenue_only(client, db_session):
    await as_role(client, db_session, "accountant", "global")
    assert [r["key"] for r in (await client.get(BASE)).json()["reports"]] == ["revenue"]
    assert (await client.get(url("revenue"))).status_code == 200
    for report in OPERATIONAL:
        response = await client.get(url(report))
        assert response.status_code == 403 and response.json()["detail"] == "You do not have access to this IT report"


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("counselor", "it"), ("it_student", "it"), ("overseas_admin", "overseas"), ("trainer", "it"), ("telecaller", "it")])
async def test_anyone_else_is_refused_everywhere(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(BASE)).status_code == 403
    for report in REPORTS:
        assert (await client.get(url(report))).status_code == 403, report
        assert (await client.get(f"{url(report)}/export")).status_code == 403, report


@pytest.mark.asyncio
async def test_signed_out_is_401_and_an_unknown_report_is_404(client, db_session):
    assert (await client.get(url("funnel"))).status_code == 401
    await as_role(client, db_session)
    assert (await client.get(url("salaries"))).status_code == 404


# --- the filters (R2, AC2) ---------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filters_are_validated_with_plain_messages(client, db_session):
    program, _ = await course(db_session)
    _, _, other_batch = await seat(db_session)
    await as_role(client, db_session)
    cases = [
        ("funnel", {"program_id": str(uuid.uuid4())}, "Choose a course from the list"),
        ("revenue", {"batch_id": str(uuid.uuid4())}, "Choose a batch from the list"),
        ("training", {"program_id": str(program.id), "batch_id": str(other_batch.id)}, "That batch is not in the chosen course"),
        ("activity", {"date_from": "2026-10-20", "date_to": "2026-10-01"}, "The start date must be on or before the end date"),
        ("placement", {"date_from": "2025-01-01", "date_to": "2026-10-01"}, "Choose a date range of at most 366 days"),
        ("conversions", {"owner_id": str(uuid.uuid4())}, "Choose an owner from the list"),
        ("funnel", {"status": "paid"}, "Choose a status from the list"),  # a lifecycle stage on a lead report
        ("revenue", {"status": "qualified"}, "Choose a status from the list"),  # a lead stage on an enrolment report
    ]
    for report, params, message in cases:
        response = await client.get(url(report), params=params)
        assert response.status_code == 422 and response.json()["detail"] == message, (report, params, response.text)
    assert (await client.get(url("funnel"), params={"limit": 201})).status_code == 422


@pytest.mark.asyncio
async def test_each_family_offers_its_own_statuses_and_the_owner_list(client, db_session):
    program, product = await course(db_session)
    owner = await make_user(db_session, "telecaller", "it")
    await lead(db_session, product, owner=owner)
    await as_role(client, db_session)
    funnel = (await client.get(url("funnel"), params={**OCT, "program_id": str(program.id)})).json()
    revenue = (await client.get(url("revenue"), params={**OCT, "program_id": str(program.id)})).json()
    assert "qualified" in [s["value"] for s in funnel["options"]["statuses"]] and "paid" not in [s["value"] for s in funnel["options"]["statuses"]]
    assert "paid" in [s["value"] for s in revenue["options"]["statuses"]] and "qualified" not in [s["value"] for s in revenue["options"]["statuses"]]
    assert str(owner.id) in [o["id"] for o in funnel["options"]["owners"]]
    assert all(d["definition"] for d in funnel["definitions"])


# --- funnel and conversions (R1, R3) -----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_funnel_groups_the_cohort_by_course_and_source_and_ties_out(client, db_session):
    program, product = await course(db_session)
    owner = await make_user(db_session, "counselor", "it")
    survivor = await lead(db_session, product, owner=owner, source="instagram", status="qualified")
    await lead(db_session, product, owner=owner, source="instagram", status="converted", converted=at(12))
    await lead(db_session, product, owner=owner, source="website", status="lost")
    await lead(db_session, product, owner=owner, source="website", status="nurture")
    await lead(db_session, product, owner=owner, created=datetime.datetime(2026, 9, 30, 20, 0, tzinfo=UTC))  # 1 Oct 01:30 IST: in
    await lead(db_session, product, owner=owner, created=datetime.datetime(2026, 9, 30, 18, 0, tzinfo=UTC))  # 30 Sep 23:30 IST: out
    await lead(db_session, product, owner=owner, merged_into=survivor)  # merged: never counted
    await as_role(client, db_session)
    body = (await client.get(url("funnel"), params={**OCT, "program_id": str(program.id)})).json()
    assert body["totals"] | {} == {**body["totals"], "leads": 5, "open": 2, "nurture": 1, "converted": 1, "closed": 1}
    groups = {(g["course"], g["source"]): g["leads"] for g in body["groups"]}
    assert groups == {(program.title, "Instagram"): 2, (program.title, "Website"): 3}
    assert body["total"] == sum(groups.values()) == sum(s["count"] for s in body["totals"]["by_stage"]) == 5
    assert all("name" not in item and "email" not in item for item in body["items"])  # no lead names or contact details


@pytest.mark.asyncio
async def test_conversions_by_course_count_the_converted_leads_of_the_cohort(client, db_session):
    program, product = await course(db_session)
    await lead(db_session, product, status="converted", converted=at(15))
    await lead(db_session, product, status="converted", converted=at(20))
    await lead(db_session, product, status="contacted")
    await lead(db_session, product, status="new")
    await as_role(client, db_session)
    body = (await client.get(url("conversions"), params={**OCT, "program_id": str(program.id)})).json()
    assert body["totals"] == {"leads": 4, "converted": 2, "conversion_pct": 50.0}
    assert [(g["course"], g["leads"], g["converted"], g["conversion_pct"]) for g in body["groups"]] == [(program.title, 4, 2, 50.0)]
    assert body["total"] == 2 and {i["converted_on"] for i in body["items"]} == {"2026-10-15", "2026-10-20"}


@pytest.mark.asyncio
async def test_lead_reports_take_every_filter(client, db_session):
    """AC2: course, batch (its course), owner, date range and status each narrow the funnel and the conversions."""
    program, product = await course(db_session)
    _, other_product = await course(db_session)
    _, _, batch = await seat(db_session, program)
    mine, theirs = await make_user(db_session, "counselor", "it"), await make_user(db_session, "counselor", "it")
    await lead(db_session, product, owner=mine, status="converted", converted=at(12), created=at(3))
    await lead(db_session, product, owner=theirs, status="qualified", created=at(25))
    await lead(db_session, other_product, owner=mine, status="converted", converted=at(12))
    await as_role(client, db_session)
    scope = {**OCT, "program_id": str(program.id)}
    for report in ("funnel", "conversions"):
        get = lambda r=report, **p: client.get(url(r), params={**scope, **p})  # noqa: E731
        base = (await get()).json()["totals"]["leads"]
        assert base == 2
        assert (await client.get(url(report), params={**OCT, "batch_id": str(batch.id)})).json()["totals"]["leads"] == 2
        assert (await get(owner_id=str(mine.id))).json()["totals"]["leads"] == 1
        assert (await get(date_from="2026-10-20")).json()["totals"]["leads"] == 1
        assert (await get(status="qualified")).json()["totals"]["leads"] == 1


# --- team activity -----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_team_activity_counts_calls_follow_ups_and_conversions_per_staff_member(client, db_session):
    program, product = await course(db_session)
    caller, counselor = await make_user(db_session, "telecaller", "it"), await make_user(db_session, "counselor", "it")
    row = await lead(db_session, product, owner=counselor, status="converted", converted=at(14), converted_by=counselor, created=at(2))
    other = await lead(db_session, product, owner=caller, status="contacted", created=at(2))
    calls = ((row, "interested", at(4)), (row, "busy", at(5)), (other, "interested", at(6)), (other, "interested", datetime.datetime(2026, 11, 1, 10, tzinfo=IST)))
    for lead_row, outcome, when in calls:  # the last one is after the range
        db_session.add(LeadCall(lead_id=lead_row.id, caller_user_id=caller.id, occurred_at=when, duration_seconds=60, call_type="outgoing", outcome=outcome))
    db_session.add(LeadFollowUp(lead_id=row.id, due_at=at(8), reason="course_details", status="done", created_by_user_id=counselor.id, completed_at=at(8),
                                completed_by_user_id=counselor.id))  # fmt: skip
    await db_session.commit()
    await as_role(client, db_session)
    body = (await client.get(url("activity"), params={**OCT, "program_id": str(program.id)})).json()
    staff = {g["owner_id"]: g for g in body["groups"]}
    assert (staff[str(caller.id)]["calls"], staff[str(caller.id)]["connected_calls"]) == (3, 2)
    assert (staff[str(counselor.id)]["follow_ups"], staff[str(counselor.id)]["conversions"]) == (1, 1)
    assert body["totals"] == {"events": 5, "calls": 3, "connected_calls": 2, "follow_ups": 1, "conversions": 1}
    assert body["total"] == 5
    assert (await client.get(url("activity"), params={**OCT, "program_id": str(program.id), "owner_id": str(counselor.id)})).json()["total"] == 2
    assert (await client.get(url("activity"), params={**OCT, "program_id": str(program.id), "status": "contacted"})).json()["total"] == 1


# --- revenue, training, placement (enrolment cohort) -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revenue_bills_collects_and_owes_and_ties_out_to_its_rows(client, db_session):
    program, _ = await course(db_session)
    _, first, _ = await seat(db_session, program, fee=30000)
    _, second, _ = await seat(db_session, program, fee=20000)
    _, dropped, _ = await seat(db_session, program, fee=10000, status="dropped")
    await seat(db_session, program, fee=50000, on=datetime.date(2026, 9, 30))  # enrolled before the range
    await settle(db_session, first, 10000, due=datetime.date(2026, 10, 10))  # what is left fell due in the past: overdue
    await settle(db_session, second, 20000)
    await as_role(client, db_session)
    body = (await client.get(url("revenue"), params={**OCT, "program_id": str(program.id)})).json()
    assert body["totals"] == {"enrolments": 3, "billed": 60000.0, "collected": 30000.0, "outstanding": 20000.0, "overdue": 20000.0}
    assert body["total"] == 3
    for key in ("billed", "collected", "outstanding", "overdue"):
        assert round(sum(i[key] for i in body["items"]), 2) == body["totals"][key] == sum(g[key] for g in body["groups"])
    assert {i["enrollment_code"]: i["outstanding"] for i in body["items"]}[dropped.enrollment_code] == 0  # not active: not outstanding
    assert all("student_name" not in i for i in body["items"])


@pytest.mark.asyncio
async def test_a_range_across_the_financial_year_end_counts_whole(client, db_session):
    """Backlog E: 15 Mar to 15 Apr spans two financial years; a full financial year (365 days) is accepted too."""
    program, _ = await course(db_session)
    await seat(db_session, program, on=datetime.date(2026, 3, 20))
    await seat(db_session, program, on=datetime.date(2026, 4, 2))
    await as_role(client, db_session)
    across = (await client.get(url("revenue"), params={"program_id": str(program.id), "date_from": "2026-03-15", "date_to": "2026-04-15"})).json()
    assert across["totals"]["enrolments"] == 2 and across["totals"]["billed"] == 60000.0
    year = await client.get(url("revenue"), params={"program_id": str(program.id), "date_from": "2025-04-01", "date_to": "2026-03-31"})
    assert year.status_code == 200 and year.json()["totals"]["enrolments"] == 1


@pytest.mark.asyncio
async def test_training_attendance_and_completion_tie_out(client, db_session):
    program, _ = await course(db_session)
    student, first, batch = await seat(db_session, program)
    other, second, other_batch = await seat(db_session, program, status="completed")
    for day, status in ((1, "present"), (2, "late"), (3, "absent"), (4, "present")):
        db_session.add(Attendance(student_id=student.id, batch_id=batch.id, session_date=datetime.date(2026, 10, day), status=status))
    db_session.add(Attendance(student_id=other.id, batch_id=other_batch.id, session_date=datetime.date(2026, 10, 1), status="present"))
    await db_session.commit()
    await as_role(client, db_session)
    body = (await client.get(url("training"), params={**OCT, "program_id": str(program.id)})).json()
    assert body["totals"] == {"enrolments": 2, "attended": 4, "counted": 5, "attendance_pct": 80.0, "completed": 1, "completion_pct": 50.0}
    rows = {i["enrollment_code"]: i for i in body["items"]}
    assert rows[first.enrollment_code]["attendance_pct"] == 75.0 and rows[second.enrollment_code]["completed"] is True


@pytest.mark.asyncio
async def test_placement_outcomes_follow_the_lifecycle(client, db_session):
    program, _ = await course(db_session)
    placed_student, _, _ = await seat(db_session, program)
    _, not_placed, _ = await seat(db_session, program)
    await seat(db_session, program)
    await application(db_session, placed_student, "joined")
    row = await db_session.get(Enrollment, not_placed.id)
    row.lifecycle_override, row.lifecycle_override_reason = "not_placed", "Chose higher studies"
    await db_session.commit()
    await as_role(client, db_session)
    body = (await client.get(url("placement"), params={**OCT, "program_id": str(program.id)})).json()
    assert body["totals"] | {} == {**body["totals"], "enrolments": 3, "placed": 1, "not_placed": 1, "not_started": 1}
    assert sum(body["groups"][0][k] for k in ("placed", "interview", "hr_screening", "resume_submitted", "not_placed", "not_started")) == 3
    placed_only = (await client.get(url("placement"), params={**OCT, "program_id": str(program.id), "status": "placed"})).json()
    assert placed_only["total"] == 1 and placed_only["items"][0]["outcome"] == "placed"


@pytest.mark.asyncio
async def test_enrolment_reports_take_every_filter(client, db_session):
    """AC2: course, batch, owner (the student's IT counselor), date range and status (the lifecycle stage) narrow each enrolment report."""
    program, _ = await course(db_session)
    counselor = await make_user(db_session, "counselor", "it")
    later = datetime.date(2027, 1, 4)
    _, first, batch = await seat(db_session, program, counselor=counselor, on=datetime.date(2026, 10, 3), starts=later)
    _, second, _ = await seat(db_session, program, on=datetime.date(2026, 10, 25), starts=later)
    await settle(db_session, second, 30000)
    await as_role(client, db_session)
    scope = {**OCT, "program_id": str(program.id)}
    for report in ("revenue", "training", "placement"):
        get = lambda r=report, **p: client.get(url(r), params={**scope, **p})  # noqa: E731
        assert (await get()).json()["total"] == 2, report
        assert (await client.get(url(report), params={**OCT, "batch_id": str(batch.id)})).json()["total"] == 1, report
        assert (await get(owner_id=str(counselor.id))).json()["total"] == 1, report
        assert (await get(date_from="2026-10-20")).json()["total"] == 1, report
        paid = (await get(status="paid")).json()
        assert paid["total"] == 1 and paid["items"][0]["enrollment_code"] == second.enrollment_code, report
    assert first.enrollment_code  # the unpaid one is the other row


# --- export (R5) -------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_export_is_every_row_injection_safe_and_audited(client, db_session):
    program, product = await course(db_session)
    owner = await make_user(db_session, "counselor", "it", name="=HYPERLINK(evil)")
    for _ in range(3):
        await lead(db_session, product, owner=owner)
    user = await as_role(client, db_session)
    params = {**OCT, "program_id": str(program.id), "limit": 1}
    response = await client.get(f"{url('funnel')}/export", params=params)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].startswith('attachment; filename="it-funnel-')
    rows = list(csv.reader(io.StringIO(response.text)))
    assert len(rows) == 4  # the header + every row, not just the page
    assert all(not cell.startswith("=") for row in rows[1:] for cell in row)
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "management.it_reports.export"))).all()
    assert len(audit) == 1 and audit[0].metadata_json["rows"] == 3 and audit[0].metadata_json["report"] == "funnel"

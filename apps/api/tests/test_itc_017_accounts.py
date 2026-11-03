"""itc-017 (DEC-SCOPE-368) -- the IT accounts workspace: collections by IST day / month / course, outstanding per enrolment and per
course, overdue installments, the receipts register and the refunds & adjustments list, each filtered by course, batch, date range and
status, paginated and exported as injection-safe CSV. Read by a `payments.view` holder in IT (the IT Admin, the accountant -- Q-17,
default grants seeded by migration 0248); anyone else 403."""

import csv
import datetime
import io
import uuid

import pytest
from sqlalchemy import select

from app.core import rbac
from app.models import AuditLog, Batch, Enrollment, FeeReminderLog, Payment, RolePermission
from tests.bdm001_helpers import make_user
from tests.test_itc_013_fee_account import API, as_admin, enrolled, record_url
from tests.upc001_helpers import login

REPORTS = f"{API}/it/accounts/reports"
UTC = datetime.UTC


def url(report: str) -> str:
    return f"{REPORTS}/{report}"


async def course_of(db, enrollment) -> Batch:
    return await db.get(Batch, enrollment.batch_id)


async def paid(db, enrollment, amount: float, at: datetime.datetime, *, mode: str = "cash", status: str = "paid", division: str = "it") -> Payment:
    row = Payment(user_id=enrollment.student_id, division=division, reference_type="enrollment_fee", reference_id=enrollment.id, amount=amount, status=status,
                  paid_at=at, provider="manual", is_manual=True, payment_mode=mode)  # fmt: skip
    db.add(row)
    await db.commit()
    return row


async def second_enrolment(db, batch: Batch, fee: float, *, status: str = "active") -> Enrollment:
    student = await make_user(db, "it_student", "it")
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"I017-{uuid.uuid4().hex[:8]}", status=status)
    db.add(enrollment)
    await db.flush()
    db.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=fee, status="pending", is_manual=True))
    await db.commit()
    return enrollment


# --- who may open it (F1-F3) ----------------------------------------------------------------------------------------------------------


def test_the_accountant_holds_the_it_payment_grants_by_default():
    assert set(rbac.DEFAULT_GRANTS["accountant"]) == {"payments.view", "payments.add", "payments.refund"}


@pytest.mark.asyncio
async def test_the_migration_seeded_the_accountant_grants(db_session):
    rows = (await db_session.scalars(select(RolePermission).where(RolePermission.role == "accountant"))).all()
    assert {f"{r.resource}.{r.action}" for r in rows} == {"payments.view", "payments.add", "payments.refund"}


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("counselor", "it"), ("it_student", "it"), ("overseas_admin", "overseas"), ("trainer", "it")])
async def test_anyone_without_it_payments_view_gets_403(client, db_session, role, division):
    """The backlog's − case: a counselor opens the accounts workspace and gets 403 (so does an Overseas admin, out of IT)."""
    await login(client, await make_user(db_session, role, division))
    for report in ("collections", "outstanding", "overdue", "receipts", "adjustments"):
        response = await client.get(url(report))
        assert response.status_code == 403, (report, response.text)
        assert response.json()["detail"] == "You do not have access to IT accounts"
    assert (await client.get(f"{url('collections')}/export")).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("it_admin", "it"), ("accountant", "global")])
async def test_the_it_admin_and_the_accountant_open_every_report(client, db_session, role, division):
    await login(client, await make_user(db_session, role, division))
    for report in ("collections", "outstanding", "overdue", "receipts", "adjustments"):
        response = await client.get(url(report))
        assert response.status_code == 200, (report, response.text)
        body = response.json()
        assert {"items", "total", "limit", "offset", "totals", "courses", "batches"} <= set(body)


@pytest.mark.asyncio
async def test_an_unknown_report_is_404(client, db_session):
    await as_admin(client, db_session)
    assert (await client.get(url("salaries"))).status_code == 404


# --- filters (AC3) ------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filters_are_validated_with_plain_messages(client, db_session):
    _, enrollment = await enrolled(db_session)
    _, other = await enrolled(db_session)
    batch, other_batch = await course_of(db_session, enrollment), await course_of(db_session, other)
    await as_admin(client, db_session)
    cases = [
        ({"program_id": str(uuid.uuid4())}, "Choose a course from the list"),
        ({"batch_id": str(uuid.uuid4())}, "Choose a batch from the list"),
        ({"program_id": str(batch.program_id), "batch_id": str(other_batch.id)}, "That batch is not in the chosen course"),
        ({"date_from": "2026-10-20", "date_to": "2026-10-01"}, "The start date must be on or before the end date"),
        ({"date_from": "2025-01-01", "date_to": "2026-10-01"}, "Choose a date range of at most 366 days"),
    ]
    for params, message in cases:
        response = await client.get(url("collections"), params=params)
        assert response.status_code == 422 and response.json()["detail"] == message, (params, response.text)
    assert (await client.get(url("collections"), params={"group": "week"})).status_code == 422
    assert (await client.get(url("collections"), params={"mode": "bitcoin"})).status_code == 422
    assert (await client.get(url("adjustments"), params={"kind": "gift"})).status_code == 422
    assert (await client.get(url("outstanding"), params={"state": "fully_paid"})).status_code == 422
    assert (await client.get(url("receipts"), params={"limit": 201})).status_code == 422


# --- collections (AC1) ----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collections_by_day_are_the_confirmed_payments_of_each_ist_day(client, db_session):
    """AC1 and the E case: confirmed at 19:00 UTC on the 14th is 00:30 IST on the 15th, so it is the 15th's collection."""
    _, enrollment = await enrolled(db_session, 90000)
    program = (await course_of(db_session, enrollment)).program_id
    await paid(db_session, enrollment, 1000, datetime.datetime(2026, 10, 14, 19, 0, tzinfo=UTC))
    await paid(db_session, enrollment, 2000, datetime.datetime(2026, 10, 15, 5, 0, tzinfo=UTC), mode="upi")
    await paid(db_session, enrollment, 4000, datetime.datetime(2026, 10, 14, 10, 0, tzinfo=UTC))
    await paid(db_session, enrollment, 8000, datetime.datetime(2026, 10, 14, 11, 0, tzinfo=UTC), status="reversed")  # corrected: not a collection
    await paid(db_session, enrollment, 16000, datetime.datetime(2026, 10, 14, 12, 0, tzinfo=UTC), status="failed")
    await as_admin(client, db_session)
    params = {"program_id": str(program), "date_from": "2026-10-01", "date_to": "2026-10-31"}
    body = (await client.get(url("collections"), params=params)).json()
    assert [(r["key"], r["payments"], r["amount"]) for r in body["items"]] == [("2026-10-14", 1, 4000.0), ("2026-10-15", 2, 3000.0)]
    assert body["totals"] == {"payments": 3, "amount": 7000.0}
    by_mode = (await client.get(url("collections"), params={**params, "mode": "upi"})).json()
    assert [(r["key"], r["amount"]) for r in by_mode["items"]] == [("2026-10-15", 2000.0)]


@pytest.mark.asyncio
async def test_collections_by_month_and_by_course(client, db_session):
    """The backlog's + case: accounts filters by one course for October."""
    _, enrollment = await enrolled(db_session, 90000)
    batch = await course_of(db_session, enrollment)
    await paid(db_session, enrollment, 1500, datetime.datetime(2026, 10, 3, 6, 0, tzinfo=UTC))
    await paid(db_session, enrollment, 2500, datetime.datetime(2026, 10, 30, 6, 0, tzinfo=UTC))
    await paid(db_session, enrollment, 9999, datetime.datetime(2026, 11, 1, 6, 0, tzinfo=UTC))  # November: outside the range
    await as_admin(client, db_session)
    params = {"program_id": str(batch.program_id), "date_from": "2026-10-01", "date_to": "2026-10-31"}
    month = (await client.get(url("collections"), params={**params, "group": "month"})).json()
    assert [(r["key"], r["label"], r["amount"]) for r in month["items"]] == [("2026-10", "October 2026", 4000.0)]
    course = (await client.get(url("collections"), params={**params, "group": "course"})).json()
    assert [(r["key"], r["payments"], r["amount"]) for r in course["items"]] == [(str(batch.program_id), 2, 4000.0)]
    assert course["items"][0]["label"].startswith("I013 Course")
    by_batch = (await client.get(url("collections"), params={**params, "batch_id": str(batch.id)})).json()
    assert by_batch["totals"]["amount"] == 4000.0


# --- outstanding (AC2) ----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outstanding_is_the_sum_of_positive_balances_of_active_enrolments(client, db_session):
    _, owing = await enrolled(db_session, 45000)
    batch = await course_of(db_session, owing)
    settled = await second_enrolment(db_session, batch, 10000)
    withdrawn = await second_enrolment(db_session, batch, 7000, status="withdrawn")
    await as_admin(client, db_session)
    assert (await client.post(record_url(owing), json={"amount": 15000, "payment_mode": "cash"})).status_code == 201
    assert (await client.post(record_url(settled), json={"amount": 10000, "payment_mode": "upi"})).status_code == 201
    bill = (await db_session.scalars(select(Payment).where(Payment.reference_id == owing.id, Payment.status == "pending"))).one()
    bill.due_date = datetime.date(2026, 1, 10)
    await db_session.commit()
    body = (await client.get(url("outstanding"), params={"program_id": str(batch.program_id)})).json()
    assert [(r["enrollment_code"], r["balance"], r["paid_confirmed"], r["overdue_amount"], r["state"]) for r in body["items"]] == [
        (owing.enrollment_code, 30000.0, 15000.0, 30000.0, "partially_paid")]  # fmt: skip
    assert body["totals"] == {"enrolments": 1, "balance": 30000.0, "overdue_amount": 30000.0}
    assert [(c["program_id"], c["enrolments"], c["balance"]) for c in body["by_course"]] == [(str(batch.program_id), 1, 30000.0)]
    account = (await client.get(f"{API}/it/enrollments/{owing.id}/fee-account")).json()
    assert account["balance"] == body["totals"]["balance"]  # AC2: the same figure the fee account shows
    assert withdrawn.enrollment_code not in {r["enrollment_code"] for r in body["items"]}
    overdue_only = (await client.get(url("outstanding"), params={"program_id": str(batch.program_id), "state": "overdue"})).json()
    assert overdue_only["total"] == 1
    pending_only = (await client.get(url("outstanding"), params={"program_id": str(batch.program_id), "state": "enrolled_pending_payment"})).json()
    assert pending_only["total"] == 0


# --- overdue installments -------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overdue_lists_each_owed_installment_due_before_today_with_its_reminders(client, db_session):
    _, enrollment = await enrolled(db_session, 20000)
    batch = await course_of(db_session, enrollment)
    bill = (await db_session.scalars(select(Payment).where(Payment.reference_id == enrollment.id))).one()
    bill.due_date, bill.installment_no = datetime.date(2026, 1, 1), 1
    db_session.add(Payment(user_id=enrollment.student_id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=5000, status="pending",
                           due_date=datetime.date(2099, 1, 1), installment_no=2, is_manual=True))  # fmt: skip
    await db_session.flush()
    db_session.add(FeeReminderLog(payment_id=bill.id, student_id=enrollment.student_id, kind="overdue", offset_days=1, reminder_date=datetime.date(2026, 1, 2),
                                  due_date=datetime.date(2026, 1, 1)))  # fmt: skip
    await db_session.commit()
    await as_admin(client, db_session)
    body = (await client.get(url("overdue"), params={"program_id": str(batch.program_id)})).json()
    assert [(r["installment_no"], r["amount"], r["due_date"], r["reminders"]) for r in body["items"]] == [(1, 20000.0, "2026-01-01", 1)]
    assert body["items"][0]["days_overdue"] > 300
    assert body["totals"] == {"installments": 1, "amount": 20000.0}


# --- receipts register and adjustments ------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_receipts_register_lists_each_receipt_with_mode_and_reference(client, db_session):
    _, enrollment = await enrolled(db_session, 30000)
    batch = await course_of(db_session, enrollment)
    await as_admin(client, db_session)
    assert (await client.post(record_url(enrollment), json={"amount": 12000, "payment_mode": "cheque", "provider_reference": "CHQ-42"})).status_code == 201
    params = {"program_id": str(batch.program_id)}
    body = (await client.get(url("receipts"), params=params)).json()
    assert [(r["amount"], r["payment_mode"], r["reference"], r["status"], r["enrollment_code"]) for r in body["items"]] == [
        (12000.0, "cheque", "CHQ-42", "paid", enrollment.enrollment_code)]  # fmt: skip
    assert body["items"][0]["receipt_no"]
    assert body["totals"] == {"receipts": 1, "amount": 12000.0}
    assert (await client.get(url("receipts"), params={**params, "mode": "cash"})).json()["total"] == 0


@pytest.mark.asyncio
async def test_the_adjustments_list_shows_credit_notes_and_refunds_with_a_kind_filter(client, db_session):
    _, enrollment = await enrolled(db_session, 30000)
    batch = await course_of(db_session, enrollment)
    await as_admin(client, db_session)
    assert (await client.post(record_url(enrollment), json={"amount": 30000, "payment_mode": "upi"})).status_code == 201
    adjust = f"{API}/it/enrollments/{enrollment.id}/adjustments"
    assert (await client.post(adjust, json={"kind": "credit_note", "amount": 5000, "reason": "Batch change"})).status_code == 201
    assert (await client.post(adjust, json={"kind": "refund", "amount": 5000, "reason": "Batch change", "payment_mode": "bank_transfer", "reference": "NEFT-1"})).status_code == 201
    params = {"program_id": str(batch.program_id)}
    body = (await client.get(url("adjustments"), params=params)).json()
    assert sorted((r["kind"], r["amount"]) for r in body["items"]) == [("credit_note", 5000.0), ("refund", 5000.0)]
    assert body["totals"] == {"count": 2, "credit_note": 5000.0, "write_off": 0.0, "refund": 5000.0, "reversal": 0.0}
    refunds = (await client.get(url("adjustments"), params={**params, "kind": "refund"})).json()
    assert [(r["kind"], r["payment_mode"], r["reference"], r["reason"]) for r in refunds["items"]] == [("refund", "bank_transfer", "NEFT-1", "Batch change")]


# --- paging and export (AC4) ----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lists_are_paginated(client, db_session):
    _, enrollment = await enrolled(db_session, 90000)
    program = (await course_of(db_session, enrollment)).program_id
    for day in (3, 4, 5):
        await paid(db_session, enrollment, 100, datetime.datetime(2026, 10, day, 6, 0, tzinfo=UTC))
    await as_admin(client, db_session)
    params = {"program_id": str(program), "date_from": "2026-10-01", "date_to": "2026-10-31", "limit": 2, "offset": 2}
    body = (await client.get(url("collections"), params=params)).json()
    assert (body["total"], body["limit"], body["offset"], [r["key"] for r in body["items"]]) == (3, 2, 2, ["2026-10-05"])
    assert body["totals"]["amount"] == 300.0  # totals cover the whole filtered list, not the page


@pytest.mark.asyncio
async def test_the_export_is_csv_injection_safe_and_audited(client, db_session):
    student = await make_user(db_session, "it_student", "it", name='=HYPERLINK("http://evil")')
    _, enrollment = await enrolled(db_session, 30000, student=student)
    program = (await course_of(db_session, enrollment)).program_id
    admin = await as_admin(client, db_session)
    response = await client.get(f"{url('outstanding')}/export", params={"program_id": str(program)})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="it-outstanding-' in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][:3] == ["Student", "Student ID", "Enrolment"]
    assert rows[1][0] == '\'=HYPERLINK("http://evil")'  # AC4: a formula-looking cell is neutralised
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.user_id == admin.id, AuditLog.action == "it.accounts.export"))
    assert audit is not None and audit.metadata_json["report"] == "outstanding" and audit.metadata_json["rows"] == 1
    for report in ("collections", "overdue", "receipts", "adjustments"):
        assert (await client.get(f"{url(report)}/export")).status_code == 200, report

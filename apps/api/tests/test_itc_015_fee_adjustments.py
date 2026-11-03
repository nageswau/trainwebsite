"""itc-015 (DEC-SCOPE-362) -- refunds, adjustments and payment correction on the itc-013 fee account: credit notes and write-offs lower
what is owed (`credits`), a refund pays a credit back out (`refunded`), a mistyped manual payment is replaced through a reversal that
never edits or deletes the original row; every write is audited with old and new values; refunds reduce IT revenue (Q-15)."""

import datetime
import uuid

import pytest
from sqlalchemy import event, select

from app.models import AuditLog, Batch, Enrollment, FeeAdjustment, Payment, Receipt
from app.services import fee_accounts, management_it_revenue, student_access
from tests.bdm001_helpers import make_user
from tests.test_itc_013_fee_account import API, account_url, as_admin, enrolled, figures, record_url, rows
from tests.upc001_helpers import login


def adjust_url(enrollment) -> str:
    return f"{API}/it/enrollments/{enrollment.id}/adjustments"


def correct_url(enrollment, payment) -> str:
    return f"{API}/it/enrollments/{enrollment.id}/payments/{payment.id}/correction"


async def paid_in_full(client, db, fee: float = 45000):
    student, enrollment = await enrolled(db, fee)
    admin = await as_admin(client, db)
    assert (await client.post(record_url(enrollment), json={"amount": fee, "payment_mode": "upi", "provider_reference": "UPI-1"})).status_code == 201
    return student, enrollment, admin


async def adjust(client, enrollment, **body):
    return await client.post(adjust_url(enrollment), json={"reason": "Batch change", **body})


async def owed_sum(db, enrollment) -> float:
    return sum(float(p.amount) for p in await rows(db, enrollment) if p.status in ("pending", "overdue"))


# --- the account figures (AC1) ------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_credit_note_then_a_refund_after_a_batch_change(client, db_session):
    """The backlog's + case: ₹45,000 paid, the new batch costs ₹5,000 less -> a credit note leaves a ₹5,000 credit, the refund clears it."""
    student, enrollment, _ = await paid_in_full(client, db_session)
    credit = await adjust(client, enrollment, kind="credit_note", amount=5000)
    assert credit.status_code == 201, credit.text
    account = credit.json()["account"]
    assert (account["credits"], account["refunded"], account["balance"], account["state"]) == (5000.0, 0.0, -5000.0, "fully_paid")
    assert credit.json()["adjustment"]["document_no"].startswith("CN-")
    refund = await adjust(client, enrollment, kind="refund", amount=5000, payment_mode="bank_transfer", reference="NEFT-77")
    assert refund.status_code == 201, refund.text
    account = refund.json()["account"]
    assert (account["course_fee"], account["paid_confirmed"], account["credits"], account["refunded"], account["balance"]) == (45000.0, 45000.0, 5000.0, 5000.0, 0.0)
    assert [(a["kind"], a["amount"], a["payment_mode"], a["reference"]) for a in account["adjustments"]] == [
        ("credit_note", 5000.0, None, None), ("refund", 5000.0, "bank_transfer", "NEFT-77")]  # fmt: skip
    assert refund.json()["adjustment"]["document_no"].startswith("RF-")
    assert await student_access.student_state(db_session, student.id) == "fully_paid"


@pytest.mark.asyncio
async def test_a_credit_note_lowers_the_owed_bills_latest_due_first_and_the_access_state_agrees(client, db_session):
    student, enrollment = await enrolled(db_session, 30000)
    first = (await rows(db_session, enrollment))[0]
    first.amount, first.due_date = 10000, datetime.date(2026, 1, 1)
    db_session.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=20000, status="pending",
                           due_date=datetime.date(2026, 2, 1), is_manual=True))  # fmt: skip
    await db_session.commit()
    await as_admin(client, db_session)
    response = await adjust(client, enrollment, kind="credit_note", amount=25000)
    assert response.status_code == 201, response.text
    by_due = {p.due_date: p for p in await rows(db_session, enrollment)}
    assert (float(by_due[datetime.date(2026, 2, 1)].amount), by_due[datetime.date(2026, 2, 1)].status) == (0.0, "waived")
    assert (float(by_due[datetime.date(2026, 1, 1)].amount), by_due[datetime.date(2026, 1, 1)].status) == (5000.0, "pending")
    got = await figures(db_session, enrollment)
    assert (got["course_fee"], got["total_payable"], got["credits"], got["balance"]) == (30000.0, 30000.0, 25000.0, 5000.0)
    assert got["balance"] == await owed_sum(db_session, enrollment)  # the bills and the account agree
    adjustment = await db_session.scalar(select(FeeAdjustment).where(FeeAdjustment.enrollment_id == enrollment.id))
    assert float(adjustment.applied_amount) == 25000.0
    assert await student_access.student_state(db_session, student.id) == "enrolled_pending_payment"
    assert (await client.post(record_url(enrollment), json={"amount": 5000, "payment_mode": "cash"})).status_code == 201  # the waived bill is never "next"
    assert (await figures(db_session, enrollment))["state"] == "fully_paid"


@pytest.mark.asyncio
async def test_a_write_off_clears_what_is_owed_and_no_more(client, db_session):
    _, enrollment = await enrolled(db_session, 12000)
    await as_admin(client, db_session)
    assert (await client.post(record_url(enrollment), json={"amount": 2000, "payment_mode": "cash"})).status_code == 201
    too_much = await adjust(client, enrollment, kind="write_off", amount=10000.01)
    assert too_much.status_code == 422 and "at most" in too_much.text
    response = await adjust(client, enrollment, kind="write_off", amount=10000)
    assert response.status_code == 201, response.text
    assert (response.json()["account"]["balance"], response.json()["account"]["state"]) == (0.0, "fully_paid")
    assert response.json()["adjustment"]["document_no"].startswith("WO-")
    assert await owed_sum(db_session, enrollment) == 0.0
    again = await client.post(record_url(enrollment), json={"amount": 1, "payment_mode": "cash"})
    assert again.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body, message",
    [
        ({"kind": "refund", "amount": 5000.01, "payment_mode": "cash"}, "at most"),  # the - case: never more than the credit (so than paid)
        ({"kind": "refund", "amount": 100}, "payment_mode"),  # a refund says how the money went back
        ({"kind": "refund", "amount": 100, "payment_mode": "razorpay"}, None),  # Q-15: manual only
        ({"kind": "credit_note", "amount": 40000.01}, "at most"),  # never more than is still payable
        ({"kind": "credit_note", "amount": 0}, None),
        ({"kind": "reversal", "amount": 10}, None),  # a reversal is made only by a correction
        ({"kind": "credit_note", "amount": 10, "reason": "  "}, "reason"),
    ],
)
async def test_an_invalid_adjustment_is_refused_and_changes_nothing(client, db_session, body, message):
    _, enrollment, _ = await paid_in_full(client, db_session)
    assert (await adjust(client, enrollment, kind="credit_note", amount=5000)).status_code == 201
    before = await figures(db_session, enrollment)
    response = await client.post(adjust_url(enrollment), json={"reason": "Batch change", **body})
    assert response.status_code == 422, response.text
    if message:
        assert message in response.text
    assert await figures(db_session, enrollment) == before


@pytest.mark.asyncio
async def test_a_refund_needs_a_credit_and_an_unbilled_enrolment_takes_no_adjustment(client, db_session):
    _, enrollment = await enrolled(db_session, 1000)
    _, unbilled = await enrolled(db_session, None)
    await as_admin(client, db_session)
    response = await adjust(client, enrollment, kind="refund", amount=1, payment_mode="cash")
    assert response.status_code == 422 and "no credit" in response.text
    assert (await adjust(client, unbilled, kind="credit_note", amount=1)).status_code == 409


@pytest.mark.asyncio
async def test_an_adjustment_is_audited_with_the_balance_before_and_after(client, db_session):
    _, enrollment, admin = await paid_in_full(client, db_session, 10000)
    response = await adjust(client, enrollment, kind="credit_note", amount=1500)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.fee.adjustment_recorded", AuditLog.entity_id == str(enrollment.id)))
    assert audit.user_id == admin.id and audit.metadata_json["changes"]["balance"] == [0.0, -1500.0]
    assert audit.metadata_json["kind"] == "credit_note" and audit.metadata_json["adjustment_id"] == response.json()["adjustment"]["id"]
    row = await db_session.get(FeeAdjustment, uuid.UUID(response.json()["adjustment"]["id"]))
    assert row.approved_by_id == admin.id  # Q-14: the recorder approves until maker-checker exists


@pytest.mark.asyncio
async def test_adjusting_needs_the_payments_refund_grant_and_an_it_enrolment(client, db_session):
    _, enrollment = await enrolled(db_session)
    for role, division, status in (("trainer", "it", 403), ("counselor", "it", 403), ("it_student", "it", 403), ("overseas_admin", "overseas", 403)):
        await login(client, await make_user(db_session, role, division))
        assert (await adjust(client, enrollment, kind="credit_note", amount=10)).status_code == status, role
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await adjust(client, enrollment, kind="credit_note", amount=10)).status_code == 201
    assert (await client.post(f"{API}/it/enrollments/{uuid.uuid4()}/adjustments", json={"kind": "credit_note", "amount": 1, "reason": "x"})).status_code == 404


# --- payment correction (AC2, AC3) -------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_mistyped_payment_is_replaced_never_edited_or_deleted(client, db_session):
    student, enrollment = await enrolled(db_session)
    admin = await as_admin(client, db_session)
    recorded = await client.post(record_url(enrollment), json={"amount": 20000, "payment_mode": "cash", "provider_reference": "TXN-1"})
    original_id = uuid.UUID(recorded.json()["payment"]["id"])
    original = await db_session.get(Payment, original_id)
    response = await client.post(correct_url(enrollment, original), json={"amount": 15000, "payment_mode": "upi", "provider_reference": "TXN-2", "reason": "Typed the wrong amount"})
    assert response.status_code == 201, response.text
    account = response.json()["account"]
    assert (account["course_fee"], account["paid_confirmed"], account["balance"], account["state"]) == (45000.0, 15000.0, 30000.0, "partially_paid")
    kept = (await db_session.execute(select(Payment).where(Payment.id == original_id).execution_options(populate_existing=True))).scalar_one()
    assert (float(kept.amount), kept.payment_mode, kept.provider_reference, kept.status) == (20000.0, "cash", "TXN-1", "reversed")  # AC2
    assert await db_session.scalar(select(Receipt.id).where(Receipt.payment_id == original_id)) is not None  # its receipt stays on file
    replacement = await db_session.get(Payment, uuid.UUID(response.json()["payment"]["id"]))
    assert (float(replacement.amount), replacement.payment_mode, replacement.provider_reference, replacement.status) == (15000.0, "upi", "TXN-2", "paid")
    reversal = await db_session.scalar(select(FeeAdjustment).where(FeeAdjustment.payment_id == original_id))
    assert (reversal.kind, float(reversal.amount), reversal.replacement_payment_id, reversal.document_no) == ("reversal", 20000.0, replacement.id, None)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.fee.payment_corrected", AuditLog.entity_id == str(enrollment.id)))
    assert audit.user_id == admin.id
    assert audit.metadata_json["changes"] == {"amount": [20000.0, 15000.0], "payment_mode": ["cash", "upi"], "provider_reference": ["TXN-1", "TXN-2"]}  # AC3
    assert account["balance"] == await owed_sum(db_session, enrollment)
    assert await student_access.student_state(db_session, student.id) == "partially_paid"
    assert [i["status"] for i in account["installments"]].count("paid") == 1  # the reversed row is not an installment any more


@pytest.mark.asyncio
async def test_a_correction_is_refused_when_it_cannot_apply(client, db_session):
    student, enrollment = await enrolled(db_session)
    await as_admin(client, db_session)
    recorded = await client.post(record_url(enrollment), json={"amount": 20000, "payment_mode": "cash"})
    payment = await db_session.get(Payment, uuid.UUID(recorded.json()["payment"]["id"]))
    body = {"amount": 20000, "payment_mode": "cash", "reason": "No change"}
    assert (await client.post(correct_url(enrollment, payment), json=body)).status_code == 422  # nothing to correct
    over = await client.post(correct_url(enrollment, payment), json={**body, "amount": 20000.01})  # the reopened bill is 20,000: no overpayment
    assert over.status_code == 422 and "at most" in over.text
    kept = (await db_session.execute(select(Payment).where(Payment.id == payment.id).execution_options(populate_existing=True))).scalar_one()
    assert kept.status == "paid" and (await figures(db_session, enrollment))["balance"] == 25000.0  # rolled back whole
    assert (await client.post(correct_url(enrollment, payment), json={**body, "payment_mode": "upi"})).status_code == 201
    again = await client.post(correct_url(enrollment, payment), json={**body, "payment_mode": "card"})
    assert again.status_code == 409  # a reversed payment is corrected once
    gateway = Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=100, status="paid", provider="razorpay", payment_mode="razorpay")
    db_session.add(gateway)
    await db_session.commit()
    refused = await client.post(correct_url(enrollment, gateway), json={**body, "amount": 50})
    assert refused.status_code == 409 and "gateway" in refused.text
    _, other = await enrolled(db_session)
    assert (await client.post(correct_url(other, payment), json={**body, "amount": 10})).status_code == 404  # not this enrolment's payment


# --- reading and documents ----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_student_sees_their_refund_and_downloads_its_document(client, db_session):
    student, enrollment, _ = await paid_in_full(client, db_session, 8000)
    await adjust(client, enrollment, kind="credit_note", amount=3000)
    refund = (await adjust(client, enrollment, kind="refund", amount=3000, payment_mode="cash")).json()["adjustment"]
    await login(client, student)
    mine = (await client.get(f"{API}/it/student/fee-accounts")).json()
    assert [a["kind"] for a in mine[0]["adjustments"]] == ["credit_note", "refund"] and mine[0]["refunded"] == 3000.0
    document = await client.get(f"{API}/it/fee-adjustments/{refund['id']}/document")
    assert document.status_code == 200 and document.json()["url"]
    await login(client, await make_user(db_session, "it_student", "it"))
    assert (await client.get(f"{API}/it/fee-adjustments/{refund['id']}/document")).status_code == 404  # never another student's
    assert (await client.get(account_url(enrollment))).status_code == 404


@pytest.mark.asyncio
async def test_balance_for_still_answers_in_one_query_with_adjustments(client, db_session):
    _, enrollment, _ = await paid_in_full(client, db_session, 1000)
    await adjust(client, enrollment, kind="credit_note", amount=400)
    queries = []

    def count(*_):
        queries.append(1)

    sync_engine = db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", count)
    try:
        got = await fee_accounts.balance_for(db_session, [enrollment.id])
    finally:
        event.remove(sync_engine, "before_cursor_execute", count)
    assert got[enrollment.id]["balance"] == -400.0 and len(queries) == 1


# --- revenue (Q-15) -----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_refund_reduces_it_revenue_for_its_course(client, db_session):
    _, enrollment, _ = await paid_in_full(client, db_session, 9000)
    await adjust(client, enrollment, kind="credit_note", amount=2000)
    await adjust(client, enrollment, kind="refund", amount=2000, payment_mode="cash")
    today = fee_accounts.india_today().replace(day=1)
    data = await management_it_revenue.dashboard(db_session, today, "month")
    program_id = await db_session.scalar(select(Batch.program_id).join(Enrollment, Enrollment.batch_id == Batch.id).where(Enrollment.id == enrollment.id))
    (row,) = [c for c in data["courses"] if c["program_id"] == program_id]
    assert float(row["revenue"]) == 7000.0  # 9,000 received - 2,000 refunded; the credit note alone moves no cash

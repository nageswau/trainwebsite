"""itc-014 (DEC-SCOPE-363) -- discount and waiver approval (maker-checker): a linked IT counselor or a `discounts.add` holder in IT asks
for an amount off an enrolment's owed fee; a `discounts.approve` holder who is not the requester approves or rejects it. Only an approval
changes payable (AC1), it is audited with the old and new values (AC2) and self-approval is 403 (AC3)."""

import datetime

import pytest
from sqlalchemy import select

from app.core import rbac
from app.models import AuditLog, FeeDiscountRequest, ItStudentCounselor, Payment
from app.services import permissions
from tests.bdm001_helpers import make_user
from tests.test_itc_013_fee_account import account_url, enrolled, figures, record_url, rows
from tests.upc001_helpers import login

API = "/api/v1"
QUEUE = f"{API}/it/discount-requests"


def requests_url(enrollment) -> str:
    return f"{API}/it/enrollments/{enrollment.id}/discount-requests"


def decide_url(request_id, verb: str) -> str:
    return f"{QUEUE}/{request_id}/{verb}"


async def counselor_of(db, student):
    counselor = await make_user(db, "counselor", "it")
    db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()
    return counselor


async def requested(client, db, amount=5000, fee=45000):
    """A linked counselor's pending request; returns (student, enrollment, counselor, request json)."""
    student, enrollment = await enrolled(db, fee)
    counselor = await counselor_of(db, student)
    await login(client, counselor)
    response = await client.post(requests_url(enrollment), json={"amount": amount, "reason": "Sibling discount"})
    assert response.status_code == 201, response.text
    return student, enrollment, counselor, response.json()


# --- the grant -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discounts_approve_is_a_catalogue_key_held_by_the_it_admin(db_session):
    assert "discounts.approve" in rbac.all_keys()
    assert "discounts.approve" in rbac.DEFAULT_GRANTS["it_admin"]
    admin = await make_user(db_session, "it_admin", "it")
    assert await permissions.user_has_grant(db_session, admin, "discounts", "approve")
    counselor = await make_user(db_session, "counselor", "it")
    assert not await permissions.user_has_grant(db_session, counselor, "discounts", "approve")


# --- AC1: a pending request changes nothing ------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pending_request_does_not_change_payable(client, db_session):
    _, enrollment, counselor, body = await requested(client, db_session)
    assert body["status"] == "pending" and body["amount"] == 5000.0 and body["reason"] == "Sibling discount"
    assert body["requested_by"]["id"] == str(counselor.id) and body["own"] is True and body["decided_by"] is None
    got = await figures(db_session, enrollment)
    assert (got["discount_approved"], got["total_payable"], got["balance"]) == (0.0, 45000.0, 45000.0)
    listed = (await client.get(requests_url(enrollment))).json()
    assert [r["id"] for r in listed] == [body["id"]]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.fee.discount_requested", AuditLog.entity_id == str(enrollment.id)))
    assert audit is not None and audit.user_id == counselor.id


# --- the + case and AC2 --------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_approval_lowers_payable_and_audits_old_and_new_values(client, db_session):
    _, enrollment, _, body = await requested(client, db_session)
    approver = await make_user(db_session, "it_admin", "it")
    await login(client, approver)
    queue = (await client.get(QUEUE)).json()
    assert body["id"] in [r["id"] for r in queue]
    response = await client.post(decide_url(body["id"], "approve"), json={})
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["request"]["status"] == "approved" and out["request"]["decided_by"]["id"] == str(approver.id)
    assert (out["account"]["course_fee"], out["account"]["discount_approved"], out["account"]["total_payable"], out["account"]["balance"]) == (45000.0, 5000.0, 40000.0, 40000.0)
    [bill] = await rows(db_session, enrollment)
    assert (float(bill.amount), float(bill.discount_amount), bill.discounted_by_id, bill.discount_reason) == (40000.0, 5000.0, approver.id, "Sibling discount")
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.fee.discount_approved", AuditLog.entity_id == str(enrollment.id)))
    assert audit.user_id == approver.id and audit.metadata_json["request_id"] == body["id"]
    assert audit.metadata_json["changes"]["balance"] == [45000.0, 40000.0]
    assert audit.metadata_json["changes"]["total_payable"] == [45000.0, 40000.0]
    assert body["id"] not in [r["id"] for r in (await client.get(QUEUE)).json()]  # the queue holds pending requests only
    assert (await client.post(decide_url(body["id"], "approve"), json={})).status_code == 409  # decided once


@pytest.mark.asyncio
async def test_a_full_waiver_marks_the_bills_waived_and_clears_the_balance(client, db_session):
    student, enrollment = await enrolled(db_session, 30000)
    (await rows(db_session, enrollment))[0].due_date = datetime.date(2027, 1, 1)
    db_session.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=10000, status="pending",
                           due_date=datetime.date(2027, 3, 1)))  # fmt: skip
    await db_session.commit()
    admin = await make_user(db_session, "it_admin", "it")
    await login(client, admin)
    request = (await client.post(requests_url(enrollment), json={"amount": 25000, "reason": "Scholarship"})).json()
    await login(client, await make_user(db_session, "it_admin", "it"))
    account = (await client.post(decide_url(request["id"], "approve"), json={"note": "OK"})).json()["account"]
    assert (account["course_fee"], account["discount_approved"], account["balance"], account["state"]) == (40000.0, 25000.0, 15000.0, "enrolled_pending_payment")
    by_due = {p.due_date: p for p in await rows(db_session, enrollment)}
    later = by_due[datetime.date(2027, 3, 1)]  # latest due first: the March 10,000 bill is fully waived, then 15,000 off January's
    assert (later.status, float(later.amount), float(later.discount_amount)) == ("waived", 0.0, 10000.0)
    first = by_due[datetime.date(2027, 1, 1)]
    assert (first.status, float(first.amount), float(first.discount_amount)) == ("pending", 15000.0, 15000.0)
    request = (await client.post(requests_url(enrollment), json={"amount": 15000, "reason": "Rest waived"})).json()
    await login(client, admin)
    account = (await client.post(decide_url(request["id"], "approve"), json={})).json()["account"]
    assert (account["course_fee"], account["balance"], account["state"]) == (40000.0, 0.0, "fully_paid")
    assert account["installments"] == []  # a waived bill is never offered for payment


# --- AC3: separation of duties -------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_requester_cannot_approve_or_reject_their_own_request(client, db_session):
    _, enrollment = await enrolled(db_session)
    admin = await make_user(db_session, "it_admin", "it")
    await login(client, admin)
    request = (await client.post(requests_url(enrollment), json={"amount": 1000, "reason": "Early bird"})).json()
    assert request["own"] is True
    assert (await client.post(decide_url(request["id"], "approve"), json={})).status_code == 403
    assert (await client.post(decide_url(request["id"], "reject"), json={"note": "no"})).status_code == 403
    assert (await figures(db_session, enrollment))["balance"] == 45000.0


@pytest.mark.asyncio
async def test_deciding_needs_the_approve_grant_in_it(client, db_session):
    _, _, counselor, body = await requested(client, db_session)
    assert (await client.post(decide_url(body["id"], "approve"), json={})).status_code == 403  # the counselor holds no approve grant
    assert (await client.get(QUEUE)).status_code == 403
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await client.post(decide_url(body["id"], "approve"), json={})).status_code == 403  # no approve grant either
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.post(decide_url("not-a-uuid", "approve"), json={})).status_code == 422
    assert (await client.post(decide_url("00000000-0000-0000-0000-000000000000", "approve"), json={})).status_code == 404


@pytest.mark.asyncio
async def test_a_rejection_needs_a_note_and_changes_nothing(client, db_session):
    _, enrollment, _, body = await requested(client, db_session)
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.post(decide_url(body["id"], "reject"), json={"note": "  "})).status_code == 422
    out = (await client.post(decide_url(body["id"], "reject"), json={"note": "Not eligible"})).json()
    assert out["request"]["status"] == "rejected" and out["request"]["decision_note"] == "Not eligible"
    assert (await figures(db_session, enrollment))["balance"] == 45000.0
    assert (await client.get(f"{QUEUE}?status=rejected")).json()[0]["id"] == body["id"]
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "it.fee.discount_rejected", AuditLog.entity_id == str(enrollment.id)))


# --- the − case and E ----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("body", "message"), [
    ({"amount": 45000.01, "reason": "Too much"}, "45,000.00"),
    ({"amount": 0, "reason": "Zero"}, None),
    ({"amount": 100, "reason": " "}, None),
    ({"amount": 100, "reason": "x" * 501}, None),
])  # fmt: skip
async def test_an_invalid_request_is_refused(client, db_session, body, message):
    _, enrollment = await enrolled(db_session)
    await login(client, await make_user(db_session, "it_admin", "it"))
    response = await client.post(requests_url(enrollment), json=body)
    assert response.status_code == 422
    if message:
        assert message in response.json()["detail"]
    assert (await client.get(requests_url(enrollment))).json() == []


@pytest.mark.asyncio
async def test_one_pending_request_per_enrolment_and_none_when_nothing_is_owed(client, db_session):
    _, enrollment, _, _ = await requested(client, db_session)
    assert (await client.post(requests_url(enrollment), json={"amount": 100, "reason": "Again"})).status_code == 409
    _, unbilled = await enrolled(db_session, None)
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.post(requests_url(unbilled), json={"amount": 100, "reason": "Nothing owed"})).status_code == 409


@pytest.mark.asyncio
async def test_a_payment_while_pending_is_rechecked_at_approval(client, db_session):
    _, enrollment, _, body = await requested(client, db_session, amount=30000)
    admin = await make_user(db_session, "it_admin", "it")
    await login(client, admin)
    assert (await client.post(record_url(enrollment), json={"amount": 20000, "payment_mode": "cash"})).status_code == 201
    response = await client.post(decide_url(body["id"], "approve"), json={})
    assert response.status_code == 409 and "25,000.00" in response.json()["detail"]
    got = await figures(db_session, enrollment)
    assert (got["discount_approved"], got["balance"]) == (0.0, 25000.0)
    assert (await client.get(QUEUE)).json()[0]["status"] == "pending"  # still pending: reject it, or ask again


# --- who may request and read ---------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_who_may_request_and_read(client, db_session):
    student, enrollment = await enrolled(db_session)
    await counselor_of(db_session, student)
    stranger = await make_user(db_session, "counselor", "it")
    await login(client, stranger)  # an IT counselor not linked to this student
    assert (await client.post(requests_url(enrollment), json={"amount": 100, "reason": "x"})).status_code == 404
    assert (await client.get(requests_url(enrollment))).status_code == 404
    await login(client, student)
    assert (await client.post(requests_url(enrollment), json={"amount": 100, "reason": "x"})).status_code == 403
    assert (await client.get(requests_url(enrollment))).status_code == 403
    assert (await client.get(account_url(enrollment))).status_code == 200  # the student still reads the account itself
    await login(client, await make_user(db_session, "trainer", "it"))
    assert (await client.post(requests_url(enrollment), json={"amount": 100, "reason": "x"})).status_code == 403
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await client.post(requests_url(enrollment), json={"amount": 100, "reason": "x"})).status_code == 404  # another division
    assert await db_session.scalar(select(FeeDiscountRequest.id).where(FeeDiscountRequest.enrollment_id == enrollment.id)) is None

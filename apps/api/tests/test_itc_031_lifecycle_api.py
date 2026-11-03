"""itc-031 (DEC-SCOPE-359) -- the lifecycle over HTTP and from its writers: the 360's lifecycle read (linked counselor, IT Admin; scope 404,
other roles 403), the IT Admin's override (only Not placed / Closed, reason, audit, history), the enrolment payloads (staff full, student
safe), the admin enrolment PATCH status check, and the history written by the fee, gateway, enrolment, HR, application and daily writers
(AC1 the stage moves with its source record, AC2 history shows actor and time)."""

import datetime

import pytest
from sqlalchemy import select

from app.models import AuditLog, EnrollmentLifecycleHistory, ItStudentCounselor, Payment, User
from app.services import applications, it_at_risk, it_lifecycle
from tests.agn011_helpers import captured, razorpay_on, signed
from tests.tel004_helpers import make_user
from tests.test_itc_031_lifecycle import PAST, application, enrolled, flag, pay
from tests.upc001_helpers import login

pytestmark = pytest.mark.asyncio

API = "/api/v1"


def lifecycle_url(portal: str, student_id) -> str:
    return f"{API}/{portal}/it/students/{student_id}/lifecycle"


def override_url(student_id, enrollment_id, portal: str = "admin") -> str:
    return f"{API}/{portal}/it/students/{student_id}/enrollments/{enrollment_id}/lifecycle-override"


async def linked_counselor(db, student_id) -> User:
    counselor = await make_user(db, "counselor", "it")
    db.add(ItStudentCounselor(student_user_id=student_id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()
    return counselor


async def history(db, enrollment) -> list[tuple]:
    rows = await db.scalars(select(EnrollmentLifecycleHistory).where(EnrollmentLifecycleHistory.enrollment_id == enrollment.id)
                            .order_by(EnrollmentLifecycleHistory.created_at, EnrollmentLifecycleHistory.id))  # fmt: skip
    return [(r.from_stage, r.to_stage, r.cause, r.actor_user_id) for r in rows.all()]


# --- the 360 read (L8) ------------------------------------------------------------------------------------------------------------


async def test_the_linked_counselor_and_the_it_admin_read_the_lifecycle_and_others_cannot(client, db_session):
    enrollment = await enrolled(db_session, start=PAST)
    counselor = await linked_counselor(db_session, enrollment.student_id)
    await login(client, counselor)
    body = (await client.get(lifecycle_url("counselor", enrollment.student_id))).json()
    row = body["enrollments"][0]
    assert (row["enrollment_id"], row["stage"], row["stage_label"]) == (str(enrollment.id), "training_active", "Training active")
    assert row["components"] == {"fee": {"stage": "fee_pending", "stage_label": "Fee pending"}, "training": {"stage": "training_active", "stage_label": "Training active"},
                                 "placement": None}  # fmt: skip
    assert row["override"] is None and row["history"] == []

    await login(client, await make_user(db_session, "counselor", "it"))  # not linked: the same 404 as a missing student
    assert (await client.get(lifecycle_url("counselor", enrollment.student_id))).status_code == 404
    await login(client, await make_user(db_session, "trainer", "it"))
    assert (await client.get(lifecycle_url("counselor", enrollment.student_id))).status_code == 403
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(lifecycle_url("admin", enrollment.student_id))).json()["enrollments"][0]["stage"] == "training_active"


async def test_staff_profile_payloads_carry_the_stage_and_the_student_sees_the_safe_subset(client, db_session):
    enrollment = await enrolled(db_session, start=PAST)
    await flag(db_session, enrollment)
    counselor = await linked_counselor(db_session, enrollment.student_id)
    await login(client, counselor)
    staff = (await client.get(f"{API}/counselor/it/students/{enrollment.student_id}/profile")).json()["enrollments"][0]
    assert staff["lifecycle"] == {"stage": "at_risk", "stage_label": "At risk"}
    await login(client, await db_session.get(User, enrollment.student_id))
    mine = (await client.get(f"{API}/it/me/profile")).json()["enrollments"][0]
    assert mine["lifecycle"] == {"stage": "training_active", "stage_label": "Training active"}  # no "At risk" wording for the student
    await login(client, await make_user(db_session, "it_admin", "it"))
    listed = next(r for r in (await client.get(f"{API}/admin/enrollments", params={"batch_id": str(enrollment.batch_id)})).json() if r["id"] == str(enrollment.id))
    assert listed["lifecycle"] == {"stage": "at_risk", "stage_label": "At risk"}


# --- the override (L4) ------------------------------------------------------------------------------------------------------------


async def test_the_it_admin_sets_and_clears_not_placed_with_history_and_audit(client, db_session):
    enrollment = await enrolled(db_session, start=PAST)
    admin = await make_user(db_session, "it_admin", "it")
    await login(client, admin)
    response = await client.put(override_url(enrollment.student_id, enrollment.id), json={"stage": "not_placed", "reason": "No offers after six drives"})
    assert response.status_code == 200, response.text
    row = response.json()["enrollments"][0]
    assert (row["stage"], row["override"]) == ("not_placed", {"stage": "not_placed", "stage_label": "Not placed", "reason": "No offers after six drives"})
    assert row["history"][0]["to_stage"] == "not_placed" and row["history"][0]["actor"] == admin.full_name and row["history"][0]["created_at"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(enrollment.id), AuditLog.action == "it.enrollment.lifecycle_override"))
    assert audit.user_id == admin.id and audit.metadata_json["changes"]["lifecycle_override"] == [None, "not_placed"]

    cleared = (await client.put(override_url(enrollment.student_id, enrollment.id), json={"stage": None})).json()["enrollments"][0]
    assert (cleared["stage"], cleared["override"]) == ("training_active", None)
    assert [h[1] for h in await history(db_session, enrollment)] == ["not_placed", "training_active"]


@pytest.mark.parametrize(("body", "status", "detail"), [
    ({"stage": "placed", "reason": "Joined Infosys"}, 409, it_lifecycle.PLACED_BY_JOINING),
    ({"stage": "training_active", "reason": "Back in class"}, 409, it_lifecycle.DERIVED_ONLY),
    ({"stage": "closed"}, 422, None),
    ({"stage": "closed", "reason": "  "}, 422, None),
    ({"stage": "graduated", "reason": "Done"}, 422, None),
    ({"stage": "closed", "reason": "x" * 501}, 422, None),
])  # fmt: skip
async def test_the_override_refuses_derived_stages_and_bad_bodies(client, db_session, body, status, detail):
    enrollment = await enrolled(db_session, start=PAST)
    await login(client, await make_user(db_session, "it_admin", "it"))
    response = await client.put(override_url(enrollment.student_id, enrollment.id), json=body)
    assert response.status_code == status, response.text
    if detail:
        assert response.json()["detail"] == detail


async def test_not_placed_is_refused_once_the_student_joined(client, db_session):
    enrollment = await enrolled(db_session, start=PAST)
    await application(db_session, await db_session.get(User, enrollment.student_id), "joined")
    await login(client, await make_user(db_session, "it_admin", "it"))
    response = await client.put(override_url(enrollment.student_id, enrollment.id), json={"stage": "not_placed", "reason": "No offer"})
    assert (response.status_code, response.json()["detail"]) == (409, it_lifecycle.ALREADY_PLACED)


async def test_only_the_it_admin_overrides_and_only_this_students_enrolment(client, db_session):
    enrollment = await enrolled(db_session, start=PAST)
    other = await enrolled(db_session, start=PAST)
    counselor = await linked_counselor(db_session, enrollment.student_id)
    await login(client, counselor)
    assert (await client.put(override_url(enrollment.student_id, enrollment.id, "counselor"), json={"stage": "closed", "reason": "Left"})).status_code in (404, 405)
    await login(client, await make_user(db_session, "counselor", "it"))
    assert (await client.put(override_url(enrollment.student_id, enrollment.id), json={"stage": "closed", "reason": "Left"})).status_code == 403
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.put(override_url(enrollment.student_id, other.id), json={"stage": "closed", "reason": "Left"})).status_code == 404


# --- the writers (AC1, AC2) -------------------------------------------------------------------------------------------------------


async def test_recording_the_final_payment_moves_partially_paid_to_paid_with_the_actor(client, db_session):
    enrollment = await enrolled(db_session)
    await pay(db_session, enrollment, 10000)
    admin = await make_user(db_session, "it_admin", "it")
    await login(client, admin)
    response = await client.post(f"{API}/it/enrollments/{enrollment.id}/payments", json={"amount": 30000, "payment_mode": "cash"})
    assert response.status_code == 201, response.text
    assert await history(db_session, enrollment) == [(None, "paid", "fee", admin.id)]  # the first row: no earlier stage recorded
    staff = (await client.get(lifecycle_url("admin", enrollment.student_id))).json()["enrollments"][0]
    assert staff["stage"] == "paid" and staff["history"][0]["actor"] == admin.full_name


async def test_a_gateway_confirmation_writes_the_fee_transition_as_the_system(client, db_session, monkeypatch):
    enrollment = await enrolled(db_session)
    await it_lifecycle.sync(db_session, [enrollment.id], actor=None, cause="enrolment")
    await db_session.commit()
    bill = await db_session.scalar(select(Payment).where(Payment.reference_id == enrollment.id))
    bill.provider, bill.checkout_provider_order_id = "razorpay", f"order_{enrollment.id.hex[:10]}"
    await db_session.commit()
    razorpay_on(monkeypatch)
    raw, headers = signed(captured(bill.checkout_provider_order_id, 4000000))
    assert (await client.post(f"{API}/payments/webhooks/razorpay", content=raw, headers=headers)).status_code == 200
    assert await history(db_session, enrollment) == [(None, "fee_pending", "enrolment", None), ("fee_pending", "paid", "fee", None)]


async def test_withdrawing_an_enrolment_closes_it_and_a_free_text_status_is_refused(client, db_session):
    enrollment = await enrolled(db_session, start=PAST)
    admin = await make_user(db_session, "it_admin", "it")
    await login(client, admin)
    bad = await client.patch(f"{API}/admin/enrollments/{enrollment.id}", json={"status": "on_hold"})
    assert bad.status_code == 422, bad.text
    assert (await client.patch(f"{API}/admin/enrollments/{enrollment.id}", json={"status": "withdrawn"})).status_code == 200
    assert await history(db_session, enrollment) == [(None, "closed", "enrolment", admin.id)]


async def test_an_application_move_writes_the_placement_transition(db_session):
    enrollment = await enrolled(db_session, start=PAST)
    student = await db_session.get(User, enrollment.student_id)
    row = await application(db_session, student, "selected")
    recruiter = await make_user(db_session, "placement_team", "it")
    await applications.change_status(db_session, recruiter, row, "joined", "Joined")
    await db_session.commit()
    assert await history(db_session, enrollment) == [(None, "placed", "placement", recruiter.id)]


async def test_the_daily_sweep_catches_transitions_no_writer_caused(db_session):
    enrollment = await enrolled(db_session, start=PAST)
    await it_at_risk.sweep(db_session, now=datetime.datetime.now(datetime.UTC))
    assert await history(db_session, enrollment) == [(None, "training_active", "daily_check", None)]


async def test_issuing_a_certificate_writes_the_completed_transition(client, db_session):
    from tests.test_nehn_031_certificate_workflow import BASE, _enrollment
    from tests.upc001_helpers import as_role

    enrollment = await _enrollment(db_session)  # a started batch, eligible (needs the seeded certificate signatories)
    coordinator = await as_role(client, db_session, "coordinator", "it")
    assert (await client.post(f"{BASE}/{enrollment.id}/issue", json={})).status_code == 201
    assert await history(db_session, enrollment) == [(None, "completed", "certificate", coordinator.id)]

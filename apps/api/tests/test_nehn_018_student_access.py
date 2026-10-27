"""nehn-018 -- student feature access by enrolment and payment status (DEC-SCOPE-304; spec
docs/superpowers/specs/2026-10-27-nehn-018-student-payment-access-design.md, RBAC_MATRIX §2.215): the derived payment state, the
admin-editable policy (AC4), `payment_required` on gated routes and the locked portal sections (AC1), unlock on the webhook (AC2) and
a partially paid student getting exactly the policy (AC3)."""

import datetime
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core import rbac
from app.models import AuditLog, Batch, Enrollment, LearningResource, LiveSession, Payment, Program, StoredFile, StudentAccessRule, User
from app.services import student_access
from tests.agn011_helpers import captured, razorpay_on, signed
from tests.bdm001_helpers import make_user
from tests.upc001_helpers import as_role, login

API = "/api/v1"
RULES = f"{API}/workflows/it/student-access/rules"
ACCESS = f"{API}/workflows/it/student/access"
FEATURES = ("attendance", "assignments", "assessments", "resources", "live_classes", "questions", "feedback", "certificates")


async def _batch(db) -> Batch:
    tag = uuid.uuid4().hex[:8]
    trainer = await make_user(db, "trainer", "it")
    program = Program(
        slug=f"n018-{tag}",
        title=f"N018 Programme {tag}",
        category="Testing",
        summary="-",
        duration="1 month",
        eligibility="-",
        fees=1000,
        certification="-",
        placement_assistance="-",
        trainer_name="-",
    )
    db.add(program)
    await db.flush()
    batch = Batch(
        program_id=program.id,
        trainer_id=trainer.id,
        name=f"N018-{tag}",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 2, 1),
        schedule="-",
        capacity=40,
        enrollment_open=True,
        status="active",
    )
    db.add(batch)
    await db.commit()
    return batch


async def _student(db, *, paid: tuple[float, ...] = (), owed: tuple[float, ...] = (), enrollment_status: str | None = "active", batch: Batch | None = None) -> User:
    """A fresh IT student; enrolled (unless `enrollment_status` is None) with one IT payment per amount in `paid` (paid) and `owed`."""
    student = await make_user(db, "it_student", "it")
    if enrollment_status:
        batch = batch or await _batch(db)
        db.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"N018-{uuid.uuid4().hex[:8]}", status=enrollment_status))
    for amount in paid:
        db.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", amount=amount, status="paid"))
    for amount in owed:
        db.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", amount=amount, status="pending"))
    await db.commit()
    return student


@pytest_asyncio.fixture
async def restore_policy(db_session):
    """The policy is one shared table: every test that changes it puts the default back."""
    yield
    for rule in (await db_session.scalars(select(StudentAccessRule))).all():
        rule.min_state = student_access.DEFAULT_MIN_STATE
    await db_session.commit()


# --- the derived state ------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "state"),
    [
        ({"enrollment_status": None}, "registered"),
        ({"enrollment_status": "rejected", "owed": (1000,)}, "registered"),
        ({"enrollment_status": "withdrawn"}, "registered"),
        ({"owed": (1000,)}, "enrolled_pending_payment"),
        ({"enrollment_status": "pending_consent", "owed": (1000,)}, "enrolled_pending_payment"),
        ({"paid": (500,), "owed": (500,)}, "partially_paid"),
        ({"paid": (1000,)}, "fully_paid"),
        ({}, "fully_paid"),  # a free course, or a student never billed
        ({"owed": (0,)}, "fully_paid"),  # a fee discounted to nothing
    ],
)
async def test_state(db_session, kwargs, state):
    student = await _student(db_session, **kwargs)
    assert await student_access.student_state(db_session, student.id) == state


@pytest.mark.asyncio
async def test_state_counts_overdue_and_ignores_refunds_and_other_divisions(db_session):
    student = await _student(db_session)
    db_session.add_all(
        [
            Payment(user_id=student.id, division="it", reference_type="enrollment_fee", amount=300, status="overdue"),
            Payment(user_id=student.id, division="it", reference_type="enrollment_fee", amount=300, status="refunded"),
            Payment(user_id=student.id, division="overseas", reference_type="service_fee", amount=300, status="paid"),
        ]
    )
    await db_session.commit()
    assert await student_access.student_state(db_session, student.id) == "enrolled_pending_payment"


def test_catalogue_entry_and_grant():
    assert rbac.CATALOGUE["student_access"]["actions"] == ("configure",)
    assert "student_access.configure" in rbac.DEFAULT_GRANTS["it_admin"]
    assert not any(k.startswith("student_access.") for role, keys in rbac.DEFAULT_GRANTS.items() if role != "it_admin" for k in keys)


# --- the student's own summary ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_summary_for_an_unpaid_student(client, db_session):
    await login(client, await _student(db_session, owed=(1000,)))
    body = (await client.get(ACCESS)).json()
    assert body["state"] == "enrolled_pending_payment"
    assert [f["key"] for f in body["features"]] == list(FEATURES)
    assert all(f["unlocked"] is False and f["required_state"] == "partially_paid" and f["label"] for f in body["features"])


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["trainer", "it_admin", "overseas_student"])
async def test_access_summary_is_the_it_students(client, db_session, role):
    await as_role(client, db_session, role, "overseas" if role == "overseas_student" else "it")
    assert (await client.get(ACCESS)).status_code == 403


# --- AC1: gated routes and locked sections ----------------------------------------------------------------------------------------


def _payment_required(response, feature: str):
    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "payment_required" and detail["feature"] == feature
    assert detail["required_state"] == "partially_paid" and detail["current_state"] == "enrolled_pending_payment"
    assert detail["message"].startswith("Complete your payment to unlock")
    assert detail["label"] == student_access.FEATURE_LABELS[feature]  # QA18-01: the web lock card names the feature


@pytest.mark.asyncio
async def test_an_unpaid_student_gets_payment_required(client, db_session):
    student = await _student(db_session, owed=(1000,))
    await login(client, student)
    w = f"{API}/workflows/it"
    _payment_required(await client.get(f"{w}/student/attendance"), "attendance")
    _payment_required(await client.post(f"{w}/student/attendance-corrections", json={}), "attendance")
    _payment_required(await client.post(f"{w}/assignments/{uuid.uuid4()}/submissions", data={}), "assignments")
    _payment_required(await client.post(f"{w}/assessments/{uuid.uuid4()}/attempts"), "assessments")
    _payment_required(await client.post(f"{w}/assessment-attempts/{uuid.uuid4()}/submit", json={"answers": {}}), "assessments")
    _payment_required(await client.get(f"{w}/student/questions"), "questions")
    _payment_required(await client.post(f"{w}/student/questions", json={}), "questions")
    _payment_required(await client.post(f"{w}/student/feedback", json={}), "feedback")
    _payment_required(await client.get(f"{API}/communications/it/live-sessions"), "live_classes")


@pytest.mark.asyncio
async def test_a_student_with_no_enrolment_is_told_to_enrol_not_to_pay(client, db_session):
    await login(client, await _student(db_session, enrollment_status=None))
    detail = (await client.get(f"{API}/workflows/it/student/questions")).json()["detail"]
    assert (detail["code"], detail["current_state"]) == ("payment_required", "registered")
    assert detail["message"] == "Enrol in a course to unlock Questions."


@pytest.mark.asyncio
async def test_material_and_certificate_downloads_check_ownership_first(client, db_session):
    batch = await _batch(db_session)
    stored = StoredFile(
        key=f"n018/{uuid.uuid4().hex}.pdf",
        purpose="learning_material",
        owner_id=batch.trainer_id,
        original_filename="notes.pdf",
        content_type="application/pdf",
        size_bytes=4,
        sha256="0" * 64,
    )
    db_session.add(stored)
    await db_session.flush()
    material = LearningResource(batch_id=batch.id, title="Notes", resource_type="pdf", stored_file_id=stored.id)
    db_session.add(material)
    await db_session.commit()
    url = f"{API}/workflows/it/materials/{material.id}/file"
    await login(client, await _student(db_session, owed=(1000,), batch=batch))
    _payment_required(await client.get(url), "resources")
    await login(client, await _student(db_session, owed=(1000,)))  # another batch's learner: still the plain 404, nothing confirmed
    assert (await client.get(url)).status_code == 404
    assert (await client.get(f"{API}/workflows/it/certificates/{uuid.uuid4()}/download")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("section", "feature"),
    [
        ("attendance", "attendance"),
        ("assignments", "assignments"),
        ("projects", "assignments"),
        ("examinations", "assessments"),
        ("downloads", "resources"),
        ("questions", "questions"),
        ("feedback", "feedback"),
        ("certificates", "certificates"),
    ],
)
async def test_locked_portal_section(client, db_session, section, feature):
    await login(client, await _student(db_session, owed=(1000,)))
    body = (await client.get(f"{API}/portal/it/student/{section}")).json()
    assert body["rows"] == [] and body["locked"]["feature"] == feature
    assert body["locked"]["required_state"] == "partially_paid" and body["locked"]["current_state"] == "enrolled_pending_payment" and body["locked"]["label"]


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["dashboard", "profile", "course", "fees", "support"])
async def test_course_and_fee_sections_stay_open(client, db_session, section):
    await login(client, await _student(db_session, owed=(1000,)))
    response = await client.get(f"{API}/portal/it/student/{section}")
    assert response.status_code == 200 and "locked" not in response.json()


@pytest.mark.asyncio
async def test_learning_payload_empties_locked_lists(client, db_session):
    await login(client, await _student(db_session, owed=(1000,)))
    body = (await client.get(f"{API}/workflows/it/student/learning")).json()
    assert body["access"]["state"] == "enrolled_pending_payment" and len(body["enrollments"]) == 1
    assert body["assignments"] == body["assessments"] == body["live_sessions"] == body["resources"] == body["certificates"] == []


@pytest.mark.asyncio
async def test_other_roles_are_unchanged(client, db_session):
    batch = await _batch(db_session)
    db_session.add(LiveSession(batch_id=batch.id, title="Intro", starts_at=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)))
    await db_session.commit()
    await login(client, await db_session.get(User, batch.trainer_id))
    response = await client.get(f"{API}/communications/it/live-sessions")
    assert response.status_code == 200 and any(s["title"] == "Intro" for s in response.json())


# --- AC2: the webhook unlocks the next request ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_payment_unlocks_without_signing_in_again(client, db_session, monkeypatch):
    razorpay_on(monkeypatch)
    student = await _student(db_session)
    order = f"order_{uuid.uuid4().hex[:14]}"
    db_session.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", amount=1000, status="pending", provider="razorpay", checkout_provider_order_id=order))
    await db_session.commit()
    await login(client, student)
    assert (await client.get(f"{API}/workflows/it/student/attendance")).status_code == 403
    raw, headers = signed(captured(order, 100_000))
    assert (await client.post(f"{API}/payments/webhooks/razorpay", content=raw, headers=headers)).json()["status"] == "paid"
    assert (await client.get(f"{API}/workflows/it/student/attendance")).status_code == 200  # same session cookie
    assert (await client.get(ACCESS)).json()["state"] == "fully_paid"


# --- AC3 + AC4: the policy --------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_reads_the_default_policy(client, db_session):
    await as_role(client, db_session, "it_admin", "it")
    body = (await client.get(RULES)).json()
    assert [r["feature"] for r in body["rules"]] == list(FEATURES) and {r["min_state"] for r in body["rules"]} == {"partially_paid"}
    assert [s["key"] for s in body["states"]] == list(student_access.STATES)


@pytest.mark.asyncio
async def test_admin_change_applies_immediately_and_is_audited(client, db_session, restore_policy):
    partial = await _student(db_session, paid=(500,), owed=(500,))
    admin = await as_role(client, db_session, "it_admin", "it")
    rules = {f: "partially_paid" for f in FEATURES} | {"attendance": "fully_paid", "feedback": "registered"}
    response = await client.put(RULES, json={"rules": rules})
    assert response.status_code == 200, response.text
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "student_access_rules.update", AuditLog.user_id == admin.id))
    assert audit.metadata_json["after"]["attendance"] == "fully_paid" and audit.metadata_json["before"]["attendance"] == "partially_paid"
    await login(client, partial)
    features = {f["key"]: f for f in (await client.get(ACCESS)).json()["features"]}
    assert features["attendance"]["unlocked"] is False and features["attendance"]["required_state"] == "fully_paid"
    assert features["questions"]["unlocked"] is True
    detail = (await client.get(f"{API}/workflows/it/student/attendance")).json()["detail"]
    assert (detail["required_state"], detail["current_state"]) == ("fully_paid", "partially_paid")
    assert (await client.get(f"{API}/workflows/it/student/questions")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rules",
    [
        {f: "partially_paid" for f in FEATURES if f != "feedback"},  # a feature left out
        {f: "partially_paid" for f in FEATURES} | {"attendance": "paid"},  # an unknown state
        {f: "partially_paid" for f in FEATURES} | {"placements": "fully_paid"},  # an unknown feature
    ],
)
async def test_policy_validation(client, db_session, rules, restore_policy):
    await as_role(client, db_session, "it_admin", "it")
    assert (await client.put(RULES, json={"rules": rules})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_student", "it"), ("trainer", "it"), ("coordinator", "it"), ("overseas_admin", "overseas")])
async def test_only_the_grant_reads_or_changes_the_policy(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(RULES)).status_code == 403
    assert (await client.put(RULES, json={"rules": {f: "registered" for f in FEATURES}})).status_code == 403

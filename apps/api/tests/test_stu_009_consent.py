"""STU-009 -- Digital agreement / consent (DATA_MODEL.md §3.4).

Covers: a booked slot is locked (holds capacity) immediately, but the enrolment itself
stays "pending_consent" -- not "active" -- until the student accepts the current
agreement (STU-009-AC02); accepting records a ConsentRecord and activates any pending
enrolment(s); acceptance is idempotent; RBAC is enforced at the API layer.
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Agreement, Batch, ConsentRecord, Enrollment, Program, User


async def _create_student(db_session) -> User:
    student = User(
        email=f"consent-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Consent Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _create_agreement(db_session, *, version: str = "v1") -> Agreement:
    agreement = Agreement(division="it", version=version, title=f"IT Programme Agreement {uuid.uuid4().hex[:6]}", body="Terms.", active=True)
    db_session.add(agreement)
    await db_session.commit()
    return agreement


async def _create_batch(db_session, *, capacity: int = 20) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"Consent Test Program {uuid.uuid4().hex[:6]}",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=10000,
        certification="Test cert",
        curriculum=["Module 1"],
        placement_assistance="Yes",
        trainer_name="Test Trainer",
        active=True,
    )
    db_session.add(program)
    await db_session.flush()
    batch = Batch(
        program_id=program.id,
        name=f"Batch-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm",
        capacity=capacity,
        enrollment_open=True,
        status="upcoming",
    )
    db_session.add(batch)
    await db_session.commit()
    return batch


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_new_enrollment_starts_pending_consent_not_active(client, db_session):
    student = await _create_student(db_session)
    batch = await _create_batch(db_session)
    await _login(client, student.email)

    response = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert response.status_code == 201
    assert response.json()["status"] == "pending_consent"

    enrollment = await db_session.scalar(select(Enrollment).where(Enrollment.student_id == student.id, Enrollment.batch_id == batch.id))
    assert enrollment.status == "pending_consent"


@pytest.mark.asyncio
async def test_pending_consent_enrollment_still_locks_capacity(client, db_session):
    """STU-009-AC02 must not weaken DEC-WF-002 -- an unconsented seat is still locked."""
    batch = await _create_batch(db_session, capacity=1)
    first = await _create_student(db_session)
    second = await _create_student(db_session)

    await _login(client, first.email)
    booked = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert booked.status_code == 201
    assert booked.json()["status"] == "pending_consent"

    await _login(client, second.email)
    rejected = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert rejected.status_code == 409


@pytest.mark.asyncio
async def test_current_agreement_reports_pending_enrollment_count(client, db_session):
    student = await _create_student(db_session)
    agreement = await _create_agreement(db_session)
    batch = await _create_batch(db_session)
    await _login(client, student.email)
    await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})

    response = await client.get("/api/v1/workflows/it/student/agreements/current")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(agreement.id)
    assert data["accepted"] is False
    assert data["pending_enrollments"] == 1


@pytest.mark.asyncio
async def test_accepting_activates_pending_enrollment_and_records_consent(client, db_session):
    student = await _create_student(db_session)
    agreement = await _create_agreement(db_session)
    batch = await _create_batch(db_session)
    await _login(client, student.email)
    await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})

    accept = await client.post(f"/api/v1/workflows/it/student/agreements/{agreement.id}/accept")
    assert accept.status_code == 201
    assert accept.json()["activated_enrollments"] == 1

    enrollment = await db_session.scalar(select(Enrollment).where(Enrollment.student_id == student.id, Enrollment.batch_id == batch.id))
    assert enrollment.status == "active"

    consent = await db_session.scalar(select(ConsentRecord).where(ConsentRecord.user_id == student.id, ConsentRecord.agreement_id == agreement.id))
    assert consent is not None
    assert consent.version == agreement.version


@pytest.mark.asyncio
async def test_accepting_twice_does_not_duplicate_the_consent_record(client, db_session):
    student = await _create_student(db_session)
    agreement = await _create_agreement(db_session)
    await _login(client, student.email)

    first = await client.post(f"/api/v1/workflows/it/student/agreements/{agreement.id}/accept")
    assert first.status_code == 201
    second = await client.post(f"/api/v1/workflows/it/student/agreements/{agreement.id}/accept")
    assert second.status_code == 201

    records = (await db_session.scalars(select(ConsentRecord).where(ConsentRecord.user_id == student.id, ConsentRecord.agreement_id == agreement.id))).all()
    assert len(records) == 1


@pytest.mark.asyncio
async def test_agreement_endpoints_require_authentication(client, db_session):
    agreement = await _create_agreement(db_session)
    assert (await client.get("/api/v1/workflows/it/student/agreements/current")).status_code == 401
    assert (await client.post(f"/api/v1/workflows/it/student/agreements/{agreement.id}/accept")).status_code == 401

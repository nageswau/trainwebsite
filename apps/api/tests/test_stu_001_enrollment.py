"""STU-001 -- Trainer/batch slot enrolment (DEC-WF-002).

Covers capacity-aware slot listing, booking, duplicate/full-slot rejection, and that
slot_locked is never client-controlled (server always locks on booking).
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Batch, Enrollment, Invoice, Payment, Program, User


async def _create_student(db_session) -> User:
    student = User(
        email=f"student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Slot Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _create_program_and_batch(db_session, *, capacity: int = 1, fees: float = 10000) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"Test Program {uuid.uuid4().hex[:6]}",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=fees,
        certification="Test cert",
        curriculum=["Module 1"],
        placement_assistance="Yes",
        trainer_name="Test Trainer",
        active=True,
    )
    db_session.add(program)
    await db_session.flush()
    import datetime

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


async def _login_as(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_available_batches_shows_real_remaining_capacity(client, db_session):
    student = await _create_student(db_session)
    batch = await _create_program_and_batch(db_session, capacity=20)
    await _login_as(client, student.email)

    response = await client.get("/api/v1/workflows/it/batches/available")
    assert response.status_code == 200
    listed = next((b for b in response.json() if b["id"] == str(batch.id)), None)
    assert listed is not None
    assert listed["available"] == 20


@pytest.mark.asyncio
async def test_booking_a_slot_locks_it_regardless_of_client_input(client, db_session):
    student = await _create_student(db_session)
    batch = await _create_program_and_batch(db_session, capacity=20)
    await _login_as(client, student.email)

    response = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert response.status_code == 201
    assert response.json()["enrollment_code"]

    enrollment = await db_session.scalar(select(Enrollment).where(Enrollment.student_id == student.id, Enrollment.batch_id == batch.id))
    assert enrollment.slot_locked is True


@pytest.mark.asyncio
async def test_booking_a_full_slot_is_rejected(client, db_session):
    batch = await _create_program_and_batch(db_session, capacity=1)
    first_student = await _create_student(db_session)
    second_student = await _create_student(db_session)

    await _login_as(client, first_student.email)
    first = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert first.status_code == 201

    await _login_as(client, second_student.email)
    second = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_duplicate_enrollment_in_same_batch_is_rejected(client, db_session):
    student = await _create_student(db_session)
    batch = await _create_program_and_batch(db_session, capacity=20)
    await _login_as(client, student.email)

    first = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert first.status_code == 201
    second = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_available_batches_and_enrollment_require_authentication(client):
    assert (await client.get("/api/v1/workflows/it/batches/available")).status_code == 401
    assert (await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(uuid.uuid4())})).status_code == 401


@pytest.mark.asyncio
async def test_full_batch_is_excluded_from_the_available_list(client, db_session):
    batch = await _create_program_and_batch(db_session, capacity=1)
    filler = await _create_student(db_session)
    await _login_as(client, filler.email)
    fill = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert fill.status_code == 201

    checker = await _create_student(db_session)
    await _login_as(client, checker.email)
    listing = await client.get("/api/v1/workflows/it/batches/available")
    assert all(b["id"] != str(batch.id) for b in listing.json())


@pytest.mark.asyncio
async def test_a_batch_the_student_already_booked_is_excluded_from_their_own_available_list(client, db_session):
    """RAID.md I-26: `create_enrollment` already 409s on a repeat booking of the same
    batch, but the batch stayed listed as "available" for the student who already
    booked it -- "Book this slot" was clickable for a batch already booked, producing a
    confusing 409 with no visible reason on the button click. Excluded here, matching
    the same rule the 409 itself already enforces."""
    batch = await _create_program_and_batch(db_session, capacity=20)
    student = await _create_student(db_session)
    await _login_as(client, student.email)

    booked = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert booked.status_code == 201

    listing = await client.get("/api/v1/workflows/it/batches/available")
    assert all(b["id"] != str(batch.id) for b in listing.json())


@pytest.mark.asyncio
async def test_a_batch_one_student_booked_still_shows_for_a_different_student(client, db_session):
    """The exclusion above is scoped to the caller's own enrolments -- it must never
    hide a batch (with remaining capacity) from anyone else."""
    batch = await _create_program_and_batch(db_session, capacity=20)
    booker = await _create_student(db_session)
    await _login_as(client, booker.email)
    booked = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert booked.status_code == 201

    other_student = await _create_student(db_session)
    await _login_as(client, other_student.email)
    listing = await client.get("/api/v1/workflows/it/batches/available")
    assert any(b["id"] == str(batch.id) for b in listing.json())


@pytest.mark.asyncio
async def test_enrolling_auto_creates_a_pending_fee_for_the_programs_own_amount(client, db_session):
    """Enrolling used to create nothing billable at all -- 'Fees' stayed empty until an
    Admin separately remembered to call `POST /admin/payments` by hand. The program's
    own listed fee is now billed the moment the seat is booked, same as any other
    Payment, invoice included."""
    batch = await _create_program_and_batch(db_session, capacity=20, fees=15000)
    student = await _create_student(db_session)
    await _login_as(client, student.email)

    response = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert response.status_code == 201
    enrollment_id = response.json()["id"]

    payment = await db_session.scalar(select(Payment).where(Payment.user_id == student.id, Payment.reference_type == "enrollment_fee"))
    assert payment is not None
    assert float(payment.amount) == 15000
    assert payment.status == "pending"
    assert str(payment.reference_id) == enrollment_id

    invoice = await db_session.scalar(select(Invoice).where(Invoice.payment_id == payment.id))
    assert invoice is not None

    mine = await client.get("/api/v1/payments/mine")
    assert mine.status_code == 200
    assert any(p["reference_type"] == "enrollment_fee" and p["amount"] == 15000.0 for p in mine.json())


@pytest.mark.asyncio
async def test_enrolling_in_a_free_program_bills_nothing(client, db_session):
    batch = await _create_program_and_batch(db_session, capacity=20, fees=0)
    student = await _create_student(db_session)
    await _login_as(client, student.email)

    response = await client.post("/api/v1/workflows/it/enrollments", json={"batch_id": str(batch.id)})
    assert response.status_code == 201

    payment = await db_session.scalar(select(Payment).where(Payment.user_id == student.id, Payment.reference_type == "enrollment_fee"))
    assert payment is None

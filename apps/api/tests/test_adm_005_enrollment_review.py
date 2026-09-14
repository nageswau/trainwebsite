"""ADM-005 -- Enrolment review and approval.

`API_CONTRACT.md` explicitly specifies dedicated `POST /admin/enrollments/{id}/approve` and
`.../reject` endpoints with rejection being terminal for that enrolment attempt -- neither
endpoint existed; only a generic, unguarded `PATCH` did. Covers: approve activates,
reject is terminal (a rejected enrolment can never be approved afterward, nor reactivated
via the generic PATCH either -- closing that back door), and RBAC.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Enrollment, Program, User


async def _create_admin(db_session) -> User:
    admin = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Enrolment Admin",
        role="it_admin",
        division="it",
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _create_enrollment(db_session, *, status: str = "pending_consent") -> Enrollment:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"ADM-005 Test Program {uuid.uuid4().hex[:6]}",
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
    student = User(
        email=f"student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Reviewed Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add_all([program, student])
    await db_session.flush()
    batch = Batch(
        program_id=program.id,
        name=f"Batch-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db_session.add(batch)
    await db_session.flush()
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status=status)
    db_session.add(enrollment)
    await db_session.commit()
    return enrollment


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_approves_an_enrollment_and_it_becomes_active(client, db_session):
    admin = await _create_admin(db_session)
    enrollment = await _create_enrollment(db_session, status="pending_consent")
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/admin/enrollments/{enrollment.id}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "active"


@pytest.mark.asyncio
async def test_admin_rejects_an_enrollment(client, db_session):
    admin = await _create_admin(db_session)
    enrollment = await _create_enrollment(db_session)
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/admin/enrollments/{enrollment.id}/reject", json={"reason": "Duplicate booking."})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_rejection_is_terminal_a_rejected_enrollment_cannot_be_approved(client, db_session):
    """ADM-005-AC02: rejected enrolment does not silently proceed to active."""
    admin = await _create_admin(db_session)
    enrollment = await _create_enrollment(db_session)
    await _login(client, admin.email)

    reject = await client.post(f"/api/v1/admin/enrollments/{enrollment.id}/reject", json={})
    assert reject.status_code == 200

    approve = await client.post(f"/api/v1/admin/enrollments/{enrollment.id}/approve")
    assert approve.status_code == 409

    await db_session.refresh(enrollment)
    assert enrollment.status == "rejected"


@pytest.mark.asyncio
async def test_rejection_is_terminal_the_generic_patch_cannot_reactivate_it_either(client, db_session):
    admin = await _create_admin(db_session)
    enrollment = await _create_enrollment(db_session)
    await _login(client, admin.email)

    reject = await client.post(f"/api/v1/admin/enrollments/{enrollment.id}/reject", json={})
    assert reject.status_code == 200

    patch = await client.patch(f"/api/v1/admin/enrollments/{enrollment.id}", json={"status": "active"})
    assert patch.status_code == 409

    await db_session.refresh(enrollment)
    assert enrollment.status == "rejected"


@pytest.mark.asyncio
async def test_approving_a_nonexistent_enrollment_404s(client, db_session):
    admin = await _create_admin(db_session)
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/admin/enrollments/{uuid.uuid4()}/approve")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_non_admin_cannot_approve_or_reject_enrollments(client, db_session):
    enrollment = await _create_enrollment(db_session)
    trainer = User(
        email=f"trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Not An Admin",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    await _login(client, trainer.email)

    assert (await client.post(f"/api/v1/admin/enrollments/{enrollment.id}/approve")).status_code == 403
    assert (await client.post(f"/api/v1/admin/enrollments/{enrollment.id}/reject", json={})).status_code == 403


@pytest.mark.asyncio
async def test_enrollment_review_requires_authentication(client):
    enrollment_id = uuid.uuid4()
    assert (await client.post(f"/api/v1/admin/enrollments/{enrollment_id}/approve")).status_code == 401
    assert (await client.post(f"/api/v1/admin/enrollments/{enrollment_id}/reject", json={})).status_code == 401

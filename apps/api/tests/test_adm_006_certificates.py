"""ADM-006 -- Certificate administration.

Issuance (`POST /workflows/it/certificates/{enrollment_id}/issue`) already existed and
already worked -- eligibility check, criteria snapshot, own-batch RBAC for a Trainer -- but
`ADM-006-AC02`'s own contract ("Requires override_reason... 422 without it") was not
enforced: an override only ever needed a bare boolean, with no written justification
captured anywhere. No Admin-facing UI to issue a certificate existed at all either -- only
a Trainer-side form under "student-progress" (`TRN`-adjacent, not this feature). Added the
`override_reason` requirement (durable on both the certificate's own `criteria_snapshot`
and the `AuditLog` entry) and an Admin-wide "certificates" portal section (`AdminCertificatePanel.tsx`).
Trainer access to the same shared issuance endpoint predates this feature (no approved
`TRN-*` Feature ID claims it, and it's already exercised by `STU-007`'s own test coverage)
-- left as-is rather than removed, since doing so would break already-shipped, tested
functionality on an interpretive reading of `ADM-006-AC03`'s "IT Admin" framing.
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import AuditLog, Batch, Certificate, Enrollment, Program, User


async def _create_admin(db_session, *, email_prefix: str = "adm006-admin") -> User:
    admin = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Certificate Admin",
        role="it_admin",
        division="it",
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _create_student(db_session) -> User:
    student = User(
        email=f"adm006-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Certificate Candidate",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _create_enrollment(db_session, student: User) -> Enrollment:
    trainer = User(
        email=f"adm006-trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Certificate Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.flush()
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"ADM-006 Test Program {uuid.uuid4().hex[:6]}",
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
        trainer_id=trainer.id,
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
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active", progress_percent=10)
    db_session.add(enrollment)
    await db_session.commit()
    await db_session.refresh(enrollment)
    return enrollment


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_issuing_before_criteria_met_requires_override_reason(db_session, client):
    admin = await _create_admin(db_session)
    student = await _create_student(db_session)
    enrollment = await _create_enrollment(db_session, student)
    await _login(client, admin.email)

    without_override = await client.post(f"/api/v1/workflows/it/certificates/{enrollment.id}/issue", json={})
    assert without_override.status_code == 409

    override_no_reason = await client.post(f"/api/v1/workflows/it/certificates/{enrollment.id}/issue", json={"override": True})
    assert override_no_reason.status_code == 422

    override_blank_reason = await client.post(f"/api/v1/workflows/it/certificates/{enrollment.id}/issue", json={"override": True, "override_reason": "   "})
    assert override_blank_reason.status_code == 422


@pytest.mark.asyncio
async def test_override_with_a_reason_issues_and_records_it_durably(db_session, client):
    admin = await _create_admin(db_session)
    student = await _create_student(db_session)
    enrollment = await _create_enrollment(db_session, student)
    await _login(client, admin.email)

    response = await client.post(
        f"/api/v1/workflows/it/certificates/{enrollment.id}/issue",
        json={"override": True, "override_reason": "Student completed an equivalent industry certification."},
    )
    assert response.status_code == 201
    certificate_id = response.json()["id"]

    certificate = await db_session.get(Certificate, certificate_id)
    assert certificate.criteria_snapshot["override_reason"] == "Student completed an equivalent industry certification."

    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_type == "certificate", AuditLog.entity_id == str(certificate_id)))
    assert audit is not None
    assert audit.metadata_json["override"] is True
    assert audit.metadata_json["override_reason"] == "Student completed an equivalent industry certification."


@pytest.mark.asyncio
async def test_admin_certificates_directory_lists_issued_certificates(db_session, client):
    admin = await _create_admin(db_session)
    student = await _create_student(db_session)
    enrollment = await _create_enrollment(db_session, student)
    await _login(client, admin.email)
    issue = await client.post(f"/api/v1/workflows/it/certificates/{enrollment.id}/issue", json={"override": True, "override_reason": "Manual review approved."})
    assert issue.status_code == 201

    listing = await client.get("/api/v1/portal/it/admin/certificates")
    assert listing.status_code == 200
    row = next(r for r in listing.json()["rows"] if r["number"] == issue.json()["certificate_no"])
    assert row["student"] == "Certificate Candidate"
    assert row["override"] == "Yes"


@pytest.mark.asyncio
async def test_non_admin_non_trainer_cannot_issue_a_certificate(db_session, client):
    student = await _create_student(db_session)
    enrollment = await _create_enrollment(db_session, student)
    await _login(client, student.email)

    response = await client.post(f"/api/v1/workflows/it/certificates/{enrollment.id}/issue", json={"override": True, "override_reason": "Self-approved"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_certificate_issuance_requires_authentication(client):
    response = await client.post(f"/api/v1/workflows/it/certificates/{uuid.uuid4()}/issue", json={})
    assert response.status_code == 401

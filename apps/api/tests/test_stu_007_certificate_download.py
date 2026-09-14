"""STU-007 -- Certificate download (PRD-STU-008).

Issuance (`ADM-006`) and the read-only listing (`GET /portal/it/student/certificates`)
already existed. The real gap: the listing's "file" column exposed the raw, permanently-
public `Certificate.file_url` through a generic table that only ever renders plain text
(never a working link) -- not the "signed, short-lived URL... never a public object
link" this feature's own contract (`API_CONTRACT.md`) calls for. Covers the new
`GET /workflows/it/certificates/{id}/download` endpoint: self-scoped signed download,
RBAC at the API layer (STU-007-AC03), and that a certificate that doesn't exist yet
(ineligible student) never confuses "unavailable" with an error (STU-007-AC02).
"""

import datetime
import secrets
import uuid

import pytest

from app.core.security import hash_password
from app.models import Certificate, Program, User


async def _create_student(db_session, *, email_prefix: str = "cert-student") -> User:
    student = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Certificate Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _create_admin(db_session) -> User:
    admin = User(
        email=f"cert-admin-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Certificate Admin",
        role="it_admin",
        division="it",
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _issue_certificate(db_session, student: User) -> Certificate:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"STU-007 Test Program {uuid.uuid4().hex[:6]}",
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
    certificate_no = f"EDU-CERT-TEST-{secrets.token_hex(4).upper()}"
    certificate = Certificate(
        student_id=student.id,
        program_id=program.id,
        certificate_no=certificate_no,
        verification_code=secrets.token_urlsafe(12),
        issued_on=datetime.date.today(),
        file_url=f"/local-files/certificates/{certificate_no}.pdf",
        status="issued",
    )
    db_session.add(certificate)
    await db_session.commit()
    await db_session.refresh(certificate)
    return certificate


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_student_lists_and_downloads_own_certificate(db_session, client):
    student = await _create_student(db_session)
    certificate = await _issue_certificate(db_session, student)

    await _login(client, student.email)
    listing = await client.get("/api/v1/portal/it/student/certificates")
    assert listing.status_code == 200
    row = next(r for r in listing.json()["rows"] if r["id"] == str(certificate.id))
    assert row["number"] == certificate.certificate_no
    assert "file" not in row  # no raw object link exposed through the generic table

    download = await client.get(f"/api/v1/workflows/it/certificates/{certificate.id}/download")
    assert download.status_code == 200
    body = download.json()
    assert body["url"] == f"/local-files/certificates/{certificate.certificate_no}.pdf"


@pytest.mark.asyncio
async def test_student_cannot_download_another_students_certificate(db_session, client):
    owner = await _create_student(db_session)
    other = await _create_student(db_session, email_prefix="cert-outsider")
    certificate = await _issue_certificate(db_session, owner)

    await _login(client, other.email)
    response = await client.get(f"/api/v1/workflows/it/certificates/{certificate.id}/download")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_download_any_certificate(db_session, client):
    student = await _create_student(db_session)
    admin = await _create_admin(db_session)
    certificate = await _issue_certificate(db_session, student)

    await _login(client, admin.email)
    response = await client.get(f"/api/v1/workflows/it/certificates/{certificate.id}/download")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_download_of_unknown_certificate_is_404_not_a_silent_failure(db_session, client):
    student = await _create_student(db_session)
    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/it/certificates/{uuid.uuid4()}/download")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_no_certificate_yet_shows_as_an_empty_list_not_an_error(db_session, client):
    """STU-007-AC02: before eligibility is met, no `Certificate` row exists at all --
    the student's own listing must show a clean empty state, never a broken response."""
    student = await _create_student(db_session)
    await _login(client, student.email)
    response = await client.get("/api/v1/portal/it/student/certificates")
    assert response.status_code == 200
    assert response.json()["rows"] == []


@pytest.mark.asyncio
async def test_certificate_download_requires_authentication(client):
    assert (await client.get(f"/api/v1/workflows/it/certificates/{uuid.uuid4()}/download")).status_code == 401

"""STU-011 -- Profile and document management (PRD-STU-012).

Profile field editing already existed and worked (`PATCH /auth/me`, inherently self-scoped
-- there is no id parameter to target another user with) but had zero test evidence
anywhere in the suite. Document management genuinely did not exist: `StudentDocument` is
Overseas-division-specific (FK to `overseas_applications`, gated to overseas roles), not
reusable for an IT student's own CV/portfolio uploads. Net-new `ProfileDocument` model
(alembic `0012`), `GET/POST /workflows/it/student/profile/documents`, and
`ProfileDocumentUpload.tsx`. Covers STU-011-AC01 (profile edit), STU-011-AC02 (invalid
type/size rejected with a clear error, not silently dropped), and STU-011-AC03 (self-scope
at the API layer).
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.models import ProfileDocument, User


async def _create_student(db_session, *, email_prefix: str = "profile-student") -> User:
    student = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Profile Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_student_edits_own_profile_fields(db_session, client):
    student = await _create_student(db_session)
    await _login(client, student.email)

    response = await client.patch("/api/v1/auth/me", json={"full_name": "Updated Name", "phone": "+91-9000000000", "profile": {"skills": ["Python", "SQL"]}})
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Updated Name"
    assert body["phone"] == "+91-9000000000"
    assert body["profile"]["skills"] == ["Python", "SQL"]


@pytest.mark.asyncio
async def test_student_uploads_and_lists_own_document(db_session, client):
    student = await _create_student(db_session)
    await _login(client, student.email)

    response = await client.post(
        "/api/v1/workflows/it/student/profile/documents",
        json={"document_type": "resume", "file_url": "/local-files/uploads/resume.pdf", "original_filename": "resume.pdf", "content_type": "application/pdf", "file_size": 1024},
    )
    assert response.status_code == 201

    listing = await client.get("/api/v1/workflows/it/student/profile/documents")
    assert listing.status_code == 200
    assert any(d["document_type"] == "resume" for d in listing.json())

    stored = await db_session.scalar(select(ProfileDocument).where(ProfileDocument.user_id == student.id))
    assert stored is not None
    assert stored.content_type == "application/pdf"


@pytest.mark.asyncio
async def test_disallowed_file_type_is_rejected_not_silently_dropped(db_session, client):
    student = await _create_student(db_session)
    await _login(client, student.email)

    response = await client.post(
        "/api/v1/workflows/it/student/profile/documents",
        json={"document_type": "resume", "file_url": "/local-files/uploads/malware.exe", "content_type": "application/x-msdownload", "file_size": 1024},
    )
    assert response.status_code == 415

    listing = await client.get("/api/v1/workflows/it/student/profile/documents")
    assert listing.json() == []


@pytest.mark.asyncio
async def test_oversized_file_is_rejected(db_session, client):
    student = await _create_student(db_session)
    await _login(client, student.email)

    response = await client.post(
        "/api/v1/workflows/it/student/profile/documents",
        json={"document_type": "resume", "file_url": "/local-files/uploads/huge.pdf", "content_type": "application/pdf", "file_size": settings.max_upload_bytes + 1},
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_document_listing_is_self_scoped(db_session, client):
    owner = await _create_student(db_session)
    other = await _create_student(db_session, email_prefix="profile-outsider")
    await _login(client, owner.email)
    await client.post(
        "/api/v1/workflows/it/student/profile/documents",
        json={"document_type": "resume", "file_url": "/local-files/uploads/resume.pdf", "content_type": "application/pdf", "file_size": 1024},
    )

    await _login(client, other.email)
    listing = await client.get("/api/v1/workflows/it/student/profile/documents")
    assert listing.status_code == 200
    assert listing.json() == []


@pytest.mark.asyncio
async def test_non_student_role_is_rejected(db_session, client):
    trainer = User(
        email=f"profile-trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Profile Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    await _login(client, trainer.email)

    response = await client.post(
        "/api/v1/workflows/it/student/profile/documents",
        json={"document_type": "resume", "file_url": "/local-files/uploads/resume.pdf", "content_type": "application/pdf", "file_size": 1024},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_document_upload_requires_authentication(client):
    response = await client.post(
        "/api/v1/workflows/it/student/profile/documents",
        json={"document_type": "resume", "file_url": "/local-files/uploads/resume.pdf", "content_type": "application/pdf", "file_size": 1024},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_student_downloads_their_own_document(db_session, client):
    """RAID.md I-16: the document list previously rendered as inert plain text -- no
    download action existed at all. Confirms the real fix, mirroring STU-007/OVS-005's
    own already-proven "exchange an id for a signed URL" pattern rather than trusting
    the stored `file_url` directly."""
    student = await _create_student(db_session)
    await _login(client, student.email)
    uploaded = await client.post(
        "/api/v1/workflows/it/student/profile/documents",
        json={"document_type": "resume", "file_url": "/local-files/uploads/resume.pdf", "original_filename": "resume.pdf", "content_type": "application/pdf", "file_size": 1024},
    )
    document_id = uploaded.json()["id"]

    response = await client.get(f"/api/v1/workflows/it/student/profile/documents/{document_id}/download")
    assert response.status_code == 200
    assert response.json()["url"]  # a real, signed download URL -- not the raw stored path


@pytest.mark.asyncio
async def test_a_students_document_cannot_be_downloaded_by_another_student(db_session, client):
    owner = await _create_student(db_session, email_prefix="profile-owner")
    outsider = await _create_student(db_session, email_prefix="profile-outsider2")
    await _login(client, owner.email)
    uploaded = await client.post(
        "/api/v1/workflows/it/student/profile/documents",
        json={"document_type": "resume", "file_url": "/local-files/uploads/resume.pdf", "content_type": "application/pdf", "file_size": 1024},
    )
    document_id = uploaded.json()["id"]

    await _login(client, outsider.email)
    response = await client.get(f"/api/v1/workflows/it/student/profile/documents/{document_id}/download")
    assert response.status_code == 404  # masks another student's document, doesn't confirm it exists


@pytest.mark.asyncio
async def test_downloading_an_unknown_document_404s(db_session, client):
    student = await _create_student(db_session)
    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/it/student/profile/documents/{uuid.uuid4()}/download")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_document_download_requires_authentication(client):
    response = await client.get(f"/api/v1/workflows/it/student/profile/documents/{uuid.uuid4()}/download")
    assert response.status_code == 401

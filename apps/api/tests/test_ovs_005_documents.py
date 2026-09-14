"""OVS-005 -- Document upload against checklist.

Upload (`POST /overseas/documents`, already using the real presign-then-upload flow via
`/files/presign`/`/files/local-upload`, least-privilege by construction) and verify
(`PATCH /overseas/documents/{id}/verify`, already correctly scoped to an assigned
Counselor) both already existed. The real, confirmed gap (`OVS-005` security note,
`OVS-DOC-02`): the student's own document list exposed the raw, permanently-public
`file_url` directly through the generic table -- the exact same gap shape already fixed
once for `STU-007`'s certificates. Added a self/assigned-scoped `GET
/overseas/documents/{id}/download` deriving a real download URL rather than trusting the
stored value directly. Unsupported file types/sizes are an explicit, confirmed open item
(`OVS-005-AC02`) and are deliberately not restricted here beyond the shared
`/files/presign` gate that already predates this feature.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import Country, OverseasApplication, StudentDocument, University, User


async def _create_user(db_session, role: str, **overrides) -> User:
    defaults = dict(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role}",
        role=role,
        division="overseas",
        active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _make_university(db_session) -> University:
    country = Country(
        slug=f"test-country-{uuid.uuid4().hex[:8]}", name="Testland", overview="", tuition="", living_expenses="",
        visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[],
    )
    db_session.add(country)
    await db_session.flush()
    university = University(
        country_id=country.id, slug=f"test-university-{uuid.uuid4().hex[:8]}", name="Test University", city="Testville",
        overview="", eligibility="", requirements=[], deadlines=[], scholarships=[],
    )
    db_session.add(university)
    await db_session.commit()
    return university


async def _make_application(db_session, student, university, counselor) -> OverseasApplication:
    application = OverseasApplication(student_id=student.id, university_id=university.id, counselor_id=counselor.id if counselor else None, intake="Fall 2027", status="enquiry")
    db_session.add(application)
    await db_session.commit()
    return application


async def _make_document(db_session, student, application=None, file_url="uploads/test-passport.pdf") -> StudentDocument:
    document = StudentDocument(student_id=student.id, application_id=application.id if application else None, document_type="Passport", file_url=file_url, verification_status="pending")
    db_session.add(document)
    await db_session.commit()
    return document


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_student_uploads_a_document_against_their_application(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)

    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/overseas/documents", json={"application_id": str(application.id), "document_type": "Passport", "file_url": "uploads/test.pdf"})
    assert response.status_code == 201
    assert response.json()["verification_status"] == "pending"


@pytest.mark.asyncio
async def test_assigned_counselor_verifies_a_document(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor)
    document = await _make_document(db_session, student, application)

    await _login(client, counselor.email)
    response = await client.patch(f"/api/v1/workflows/overseas/documents/{document.id}/verify", json={"verification_status": "verified", "notes": "Looks good"})
    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_an_unassigned_counselor_cannot_verify_the_document(client, db_session):
    university = await _make_university(db_session)
    assigned_counselor = await _create_user(db_session, "counselor")
    other_counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, assigned_counselor)
    document = await _make_document(db_session, student, application)

    await _login(client, other_counselor.email)
    response = await client.patch(f"/api/v1/workflows/overseas/documents/{document.id}/verify", json={"verification_status": "verified"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_owning_student_can_get_a_real_download_url(client, db_session):
    student = await _create_user(db_session, "overseas_student")
    document = await _make_document(db_session, student)

    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/overseas/documents/{document.id}/download")
    assert response.status_code == 200
    body = response.json()
    assert "url" in body and body["url"]


@pytest.mark.asyncio
async def test_a_different_student_cannot_download_the_document(client, db_session):
    student = await _create_user(db_session, "overseas_student")
    other_student = await _create_user(db_session, "overseas_student")
    document = await _make_document(db_session, student)

    await _login(client, other_student.email)
    response = await client.get(f"/api/v1/workflows/overseas/documents/{document.id}/download")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assigned_counselor_can_download_but_unassigned_counselor_cannot(client, db_session):
    university = await _make_university(db_session)
    assigned_counselor = await _create_user(db_session, "counselor")
    other_counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, assigned_counselor)
    document = await _make_document(db_session, student, application)

    await _login(client, assigned_counselor.email)
    ok = await client.get(f"/api/v1/workflows/overseas/documents/{document.id}/download")
    assert ok.status_code == 200

    await _login(client, other_counselor.email)
    denied = await client.get(f"/api/v1/workflows/overseas/documents/{document.id}/download")
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_download_url_normalizes_a_local_upload_path_to_the_same_resolvable_path(client, db_session):
    student = await _create_user(db_session, "overseas_student")
    document = await _make_document(db_session, student, file_url="/local-files/uploads/already-prefixed.pdf")

    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/overseas/documents/{document.id}/download")
    assert response.status_code == 200
    assert response.json()["url"] == "/local-files/uploads/already-prefixed.pdf"


@pytest.mark.asyncio
async def test_download_404s_for_an_unknown_document(client, db_session):
    student = await _create_user(db_session, "overseas_student")
    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/overseas/documents/{uuid.uuid4()}/download")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_document_download_requires_authentication(client, db_session):
    student = await _create_user(db_session, "overseas_student")
    document = await _make_document(db_session, student)
    response = await client.get(f"/api/v1/workflows/overseas/documents/{document.id}/download")
    assert response.status_code == 401

"""VISA-001 -- Visa checklist and documentation.

`POST`/`PATCH /overseas/visa` already existed but had two real, confirmed gaps. First, no
endpoint let the Student (the primary actor) view their own checklist at all -- both
existing endpoints are Counselor/Admin-only writes. Second, `status` accepted any
free-text value with zero validation against `DATA_MODEL.md` #6.5's contract-fixed stage
enum (`DEC-SCOPE-006`), and nothing enforced this feature's own error/edge behavior:
"an unverified document does not block viewing the checklist -- only advancing past the
stage that requires it" (`VISA-001-AC02`). Added a Self/Counselor-scoped `GET
/overseas/applications/{id}/visa-checklist` (merges the checklist with each item's real
document verification status, viewable unconditionally) and an enum + verification gate
on `update_visa`/`create_visa_case`.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import Country, OverseasApplication, StudentDocument, University, User, VisaCase


async def _create_user(db_session, role: str, **overrides) -> User:
    defaults = dict(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role}", role=role, division="overseas", active=True,
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


async def _make_visa_case(db_session, application, checklist=None) -> VisaCase:
    case = VisaCase(application_id=application.id, status="checklist", checklist=checklist or ["Passport", "Offer letter"])
    db_session.add(case)
    await db_session.commit()
    return case


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_student_views_checklist_even_with_unverified_documents(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)
    await _make_visa_case(db_session, application)

    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-checklist")
    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is True
    assert {item["item"] for item in body["checklist"]} == {"Passport", "Offer letter"}
    assert all(item["verification_status"] == "not_uploaded" for item in body["checklist"])


@pytest.mark.asyncio
async def test_a_different_student_cannot_view_the_checklist(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    other_student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)
    await _make_visa_case(db_session, application)

    await _login(client, other_student.email)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-checklist")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assigned_counselor_can_view_but_unassigned_counselor_cannot(client, db_session):
    university = await _make_university(db_session)
    assigned_counselor = await _create_user(db_session, "counselor")
    other_counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, assigned_counselor)
    await _make_visa_case(db_session, application)

    await _login(client, assigned_counselor.email)
    ok = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-checklist")
    assert ok.status_code == 200

    await _login(client, other_counselor.email)
    denied = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-checklist")
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_no_visa_case_yet_is_an_honest_empty_state_not_an_error(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)

    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-checklist")
    assert response.status_code == 200
    assert response.json() == {"exists": False, "status": None, "checklist": [], "appointment_date": None, "tracking_reference": None}


@pytest.mark.asyncio
async def test_setting_an_unsupported_stage_is_rejected(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor)
    case = await _make_visa_case(db_session, application)

    await _login(client, counselor.email)
    response = await client.patch(f"/api/v1/workflows/overseas/visa/{case.id}", json={"status": "approved"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_advancing_past_checklist_stage_with_an_unverified_document_is_rejected(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor)
    case = await _make_visa_case(db_session, application)
    db_session.add(StudentDocument(student_id=student.id, application_id=application.id, document_type="Passport", file_url="uploads/x.pdf", verification_status="verified"))
    await db_session.commit()
    # "Offer letter" was never uploaded at all -- still not verified.

    await _login(client, counselor.email)
    response = await client.patch(f"/api/v1/workflows/overseas/visa/{case.id}", json={"status": "documentation"})
    assert response.status_code == 422

    await db_session.refresh(case)
    assert case.status == "checklist"


@pytest.mark.asyncio
async def test_advancing_past_checklist_stage_succeeds_once_every_item_is_verified(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor)
    case = await _make_visa_case(db_session, application)
    for doc_type in ("Passport", "Offer letter"):
        db_session.add(StudentDocument(student_id=student.id, application_id=application.id, document_type=doc_type, file_url="uploads/x.pdf", verification_status="verified"))
    await db_session.commit()

    await _login(client, counselor.email)
    response = await client.patch(f"/api/v1/workflows/overseas/visa/{case.id}", json={"status": "documentation"})
    assert response.status_code == 200
    assert response.json()["status"] == "documentation"


@pytest.mark.asyncio
async def test_create_visa_case_rejects_an_unsupported_initial_status(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor)

    await _login(client, counselor.email)
    response = await client.post("/api/v1/workflows/overseas/visa", json={"application_id": str(application.id), "status": "approved"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_visa_checklist_requires_authentication(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-checklist")
    assert response.status_code == 401

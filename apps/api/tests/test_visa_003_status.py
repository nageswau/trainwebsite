"""VISA-003 -- Visa approval status tracking.

No dedicated `GET .../visa-status` endpoint existed at all -- `API_CONTRACT.md` #7 names
it as its own route, distinct from `VISA-001`'s checklist endpoint, and a Counselor had
no per-application status view (only the aggregate "Visa Tracking" table). Added a
Self/Counselor-scoped `GET /overseas/applications/{id}/visa-status`, reusing the same
scoping as `VISA-001`'s checklist endpoint. `VISA-003-AC02`'s compliance rule ("never
represent EduSphere as the visa decision-maker") is satisfied by a fixed, sourced
disclaimer string returned on every response -- verified directly here, never assumed.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import Country, OverseasApplication, University, User, VisaCase

FORBIDDEN_PHRASES = ["EduSphere has approved", "EduSphere approved", "EduSphere granted", "EduSphere decided", "EduSphere rejects", "we have approved your visa"]


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


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_student_views_own_visa_status_with_the_compliance_disclaimer(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)
    db_session.add(VisaCase(application_id=application.id, status="tracking", tracking_reference="TRK-001"))
    await db_session.commit()

    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-status")
    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is True
    assert body["status"] == "tracking"
    assert body["tracking_reference"] == "TRK-001"
    assert "EduSphere does not decide visa outcomes" in body["disclaimer"]


@pytest.mark.asyncio
async def test_no_forbidden_decision_maker_language_appears_anywhere_in_the_response(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)
    db_session.add(VisaCase(application_id=application.id, status="decision"))
    await db_session.commit()

    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-status")
    assert response.status_code == 200
    payload_text = str(response.json())
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in payload_text


@pytest.mark.asyncio
async def test_a_different_student_cannot_view_the_status(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    other_student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)
    db_session.add(VisaCase(application_id=application.id, status="checklist"))
    await db_session.commit()

    await _login(client, other_student.email)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-status")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assigned_counselor_can_view_but_unassigned_counselor_cannot(client, db_session):
    university = await _make_university(db_session)
    assigned_counselor = await _create_user(db_session, "counselor")
    other_counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, assigned_counselor)
    db_session.add(VisaCase(application_id=application.id, status="checklist"))
    await db_session.commit()

    await _login(client, assigned_counselor.email)
    ok = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-status")
    assert ok.status_code == 200

    await _login(client, other_counselor.email)
    denied = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-status")
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_no_visa_case_yet_is_an_honest_empty_state_with_the_disclaimer_still_present(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)

    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-status")
    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is False
    assert body["status"] is None
    assert "EduSphere does not decide visa outcomes" in body["disclaimer"]


@pytest.mark.asyncio
async def test_visa_status_requires_authentication(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/visa-status")
    assert response.status_code == 401

"""VISA-002 -- Visa interview preparation.

`API_CONTRACT.md` #7 names a dedicated `GET /overseas/visa/interview-prep` -- Self only
(no Counselor scope, unlike its `visa-checklist`/`visa-status` siblings), and not scoped
to one `application_id` (unlike them too) -- it returns one entry per the student's own
visa cases. No such endpoint existed at all before this feature. The actual interview-prep
*content* is a confirmed open item (`PRODUCT_DECISION_REGISTER.md` DEC-DATA-001/
DEC-SCOPE-006), so `Country.interview_prep` is nullable and a country with none returns an
explicit fallback (`available: false`), never a 500 (`VISA-002-AC02`).
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import Country, OverseasApplication, University, User, VisaCase


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


async def _make_university(db_session, *, interview_prep=None) -> University:
    country = Country(
        slug=f"test-country-{uuid.uuid4().hex[:8]}", name="Testland", overview="", tuition="", living_expenses="",
        visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[], interview_prep=interview_prep,
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


async def _make_application(db_session, student, university) -> OverseasApplication:
    application = OverseasApplication(student_id=student.id, university_id=university.id, intake="Fall 2027", status="enquiry")
    db_session.add(application)
    await db_session.commit()
    return application


async def _make_visa_case(db_session, application) -> VisaCase:
    case = VisaCase(application_id=application.id, status="checklist", checklist=["Passport"])
    db_session.add(case)
    await db_session.commit()
    return case


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_available_material_is_returned_for_the_students_own_case(client, db_session):
    university = await _make_university(db_session, interview_prep="Bring your passport and financial documents.")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university)
    await _make_visa_case(db_session, application)

    await _login(client, student.email)
    response = await client.get("/api/v1/workflows/overseas/visa/interview-prep")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["application_id"] == str(application.id)
    assert body[0]["available"] is True
    assert body[0]["content"] == "Bring your passport and financial documents."


@pytest.mark.asyncio
async def test_missing_material_is_an_explicit_fallback_not_a_500(client, db_session):
    university = await _make_university(db_session, interview_prep=None)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university)
    await _make_visa_case(db_session, application)

    await _login(client, student.email)
    response = await client.get("/api/v1/workflows/overseas/visa/interview-prep")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["available"] is False
    assert body[0]["content"] is None


@pytest.mark.asyncio
async def test_no_visa_case_yet_is_an_honest_empty_list_not_an_error(client, db_session):
    university = await _make_university(db_session, interview_prep="Some material.")
    student = await _create_user(db_session, "overseas_student")
    await _make_application(db_session, student, university)
    # No visa case created at all.

    await _login(client, student.email)
    response = await client.get("/api/v1/workflows/overseas/visa/interview-prep")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_a_different_student_never_sees_another_students_case(client, db_session):
    university = await _make_university(db_session, interview_prep="Some material.")
    student = await _create_user(db_session, "overseas_student")
    other_student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university)
    await _make_visa_case(db_session, application)

    await _login(client, other_student.email)
    response = await client.get("/api/v1/workflows/overseas/visa/interview-prep")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_counselor_role_is_rejected_self_only_per_contract(client, db_session):
    university = await _make_university(db_session, interview_prep="Some material.")
    student = await _create_user(db_session, "overseas_student")
    counselor = await _create_user(db_session, "counselor")
    application = await _make_application(db_session, student, university)
    await _make_visa_case(db_session, application)

    await _login(client, counselor.email)
    response = await client.get("/api/v1/workflows/overseas/visa/interview-prep")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_interview_prep_requires_authentication(client, db_session):
    response = await client.get("/api/v1/workflows/overseas/visa/interview-prep")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_interview_prep_is_never_exposed_through_the_public_country_endpoint(client, db_session):
    university = await _make_university(db_session, interview_prep="Confidential-ish prep content.")
    country = await db_session.get(Country, university.country_id)

    response = await client.get(f"/api/v1/public/countries/{country.slug}")
    assert response.status_code == 200
    assert "interview_prep" not in response.json()["country"]

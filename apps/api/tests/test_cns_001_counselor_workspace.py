"""CNS-001 -- Counselor workspace [base].

`PORTAL_NAV`'s Counselor workspace lists "Leads" and "Reports" among its sections, but
neither had a handler at all -- both 404'd with "Workspace not found" (confirmed
directly against the running stack before writing this fix). Added both, scoped to the
Counselor's own routed leads (`Enquiry.owner_id`, the same field `ADM-002` already lets
Admin set) and an aggregate of their own already-scoped caseload. Separately,
`CNS-001-AC02` ("a Counselor cannot act on a student who is not assigned to them, even
via a direct record ID") was violated by `POST /overseas/appointments` -- a Counselor
could schedule an appointment for *any* overseas student, not just their assigned ones
(unlike `add_document`, which already had the equivalent check). Fixed both.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import Country, Enquiry, OverseasApplication, StudentDocument, University, User, VisaCase


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


async def _make_application(db_session, student, university, counselor, status="enquiry") -> OverseasApplication:
    application = OverseasApplication(student_id=student.id, university_id=university.id, counselor_id=counselor.id if counselor else None, intake="Fall 2027", status=status)
    db_session.add(application)
    await db_session.commit()
    return application


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_counselor_leads_section_is_scoped_to_their_own_routed_enquiries(client, db_session):
    counselor = await _create_user(db_session, "counselor")
    other_counselor = await _create_user(db_session, "counselor")
    mine = Enquiry(division="overseas", name="Mine", email="mine@example.local", subject="Study in Canada", message="x", owner_id=counselor.id)
    others = Enquiry(division="overseas", name="Not mine", email="notmine@example.local", subject="Study in UK", message="x", owner_id=other_counselor.id)
    unrouted = Enquiry(division="overseas", name="Unrouted", email="unrouted@example.local", subject="Study in USA", message="x")
    db_session.add_all([mine, others, unrouted])
    await db_session.commit()

    await _login(client, counselor.email)
    response = await client.get("/api/v1/portal/overseas/counselor/leads")
    assert response.status_code == 200
    names = {row["name"] for row in response.json()["rows"]}
    assert names == {"Mine"}


@pytest.mark.asyncio
async def test_counselor_reports_section_aggregates_their_own_caseload(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor, status="eligibility_evaluation")
    db_session.add(StudentDocument(student_id=student.id, application_id=application.id, document_type="Passport", file_url="uploads/x.pdf", verification_status="pending"))
    db_session.add(VisaCase(application_id=application.id, status="checklist", checklist=["Passport"]))
    await db_session.commit()

    await _login(client, counselor.email)
    response = await client.get("/api/v1/portal/overseas/counselor/reports")
    assert response.status_code == 200
    body = response.json()
    metrics = {m["label"]: m["value"] for m in body["metrics"]}
    assert metrics["Assigned applications"] == 1
    assert metrics["Documents pending verification"] == 1
    assert metrics["Active visa cases"] == 1
    assert {"status": "eligibility_evaluation", "count": 1} in body["rows"]


@pytest.mark.asyncio
async def test_counselor_cannot_schedule_an_appointment_for_a_student_not_assigned_to_them(client, db_session):
    counselor = await _create_user(db_session, "counselor")
    unassigned_student = await _create_user(db_session, "overseas_student")

    await _login(client, counselor.email)
    response = await client.post("/api/v1/workflows/overseas/appointments", json={"student_id": str(unassigned_student.id), "scheduled_at": "2027-01-15T10:00:00", "appointment_type": "Career Counseling"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_counselor_can_schedule_an_appointment_for_their_own_assigned_student(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    await _make_application(db_session, student, university, counselor)

    await _login(client, counselor.email)
    response = await client.post("/api/v1/workflows/overseas/appointments", json={"student_id": str(student.id), "scheduled_at": "2027-01-15T10:00:00", "appointment_type": "Career Counseling"})
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_student_can_still_self_schedule_their_own_appointment(client, db_session):
    student = await _create_user(db_session, "overseas_student")
    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/overseas/appointments", json={"scheduled_at": "2027-01-15T10:00:00", "appointment_type": "Career Counseling"})
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_counselor_workspace_sections_require_authentication(client):
    for path in ("/api/v1/portal/overseas/counselor/leads", "/api/v1/portal/overseas/counselor/reports"):
        assert (await client.get(path)).status_code == 401

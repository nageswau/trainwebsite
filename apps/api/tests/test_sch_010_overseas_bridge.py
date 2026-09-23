"""SCH-010 -- School->Overseas bridge (`DEC-SCOPE-018`).

Overseas Admin/Counselor (never `school_coordinator`, per direct user decision) links a
School-affiliated student to a real Overseas application. `OverseasApplication.student_id`
is nullable specifically for this case; `school_student_id` is set instead, since a
`SchoolStudent` never gets a `users` row (`DEC-ROLE-004`). Status advance and `VisaCase`
work unchanged on a bridged application (both key off `application_id`/`counselor_id`,
never `User`); no bridged row ever leaks into an Overseas-student self-service listing
(those all inner-join `User` on `student_id`, which is NULL here). Net-new.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import Country, OverseasApplication, School, SchoolStudent, University, User, UserRoleAssignment, VisaCase

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school_with_coordinator(db_session) -> dict:
    admin = User(email=f"sch010-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"SCH-010 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id, tier="platinum")  # ENH-022: entitled to every service
    db_session.add(school)
    await db_session.flush()
    coordinator = User(email=f"sch010-coord-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Coordinator", role="school_coordinator", division="overseas", active=True, profile={"school_id": str(school.id)})
    db_session.add(coordinator)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    student = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Test Student", created_by_user_id=coordinator.id)
    db_session.add(student)
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "student": student}


async def _add_counselor(db_session, admin) -> User:
    counselor = User(email=f"sch010-counselor-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Counselor", role="counselor", division="overseas", active=True)
    db_session.add(counselor)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=counselor.id, division="overseas", role="counselor", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    await db_session.commit()
    return counselor


async def _make_university(db_session) -> University:
    country = Country(
        slug=f"sch010-country-{uuid.uuid4().hex[:8]}", name="Testland", overview="A test destination.",
        tuition="USD 20,000/year", living_expenses="USD 1,000/month", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[],
    )
    db_session.add(country)
    await db_session.flush()
    university = University(country_id=country.id, slug=f"sch010-university-{uuid.uuid4().hex[:8]}", name="Test University", city="Testville", overview="A test university.", eligibility="", requirements=[], deadlines=[], scholarships=[])
    db_session.add(university)
    await db_session.commit()
    return university


@pytest.mark.asyncio
async def test_school_coordinator_cannot_initiate_the_bridge(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    university = await _make_university(db_session)
    await _login(client, ctx["coordinator"].email)
    response = await client.post(f"/api/v1/overseas-admin/school-students/{ctx['student'].id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_counselor_can_initiate_the_bridge_via_student_id_lookup(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    counselor = await _add_counselor(db_session, ctx["admin"])
    university = await _make_university(db_session)
    await _login(client, counselor.email)

    lookup = await client.get(f"/api/v1/overseas-admin/school-students/lookup?code={ctx['student'].student_code}")
    assert lookup.status_code == 200
    assert lookup.json()["id"] == str(ctx["student"].id)

    response = await client.post(f"/api/v1/overseas-admin/school-students/{ctx['student'].id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "enquiry"

    application = await db_session.get(OverseasApplication, uuid.UUID(response.json()["id"]))
    assert application.student_id is None
    assert application.school_student_id == ctx["student"].id
    assert application.counselor_id == counselor.id


@pytest.mark.asyncio
async def test_overseas_admin_can_also_initiate_the_bridge(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    university = await _make_university(db_session)
    await _login(client, ctx["admin"].email)
    response = await client.post(f"/api/v1/overseas-admin/school-students/{ctx['student'].id}/applications", json={"university_id": str(university.id), "intake": "Spring 2028"})
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_duplicate_bridge_for_the_same_university_is_rejected(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    university = await _make_university(db_session)
    await _login(client, ctx["admin"].email)
    first = await client.post(f"/api/v1/overseas-admin/school-students/{ctx['student'].id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})
    assert first.status_code == 201
    duplicate = await client.post(f"/api/v1/overseas-admin/school-students/{ctx['student'].id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_status_advance_and_visa_case_work_unchanged_on_a_bridged_application(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    counselor = await _add_counselor(db_session, ctx["admin"])
    university = await _make_university(db_session)
    await _login(client, counselor.email)
    created = await client.post(f"/api/v1/overseas-admin/school-students/{ctx['student'].id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})
    application_id = created.json()["id"]

    advanced = await client.post(f"/api/v1/workflows/overseas/applications/{application_id}/advance", json={"to_status": "eligibility_evaluation"})
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["status"] == "eligibility_evaluation"

    visa = await client.post("/api/v1/workflows/overseas/visa", json={"application_id": application_id, "status": "checklist"})
    assert visa.status_code == 201, visa.text

    case = await db_session.scalar(select(VisaCase).where(VisaCase.application_id == uuid.UUID(application_id)))
    assert case is not None and case.status == "checklist"


@pytest.mark.asyncio
async def test_bridged_application_never_appears_in_overseas_student_self_service_listing(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    counselor = await _add_counselor(db_session, ctx["admin"])
    university = await _make_university(db_session)
    await _login(client, counselor.email)
    await client.post(f"/api/v1/overseas-admin/school-students/{ctx['student'].id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})

    listing = await client.get("/api/v1/workflows/overseas/applications")
    assert listing.status_code == 200
    assert listing.json() == []


@pytest.mark.asyncio
async def test_overseas_admin_school_applications_view_lists_the_bridged_row(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    counselor = await _add_counselor(db_session, ctx["admin"])
    university = await _make_university(db_session)
    await _login(client, counselor.email)
    await client.post(f"/api/v1/overseas-admin/school-students/{ctx['student'].id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})

    rows = await client.get("/api/v1/overseas-admin/school-applications")
    assert rows.status_code == 200
    assert len(rows.json()) == 1
    assert rows.json()[0]["student_code"] == ctx["student"].student_code

    other_counselor = await _add_counselor(db_session, ctx["admin"])
    await _login(client, other_counselor.email)
    scoped = await client.get("/api/v1/overseas-admin/school-applications")
    assert scoped.json() == []


@pytest.mark.asyncio
async def test_students_overview_reflects_the_bridged_application(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    counselor = await _add_counselor(db_session, ctx["admin"])
    university = await _make_university(db_session)
    await _login(client, counselor.email)
    await client.post(f"/api/v1/overseas-admin/school-students/{ctx['student'].id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})

    await _login(client, ctx["coordinator"].email)
    overview = await client.get(f"/api/v1/school/students/{ctx['student'].id}/overview")
    assert overview.status_code == 200
    global_education = overview.json()["global_education"]
    assert global_education["status"] == "linked"
    assert global_education["applications"][0]["university_name"] == university.name

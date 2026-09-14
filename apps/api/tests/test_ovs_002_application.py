"""OVS-002 -- Overseas application submission.

`POST /overseas/applications` already existed and already used the real
`University`/`OverseasCourse` catalogue, but had two real, confirmed gaps against the
approved contract: no duplicate-prevention at all (`OVS-002-AC02`,
`DATA_MODEL.md` #6.2's unique-constraint requirement), and an initial `status` value
("profile_evaluation") that predates `DATA_MODEL.md` #6.2's contract-fixed enum
(the sequence starts at "enquiry"). Both fixed in `apps/api/app/api/workflows.py`. The
frontend "applications" section also only offered a raw university/course UUID typed by
hand (same class of gap already fixed for `ADM-001`/`002`/`003`/`004`/`006`/`007`) --
replaced with a real picker, `OverseasApplyPanel.tsx`.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Country, OverseasApplication, OverseasCourse, University, User


async def _create_overseas_student(db_session, **overrides) -> User:
    defaults = dict(
        email=f"ovs-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Overseas Student",
        role="overseas_student",
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
        slug=f"test-country-{uuid.uuid4().hex[:8]}",
        name="Testland",
        overview="A test destination.",
        tuition="USD 20,000/year",
        living_expenses="USD 1,000/month",
        visa_process=[],
        work_opportunities="",
        post_study_work="",
        pr_opportunities="",
        faq=[],
    )
    db_session.add(country)
    await db_session.flush()
    university = University(
        country_id=country.id,
        slug=f"test-university-{uuid.uuid4().hex[:8]}",
        name="Test University",
        city="Testville",
        overview="A test university.",
        eligibility="",
        requirements=[],
        deadlines=[],
        scholarships=[],
    )
    db_session.add(university)
    await db_session.commit()
    return university


async def _make_course(db_session, university_id) -> OverseasCourse:
    course = OverseasCourse(
        university_id=university_id,
        title="MSc Test Engineering",
        level="Masters",
        category="Engineering",
        duration="2 years",
        tuition_fee="USD 25,000/year",
        intake="Fall",
    )
    db_session.add(course)
    await db_session.commit()
    return course


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_student_submits_application_and_it_enters_the_enquiry_stage(client, db_session):
    student = await _create_overseas_student(db_session)
    university = await _make_university(db_session)

    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/overseas/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "enquiry"

    stored = await db_session.get(OverseasApplication, uuid.UUID(body["id"]))
    assert stored.student_id == student.id
    assert stored.status == "enquiry"


@pytest.mark.asyncio
async def test_duplicate_application_for_same_university_and_course_is_rejected(client, db_session):
    student = await _create_overseas_student(db_session)
    university = await _make_university(db_session)
    course = await _make_course(db_session, university.id)

    await _login(client, student.email)
    first = await client.post("/api/v1/workflows/overseas/applications", json={"university_id": str(university.id), "course_id": str(course.id)})
    assert first.status_code == 201

    second = await client.post("/api/v1/workflows/overseas/applications", json={"university_id": str(university.id), "course_id": str(course.id)})
    assert second.status_code == 409

    count = (await db_session.execute(select(OverseasApplication).where(OverseasApplication.student_id == student.id, OverseasApplication.university_id == university.id))).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_a_different_course_at_the_same_university_is_not_a_duplicate(client, db_session):
    student = await _create_overseas_student(db_session)
    university = await _make_university(db_session)
    course_one = await _make_course(db_session, university.id)
    course_two = await _make_course(db_session, university.id)

    await _login(client, student.email)
    first = await client.post("/api/v1/workflows/overseas/applications", json={"university_id": str(university.id), "course_id": str(course_one.id)})
    assert first.status_code == 201
    second = await client.post("/api/v1/workflows/overseas/applications", json={"university_id": str(university.id), "course_id": str(course_two.id)})
    assert second.status_code == 201


@pytest.mark.asyncio
async def test_a_student_can_only_submit_for_themself_never_another_student(client, db_session):
    student = await _create_overseas_student(db_session)
    other_student = await _create_overseas_student(db_session)
    university = await _make_university(db_session)

    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/overseas/applications", json={"university_id": str(university.id), "student_id": str(other_student.id)})
    assert response.status_code == 201

    stored = await db_session.get(OverseasApplication, uuid.UUID(response.json()["id"]))
    assert stored.student_id == student.id
    assert stored.student_id != other_student.id


@pytest.mark.asyncio
async def test_unknown_university_404s(client, db_session):
    student = await _create_overseas_student(db_session)
    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/overseas/applications", json={"university_id": str(uuid.uuid4())})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_it_student_role_is_rejected(client, db_session):
    it_student = User(
        email=f"it-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="IT Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(it_student)
    await db_session.commit()
    university = await _make_university(db_session)

    login = await client.post("/api/v1/auth/login", json={"email": it_student.email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert login.status_code == 200
    response = await client.post("/api/v1/workflows/overseas/applications", json={"university_id": str(university.id)})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_application_creation_requires_authentication(client, db_session):
    university = await _make_university(db_session)
    response = await client.post("/api/v1/workflows/overseas/applications", json={"university_id": str(university.id)})
    assert response.status_code == 401

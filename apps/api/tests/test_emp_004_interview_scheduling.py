"""EMP-004 -- Interview scheduling and shortlist.

Net-new: `POST /employer/shortlist` creates a `JobApplication` (status "shortlisted")
against the Employer's own posting -- reusing the existing table rather than inventing a
parallel one, the same "extend, don't fork" precedent as `EMP-001`'s `Company` columns.
`POST /employer/interviews` creates an `Interview` against that application. Both are
scoped to the Employer's own postings even via a direct id (`EMP-004-AC03`). No
`duration` field exists anywhere on `Interview` to compute a true overlap window, so the
only honestly detectable scheduling conflict (`EMP-004-AC02`), without inventing an
assumed duration, is another interview for the same candidate at the exact same instant --
flagged with a 409, not silently double-booked.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Company, EmployerProfile, Job, JobApplication, User


async def _create_employer(db_session) -> tuple[User, Company]:
    user = User(
        email=f"emp004-employer-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Test Employer", role="employer", division="it", active=True,
    )
    db_session.add(user)
    await db_session.flush()
    company = Company(name=f"EMP-004 Test Co {uuid.uuid4().hex[:6]}", partner_type="employer", owner_type="employer_self_service", employer_user_id=user.id)
    db_session.add(company)
    await db_session.flush()
    db_session.add(EmployerProfile(user_id=user.id, company_id=company.id, registration_status=None))
    await db_session.commit()
    return user, company


async def _create_job(db_session, company: Company, status="open") -> Job:
    job = Job(company_id=company.id, title="Test Role", location="Remote", description="", skills=[], status=status)
    db_session.add(job)
    await db_session.commit()
    return job


async def _create_student(db_session) -> User:
    student = User(
        email=f"emp004-student-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Test Student", role="it_student", division="it", active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_employer_shortlists_a_candidate_for_their_own_posting(client, db_session):
    employer, company = await _create_employer(db_session)
    job = await _create_job(db_session, company)
    student = await _create_student(db_session)

    await _login(client, employer.email)
    response = await client.post("/api/v1/employer/shortlist", json={"job_id": str(job.id), "student_id": str(student.id)})
    assert response.status_code == 201
    assert response.json()["status"] == "shortlisted"


@pytest.mark.asyncio
async def test_shortlisting_the_same_candidate_twice_is_rejected(client, db_session):
    employer, company = await _create_employer(db_session)
    job = await _create_job(db_session, company)
    student = await _create_student(db_session)

    await _login(client, employer.email)
    await client.post("/api/v1/employer/shortlist", json={"job_id": str(job.id), "student_id": str(student.id)})
    response = await client.post("/api/v1/employer/shortlist", json={"job_id": str(job.id), "student_id": str(student.id)})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_employer_cannot_shortlist_against_another_employers_job(client, db_session):
    _, other_company = await _create_employer(db_session)
    other_job = await _create_job(db_session, other_company)
    employer, _ = await _create_employer(db_session)
    student = await _create_student(db_session)

    await _login(client, employer.email)
    response = await client.post("/api/v1/employer/shortlist", json={"job_id": str(other_job.id), "student_id": str(student.id)})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_employer_schedules_an_interview_for_a_shortlisted_candidate(client, db_session):
    employer, company = await _create_employer(db_session)
    job = await _create_job(db_session, company)
    student = await _create_student(db_session)
    application = JobApplication(job_id=job.id, student_id=student.id, status="shortlisted")
    db_session.add(application)
    await db_session.commit()

    await _login(client, employer.email)
    response = await client.post("/api/v1/employer/interviews", json={"application_id": str(application.id), "scheduled_at": "2027-02-01T10:00:00Z"})
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_a_scheduling_conflict_for_the_same_candidate_is_flagged_not_double_booked(client, db_session):
    employer, company = await _create_employer(db_session)
    job_a = await _create_job(db_session, company)
    job_b = await _create_job(db_session, company)
    student = await _create_student(db_session)
    application_a = JobApplication(job_id=job_a.id, student_id=student.id, status="shortlisted")
    application_b = JobApplication(job_id=job_b.id, student_id=student.id, status="shortlisted")
    db_session.add_all([application_a, application_b])
    await db_session.commit()

    await _login(client, employer.email)
    scheduled_at = "2027-02-01T10:00:00Z"
    first = await client.post("/api/v1/employer/interviews", json={"application_id": str(application_a.id), "scheduled_at": scheduled_at})
    assert first.status_code == 201
    second = await client.post("/api/v1/employer/interviews", json={"application_id": str(application_b.id), "scheduled_at": scheduled_at})
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_employer_cannot_schedule_an_interview_for_another_employers_application(client, db_session):
    _, other_company = await _create_employer(db_session)
    other_job = await _create_job(db_session, other_company)
    student = await _create_student(db_session)
    other_application = JobApplication(job_id=other_job.id, student_id=student.id, status="shortlisted")
    db_session.add(other_application)
    await db_session.commit()

    employer, _ = await _create_employer(db_session)
    await _login(client, employer.email)
    response = await client.post("/api/v1/employer/interviews", json={"application_id": str(other_application.id), "scheduled_at": "2027-02-01T10:00:00Z"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_employer_only_sees_their_own_scheduled_interviews(client, db_session):
    employer, company = await _create_employer(db_session)
    job = await _create_job(db_session, company)
    student = await _create_student(db_session)
    application = JobApplication(job_id=job.id, student_id=student.id, status="shortlisted")
    db_session.add(application)
    await db_session.commit()

    await _login(client, employer.email)
    await client.post("/api/v1/employer/interviews", json={"application_id": str(application.id), "scheduled_at": "2027-02-01T10:00:00Z"})

    other_employer, _ = await _create_employer(db_session)
    await _login(client, other_employer.email)
    response = await client.get("/api/v1/employer/interviews")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_non_employer_role_is_rejected(client, db_session):
    student = await _create_student(db_session)
    await _login(client, student.email)
    response = await client.post("/api/v1/employer/shortlist", json={"job_id": str(uuid.uuid4()), "student_id": str(student.id)})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_shortlist_requires_authentication(client):
    response = await client.post("/api/v1/employer/shortlist", json={"job_id": str(uuid.uuid4()), "student_id": str(uuid.uuid4())})
    assert response.status_code == 401

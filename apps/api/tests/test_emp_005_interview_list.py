"""EMP-005 -- Interview list and status.

`GET /employer/interviews` and `EmployerInterviewsPanel.tsx` already existed, built as
part of `EMP-004`'s own scheduling flow -- the backend already returns every interview
for the Employer's own company unconditionally (no `result`/status filter anywhere) and
is already correctly scoped via `company.id` (`EMP-005-AC03` confirmed by an existing
`EMP-004` test, `test_employer_only_sees_their_own_scheduled_interviews`). The real,
confirmed gap was entirely in the frontend: `EmployerInterviewsPanel.tsx`'s interview
cards rendered only `candidate`/`job_title`/`scheduled_at` -- `result` (and `mode`) were
fetched from the API but never displayed, so an Employer had no way to actually see an
interview's outcome, including whether one had been cancelled/resulted by Placement Team
via `PATCH /workflows/it/interviews/{id}` -- the data was never filtered out
(`EMP-005-AC02`'s "remain visible, not deleted" already held), but it was invisible.
Added the missing display; this file proves the backend property the UI now surfaces.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Company, EmployerProfile, Interview, Job, JobApplication, User


async def _create_user(db_session, *, role: str, division: str = "it", **overrides) -> User:
    defaults = dict(
        email=f"emp005-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role.title()}",
        role=role,
        division=division,
        active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _create_employer_with_company(db_session) -> tuple[User, Company]:
    employer = await _create_user(db_session, role="employer")
    company = Company(name=f"EMP-005 Test Co {uuid.uuid4().hex[:8]}", partner_type="employer", owner_type="employer_self_service", employer_user_id=employer.id)
    db_session.add(company)
    await db_session.flush()
    db_session.add(EmployerProfile(user_id=employer.id, company_id=company.id, registration_status=None))
    await db_session.commit()
    return employer, company


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_a_cancelled_interview_remains_visible_in_the_employers_list(db_session, client):
    employer, company = await _create_employer_with_company(db_session)
    job = Job(company_id=company.id, title="Backend Engineer", location="Remote", description="", skills=[], status="open")
    db_session.add(job)
    await db_session.flush()
    student = await _create_user(db_session, role="it_student")
    application = JobApplication(job_id=job.id, student_id=student.id, status="shortlisted")
    db_session.add(application)
    await db_session.flush()
    interview = Interview(application_id=application.id, scheduled_at=datetime.fromisoformat("2027-02-01T10:00:00+00:00"), mode="Online", result="cancelled")
    db_session.add(interview)
    await db_session.commit()

    await _login(client, employer.email)
    response = await client.get("/api/v1/employer/interviews")
    assert response.status_code == 200
    rows = response.json()
    matching = next(row for row in rows if row["id"] == str(interview.id))
    assert matching["result"] == "cancelled"


@pytest.mark.asyncio
async def test_interviews_with_no_result_yet_are_also_returned(db_session, client):
    employer, company = await _create_employer_with_company(db_session)
    job = Job(company_id=company.id, title="Frontend Engineer", location="Remote", description="", skills=[], status="open")
    db_session.add(job)
    await db_session.flush()
    student = await _create_user(db_session, role="it_student")
    application = JobApplication(job_id=job.id, student_id=student.id, status="shortlisted")
    db_session.add(application)
    await db_session.flush()
    interview = Interview(application_id=application.id, scheduled_at=datetime.fromisoformat("2027-03-01T10:00:00+00:00"), mode="Online")
    db_session.add(interview)
    await db_session.commit()

    await _login(client, employer.email)
    response = await client.get("/api/v1/employer/interviews")
    assert response.status_code == 200
    matching = next(row for row in response.json() if row["id"] == str(interview.id))
    assert matching["result"] is None


@pytest.mark.asyncio
async def test_a_non_employer_role_cannot_view_the_interview_list(db_session, client):
    student = await _create_user(db_session, role="it_student")
    await _login(client, student.email)
    response = await client.get("/api/v1/employer/interviews")
    assert response.status_code in {403, 404}


@pytest.mark.asyncio
async def test_interview_list_requires_authentication(client):
    response = await client.get("/api/v1/employer/interviews")
    assert response.status_code == 401

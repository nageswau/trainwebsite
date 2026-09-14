"""ADM-008 -- HR Team workspace.

Most of the underlying job/candidate/interview/offer machinery already existed and was
already shared correctly with `ADM-007`'s own RBAC. The real gap: HR Team's own main
workflow ("manages hiring requirements and shortlists") had no way to actually view a
specific hiring requirement's shortlist at all -- only a flat, job-agnostic candidate pool
and a flat list of requirements, with no bridge between the two. Added `GET
/workflows/it/jobs` (any status, for the requirement picker) and `GET
/workflows/it/jobs/{id}/shortlist` (the actual per-requirement shortlist), plus
`HrShortlistPanel.tsx`. Covers `ADM-008-AC02` directly: a requirement with no matching
candidates returns a clean empty list, never an error.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Company, Job, JobApplication, User


async def _create_staff(db_session, *, role: str = "hr_team") -> User:
    user = User(
        email=f"adm008-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="HR Staff",
        role=role,
        division="it",
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _create_job(db_session) -> Job:
    company = Company(name=f"Company {uuid.uuid4().hex[:6]}", partner_type="recruiter")
    db_session.add(company)
    await db_session.flush()
    job = Job(company_id=company.id, title="Backend Developer", location="Remote", description="Test", status="open")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


async def _create_student(db_session) -> User:
    student = User(
        email=f"adm008-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Job Candidate",
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
async def test_hr_team_lists_all_requirements_regardless_of_status(db_session, client):
    hr = await _create_staff(db_session)
    job = await _create_job(db_session)
    job.status = "closed"
    await db_session.commit()
    await _login(client, hr.email)

    response = await client.get("/api/v1/workflows/it/jobs")
    assert response.status_code == 200
    assert any(j["id"] == str(job.id) and j["status"] == "closed" for j in response.json())


@pytest.mark.asyncio
async def test_requirement_with_no_candidates_returns_empty_shortlist_not_an_error(db_session, client):
    hr = await _create_staff(db_session)
    job = await _create_job(db_session)
    await _login(client, hr.email)

    response = await client.get(f"/api/v1/workflows/it/jobs/{job.id}/shortlist")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_requirement_shortlist_lists_applicants(db_session, client):
    hr = await _create_staff(db_session)
    job = await _create_job(db_session)
    student = await _create_student(db_session)
    db_session.add(JobApplication(job_id=job.id, student_id=student.id, status="shortlisted"))
    await db_session.commit()
    await _login(client, hr.email)

    response = await client.get(f"/api/v1/workflows/it/jobs/{job.id}/shortlist")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["student"] == "Job Candidate"
    assert body[0]["status"] == "shortlisted"


@pytest.mark.asyncio
async def test_shortlist_for_unknown_job_is_404(db_session, client):
    hr = await _create_staff(db_session)
    await _login(client, hr.email)
    response = await client.get(f"/api/v1/workflows/it/jobs/{uuid.uuid4()}/shortlist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_job_requirements_portal_section_shows_the_closing_date(db_session, client):
    # Tester feedback (2026-09-04, RAID.md I-13): "add the close date on job
    # requirements". `Job.closes_on` was already collected by the create form and
    # already enforced server-side, but this portal table never displayed it back --
    # confirmed directly against the running app before this fix.
    hr = await _create_staff(db_session)
    job = await _create_job(db_session)
    job.closes_on = datetime.date(2027, 1, 31)
    await db_session.commit()
    await _login(client, hr.email)

    response = await client.get("/api/v1/portal/it/hr/job-requirements")
    assert response.status_code == 200
    row = next(r for r in response.json()["rows"] if r["id"] == str(job.id))
    assert row["closes_on"] == "2027-01-31"


@pytest.mark.asyncio
async def test_hr_can_update_a_requirements_closing_date(db_session, client):
    hr = await _create_staff(db_session)
    job = await _create_job(db_session)
    await _login(client, hr.email)

    response = await client.patch(f"/api/v1/workflows/it/jobs/{job.id}", json={"closes_on": "2027-06-30"})
    assert response.status_code == 200

    await db_session.refresh(job)
    assert job.closes_on == datetime.date(2027, 6, 30)


@pytest.mark.asyncio
async def test_non_staff_role_cannot_view_requirements_or_shortlists(db_session, client):
    student = await _create_student(db_session)
    job = await _create_job(db_session)
    await _login(client, student.email)

    assert (await client.get("/api/v1/workflows/it/jobs")).status_code == 403
    assert (await client.get(f"/api/v1/workflows/it/jobs/{job.id}/shortlist")).status_code == 403


@pytest.mark.asyncio
async def test_hr_endpoints_require_authentication(client):
    assert (await client.get("/api/v1/workflows/it/jobs")).status_code == 401
    assert (await client.get(f"/api/v1/workflows/it/jobs/{uuid.uuid4()}/shortlist")).status_code == 401

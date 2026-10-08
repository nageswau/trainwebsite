"""rec-017 -- the legacy student / placement / employer routes keep their paths and payloads but write through services/applications
(spec §3; AC3, AC4; DEC-SCOPE-134 A1, A2, A4)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Candidate, Company, Job, JobApplication, JobApplicationStatusHistory
from tests.rec001_helpers import login, make_user
from tests.rec017_helpers import student_application
from tests.test_emp_004_interview_scheduling import _create_employer, _create_job, _create_student
from tests.test_emp_004_interview_scheduling import _login as login_email

WF = "/api/v1/workflows/it"


async def _job(db) -> Job:
    company = Company(name=f"Legacy Co {uuid.uuid4().hex[:8]}")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title="Analyst", location="Remote", description="", skills=[], status="requirement_received")
    db.add(job)
    await db.commit()
    return job


async def _fresh(db, application_id) -> JobApplication:
    return await db.scalar(select(JobApplication).where(JobApplication.id == application_id).execution_options(populate_existing=True))


async def _trail(db, application_id) -> list[tuple]:
    rows = (await db.scalars(select(JobApplicationStatusHistory).where(JobApplicationStatusHistory.application_id == application_id).order_by(JobApplicationStatusHistory.created_at, JobApplicationStatusHistory.id))).all()
    return [(r.from_status, r.to_status) for r in rows]


@pytest.mark.asyncio
async def test_student_apply_creates_a_candidate_outside_the_pool_and_sources_the_application(client, db_session):
    job = await _job(db_session)
    student = await make_user(db_session, "it_student", "it")
    await login(client, student)
    response = await client.post(f"{WF}/jobs/{job.id}/apply", json={})
    assert response.status_code == 201 and response.json()["status"] == "sourced"
    application = await _fresh(db_session, uuid.UUID(response.json()["id"]))
    candidate = await db_session.get(Candidate, application.candidate_id)
    assert candidate.user_id == student.id and candidate.opted_in is False  # A4: the opt-in prompt is rec-010's
    assert application.student_id == student.id and application.added_by_user_id is None
    assert await _trail(db_session, application.id) == [(None, "sourced")]
    again = await client.post(f"{WF}/jobs/{job.id}/apply", json={})
    assert again.status_code == 409 and again.json()["detail"] == "Already applied"
    portal = await client.get("/api/v1/portal/it/student/job-applications")
    assert portal.status_code == 200, portal.text  # the student's own view shows the label
    assert [r["status"] for r in portal.json()["rows"]] == ["Sourced"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("word", "expected"), [("screening", "screened"), ("interview_scheduled", "interview"), ("offer_received", "selected"), ("profile_shared", "profile_shared")])
async def test_legacy_patch_maps_words_and_writes_history(client, db_session, word, expected):
    job = await _job(db_session)
    student = await make_user(db_session, "it_student", "it")
    application = await student_application(db_session, job.id, student)
    await db_session.commit()
    await login(client, await make_user(db_session, "placement_team", "it"))
    response = await client.patch(f"{WF}/job-applications/{application.id}", json={"status": word})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == expected
    assert await _trail(db_session, application.id) == [("sourced", expected)]


@pytest.mark.asyncio
async def test_legacy_patch_keeps_its_no_op_and_refuses_hired_without_an_offer(client, db_session):
    job = await _job(db_session)
    application = await student_application(db_session, job.id, await make_user(db_session, "it_student", "it"), "shortlisted")
    await db_session.commit()
    await login(client, await make_user(db_session, "hr_team", "it"))
    same = await client.patch(f"{WF}/job-applications/{application.id}", json={"status": "shortlisted"})
    assert same.status_code == 200 and await _trail(db_session, application.id) == []
    assert (await client.patch(f"{WF}/job-applications/{application.id}", json={"status": "hired"})).status_code == 409
    assert (await client.patch(f"{WF}/job-applications/{application.id}", json={"status": "bogus"})).status_code == 422


@pytest.mark.asyncio
async def test_interview_offer_flow_follows_a2(client, db_session):
    job = await _job(db_session)
    application = await student_application(db_session, job.id, await make_user(db_session, "it_student", "it"), "shortlisted")
    await db_session.commit()
    await login(client, await make_user(db_session, "placement_team", "it"))
    interview = await client.post(f"{WF}/interviews", json={"application_id": str(application.id), "scheduled_at": "2027-02-01T10:00:00+00:00"})
    assert interview.status_code == 201 and (await _fresh(db_session, application.id)).status == "interview"
    result = await client.patch(f"{WF}/interviews/{interview.json()['id']}", json={"result": "selected"})
    assert result.status_code == 200 and (await _fresh(db_session, application.id)).status == "selected"  # was "shortlisted" before A2
    offer = await client.post(f"{WF}/offers", json={"application_id": str(application.id), "compensation": 500000})
    assert offer.status_code == 201 and (await _fresh(db_session, application.id)).status == "selected"
    accepted = await client.patch(f"{WF}/offers/{offer.json()['id']}", json={"status": "accepted"})
    assert accepted.status_code == 200 and (await _fresh(db_session, application.id)).status == "joined"
    assert await _trail(db_session, application.id) == [("shortlisted", "interview"), ("interview", "selected"), ("selected", "joined")]


@pytest.mark.asyncio
async def test_a_side_effect_never_fails_where_it_used_to_succeed(client, db_session):
    job = await _job(db_session)
    application = await student_application(db_session, job.id, await make_user(db_session, "it_student", "it"), "rejected")
    await db_session.commit()
    await login(client, await make_user(db_session, "placement_team", "it"))
    interview = await client.post(f"{WF}/interviews", json={"application_id": str(application.id), "scheduled_at": "2027-02-02T10:00:00+00:00"})
    assert interview.status_code == 201 and (await _fresh(db_session, application.id)).status == "rejected"


@pytest.mark.asyncio
async def test_interview_result_rejected_rejects(client, db_session):
    job = await _job(db_session)
    application = await student_application(db_session, job.id, await make_user(db_session, "it_student", "it"), "interview")
    await db_session.commit()
    await login(client, await make_user(db_session, "placement_team", "it"))
    interview = await client.post(f"{WF}/interviews", json={"application_id": str(application.id), "scheduled_at": "2027-02-03T10:00:00+00:00"})
    await client.patch(f"{WF}/interviews/{interview.json()['id']}", json={"result": "rejected"})
    assert (await _fresh(db_session, application.id)).status == "rejected"


@pytest.mark.asyncio
async def test_employer_shortlist_links_the_candidate_and_interview_promotes_a_sourced_application(client, db_session):
    employer, company = await _create_employer(db_session)
    job = await _create_job(db_session, company)
    student = await _create_student(db_session)
    await login_email(client, employer.email)
    response = await client.post("/api/v1/employer/shortlist", json={"job_id": str(job.id), "student_id": str(student.id)})
    assert response.status_code == 201 and response.json()["status"] == "shortlisted"
    application = await _fresh(db_session, uuid.UUID(response.json()["id"]))
    assert (await db_session.get(Candidate, application.candidate_id)).user_id == student.id
    listing = (await client.get("/api/v1/employer/shortlist")).json()
    assert [(r["status"], r["status_label"]) for r in listing] == [("shortlisted", "Shortlisted")]

    other = await _create_student(db_session)
    applied = await student_application(db_session, job.id, other)  # a student self-application (Sourced)
    await db_session.commit()
    scheduled = await client.post("/api/v1/employer/interviews", json={"application_id": str(applied.id), "scheduled_at": "2027-04-01T10:00:00Z"})
    assert scheduled.status_code == 201 and (await _fresh(db_session, applied.id)).status == "shortlisted"


@pytest.mark.asyncio
async def test_hr_shortlist_shows_the_label(client, db_session):
    job = await _job(db_session)
    await student_application(db_session, job.id, await make_user(db_session, "it_student", "it"), "interview")
    await db_session.commit()
    await login(client, await make_user(db_session, "hr_team", "it"))
    rows = (await client.get(f"{WF}/jobs/{job.id}/shortlist")).json()
    assert [(r["status"], r["status_label"]) for r in rows] == [("interview", "Interview")]

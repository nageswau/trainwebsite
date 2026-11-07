"""hrc-001 (DEC-SCOPE-371, spec docs/superpowers/specs/2026-11-04-hrc-001-access-control-hardening-design.md): the legacy IT placement
writes use the recruiter record scope (H1), candidate compensation follows the `candidates.compensation.view` grant (H2), interview
outcomes stay off student and employer screens (H3), recruitment documents leave only through their own routes (H4), and no student,
employer or anonymous route returns feedback, screening, notes, compensation or an unreleased result (H5)."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models import (
    ApplicationScreening,
    Candidate,
    CandidateSkill,
    Company,
    Interview,
    InterviewFeedback,
    Job,
    JobApplication,
    JobOffer,
    ScreeningAnswer,
    ScreeningForm,
    ScreeningFormQuestion,
    ScreeningSession,
    Skill,
    SkillCategory,
    UserPermissionOverride,
)
from app.services import permissions
from tests.rec038_helpers import add, core, headers, tag

pytestmark = pytest.mark.asyncio
SENTINEL_RESULT = "hrc001-secret-outcome"
SENTINEL_TEXT = "hrc001-internal-text"
SALARY = Decimal("987654.00")


async def _world(client, db):
    world = await core(client, db)
    candidate = await db.get(Candidate, UUID(world["candidate"]))
    candidate.current_salary, candidate.expected_salary, candidate.experience_months = Decimal("876543.00"), SALARY, 12
    await db.commit()
    return world


async def _deny(db, user, resource="candidates.compensation", action="view"):
    await add(db, UserPermissionOverride(user_id=user.id, resource=resource, action=action, effect="deny", reason="hrc-001 test"))
    await db.commit()


def _u(world, role):
    return headers(world["users"][role])


# --- H1: legacy writes -----------------------------------------------------------------------------------------------------------------
async def _interview(db, world) -> Interview:
    return await add(db, Interview(application_id=UUID(world["application"]), scheduled_at=datetime.now(UTC) + timedelta(days=2), mode="Online"))


async def _offer(db, world) -> JobOffer:
    return await add(db, JobOffer(application_id=UUID(world["application"]), status="offer_pending", currency="INR", created_by_user_id=world["users"]["rec"].id))


async def test_out_of_scope_recruiter_gets_404_on_every_legacy_write(client, db_session):
    world = await _world(client, db_session)
    interview, offer = await _interview(db_session, world), await _offer(db_session, world)
    await db_session.commit()
    out = _u(world, "rec_out")
    base = "/api/v1/workflows/it"
    calls = [
        ("patch", f"{base}/jobs/{world['requirement']}", {"closes_on": "2031-01-31"}),
        ("patch", f"{base}/job-applications/{world['application']}", {"status": "screened"}),
        ("post", f"{base}/interviews", {"application_id": world["application"], "scheduled_at": "2031-03-01T10:00:00+00:00"}),
        ("patch", f"{base}/interviews/{interview.id}", {"result": "selected"}),
        ("post", f"{base}/offers", {"application_id": world["application"]}),
        ("patch", f"{base}/offers/{offer.id}", {"currency": "USD"}),
        ("post", f"{base}/jobs", {"company_id": world["company"], "title": "Ops"}),
    ]
    for method, path, body in calls:
        response = await getattr(client, method)(path, json=body, headers=out)
        assert response.status_code == 404, (path, response.status_code, response.text)
    await db_session.refresh(interview)
    assert interview.result is None


async def test_existing_company_by_name_out_of_scope_is_404(client, db_session):
    world = await _world(client, db_session)
    company = await db_session.get(Company, UUID(world["company"]))
    response = await client.post("/api/v1/workflows/it/jobs", json={"company_name": company.name, "title": "Ops"}, headers=_u(world, "rec_out"))
    assert response.status_code == 404


async def test_in_scope_recruiter_still_writes(client, db_session):
    world = await _world(client, db_session)
    rec = _u(world, "rec")
    response = await client.patch(f"/api/v1/workflows/it/jobs/{world['requirement']}", json={"closes_on": "2031-01-31"}, headers=rec)
    assert response.status_code == 200
    response = await client.patch(f"/api/v1/workflows/it/job-applications/{world['application']}", json={"status": "screened"}, headers=rec)
    assert response.status_code == 200, response.text
    response = await client.post("/api/v1/workflows/it/interviews", json={"application_id": world["application"], "scheduled_at": "2031-03-01T10:00:00+00:00"}, headers=rec)
    assert response.status_code == 201, response.text


async def test_recruiter_owns_the_requirement_and_company_they_create(client, db_session):
    world = await _world(client, db_session)
    rec = world["users"]["rec"]
    response = await client.post("/api/v1/workflows/it/jobs", json={"company_name": f"HRC Co {tag()}", "title": "Ops"}, headers=headers(rec))
    assert response.status_code == 201, response.text
    job = await db_session.get(Job, UUID(response.json()["id"]))
    company = await db_session.get(Company, job.company_id)
    assert job.assigned_recruiter_user_id == rec.id and company.assigned_recruiter_user_id == rec.id
    assert (await client.patch(f"/api/v1/workflows/it/jobs/{job.id}", json={"closes_on": "2031-01-31"}, headers=headers(rec))).status_code == 200


async def test_hr_no_longer_writes_and_it_admin_keeps_it_wide_access(client, db_session):
    world = await _world(client, db_session)
    path = f"/api/v1/workflows/it/jobs/{world['requirement']}"
    assert (await client.patch(path, json={"closes_on": "2031-01-31"}, headers=_u(world, "hr"))).status_code == 403
    assert (await client.patch(path, json={"closes_on": "2031-02-28"}, headers=_u(world, "it_admin"))).status_code == 200
    assert (await client.patch(path, json={"closes_on": "2031-03-31"}, headers=_u(world, "super"))).status_code == 200


# --- H2: compensation ------------------------------------------------------------------------------------------------------------------
async def test_default_grant_holders(db_session):
    for role, expected in (("placement_team", True), ("placement_manager", True), ("hr_team", False), ("bdm", False), ("it_admin", False)):
        assert await permissions.has_grant(db_session, role, "candidates.compensation", "view") is expected, role


async def test_candidate_detail_hides_salary_without_the_grant(client, db_session):
    world = await _world(client, db_session)
    path = f"/api/v1/recruiter/candidates/{world['candidate']}"
    shown = (await client.get(path, headers=_u(world, "rec"))).json()
    assert Decimal(shown["expected_salary"]) == SALARY and "current_salary" in shown
    hidden = await client.get(path, headers=_u(world, "hr"))
    assert hidden.status_code == 200
    assert "current_salary" not in hidden.json() and "expected_salary" not in hidden.json()
    assert "987654" not in hidden.text and "876543" not in hidden.text


async def test_a_denied_writer_cannot_send_salary_and_keeps_the_stored_one(client, db_session):
    world = await _world(client, db_session)
    await _deny(db_session, world["users"]["rec"])
    path = f"/api/v1/recruiter/candidates/{world['candidate']}"
    assert (await client.patch(path, json={"expected_salary": "1"}, headers=_u(world, "rec"))).status_code == 403
    response = await client.patch(path, json={"notice_days": 30}, headers=_u(world, "rec"))
    assert response.status_code == 200 and "expected_salary" not in response.json()
    candidate = await db_session.get(Candidate, UUID(world["candidate"]))
    await db_session.refresh(candidate)
    assert candidate.expected_salary == SALARY and candidate.notice_days == 30


async def test_a_denied_writer_cannot_create_with_salary(client, db_session):
    world = await _world(client, db_session)
    await _deny(db_session, world["users"]["rec"])
    candidate = await db_session.get(Candidate, UUID(world["candidate"]))
    body = {"name": "Asha Rao", "email": f"{tag('hrc-')}@example.com", "source_id": str(candidate.source_id), "current_salary": "5"}
    assert (await client.post("/api/v1/recruiter/candidates", json=body, headers=_u(world, "rec"))).status_code == 403


async def test_search_cards_and_salary_filter_follow_the_grant(client, db_session):
    world = await _world(client, db_session)
    category = await db_session.scalar(select(SkillCategory.id).where(SkillCategory.name == "Programming"))
    skill = await add(db_session, Skill(name=f"Kotlin {tag()}", category_id=category))
    await add(db_session, CandidateSkill(candidate_id=UUID(world["candidate"]), skill_id=skill.id, level="advanced", added_by_user_id=world["users"]["rec"].id, status="claimed"))
    await db_session.commit()
    search = {"all": [skill.name]}
    shown = await client.post("/api/v1/recruiter/candidates/search", json=search, headers=_u(world, "rec"))
    assert shown.status_code == 200 and [Decimal(str(i["expected_salary"])) for i in shown.json()["items"]] == [SALARY], shown.text
    hidden = await client.post("/api/v1/recruiter/candidates/search", json=search, headers=_u(world, "hr"))
    assert hidden.status_code == 200 and len(hidden.json()["items"]) == 1 and "expected_salary" not in hidden.json()["items"][0]
    for extra in ({"salary_min": 900000}, {"salary_max": 990000}):
        body = {**search, **extra}
        assert (await client.post("/api/v1/recruiter/candidates/search", json=body, headers=_u(world, "hr"))).status_code == 403
        assert (await client.post("/api/v1/recruiter/candidates/search", json=body, headers=_u(world, "rec"))).status_code == 200


async def test_pool_cards_hide_salary_without_the_grant(client, db_session):
    world = await _world(client, db_session)
    created = await client.post("/api/v1/recruiter/pools", json={"name": f"Pool {tag()}", "experience_min_months": 0}, headers=_u(world, "mgr"))
    assert created.status_code == 201, created.text
    path = f"/api/v1/recruiter/pools/{created.json()['id']}/candidates"
    assert any("expected_salary" in item for item in (await client.get(path, headers=_u(world, "rec"))).json()["items"])
    hidden = await client.get(path, headers=_u(world, "hr"))
    assert hidden.status_code == 200 and hidden.json()["items"] and all("expected_salary" not in item for item in hidden.json()["items"])


async def test_screening_salary_follows_the_grant(client, db_session):
    world = await _world(client, db_session)
    application_id = UUID(world["application"])
    await add(db_session, ApplicationScreening(application_id=application_id, screened_by_user_id=world["users"]["rec"].id, expected_salary=SALARY, result="hold"))
    await db_session.commit()
    path = f"/api/v1/recruiter/applications/{application_id}/screening"
    assert (await client.get(path, headers=_u(world, "rec"))).json()["screening"]["expected_salary"] == float(SALARY)
    bdm = await client.get(path, headers=_u(world, "bdm"))
    assert bdm.status_code == 200 and "expected_salary" not in bdm.json()["screening"]
    await _deny(db_session, world["users"]["rec"])
    assert (await client.put(path, json={"result": "hold", "expected_salary": 1}, headers=_u(world, "rec"))).status_code == 403
    saved = await client.put(path, json={"result": "hold", "notice_days": 15}, headers=_u(world, "rec"))
    assert saved.status_code == 200, saved.text
    assert "expected_salary" not in saved.json()["screening"]
    row = await db_session.scalar(select(ApplicationScreening).where(ApplicationScreening.application_id == application_id).execution_options(populate_existing=True))
    assert row.expected_salary == SALARY and row.notice_days == 15


# --- H3 + H5: what students, employers and anonymous callers can read ----------------------------------------------------------------
async def _student_world(client, db):
    """The student's own application on the world's requirement, with every internal value set to a sentinel."""
    world = await _world(client, db)
    student, rec = world["users"]["student"], world["users"]["rec"]
    student_candidate = await db.get(Candidate, UUID(world["student_candidate"]))
    student_candidate.current_salary, student_candidate.expected_salary = SALARY, SALARY
    application = await add(db, JobApplication(job_id=UUID(world["requirement"]), candidate_id=student_candidate.id, student_id=student.id, added_by_user_id=rec.id, status="interview"))
    interview = await add(db, Interview(application_id=application.id, scheduled_at=datetime.now(UTC) - timedelta(days=1), mode="Online", result=SENTINEL_RESULT, status="selected", round="final_round"))
    await add(db, InterviewFeedback(interview_id=interview.id, recorded_by_user_id=rec.id, overall_rating=4, recruiter_comments=SENTINEL_TEXT, strengths=SENTINEL_TEXT, final_decision="selected"))
    await add(db, ApplicationScreening(application_id=application.id, screened_by_user_id=rec.id, expected_salary=SALARY, remarks=SENTINEL_TEXT, result="shortlisted"))
    # pob-020: a screening session's notes, answer and salary answer must stay as private as the checklist
    form = await add(db, ScreeningForm(job_id=application.job_id, name=SENTINEL_TEXT))
    question = await add(db, ScreeningFormQuestion(form_id=form.id, version=1, position=1, category="compensation", question=SENTINEL_TEXT, format="text"))
    session = await add(db, ScreeningSession(application_id=application.id, kind="form", form_id=form.id, form_version=1, screened_by_user_id=rec.id, notes=SENTINEL_TEXT, recommendation="pass"))
    await add(db, ScreeningAnswer(session_id=session.id, form_question_id=question.id, answer=SENTINEL_TEXT, score=5))
    await db.commit()
    return world, application, interview


FORBIDDEN_KEYS = {"result", "feedback", "feedbacks", "screening", "remarks", "recruiter_comments", "strengths", "weaknesses", "final_decision", "current_salary", "expected_salary", "notes", "scorecard", "recommendation", "sessions", "answers"}


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_keys(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_keys(v) for v in value)) if value else set()
    return set()


def _no_leak(response, path):
    assert response.status_code == 200, (path, response.status_code, response.text)
    text = response.text
    assert SENTINEL_RESULT not in text and SENTINEL_TEXT not in text and "987654" not in text, path
    assert not (_keys(response.json()) & FORBIDDEN_KEYS), (path, _keys(response.json()) & FORBIDDEN_KEYS)


async def test_student_routes_leak_nothing(client, db_session):
    world, _application, _interview = await _student_world(client, db_session)
    student = _u(world, "student")
    for path in ("/api/v1/portal/it/student/interview-schedule", "/api/v1/portal/it/student/job-applications", "/api/v1/portal/it/student/placement-status", "/api/v1/workflows/it/student/offers", "/api/v1/workflows/it/jobs/open"):
        _no_leak(await client.get(path, headers=student), path)


async def test_employer_routes_leak_nothing_and_a_decision_reads_completed(client, db_session):
    world, _application, interview = await _student_world(client, db_session)
    employer = _u(world, "employer")
    for path in ("/api/v1/employer/interviews", "/api/v1/employer/shortlist", "/api/v1/employer/candidates", "/api/v1/employer/shared-profiles", "/api/v1/employer/jobs"):
        _no_leak(await client.get(path, headers=employer), path)
    rows = (await client.get("/api/v1/employer/interviews", headers=employer)).json()
    row = next(r for r in rows if r["id"] == str(interview.id))
    assert row["status"] == "completed" and row["status_label"] == "Completed"


async def test_public_job_routes_leak_nothing(client, db_session):
    await _student_world(client, db_session)
    _no_leak(await client.get("/api/v1/public/jobs"), "/public/jobs")


async def test_staff_still_read_the_result(client, db_session):
    """The narrowing is for students and employers only: the recruiter's own interview view keeps the outcome."""
    world, application, interview = await _student_world(client, db_session)
    response = await client.get(f"/api/v1/recruiter/applications/{application.id}/interviews", headers=_u(world, "rec"))
    assert response.status_code == 200 and str(interview.id) in response.text and "selected" in json.dumps(response.json())


# --- H4: recruitment documents only through their own routes -------------------------------------------------------------------------
@pytest.mark.parametrize("prefix", ["candidate-resumes", "career-resumes", "student-resumes", "job-offers", "job-joinings", "recruiter-contracts"])
async def test_generic_file_routes_withhold_recruitment_keys(client, db_session, prefix):
    world = await _world(client, db_session)
    for role in ("student", "employer", "rec"):
        assert (await client.get(f"/api/v1/files/download?key={prefix}/abc.pdf", headers=_u(world, role))).status_code == 404, (prefix, role)
        assert (await client.get(f"/local-files/{prefix}/abc.pdf", headers=_u(world, role))).status_code == 404, (prefix, role)


async def test_generic_file_route_still_serves_other_keys(client, db_session):
    world = await _world(client, db_session)
    assert (await client.get("/api/v1/files/download?key=uploads/abc.pdf", headers=_u(world, "student"))).status_code == 200

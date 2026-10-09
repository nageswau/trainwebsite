"""rec-010 -- an IT student opts in to (and out of) the placement candidate pool; EMP-003 reads the opted-in pool (spec §1-§4, §6;
DEC-SCOPE-138 OI1-OI4). The shared test database is never truncated, so every assertion uses rows created by the test."""

import asyncio
import datetime
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import (
    AuditLog,
    Batch,
    Candidate,
    CandidateConsent,
    CandidateSkill,
    Enrollment,
    JobApplication,
    PlacementProfile,
    Program,
    RecCandidateSource,
    Skill,
    User,
)
from app.services.placement_pool import CONSENT_TEXT, CONSENT_VERSION
from tests.rec001_helpers import as_role, login, make_recruiter, make_user
from tests.rec017_helpers import student_application
from tests.test_emp_004_interview_scheduling import _create_employer, _create_job

POOL = "/api/v1/account/placement-pool"
EMPLOYER = "/api/v1/employer/candidates"
RECRUITER = "/api/v1/recruiter/candidates"
JOIN = {"consent_version": "v1"}


async def _student(db, *, skills=None, course: str | None = None, profile: dict | None = None, name: str | None = None) -> User:
    student = await make_user(db, "it_student", "it", name=name or f"Pool Student {uuid.uuid4().hex[:6]}")
    student.profile = {"skills": skills or []}
    if course:
        trainer = await make_user(db, "trainer", "it")
        program = Program(
            slug=f"rec010-{uuid.uuid4().hex[:8]}",
            category="Software Development",
            title=course,
            summary="Test",
            duration="8 weeks",
            eligibility="None",
            fees=10000,
            certification="Cert",
            curriculum=["M1"],
            placement_assistance="Yes",
            trainer_name="T",
            active=True,
        )
        db.add(program)
        await db.flush()
        batch = Batch(
            program_id=program.id,
            trainer_id=trainer.id,
            name=f"B-{uuid.uuid4().hex[:6]}",
            start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=90),
            schedule="Mon-Fri",
            capacity=20,
            enrollment_open=True,
            status="active",
        )
        db.add(batch)
        await db.flush()
        db.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-{uuid.uuid4().hex[:8]}", status="completed"))
    if profile is not None:
        db.add(PlacementProfile(student_id=student.id, **profile))
    await db.commit()
    return student


async def _candidate_of(db, user_id) -> Candidate | None:
    return await db.scalar(select(Candidate).where(Candidate.user_id == user_id).execution_options(populate_existing=True))


async def _employer_ids(client, db, q: str | None = None) -> set[str]:
    employer, _ = await _create_employer(db)
    await client.post("/api/v1/auth/login", json={"email": employer.email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    response = await client.get(EMPLOYER, params={"q": q} if q else None)
    assert response.status_code == 200, response.text
    return {c["student_id"] for c in response.json()}


async def _join(client, db, student: User) -> dict:
    await login(client, student)
    response = await client.post(f"{POOL}/opt-in", json=JOIN)
    assert response.status_code == 200, response.text
    return response.json()


# --- authentication and roles (OI1) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [("get", ""), ("post", "/opt-in"), ("post", "/opt-out")])
async def test_signed_out_is_401(client, method, path):
    response = await getattr(client, method)(f"{POOL}{path}", **({"json": JOIN} if method == "post" else {}))
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("employer", "it"), ("placement_team", "it"), ("overseas_student", "overseas"), ("it_admin", "it")])
async def test_only_it_students_may_use_the_pool(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    for response in (await client.get(POOL), await client.post(f"{POOL}/opt-in", json=JOIN), await client.post(f"{POOL}/opt-out")):
        assert response.status_code == 403
        assert response.json()["detail"] == "Only IT students can join the placement candidate pool"


@pytest.mark.asyncio
async def test_state_before_opt_in_shows_the_consent_and_creates_nothing(client, db_session):
    student = await _student(db_session)
    await login(client, student)
    response = await client.get(POOL)
    assert response.status_code == 200
    assert response.json() == {"opted_in": False, "consent": {"version": CONSENT_VERSION, "text": CONSENT_TEXT}, "history": []}
    assert CONSENT_VERSION == "v1" and "never my email or phone" in CONSENT_TEXT
    assert await _candidate_of(db_session, student.id) is None


# --- AC1-AC3 -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_placement_profile_alone_no_longer_reaches_employers(client, db_session):
    student = await _student(db_session, skills=["Python"], profile={"available": True})
    assert str(student.id) not in await _employer_ids(client, db_session)


@pytest.mark.asyncio
async def test_after_opt_in_the_student_is_in_recruiter_search_and_emp_003_python_search(client, db_session):
    student = await _student(db_session, skills=["Python"], course=f"Python Full Stack {uuid.uuid4().hex[:6]}")
    state = await _join(client, db_session, student)
    assert state["opted_in"] is True
    assert [h["action"] for h in state["history"]] == ["opt_in"]

    employer_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        assert str(student.id) in await _employer_ids(employer_client, db_session, q="Python")
        match = next(c for c in (await employer_client.get(EMPLOYER, params={"q": student.full_name})).json() if c["student_id"] == str(student.id))
        assert set(match) == {"student_id", "name", "course", "skills", "availability"}  # R12: today's fields only
        assert match["availability"] is True and match["skills"] == ["Python"] and match["course"].startswith("Python Full Stack")
    finally:
        await employer_client.aclose()

    await as_role(client, db_session, "placement_team", "it")
    listed = (await client.get(RECRUITER, params={"q": student.full_name})).json()["items"]
    assert [c["candidate_code"] for c in listed] == [(await _candidate_of(db_session, student.id)).candidate_code]


@pytest.mark.asyncio
async def test_opt_out_hides_the_student_again_and_applications_continue(client, db_session):
    _, company = await _create_employer(db_session)
    job = await _create_job(db_session, company)
    student = await _student(db_session, skills=["Python"])
    application = await student_application(db_session, job.id, student, "shortlisted")
    await db_session.commit()
    await _join(client, db_session, student)
    response = await client.post(f"{POOL}/opt-out")
    assert response.status_code == 200
    assert response.json()["opted_in"] is False
    assert [h["action"] for h in response.json()["history"]] == ["opt_out", "opt_in"]

    candidate = await _candidate_of(db_session, student.id)
    assert candidate.opted_in is False
    other = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        assert str(student.id) not in await _employer_ids(other, db_session)
    finally:
        await other.aclose()
    await as_role(client, db_session, "placement_team", "it")
    assert (await client.get(RECRUITER, params={"q": student.full_name})).json()["items"] == []
    assert (await client.get(f"{RECRUITER}/{candidate.id}")).status_code == 404
    kept = await db_session.scalar(select(JobApplication).where(JobApplication.id == application.id).execution_options(populate_existing=True))
    assert kept.status == "shortlisted" and kept.candidate_id == candidate.id


@pytest.mark.asyncio
async def test_consent_history_is_kept_newest_first_with_an_audit_row_each(client, db_session):
    student = await _student(db_session)
    await _join(client, db_session, student)
    await client.post(f"{POOL}/opt-out")
    await client.post(f"{POOL}/opt-in", json=JOIN)
    response = await client.post(f"{POOL}/opt-out")
    history = response.json()["history"]
    assert [h["action"] for h in history] == ["opt_out", "opt_in", "opt_out", "opt_in"]
    assert all(h["consent_version"] == "v1" and h["created_at"] for h in history)
    candidate = await _candidate_of(db_session, student.id)
    rows = (await db_session.scalars(select(CandidateConsent).where(CandidateConsent.candidate_id == candidate.id))).all()
    assert len(rows) == 4 and {r.user_id for r in rows} == {student.id}
    audits = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(candidate.id), AuditLog.action.like("placement_pool.%")))).all()
    assert sorted(audits) == ["placement_pool.opt_in"] * 2 + ["placement_pool.opt_out"] * 2


# --- negatives and idempotency -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_student_can_only_ever_opt_in_themselves(client, db_session):
    me, other = await _student(db_session), await _student(db_session)
    await login(client, me)
    response = await client.post(f"{POOL}/opt-in", json=JOIN | {"user_id": str(other.id), "student_id": str(other.id)})
    assert response.status_code == 200
    assert (await _candidate_of(db_session, me.id)).opted_in is True
    assert await _candidate_of(db_session, other.id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("body,status", [({"consent_version": "v0"}, 409), ({}, 422), ({"consent_version": "x" * 21}, 422)])
async def test_a_stale_or_missing_consent_version_changes_nothing(client, db_session, body, status):
    student = await _student(db_session)
    await login(client, student)
    response = await client.post(f"{POOL}/opt-in", json=body)
    assert response.status_code == status
    if status == 409:
        assert response.json()["detail"] == "The consent wording has changed. Review it and try again."
    assert await _candidate_of(db_session, student.id) is None


@pytest.mark.asyncio
async def test_opting_in_twice_records_one_consent_and_opting_out_when_out_records_none(client, db_session):
    student = await _student(db_session)
    await login(client, student)
    assert (await client.post(f"{POOL}/opt-out")).json()["history"] == []
    await client.post(f"{POOL}/opt-in", json=JOIN)
    second = await client.post(f"{POOL}/opt-in", json=JOIN)
    assert second.status_code == 200 and [h["action"] for h in second.json()["history"]] == ["opt_in"]


@pytest.mark.asyncio
async def test_two_concurrent_opt_ins_give_one_candidate_and_one_consent(db_session):
    student = await _student(db_session)
    clients = [AsyncClient(transport=ASGITransport(app=app), base_url="http://test") for _ in range(2)]
    try:
        for c in clients:
            await login(c, student)
        results = await asyncio.gather(*(c.post(f"{POOL}/opt-in", json=JOIN) for c in clients))
    finally:
        for c in clients:
            await c.aclose()
    assert [r.status_code for r in results] == [200, 200]
    assert await db_session.scalar(select(func.count()).select_from(Candidate).where(Candidate.user_id == student.id)) == 1
    candidate = await _candidate_of(db_session, student.id)
    assert await db_session.scalar(select(func.count()).select_from(CandidateConsent).where(CandidateConsent.candidate_id == candidate.id)) == 1


# --- linking, never duplicating (R6, A3) -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_backfilled_student_is_linked_to_the_same_candidate(client, db_session):
    _, company = await _create_employer(db_session)
    job = await _create_job(db_session, company)
    student = await _student(db_session)
    await student_application(db_session, job.id, student)
    await db_session.commit()
    before = await _candidate_of(db_session, student.id)
    assert before.opted_in is False
    await _join(client, db_session, student)
    after = await _candidate_of(db_session, student.id)
    assert after.id == before.id and after.opted_in is True
    assert await db_session.scalar(select(func.count()).select_from(Candidate).where(Candidate.user_id == student.id)) == 1


@pytest.mark.asyncio
async def test_an_external_candidate_with_the_students_email_is_linked_and_keeps_its_source(client, db_session):
    student = await _student(db_session, course=f"Data Science {uuid.uuid4().hex[:6]}")
    recruiter = await make_recruiter(db_session)
    referral = await db_session.scalar(select(RecCandidateSource).where(RecCandidateSource.name == "Referral"))
    external = Candidate(
        candidate_code=f"T-{uuid.uuid4().hex[:8]}",
        name="Same Person",
        email=student.email.upper(),
        preferred_locations=[],
        source_id=referral.id,
        created_by_user_id=recruiter.id,
    )
    db_session.add(external)
    await db_session.commit()
    await _join(client, db_session, student)
    linked = await _candidate_of(db_session, student.id)
    assert linked.id == external.id and linked.opted_in is True
    assert linked.source_id == referral.id and linked.name == "Same Person"
    assert linked.source_detail.startswith("Data Science")  # empty, so filled from the course


# --- seed (OI3) --------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_opt_in_seeds_the_course_and_master_skills_as_claimed(client, db_session):
    course = f"Python Full Stack {uuid.uuid4().hex[:6]}"
    student = await _student(db_session, skills=["Python", "  java ", "Underwater Basket Weaving", "python"], course=course)
    state = await _join(client, db_session, student)
    assert state["opted_in"] is True
    candidate = await _candidate_of(db_session, student.id)
    source = await db_session.get(RecCandidateSource, candidate.source_id)
    assert source.name == "Edusphere students" and candidate.source_detail == course
    rows = (await db_session.execute(select(Skill.name, CandidateSkill).join(Skill, Skill.id == CandidateSkill.skill_id).where(CandidateSkill.candidate_id == candidate.id))).all()
    assert sorted(name for name, _ in rows) == ["Java", "Python"]
    assert {(s.level, s.source, s.status, s.added_by_user_id) for _, s in rows} == {("beginner", "resume", "claimed", student.id)}


@pytest.mark.asyncio
async def test_opt_in_never_overwrites_what_a_recruiter_entered(client, db_session):
    _, company = await _create_employer(db_session)
    job = await _create_job(db_session, company)
    student = await _student(db_session, skills=["Python"], course=f"Python Full Stack {uuid.uuid4().hex[:6]}")
    await student_application(db_session, job.id, student)
    await db_session.commit()
    candidate = await _candidate_of(db_session, student.id)
    python = await db_session.scalar(select(Skill).where(Skill.name == "Python"))
    recruiter = await make_recruiter(db_session)
    candidate.source_detail = "Referred by the HOD"
    db_session.add(CandidateSkill(candidate_id=candidate.id, skill_id=python.id, level="advanced", added_by_user_id=recruiter.id))
    await db_session.commit()
    await _join(client, db_session, student)
    candidate = await _candidate_of(db_session, student.id)
    assert candidate.source_detail == "Referred by the HOD"
    skill = await db_session.scalar(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id).execution_options(populate_existing=True))
    assert (skill.level, skill.added_by_user_id) == ("advanced", recruiter.id)


# --- EMP-003 visibility (OI4) ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_emp_003_hides_withdrawn_and_archived_and_reads_availability_from_the_candidate_status(client, db_session):
    withdrawn = await _student(db_session, profile={"withdrawn": True, "available": True})
    archived, not_looking = await _student(db_session), await _student(db_session, profile={"available": True})
    for student in (withdrawn, archived, not_looking):
        await _join(client, db_session, student)
    a = await _candidate_of(db_session, archived.id)
    a.archived_at = datetime.datetime.now(datetime.UTC)
    n = await _candidate_of(db_session, not_looking.id)
    n.status = "not_looking"
    await db_session.commit()
    employer, _ = await _create_employer(db_session)
    await client.post("/api/v1/auth/login", json={"email": employer.email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    results = {c["student_id"]: c for c in (await client.get(EMPLOYER)).json()}
    assert str(withdrawn.id) not in results and str(archived.id) not in results
    assert results[str(not_looking.id)]["availability"] is False

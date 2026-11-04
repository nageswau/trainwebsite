"""hrc-008 (DEC-SCOPE-385, spec docs/superpowers/specs/2026-11-04-hrc-008-vacancy-visibility-design.md): vacancy visibility -- who sees
and applies to an open job (V5), the segment rule (V2), applications kept (V6) and the `jobs.publish` change route (V4, V7). The database
is shared, so every test makes its own jobs, skills and pools and asserts only on them."""

import uuid

import pytest
from sqlalchemy import select

from app.core import rbac
from app.models import AuditLog, CandidateSkill, Company, Job, Skill, SkillCategory, TalentPool
from app.services.applications import candidate_for_student
from tests.hrc007_helpers import employer_self_publish  # noqa: F401  (fixture)
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user
from tests.rec017_helpers import student_application
from tests.test_emp_002_job_posting import _create_student, _login, _register_employer

BASE = "/api/v1/recruiter/requirements"
STUDENT_OPEN = "/api/v1/workflows/it/jobs/open"
STUDENT_PORTAL = "/api/v1/portal/it/it_student/job-applications"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _job(db, visibility: str = "public", pool: TalentPool | None = None, status: str = "requirement_received", **extra) -> Job:
    company = Company(name=f"Vis Co {_tag()}")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title=f"Vis Job {_tag()}", location="Pune", description="d", skills=[], status=status, visibility=visibility, segment_pool_id=pool.id if pool else None, **extra)
    db.add(job)
    await db.commit()
    return job


async def _skill(db) -> Skill:
    category = await db.scalar(select(SkillCategory).order_by(SkillCategory.sort_order).limit(1))
    skill = Skill(name=f"VisSkill {_tag()}", category_id=category.id)
    db.add(skill)
    await db.commit()
    return skill


async def _pool(db, skill: Skill, active: bool = True) -> TalentPool:
    pool = TalentPool(name=f"Vis Pool {_tag()}", all_terms=[skill.name], any_terms=[], active=active)
    db.add(pool)
    await db.commit()
    return pool


async def _member(db, student, skill: Skill):
    """The student's candidate, opted in (rec-010, so it is in the pool) with the pool's skill."""
    candidate = await candidate_for_student(db, student)
    candidate.opted_in = True
    await db.flush()
    db.add(CandidateSkill(candidate_id=candidate.id, skill_id=skill.id, level="beginner", added_by_user_id=student.id, status="claimed"))
    await db.commit()
    return candidate


async def _ids(client, url: str) -> set[str]:
    response = await client.get(url)
    assert response.status_code == 200, response.text
    return {str(row["id"]) for row in response.json()}


async def _portal_panel(client) -> str:
    response = await client.get(STUDENT_PORTAL)
    assert response.status_code == 200, response.text
    return " ".join(" ".join(p["items"]) for p in response.json()["panels"])


def _apply_public(client, job_id):
    return client.post(f"/api/v1/public/jobs/{job_id}/apply", json={"full_name": "Pat", "email": f"pat-{_tag()}@example.local", "resume_url": "https://example.local/cv.pdf"})


# --- AC1 / + / -: the public site shows and accepts public jobs only ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_public_endpoints_show_and_accept_only_public_jobs(client, db_session):
    skill = await _skill(db_session)
    pool = await _pool(db_session, skill)
    public, internal, portal, segment = await _job(db_session), await _job(db_session, "internal"), await _job(db_session, "portal"), await _job(db_session, "segment", pool)
    listed = await _ids(client, "/api/v1/public/jobs")
    assert str(public.id) in listed  # + a public job appears on /it/careers
    assert not {str(internal.id), str(portal.id), str(segment.id)} & listed  # AC1
    assert (await _apply_public(client, public.id)).status_code == 201
    for job in (internal, portal, segment):  # - applying to a non-public job through the public route is the missing-job 404
        response = await _apply_public(client, job.id)
        assert response.status_code == 404 and response.json()["detail"] == "Open job not found"


# --- AC1 / V5: students see portal and public jobs, never internal ones; staff lists are unchanged ---------------------------------
@pytest.mark.asyncio
async def test_students_see_portal_and_public_jobs_but_not_internal_ones(client, db_session):
    public, internal, portal = await _job(db_session), await _job(db_session, "internal"), await _job(db_session, "portal")
    student = await _create_student(db_session)
    await _login(client, student.email)
    listed = await _ids(client, STUDENT_OPEN)
    assert {str(public.id), str(portal.id)} <= listed and str(internal.id) not in listed
    panel = await _portal_panel(client)
    assert str(portal.id) in panel and str(public.id) in panel and str(internal.id) not in panel
    assert (await client.post(f"/api/v1/workflows/it/jobs/{internal.id}/apply", json={})).status_code == 404
    assert (await client.post(f"/api/v1/workflows/it/jobs/{portal.id}/apply", json={})).status_code == 201

    await as_role(client, db_session, "hr_team", "it")  # V5: internal staff still see every open job
    assert {str(public.id), str(internal.id), str(portal.id)} <= await _ids(client, STUDENT_OPEN)


# --- AC2 / E: a segment job is visible only to the pool's members; leaving the pool keeps the application -----------------------
@pytest.mark.asyncio
async def test_segment_job_is_visible_only_to_pool_members(client, db_session):
    skill = await _skill(db_session)
    pool = await _pool(db_session, skill)
    segment = await _job(db_session, "segment", pool)
    member, outsider = await _create_student(db_session), await _create_student(db_session)
    candidate = await _member(db_session, member, skill)

    await _login(client, outsider.email)
    assert str(segment.id) not in await _ids(client, STUDENT_OPEN)
    assert (await client.post(f"/api/v1/workflows/it/jobs/{segment.id}/apply", json={})).status_code == 404

    await _login(client, member.email)
    assert str(segment.id) in await _ids(client, STUDENT_OPEN)
    assert str(segment.id) in await _portal_panel(client)
    assert (await client.post(f"/api/v1/workflows/it/jobs/{segment.id}/apply", json={})).status_code == 201

    # E: the candidate stops matching -- the job leaves their list, their application stays
    row = await db_session.scalar(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id, CandidateSkill.skill_id == skill.id))
    await db_session.delete(row)
    await db_session.commit()
    assert str(segment.id) not in await _ids(client, STUDENT_OPEN)
    rows = (await client.get(STUDENT_PORTAL)).json()["rows"]
    assert any(r["role"] == segment.title for r in rows)


@pytest.mark.asyncio
async def test_a_segment_job_of_an_inactive_pool_reaches_nobody(client, db_session):
    skill = await _skill(db_session)
    pool = await _pool(db_session, skill, active=False)
    segment = await _job(db_session, "segment", pool)
    student = await _create_student(db_session)
    await _member(db_session, student, skill)
    await _login(client, student.email)
    assert str(segment.id) not in await _ids(client, STUDENT_OPEN)


# --- AC3: a closed job leaves the public views; the existing application stays visible to its owner -------------------------------
@pytest.mark.asyncio
async def test_closed_job_leaves_public_views_and_the_application_stays(client, db_session):
    job = await _job(db_session)
    student = await _create_student(db_session)
    await student_application(db_session, job.id, student)
    job.status = "closed"
    await db_session.commit()
    assert str(job.id) not in await _ids(client, "/api/v1/public/jobs")
    await _login(client, student.email)
    assert str(job.id) not in await _ids(client, STUDENT_OPEN)
    assert any(r["role"] == job.title for r in (await client.get(STUDENT_PORTAL)).json()["rows"])


@pytest.mark.asyncio
async def test_making_a_job_internal_keeps_the_students_application(client, db_session):
    job = await _job(db_session, "portal")
    student = await _create_student(db_session)
    await student_application(db_session, job.id, student)
    job.visibility = "internal"
    await db_session.commit()
    await _login(client, student.email)
    assert str(job.id) not in await _ids(client, STUDENT_OPEN)
    assert any(r["role"] == job.title for r in (await client.get(STUDENT_PORTAL)).json()["rows"])  # V6


# --- V4 / V7: changing visibility ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_placement_manager_changes_visibility_and_it_is_audited(client, db_session):
    skill = await _skill(db_session)
    pool = await _pool(db_session, skill)
    job = await _job(db_session)
    manager = await make_pm(db_session)
    await login(client, manager)
    response = await client.put(f"{BASE}/{job.id}/visibility", json={"visibility": "segment", "segment_pool_id": str(pool.id)})
    assert response.status_code == 200, response.text
    visibility = response.json()["requirement"]["visibility"]
    assert visibility == {"key": "segment", "label": "Segment (talent pool)", "segment_pool": {"id": str(pool.id), "name": pool.name, "active": True}, "can_change": True}
    assert response.json()["requirement"]["updated_by"]["id"] == str(manager.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(job.id), AuditLog.action == "recruiter_requirement.visibility"))
    assert audit.user_id == manager.id
    assert audit.metadata_json["changes"] == {"visibility": ["public", "segment"], "segment_pool": [None, pool.name]}

    again = await client.put(f"{BASE}/{job.id}/visibility", json={"visibility": "segment", "segment_pool_id": str(pool.id)})
    assert again.status_code == 200  # the same values are not a change: no second audit row
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(job.id), AuditLog.action == "recruiter_requirement.visibility"))).all()
    assert len(rows) == 1

    back = await client.put(f"{BASE}/{job.id}/visibility", json={"visibility": "internal"})
    assert back.status_code == 200 and back.json()["requirement"]["visibility"]["segment_pool"] is None
    stored = await db_session.scalar(select(Job).where(Job.id == job.id).execution_options(populate_existing=True))
    assert (stored.visibility, stored.segment_pool_id) == ("internal", None)


@pytest.mark.asyncio
async def test_changing_visibility_needs_the_publish_grant(client, db_session):
    job = await _job(db_session)
    manager = await make_pm(db_session)
    recruiter = await make_recruiter(db_session, manager)
    job.assigned_recruiter_user_id = recruiter.id
    await db_session.commit()
    await login(client, recruiter)
    detail = (await client.get(f"{BASE}/{job.id}")).json()["requirement"]
    assert detail["visibility"]["key"] == "public" and detail["visibility"]["can_change"] is False
    for actor in (recruiter, await make_user(db_session, "hr_manager", "it"), await make_user(db_session, "placement_officer", "it")):
        await login(client, actor)
        response = await client.put(f"{BASE}/{job.id}/visibility", json={"visibility": "internal"})
        assert response.status_code == 403 and response.json()["detail"] == "You cannot change who sees job requirements"
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.put(f"{BASE}/{job.id}/visibility", json={"visibility": "portal"})).status_code == 200
    client.cookies.clear()
    assert (await client.put(f"{BASE}/{job.id}/visibility", json={"visibility": "public"})).status_code == 401
    assert {r for r, keys in rbac.DEFAULT_GRANTS.items() if "jobs.publish" in keys} == {"placement_manager"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"visibility": "segment"},  # a segment needs a pool
        {"visibility": "public", "segment_pool_id": "POOL"},  # only a segment names a pool
        {"visibility": "segment", "segment_pool_id": str(uuid.uuid4())},  # unknown pool
        {"visibility": "segment", "segment_pool_id": "INACTIVE"},  # inactive pool
        {"visibility": "everyone"},
        {"visibility": "public", "extra": 1},
    ],
)
async def test_an_invalid_visibility_is_a_422(client, db_session, body):
    skill = await _skill(db_session)
    pool, inactive = await _pool(db_session, skill), await _pool(db_session, skill, active=False)
    job = await _job(db_session)
    await login(client, await make_pm(db_session))
    sent = {k: (str(pool.id) if v == "POOL" else str(inactive.id) if v == "INACTIVE" else v) for k, v in body.items()}
    response = await client.put(f"{BASE}/{job.id}/visibility", json=sent)
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_an_unknown_job_is_a_404(client, db_session):
    await login(client, await make_pm(db_session))
    assert (await client.put(f"{BASE}/{uuid.uuid4()}/visibility", json={"visibility": "public"})).status_code == 404


# --- V8: the employer's "visible to students" flag follows an internal visibility ------------------------------------------------
@pytest.mark.asyncio
async def test_the_employer_sees_an_internal_job_as_not_visible_to_students(client, db_session, employer_self_publish):  # noqa: F811
    await _register_employer(client)
    created = (await client.post("/api/v1/employer/jobs", json={"title": f"Vis Emp {_tag()}", "location": "Pune", "description": "d", "skills": []})).json()
    published = (await client.patch(f"/api/v1/employer/jobs/{created['id']}", json={"status": "open"})).json()
    assert published["visible_to_students"] is True
    job = await db_session.scalar(select(Job).where(Job.id == uuid.UUID(created["id"])))
    job.visibility = "internal"
    await db_session.commit()
    listed = next(j for j in (await client.get("/api/v1/employer/jobs")).json() if j["id"] == created["id"])
    assert listed["visible_to_students"] is False

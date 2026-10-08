"""rec-007 -- the Job Requirement (spec §2-§5; AC1-AC5; DEC-SCOPE-128 J1-J7). Names are unique per test (the database is shared)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, CompanyStageHistory, Job, JobApplication, JobSkill, JobStatusHistory, RecJobCategory, Skill, SkillAlias, SkillCategory
from app.services.recruiter_requirements import ist_today
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user
from tests.test_emp_002_job_posting import _register_employer

BASE = "/api/v1/recruiter/requirements"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _company(db, recruiter=None, **extra) -> Company:
    company = Company(name=f"Req Co {_tag()}", assigned_recruiter_user_id=recruiter.id if recruiter else None, **extra)
    db.add(company)
    await db.commit()
    return company


async def _skill(db, name: str, alias: str | None = None) -> Skill:
    category = await db.scalar(select(SkillCategory).order_by(SkillCategory.sort_order).limit(1))
    skill = Skill(name=name, category_id=category.id)
    db.add(skill)
    await db.flush()
    if alias:
        db.add(SkillAlias(skill_id=skill.id, alias=alias))
    await db.commit()
    return skill


async def _team(client, db):
    """A manager with one logged-in recruiter who owns one company."""
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    company = await _company(db, recruiter)
    await login(client, recruiter)
    return manager, recruiter, company


async def _create(client, company, **body):
    return await client.post(BASE, json={"company_id": str(company.id), "title": f"Python Developer {_tag()}", "location": "Hyderabad", **body})


async def _history(db, job_id):
    return (await db.scalars(select(JobStatusHistory).where(JobStatusHistory.job_id == job_id).order_by(JobStatusHistory.created_at))).all()


async def _set_status(client, requirement_id, status, note=None):
    return await client.post(f"{BASE}/{requirement_id}/status", json={"status": status, **({"note": note} if note else {})})


# --- create (AC1) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiter_creates_a_requirement_with_every_field_and_three_required_skills(client, db_session):
    _, recruiter, company = await _team(client, db_session)
    tag = _tag()
    python = await _skill(db_session, f"Python{tag}", alias=f"py{tag}")
    sql = await _skill(db_session, f"SQL{tag}")
    category = RecJobCategory(name=f"IT {tag}", sort_order=9999)  # after the seeded values (test_rec_002 checks their order)
    db_session.add(category)
    await db_session.commit()
    body = {
        "department": "Engineering", "job_category_id": str(category.id), "vacancies": 3, "qualification": "B.Tech",
        "experience_min_months": 0, "experience_max_months": 24, "salary_min": "300000", "salary_max": "600000", "work_mode": "hybrid",
        "shift": "day", "employment_type": "full_time", "joining_requirement": "Within 30 days", "closes_on": str(ist_today() + timedelta(days=30)),
        "priority": "high", "description": "Build APIs",
        "required_skills": [f"PY{tag}", f"sql{tag}", f"FastAPI-{tag}"], "preferred_skills": [f"python{tag}", f"Kube{tag}"],
    }
    response = await _create(client, company, **body)
    assert response.status_code == 201, response.text
    req = response.json()["requirement"]
    assert req["code"].startswith("REQ-") and req["status"] == "new" and req["status_label"] == "New"
    assert req["assigned_recruiter"]["id"] == str(recruiter.id)
    assert req["requirement_date"] == str(ist_today())
    for key in ("department", "vacancies", "qualification", "experience_min_months", "experience_max_months", "work_mode", "shift", "employment_type", "joining_requirement", "priority"):
        assert req[key] == body[key], key
    assert float(req["salary_min"]) == 300000 and req["job_category"]["id"] == str(category.id)
    skills = [(s["name"], s["kind"], s["matched"]) for s in req["skills"]]
    # the alias resolves to its skill; "python" again as preferred is already required; the unmatched value is kept and flagged
    assert skills == [(python.name, "required", True), (sql.name, "required", True), (f"FastAPI-{tag}", "required", False), (f"Kube{tag}", "preferred", False)]
    job = await db_session.get(Job, uuid.UUID(req["id"]))
    await db_session.refresh(job)
    assert job.skills == [python.name, sql.name, f"FastAPI-{tag}", f"Kube{tag}"]  # the legacy mirror
    history = await _history(db_session, job.id)
    assert [(h.from_status, h.to_status, h.changed_by_user_id) for h in history] == [(None, "new", recruiter.id)]
    assert await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(job.id), AuditLog.action == "recruiter_requirement.create"))


@pytest.mark.asyncio
async def test_experience_min_above_max_is_422_sent_together_and_against_the_stored_value(client, db_session):
    _, _, company = await _team(client, db_session)
    assert (await _create(client, company, experience_min_months=36, experience_max_months=12)).status_code == 422
    assert (await _create(client, company, salary_min="9", salary_max="1")).status_code == 422
    created = (await _create(client, company, experience_max_months=24)).json()["requirement"]
    response = await client.patch(f"{BASE}/{created['id']}", json={"experience_min_months": 30})
    assert response.status_code == 422 and "experience" in response.text


@pytest.mark.asyncio
async def test_a_recruiter_cannot_create_for_another_recruiters_company_or_an_archived_one(client, db_session):
    manager, _, _ = await _team(client, db_session)
    other = await _company(db_session, await make_recruiter(db_session, manager))
    assert (await _create(client, other)).status_code == 404
    _, _, archived = await _team(client, db_session)
    archived.archived_at = datetime.now(UTC)
    await db_session.commit()
    assert (await _create(client, archived)).status_code == 409


@pytest.mark.asyncio
async def test_a_manager_creates_for_a_team_company_and_it_goes_to_the_companys_recruiter(client, db_session):
    manager, recruiter, company = await _team(client, db_session)
    await login(client, manager)
    req = (await _create(client, company)).json()["requirement"]
    assert req["assigned_recruiter"]["id"] == str(recruiter.id)
    second = await make_recruiter(db_session, manager)
    moved = await client.post(f"{BASE}/{req['id']}/assign", json={"recruiter_user_id": str(second.id)})
    assert moved.status_code == 200 and moved.json()["requirement"]["assigned_recruiter"]["id"] == str(second.id)
    assert (await client.post(f"{BASE}/{req['id']}/assign", json={"recruiter_user_id": str(second.id)})).status_code == 409
    # the manager reads and reassigns, but does not edit (the rec-003 D6 rule)
    assert (await client.patch(f"{BASE}/{req['id']}", json={"department": "QA"})).status_code == 403


# --- statuses (AC2) -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_each_status_change_is_kept_in_history_and_disallowed_moves_are_409(client, db_session):
    _, recruiter, company = await _team(client, db_session)
    req = (await _create(client, company)).json()["requirement"]
    assert (await _set_status(client, req["id"], "joined")).status_code == 409  # new -> joined is not a move
    assert (await _set_status(client, req["id"], "new")).status_code == 409  # the same status
    moved = await _set_status(client, req["id"], "requirement_received", "Call with HR")
    assert moved.status_code == 200
    body = moved.json()["requirement"]
    assert body["status"] == "requirement_received" and "sourcing" in [s["key"] for s in body["allowed_statuses"]]
    assert body["status_history"][0]["note"] == "Call with HR" and body["status_history"][0]["changed_by"]["id"] == str(recruiter.id)
    for status in ("sourcing", "shortlisting", "profiles_shared", "interviewing", "selected", "joined", "closed", "requirement_received", "cancelled"):
        assert (await _set_status(client, req["id"], status)).status_code == 200, status
    assert (await _set_status(client, req["id"], "sourcing")).status_code == 409  # cancelled is terminal
    assert (await client.patch(f"{BASE}/{req['id']}", json={"department": "QA"})).status_code == 409
    history = await _history(db_session, uuid.UUID(req["id"]))
    assert [h.to_status for h in history][-3:] == ["closed", "requirement_received", "cancelled"] and len(history) == 11
    assert (await _set_status(client, req["id"], "filled")).status_code == 422


@pytest.mark.asyncio
async def test_vacancies_cannot_drop_below_the_joined_count(client, db_session):
    _, _, company = await _team(client, db_session)
    req = (await _create(client, company, vacancies=3)).json()["requirement"]
    students = [await make_user(db_session, "it_student", "it") for _ in range(2)]
    db_session.add_all(JobApplication(job_id=uuid.UUID(req["id"]), student_id=s.id, status="hired") for s in students)
    await db_session.commit()
    response = await client.patch(f"{BASE}/{req['id']}", json={"vacancies": 1})
    assert response.status_code == 409 and "2" in response.json()["detail"]
    assert (await client.patch(f"{BASE}/{req['id']}", json={"vacancies": 2})).status_code == 200


# --- scope (AC5) ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scope_own_team_and_refused_roles(client, db_session):
    manager, recruiter, company = await _team(client, db_session)
    req = (await _create(client, company)).json()["requirement"]
    assert (await client.get(f"{BASE}?company_id={company.id}")).json()["total"] == 1
    other = await make_recruiter(db_session, manager)
    await login(client, other)
    assert (await client.get(f"{BASE}/{req['id']}")).status_code == 404
    assert (await client.get(f"{BASE}?company_id={company.id}")).json()["total"] == 0
    await login(client, manager)
    assert (await client.get(f"{BASE}/{req['id']}")).status_code == 200
    await login(client, await make_pm(db_session))  # another manager's team
    assert (await client.get(f"{BASE}/{req['id']}")).status_code == 404
    for role, division in (("hr_team", "it"), ("it_admin", "it"), ("it_student", "it")):
        await as_role(client, db_session, role, division)
        assert (await client.get(BASE)).status_code == 403, role
    bdm = await make_user(db_session, "bdm", "it")
    company.assigned_bdm_user_id = bdm.id
    await db_session.commit()
    await login(client, bdm)
    assert (await client.get(f"{BASE}/{req['id']}")).status_code == 200
    assert (await client.patch(f"{BASE}/{req['id']}", json={"department": "QA"})).status_code == 403
    assert (await _set_status(client, req["id"], "requirement_received")).status_code == 403


@pytest.mark.asyncio
async def test_list_filters_and_deadline_states(client, db_session):
    _, _, company = await _team(client, db_session)
    soon = (await _create(client, company, closes_on=str(ist_today() + timedelta(days=3)), priority="low")).json()["requirement"]
    later = (await _create(client, company, closes_on=str(ist_today() + timedelta(days=40)))).json()["requirement"]
    past = (await _create(client, company)).json()["requirement"]
    for req in (soon, later, past):
        assert (await _set_status(client, req["id"], "requirement_received")).status_code == 200
    job = await db_session.get(Job, uuid.UUID(past["id"]))
    job.closes_on = ist_today() - timedelta(days=1)
    await db_session.commit()
    expiring = (await client.get(f"{BASE}?company_id={company.id}&deadline=expiring")).json()
    assert [i["id"] for i in expiring["items"]] == [soon["id"]] and expiring["items"][0]["deadline_state"] == "expiring"
    assert [i["id"] for i in (await client.get(f"{BASE}?company_id={company.id}&deadline=expired")).json()["items"]] == [past["id"]]
    assert (await client.get(f"{BASE}?company_id={company.id}&priority=low")).json()["total"] == 1
    assert (await client.get(f"{BASE}?q={soon['code']}")).json()["total"] == 1
    assert (await client.get(f"{BASE}?status=bogus")).status_code == 422
    statuses = (await client.get(f"{BASE}/statuses")).json()
    assert len(statuses["statuses"]) == 11 and statuses["expiring_days"] == 7


# --- students and the legacy shim (AC3, AC4) ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_students_see_a_requirement_only_in_the_open_set(client, db_session):
    _, recruiter, company = await _team(client, db_session)
    req = (await _create(client, company)).json()["requirement"]
    student = await make_user(db_session, "it_student", "it")

    async def listed() -> bool:
        await login(client, student)
        ids = [j["id"] for j in (await client.get("/api/v1/workflows/it/jobs/open")).json()]
        return req["id"] in ids

    assert not await listed()  # new
    for status, expected in (("requirement_received", True), ("interviewing", True), ("on_hold", False), ("sourcing", True), ("selected", False)):
        await login(client, recruiter)
        assert (await _set_status(client, req["id"], status)).status_code == 200
        assert await listed() is expected, status


@pytest.mark.asyncio
async def test_the_employer_api_keeps_its_words_and_writes_history_and_skills(client, db_session):
    await _register_employer(client)
    tag = _tag()
    skill = await _skill(db_session, f"Go{tag}", alias=f"golang{tag}")
    created = (await client.post("/api/v1/employer/jobs", json={"title": f"Go dev {tag}", "skills": [f"GOLANG{tag}", "Rare skill"]})).json()
    assert created["status"] == "draft" and created["requirement_status"] == "new" and created["status_label"] == "New"
    assert created["skills"] == [skill.name, "Rare skill"]
    rows = (await db_session.scalars(select(JobSkill).where(JobSkill.job_id == uuid.UUID(created["id"])).order_by(JobSkill.position))).all()
    assert [(r.name, r.skill_id) for r in rows] == [(skill.name, skill.id), ("Rare skill", None)]
    published = (await client.patch(f"/api/v1/employer/jobs/{created['id']}", json={"status": "open"})).json()
    assert published["status"] == "open" and published["requirement_status"] == "requirement_received" and published["visible_to_students"]
    again = await client.patch(f"/api/v1/employer/jobs/{created['id']}", json={"status": "open"})  # already open: a no-op, not a 409
    assert again.status_code == 200
    closed = (await client.patch(f"/api/v1/employer/jobs/{created['id']}", json={"status": "closed"})).json()
    assert closed["status"] == "closed" and closed["requirement_status"] == "closed"
    history = await _history(db_session, uuid.UUID(created["id"]))
    assert [(h.from_status, h.to_status) for h in history] == [(None, "new"), ("new", "requirement_received"), ("requirement_received", "closed")]


@pytest.mark.asyncio
async def test_the_workflows_patch_validates_statuses(client, db_session):
    await as_role(client, db_session, "placement_team", "it")
    company_name = f"Wf Co {_tag()}"
    created = (await client.post("/api/v1/workflows/it/jobs", json={"company_name": company_name, "title": "Ops", "skills": ["Linux"]})).json()
    assert created["status"] == "requirement_received"
    job_id = created["id"]
    assert (await client.patch(f"/api/v1/workflows/it/jobs/{job_id}", json={"status": "filled"})).status_code == 422
    assert (await client.patch(f"/api/v1/workflows/it/jobs/{job_id}", json={"status": "joined"})).status_code == 409
    assert (await client.patch(f"/api/v1/workflows/it/jobs/{job_id}", json={"status": "open"})).json()["status"] == "requirement_received"
    assert (await client.patch(f"/api/v1/workflows/it/jobs/{job_id}", json={"status": "closed"})).json()["status"] == "closed"
    listing = (await client.get("/api/v1/workflows/it/jobs")).json()
    assert any(j["id"] == job_id and j["status_label"] == "Closed" for j in listing)


# --- the company stage (AC2; rec-005's EVENTS: rec-007 fires requirement_received / requirement_closed) -------------------------
async def _stage(db, company_id):
    company = await db.scalar(select(Company).where(Company.id == company_id).execution_options(populate_existing=True))
    events = (await db.scalars(select(CompanyStageHistory.event).where(CompanyStageHistory.company_id == company_id).order_by(CompanyStageHistory.created_at))).all()
    return company.stage, list(events)


@pytest.mark.asyncio
async def test_status_changes_drive_the_company_stage(client, db_session):
    _, _, company = await _team(client, db_session)
    first = (await _create(client, company)).json()["requirement"]
    second = (await _create(client, company)).json()["requirement"]
    assert (await _stage(db_session, company.id))[0] == "new_lead"  # a New requirement is not yet received
    await _set_status(client, first["id"], "requirement_received")
    assert await _stage(db_session, company.id) == ("requirement_received", ["requirement_received"])
    await _set_status(client, second["id"], "requirement_received")  # already there: the event does not fire twice
    await _set_status(client, first["id"], "closed")
    assert (await _stage(db_session, company.id))[0] == "requirement_received"  # the second requirement is still open
    await _set_status(client, second["id"], "cancelled")
    assert await _stage(db_session, company.id) == ("requirement_closed", ["requirement_received", "requirement_closed"])
    await _set_status(client, first["id"], "requirement_received")  # reopened: the one driven way back
    assert await _stage(db_session, company.id) == ("requirement_received", ["requirement_received", "requirement_closed", "requirement_received"])


@pytest.mark.asyncio
async def test_legacy_writers_drive_the_company_stage_too(client, db_session):
    await as_role(client, db_session, "placement_team", "it")
    name = f"Wf Stage Co {_tag()}"
    created = (await client.post("/api/v1/workflows/it/jobs", json={"company_name": name, "title": "Ops"})).json()
    company = await db_session.scalar(select(Company).where(Company.name == name))
    assert await _stage(db_session, company.id) == ("requirement_received", ["requirement_received"])
    await client.patch(f"/api/v1/workflows/it/jobs/{created['id']}", json={"status": "closed"})
    assert (await _stage(db_session, company.id))[0] == "requirement_closed"
    await _register_employer(client)
    job = (await client.post("/api/v1/employer/jobs", json={"title": f"Posted {_tag()}"})).json()
    employer_company = (await db_session.get(Job, uuid.UUID(job["id"]))).company_id
    assert (await _stage(db_session, employer_company))[0] == "new_lead"
    await client.patch(f"/api/v1/employer/jobs/{job['id']}", json={"status": "open"})
    assert (await _stage(db_session, employer_company))[0] == "requirement_received"

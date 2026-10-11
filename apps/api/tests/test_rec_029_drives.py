"""rec-029 -- campus recruitment drives (spec §1-§3; AC1, AC2; DEC-SCOPE-178 DR1-DR10). Names are unique per test (the database is
shared and never truncated)."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, select

from app.core.database import engine
from app.models import AuditLog, BdmOrganization, Company, Interview, JobApplication
from app.services import recruitment_drives as svc
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user
from tests.test_rec_017_tracking import _candidate, _move, _requirement

DRIVES = "/api/v1/recruiter/drives"
REQ = "/api/v1/recruiter/requirements"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _college(db, owner, *, org_type="college", archived=False) -> BdmOrganization:
    t = _tag()
    org = BdmOrganization(
        code=f"ORG-D{t}", org_type=org_type, bdm_type="college" if org_type in ("college", "university") else "agent", name=f"ABC College {t}",
        name_key=f"abc college {t}", city="Kochi", city_key="kochi", assigned_bdm_user_id=owner.id, created_by_user_id=owner.id,
        archived_at=datetime.now(UTC) if archived else None,
    )
    db.add(org)
    await db.commit()
    return org


async def _setup(client, db, *, requirements=2):
    """A recruiter signed in, their company (XYZ Technologies) and `requirements` live requirements of it."""
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    company = Company(name=f"XYZ Technologies {_tag()}", assigned_recruiter_user_id=recruiter.id)
    db.add(company)
    await db.commit()
    jobs = [await _requirement(db, recruiter, company=company) for _ in range(requirements)]
    await login(client, recruiter)
    return manager, recruiter, company, jobs


def _body(company, jobs, **over) -> dict:
    return {
        "company_id": str(company.id), "college_name": "ABC College", "requirement_ids": [str(j.id) for j in jobs], "drive_date": "2026-11-20",
        "job_role": "Graduate Engineer Trainee", "vacancies": 40, "eligibility": "B.Tech 2026, 60%+", "students_registered": 200,
        "students_attended": 100, **over,
    }


async def _create(client, company, jobs, **over) -> dict:
    response = await client.post(DRIVES, json=_body(company, jobs, **over))
    assert response.status_code == 201, response.text
    return response.json()


def _loc(response) -> list:
    return [e["loc"][-1] for e in response.json()["detail"]]


# --- create (DR1, DR2, DR4, DR5) ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_with_a_bdm_college_and_two_requirements(client, db_session):
    _, recruiter, company, jobs = await _setup(client, db_session)
    college = await _college(db_session, await make_user(db_session, "bdm", "it"))
    drive = await _create(client, company, jobs, college_name=None, college_org_id=str(college.id))
    assert drive["code"].startswith("DRV-") and len(drive["code"]) == 10
    assert drive["college"] == {"org_id": str(college.id), "code": college.code, "name": college.name, "city": "Kochi"}
    assert drive["company"]["id"] == str(company.id) and drive["status"] == "planned"
    assert {r["id"] for r in drive["requirements"]} == {str(j.id) for j in jobs}
    assert drive["funnel"] == {"registered": 200, "attended": 100, "tagged": 0, "shortlisted": 0, "interviewed": 0, "selected": 0, "joined": 0}
    assert drive["can_edit"] is True
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == drive["id"], AuditLog.action == "recruitment_drive.create"))
    assert audit is not None and audit.user_id == recruiter.id


@pytest.mark.asyncio
async def test_create_with_a_free_text_college(client, db_session):
    _, _, company, jobs = await _setup(client, db_session, requirements=1)
    drive = await _create(client, company, jobs, college_name="  St. Mary's   College ")
    assert drive["college"] == {"org_id": None, "code": None, "name": "St. Mary's College", "city": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["both", "neither"])
async def test_exactly_one_college_is_422(client, db_session, which):
    _, _, company, jobs = await _setup(client, db_session, requirements=1)
    college = await _college(db_session, await make_user(db_session, "bdm", "it"))
    over = {"college_org_id": str(college.id)} if which == "both" else {"college_name": None}
    response = await client.post(DRIVES, json=_body(company, jobs, **over))
    assert response.status_code == 422 and _loc(response) == ["college_org_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["agent", "archived", "missing"])
async def test_college_must_be_a_live_bdm_college_or_university(client, db_session, kind):
    _, _, company, jobs = await _setup(client, db_session, requirements=1)
    bdm = await make_user(db_session, "bdm", "it")
    org_id = uuid.uuid4() if kind == "missing" else (await _college(db_session, bdm, org_type="agent" if kind == "agent" else "college", archived=kind == "archived")).id
    response = await client.post(DRIVES, json=_body(company, jobs, college_name=None, college_org_id=str(org_id)))
    assert response.status_code == 422 and _loc(response) == ["college_org_id"]


@pytest.mark.asyncio
async def test_a_university_org_is_a_college(client, db_session):
    _, _, company, jobs = await _setup(client, db_session, requirements=1)
    university = await _college(db_session, await make_user(db_session, "bdm", "it"), org_type="university")
    drive = await _create(client, company, jobs, college_name=None, college_org_id=str(university.id))
    assert drive["college"]["org_id"] == str(university.id)


@pytest.mark.asyncio
async def test_requirements_must_be_live_requirements_of_the_drive_company(client, db_session):
    _, recruiter, company, jobs = await _setup(client, db_session, requirements=1)
    other = await _requirement(db_session, recruiter)  # the recruiter's, but another company's
    closed = await _requirement(db_session, recruiter, status="closed", company=company)
    for bad in (other, closed):
        response = await client.post(DRIVES, json=_body(company, [jobs[0], bad]))
        assert response.status_code == 422 and _loc(response) == ["requirement_ids"], response.text
    response = await client.post(DRIVES, json=_body(company, []))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ac2_attended_above_registered_is_422(client, db_session):
    _, _, company, jobs = await _setup(client, db_session, requirements=1)
    response = await client.post(DRIVES, json=_body(company, jobs, students_registered=100, students_attended=101))
    assert response.status_code == 422 and _loc(response) == ["students_attended"]
    drive = await _create(client, company, jobs, students_registered=200, students_attended=100)
    lower = await client.patch(f"{DRIVES}/{drive['id']}", json={"students_registered": 99})  # merged with the stored attended
    assert lower.status_code == 422 and _loc(lower) == ["students_attended"]
    ok = await client.patch(f"{DRIVES}/{drive['id']}", json={"students_attended": 180})
    assert ok.status_code == 200 and ok.json()["funnel"]["attended"] == 180


@pytest.mark.asyncio
async def test_create_needs_the_company_in_scope_and_can_edit(client, db_session):
    manager, _, company, jobs = await _setup(client, db_session, requirements=1)
    stranger = await make_recruiter(db_session, manager)
    await login(client, stranger)
    assert (await client.post(DRIVES, json=_body(company, jobs))).status_code == 404
    await login(client, manager)
    assert (await client.post(DRIVES, json=_body(company, jobs))).status_code == 403


# --- reads and scope (DR8) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scope_owner_manager_bdm_and_others(client, db_session):
    manager, recruiter, company, jobs = await _setup(client, db_session, requirements=1)
    bdm = await make_user(db_session, "bdm", "it")
    company.assigned_bdm_user_id = bdm.id
    await db_session.commit()
    drive = await _create(client, company, jobs)
    url = f"{DRIVES}/{drive['id']}"
    listed = (await client.get(DRIVES, params={"q": drive["code"]})).json()
    assert [i["id"] for i in listed["items"]] == [drive["id"]] and listed["can_create"] is True

    await login(client, await make_recruiter(db_session, manager))
    assert (await client.get(url)).status_code == 404
    assert (await client.get(f"{url}/funnel")).status_code == 404
    assert (await client.get(DRIVES, params={"q": drive["code"]})).json()["total"] == 0

    for reader in (manager, bdm):
        await login(client, reader)
        read = await client.get(url)
        assert read.status_code == 200 and read.json()["can_edit"] is False
        assert (await client.patch(url, json={"job_role": "Changed"})).status_code == 403

    await as_role(client, db_session, "hr_team", "it")
    assert (await client.get(DRIVES)).status_code == 403
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(url)).json()["can_edit"] is True


@pytest.mark.asyncio
async def test_list_filters_by_status_and_search(client, db_session):
    _, _, company, jobs = await _setup(client, db_session, requirements=1)
    planned = await _create(client, company, jobs, job_role=f"Analyst {_tag()}")
    done = await _create(client, company, jobs, job_role=f"Analyst {_tag()}")
    assert (await client.patch(f"{DRIVES}/{done['id']}", json={"status": "completed"})).status_code == 200
    by_role = (await client.get(DRIVES, params={"q": planned["job_role"]})).json()
    assert [i["id"] for i in by_role["items"]] == [planned["id"]]
    assert by_role["items"][0]["requirement_count"] == 1
    completed = (await client.get(DRIVES, params={"q": company.name, "status": "completed"})).json()
    assert [i["id"] for i in completed["items"]] == [done["id"]]


@pytest.mark.asyncio
async def test_college_options_list_live_college_and_university_orgs(client, db_session):
    await _setup(client, db_session, requirements=0)
    bdm = await make_user(db_session, "bdm", "it")
    college, university = await _college(db_session, bdm), await _college(db_session, bdm, org_type="university")
    agent, archived = await _college(db_session, bdm, org_type="agent"), await _college(db_session, bdm, archived=True)
    found = set()
    for org in (college, university, agent, archived):
        items = (await client.get(f"{DRIVES}/college-options", params={"q": org.name})).json()["items"]
        found |= {i["id"] for i in items}
        if org in (college, university):
            assert items == [{"id": str(org.id), "code": org.code, "name": org.name, "city": "Kochi"}]
    assert found == {str(college.id), str(university.id)}


# --- edits (DR3, DR4) --------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_replaces_requirements_and_a_cancelled_drive_is_final(client, db_session):
    _, recruiter, company, jobs = await _setup(client, db_session, requirements=2)
    drive = await _create(client, company, jobs[:1])
    url = f"{DRIVES}/{drive['id']}"
    both = await client.patch(url, json={"requirement_ids": [str(j.id) for j in jobs], "job_role": "SDE Trainee"})
    assert both.status_code == 200 and len(both.json()["requirements"]) == 2 and both.json()["job_role"] == "SDE Trainee"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == drive["id"], AuditLog.action == "recruitment_drive.update"))
    assert audit is not None and audit.metadata_json["fields"] == ["job_role", "requirement_ids"]

    candidate = await _candidate(db_session, recruiter)
    added = await client.post(f"{REQ}/{jobs[1].id}/candidates", json={"candidate_id": str(candidate.id), "drive_id": drive["id"]})
    assert added.status_code == 201, added.text
    removed = await client.patch(url, json={"requirement_ids": [str(jobs[0].id)]})
    assert removed.status_code == 409

    assert (await client.patch(url, json={"status": "cancelled"})).status_code == 200
    assert (await client.patch(url, json={"job_role": "Again"})).status_code == 409
    assert (await client.patch(url, json={"status": "planned"})).status_code == 409


@pytest.mark.asyncio
async def test_null_on_a_required_field_is_422(client, db_session):
    _, _, company, jobs = await _setup(client, db_session, requirements=1)
    drive = await _create(client, company, jobs)
    for field in ("drive_date", "job_role", "vacancies", "status", "requirement_ids"):
        assert (await client.patch(f"{DRIVES}/{drive['id']}", json={field: None})).status_code == 422, field


# --- adding candidates with the drive tag (DR9) ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_adding_through_a_drive_tags_the_application(client, db_session):
    manager, recruiter, company, jobs = await _setup(client, db_session, requirements=1)
    outside = await _requirement(db_session, recruiter, company=company)
    drive = await _create(client, company, jobs)
    candidate = await _candidate(db_session, recruiter)
    wrong = await client.post(f"{REQ}/{outside.id}/candidates", json={"candidate_id": str(candidate.id), "drive_id": drive["id"]})
    assert wrong.status_code == 422 and _loc(wrong) == ["drive_id"]
    missing = await client.post(f"{REQ}/{jobs[0].id}/candidates", json={"candidate_id": str(candidate.id), "drive_id": str(uuid.uuid4())})
    assert missing.status_code == 422 and _loc(missing) == ["drive_id"]

    added = await client.post(f"{REQ}/{jobs[0].id}/candidates", json={"candidate_id": str(candidate.id), "drive_id": drive["id"]})
    assert added.status_code == 201
    stored = await db_session.scalar(select(JobApplication.drive_id).where(JobApplication.id == uuid.UUID(added.json()["application"]["id"])))
    assert stored == uuid.UUID(drive["id"])
    listed = (await client.get(f"{DRIVES}/{drive['id']}/candidates")).json()["items"]
    assert [(i["candidate"]["id"], i["requirement"]["id"], i["status"]) for i in listed] == [(str(candidate.id), str(jobs[0].id), "sourced")]

    await client.patch(f"{DRIVES}/{drive['id']}", json={"status": "cancelled"})
    other = await _candidate(db_session, recruiter)
    closed = await client.post(f"{REQ}/{jobs[0].id}/candidates", json={"candidate_id": str(other.id), "drive_id": drive["id"]})
    assert closed.status_code == 409


# --- the funnel (AC1, DR7) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_funnel_equals_the_drive_tagged_counts(client, db_session):
    _, recruiter, company, jobs = await _setup(client, db_session, requirements=2)
    drive = await _create(client, company, jobs)
    paths = [
        (),  # stays Sourced
        ("shortlisted",),
        ("shortlisted", "rejected"),  # reached Shortlisted, then rejected: still shortlisted
        ("interview", "selected"),
        ("interview", "selected", "joined"),
    ]
    applications = []
    for i, path in enumerate(paths):
        candidate = await _candidate(db_session, recruiter)
        added = await client.post(f"{REQ}/{jobs[i % 2].id}/candidates", json={"candidate_id": str(candidate.id), "drive_id": drive["id"]})
        application_id = added.json()["application"]["id"]
        applications.append(application_id)
        for step in path:
            assert (await _move(client, application_id, step)).status_code == 200, (path, step)
    untagged = await _candidate(db_session, recruiter)  # same requirement, not through the drive: never counted
    plain = (await client.post(f"{REQ}/{jobs[0].id}/candidates", json={"candidate_id": str(untagged.id)})).json()["application"]["id"]
    for step in ("interview", "selected"):
        await _move(client, plain, step)
    for application_id, status in ((applications[3], "completed"), (applications[4], "selected"), (applications[1], "scheduled"), (plain, "completed")):
        db_session.add(Interview(application_id=uuid.UUID(application_id), scheduled_at=datetime.now(UTC), status=status))
    await db_session.commit()

    funnel = (await client.get(f"{DRIVES}/{drive['id']}/funnel")).json()
    assert funnel == {"registered": 200, "attended": 100, "tagged": 5, "shortlisted": 4, "interviewed": 2, "selected": 2, "joined": 1}
    assert (await client.get(f"{DRIVES}/{drive['id']}")).json()["funnel"] == funnel


@pytest.mark.asyncio
async def test_the_funnel_is_one_query(client, db_session):
    _, _, company, jobs = await _setup(client, db_session, requirements=1)
    drive = await _create(client, company, jobs)
    seen: list[str] = []
    listener = lambda *args: seen.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        await svc.funnel(db_session, uuid.UUID(drive["id"]))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert len(seen) == 1

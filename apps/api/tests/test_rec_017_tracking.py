"""rec-017 -- candidate + requirement tracking (spec §2-§4; AC1, AC2; DEC-SCOPE-134 A1-A4). Names are unique per test (the database is
shared and never truncated)."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import AuditLog, Candidate, Company, CompanyStageHistory, Job, JobApplication, JobApplicationStatusHistory, Notification, RecCandidateSource
from app.services import applications as svc
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user

REQ = "/api/v1/recruiter/requirements"
APPS = "/api/v1/recruiter/applications"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _requirement(db, recruiter=None, status="requirement_received", company=None) -> Job:
    if company is None:
        company = Company(name=f"Track Co {_tag()}", assigned_recruiter_user_id=recruiter.id if recruiter else None)
        db.add(company)
        await db.flush()
    job = Job(company_id=company.id, title=f"Java Dev {_tag()}", location="Pune", description="", skills=[], status=status)
    db.add(job)
    await db.commit()
    return job


async def _candidate(db, creator, **extra) -> Candidate:
    source = await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == "referral"))
    fields = {"name": f"Rahul {_tag()}", "email": f"{_tag()}@example.com", "preferred_locations": [], **extra}
    candidate = Candidate(candidate_code=await svc.candidates.next_code(db), source_id=source.id, created_by_user_id=creator.id, **fields)
    db.add(candidate)
    await db.commit()
    return candidate


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _add(client, job, candidate, **body):
    return await client.post(f"{REQ}/{job.id}/candidates", json={"candidate_id": str(candidate.id), **body})


async def _move(client, application_id, status, note=None):
    return await client.post(f"{APPS}/{application_id}/status", json={"status": status, **({"note": note} if note else {})})


# --- the engine (A2) ------------------------------------------------------------------------------------------------------------------
def test_transition_table_matches_a2():
    for status in svc.OPEN:
        assert set(svc.TRANSITIONS[status]) == (set(svc.OPEN) - {status}) | {"selected", "rejected", "withdrawn"}
    assert svc.TRANSITIONS["selected"] == ("joined", "rejected", "withdrawn")
    assert svc.TRANSITIONS["joined"] == ()
    assert svc.TRANSITIONS["rejected"] == svc.TRANSITIONS["withdrawn"] == ("sourced",)
    assert set(svc.LABELS) == set(svc.TRANSITIONS)


@pytest.mark.parametrize("current", ["sourced", "interview", "rejected", "withdrawn"])
def test_joined_only_from_selected(current):
    with pytest.raises(HTTPException) as exc:
        svc.check_transition(current, "joined")
    assert exc.value.status_code == 409 and exc.value.detail == svc.JOINED_GATE
    svc.check_transition("selected", "joined")


def test_legacy_words_map_to_a1():
    assert {w: svc.from_legacy(w) for w in svc.LEGACY} == {
        "applied": "sourced", "screening": "screened", "shortlisted": "shortlisted", "interview_scheduled": "interview",
        "offer_received": "selected", "hired": "joined", "rejected": "rejected", "withdrawn": "withdrawn",
    }
    assert svc.from_legacy("profile_shared") == "profile_shared" and svc.from_legacy("nonsense") is None


def test_migration_and_service_share_the_legacy_map():
    from tests.test_rec_017_migration import _migration

    assert _migration.LEGACY == svc.LEGACY


# --- AC1 / AC2 -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_one_candidate_has_different_statuses_per_requirement(client, db_session):
    _, recruiter = await _team(client, db_session)
    abc, xyz = await _requirement(db_session, recruiter), await _requirement(db_session, recruiter)
    rahul = await _candidate(db_session, recruiter)
    a = (await _add(client, abc, rahul)).json()["application"]
    x = (await _add(client, xyz, rahul, status="shortlisted")).json()["application"]
    for step in ("screened", "shortlisted", "interview"):
        response = await _move(client, a["id"], step)
        assert response.status_code == 200, response.text
    assert (await _move(client, x["id"], "rejected", "Not a fit")).status_code == 200
    tab = await client.get(f"/api/v1/recruiter/candidates/{rahul.id}/applications")
    assert tab.status_code == 200
    by_job = {i["requirement"]["id"]: (i["status"], i["status_label"], i["in_scope"]) for i in tab.json()["items"]}
    assert by_job == {str(abc.id): ("interview", "Interview", True), str(xyz.id): ("rejected", "Rejected", True)}
    history = (await client.get(f"{APPS}/{a['id']}/history")).json()["items"]
    assert [(h["from_status"], h["to_status"]) for h in history] == [("shortlisted", "interview"), ("screened", "shortlisted"), ("sourced", "screened"), (None, "sourced")]
    assert history[0]["changed_by"]["id"] == str(recruiter.id)


@pytest.mark.asyncio
async def test_ac2_adding_the_same_candidate_twice_is_409(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    candidate = await _candidate(db_session, recruiter)
    first = await _add(client, job, candidate, note="From LinkedIn")
    assert first.status_code == 201
    body = first.json()["application"]
    assert body["status"] == "sourced" and body["candidate"]["code"] == candidate.candidate_code
    assert {s["key"] for s in body["allowed_statuses"]} == {"screened", "shortlisted", "profile_shared", "interview", "selected", "rejected", "withdrawn"}
    again = await _add(client, job, candidate, status="shortlisted")
    assert again.status_code == 409 and again.json()["detail"] == svc.DUPLICATE
    assert await db_session.scalar(select(func.count()).select_from(JobApplication).where(JobApplication.job_id == job.id)) == 1


@pytest.mark.asyncio
async def test_adding_fires_candidates_sourcing_on_the_company_and_audits(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    company = await db_session.get(Company, job.company_id)
    company.stage = "requirement_received"
    await db_session.commit()
    response = await _add(client, job, await _candidate(db_session, recruiter))
    app_id = response.json()["application"]["id"]
    stage = await db_session.scalar(select(Company.stage).where(Company.id == job.company_id).execution_options(populate_existing=True))
    assert stage == "candidates_sourcing"
    events = (await db_session.scalars(select(CompanyStageHistory.event).where(CompanyStageHistory.company_id == job.company_id))).all()
    assert "candidates_sourcing" in events
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == app_id))
    assert audit.action == "recruiter_application.add" and "name" not in audit.metadata_json


@pytest.mark.asyncio
async def test_joined_without_selection_is_409_and_with_selection_is_allowed(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    skip = await _move(client, app_id, "joined")
    assert skip.status_code == 409 and skip.json()["detail"] == svc.JOINED_GATE
    assert (await _move(client, app_id, "selected")).status_code == 200
    joined = await _move(client, app_id, "joined")
    assert joined.status_code == 200 and joined.json()["application"]["allowed_statuses"] == []
    assert (await _move(client, app_id, "rejected")).status_code == 409  # joined is terminal


@pytest.mark.asyncio
async def test_rejected_reopens_to_sourced_and_same_status_is_409(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter), status="screened")).json()["application"]["id"]
    assert (await _move(client, app_id, "screened")).status_code == 409
    assert (await _move(client, app_id, "rejected")).status_code == 200
    assert (await _move(client, app_id, "interview")).status_code == 409
    assert (await _move(client, app_id, "sourced", "Reconsidered")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"status": "joined"}, {"status": "applied"}, {"extra": 1}, {"note": "x" * 501}])
async def test_invalid_add_bodies_are_422(client, db_session, body):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    assert (await _add(client, job, await _candidate(db_session, recruiter), **body)).status_code == 422


@pytest.mark.asyncio
async def test_unknown_status_is_422(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    assert (await _move(client, app_id, "interview_scheduled")).status_code == 422


# --- the candidate pool and the requirement state ---------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_only_active_pool_candidates_can_be_added(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    student = await make_user(db_session, "it_student", "it")
    hidden = await _candidate(db_session, recruiter, user_id=student.id, opted_in=False)  # backfilled, not opted in (R6)
    assert (await _add(client, job, hidden)).status_code == 422
    from datetime import UTC, datetime

    archived = await _candidate(db_session, recruiter, archived_at=datetime.now(UTC))
    assert (await _add(client, job, archived)).status_code == 422
    assert (await client.post(f"{REQ}/{job.id}/candidates", json={"candidate_id": str(uuid.uuid4())})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["closed", "cancelled"])
async def test_ended_requirements_take_no_new_candidates(client, db_session, status):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter, status=status)
    listing = await client.get(f"{REQ}/{job.id}/candidates")
    assert listing.status_code == 200 and listing.json()["can_add"] is False
    assert (await _add(client, job, await _candidate(db_session, recruiter))).status_code == 409


# --- RBAC (§4) --------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_another_recruiters_requirement_is_404(client, db_session):
    _, recruiter = await _team(client, db_session)
    other = await make_recruiter(db_session, None)
    theirs = await _requirement(db_session, other)
    candidate = await _candidate(db_session, other)
    await login(client, other)
    app_id = (await _add(client, theirs, candidate)).json()["application"]["id"]
    await login(client, recruiter)
    assert (await client.get(f"{REQ}/{theirs.id}/candidates")).status_code == 404
    assert (await _add(client, theirs, candidate)).status_code == 404
    assert (await _move(client, app_id, "screened")).status_code == 404
    assert (await client.get(f"{APPS}/{app_id}/history")).status_code == 404
    tab = (await client.get(f"/api/v1/recruiter/candidates/{candidate.id}/applications")).json()["items"]
    assert [(i["status"], i["in_scope"]) for i in tab] == [("sourced", False)]


@pytest.mark.asyncio
async def test_manager_reads_the_team_but_never_writes(client, db_session):
    manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    candidate = await _candidate(db_session, recruiter)
    app_id = (await _add(client, job, candidate)).json()["application"]["id"]
    await login(client, manager)
    listing = await client.get(f"{REQ}/{job.id}/candidates")
    assert listing.status_code == 200 and listing.json()["can_add"] is False
    assert listing.json()["items"][0]["allowed_statuses"] == []
    assert (await _move(client, app_id, "screened")).status_code == 403
    assert (await _add(client, job, await _candidate(db_session, recruiter))).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_writes_and_assigned_bdm_reads(client, db_session):
    recruiter = await make_recruiter(db_session, None)
    bdm = await make_user(db_session, "bdm", "global")
    job = await _requirement(db_session, recruiter)
    company = await db_session.get(Company, job.company_id)
    company.assigned_bdm_user_id = bdm.id
    await db_session.commit()
    await as_role(client, db_session, "super_admin", "global")
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    assert (await _move(client, app_id, "screened")).status_code == 200
    await login(client, bdm)
    assert (await client.get(f"{REQ}/{job.id}/candidates")).status_code == 200
    assert (await _move(client, app_id, "shortlisted")).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_student", "it"), ("employer", "it"), ("hr_team", "it"), ("overseas_admin", "overseas"), ("telecaller", "global")])
async def test_outsiders_are_refused(client, db_session, role, division):
    recruiter = await make_recruiter(db_session, None)
    job = await _requirement(db_session, recruiter)
    await as_role(client, db_session, role, division)
    assert (await client.get(f"{REQ}/{job.id}/candidates")).status_code == 403
    assert (await client.post(f"{REQ}/{job.id}/candidates", json={"candidate_id": str(uuid.uuid4())})).status_code == 403
    assert (await _move(client, uuid.uuid4(), "screened")).status_code == 403


@pytest.mark.asyncio
async def test_hr_team_reads_the_candidate_applications_tab(client, db_session):
    recruiter = await make_recruiter(db_session, None)
    job = await _requirement(db_session, recruiter)
    candidate = await _candidate(db_session, recruiter)
    await login(client, recruiter)
    await _add(client, job, candidate)
    await as_role(client, db_session, "hr_team", "it")
    tab = await client.get(f"/api/v1/recruiter/candidates/{candidate.id}/applications")
    assert tab.status_code == 200 and [i["in_scope"] for i in tab.json()["items"]] == [False]
    await as_role(client, db_session, "it_student", "it")
    assert (await client.get(f"/api/v1/recruiter/candidates/{candidate.id}/applications")).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(f"{REQ}/{uuid.uuid4()}/candidates")).status_code == 401


# --- students (A3/A4) -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_student_status_change_notifies_the_student(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    student = await make_user(db_session, "it_student", "it")
    candidate = await _candidate(db_session, recruiter, user_id=student.id, opted_in=True)
    app_id = (await _add(client, job, candidate)).json()["application"]["id"]
    application = await db_session.get(JobApplication, uuid.UUID(app_id))
    assert application.student_id == student.id
    assert (await _move(client, app_id, "shortlisted")).status_code == 200
    note = await db_session.scalar(select(Notification).where(Notification.user_id == student.id).order_by(Notification.created_at.desc()))
    assert note.body == "Your application status is now Shortlisted."


@pytest.mark.asyncio
async def test_candidate_for_student_links_an_external_match_and_keeps_it_visible(db_session):
    recruiter = await make_recruiter(db_session, None)
    student = await make_user(db_session, "it_student", "it")
    external = await _candidate(db_session, recruiter, email=student.email.upper())
    linked = await svc.candidate_for_student(db_session, student)
    assert linked.id == external.id and linked.user_id == student.id and linked.opted_in is True
    assert (await svc.candidate_for_student(db_session, student)).id == external.id


@pytest.mark.asyncio
async def test_candidate_for_student_creates_one_outside_the_pool(db_session):
    student = await make_user(db_session, "it_student", "it")
    created = await svc.candidate_for_student(db_session, student)
    await db_session.commit()
    assert created.user_id == student.id and created.opted_in is False and created.email == student.email
    assert created.candidate_code.startswith("CAN-") and created.created_by_user_id == student.id
    source = await db_session.get(RecCandidateSource, created.source_id)
    assert source.name.lower() == svc.STUDENT_SOURCE.lower()


@pytest.mark.asyncio
async def test_history_rows_are_written_for_every_change(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    await _move(client, app_id, "interview", "Round 1 on Monday")
    rows = (await db_session.scalars(select(JobApplicationStatusHistory).where(JobApplicationStatusHistory.application_id == uuid.UUID(app_id)))).all()
    assert sorted((r.from_status or "", r.to_status, r.note or "") for r in rows) == [("", "sourced", ""), ("sourced", "interview", "Round 1 on Monday")]

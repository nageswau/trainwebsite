"""hrc-007 (DEC-SCOPE-380, spec docs/superpowers/specs/2026-11-04-hrc-007-vacancy-approval-design.md): the vacancy approval workflow
(A3-A10, AC1-AC4, the + / - / E scenarios) and the Filled status (A11). Names are unique per test (the database is shared); a test that
changes an approval setting or a role's grants puts the seeded value back."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.core import rbac
from app.models import JOB_OPEN_STATUSES, AuditLog, Job, JobApprovalSetting, JobStatusHistory
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user
from tests.rec017_helpers import student_application
from tests.test_emp_002_job_posting import _create_student, _login, _register_employer
from tests.test_rec_007_requirements import _company, _create, _set_status

BASE = "/api/v1/recruiter/requirements"
QUEUE = "/api/v1/recruiter/requirement-approvals"
SEEDED = {"employer": True, "recruiter": False, "legacy": False}  # A4


@pytest_asyncio.fixture(autouse=True)
async def _restore_settings(db_session):
    yield
    for source, required in SEEDED.items():
        await db_session.execute(update(JobApprovalSetting).where(JobApprovalSetting.source == source).values(required=required))
    await db_session.commit()


async def _require(db, source: str, required: bool) -> None:
    await db.execute(update(JobApprovalSetting).where(JobApprovalSetting.source == source).values(required=required))
    await db.commit()


async def _recruiter_job(client, db, **body):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    company = await _company(db, recruiter)
    await login(client, recruiter)
    response = await _create(client, company, **body)
    assert response.status_code == 201, response.text
    return recruiter, response.json()["requirement"]


async def _approver(client, db):
    return await as_role(client, db, "hr_manager", "it")


async def _employer_pending_job(client):
    await _register_employer(client)
    job = (await client.post("/api/v1/employer/jobs", json={"title": f"Approval Job {uuid.uuid4().hex[:6]}", "location": "Pune", "description": "d", "skills": []})).json()
    published = await client.patch(f"/api/v1/employer/jobs/{job['id']}", json={"status": "open"})
    assert published.status_code == 200, published.text
    return published.json()


# --- + scenario, AC1, AC2: employer posts, HR Manager approves, it becomes visible ------------------------------------------------
@pytest.mark.asyncio
async def test_employer_publish_waits_for_hr_manager_approval_then_opens(client, db_session):
    job = await _employer_pending_job(client)
    assert job["status"] == "draft" and job["requirement_status"] == "pending_approval" and job["status_label"] == "Pending Approval"
    assert job["visible_to_students"] is False

    student = await _create_student(db_session)
    await _login(client, student.email)
    assert (await client.post(f"/api/v1/workflows/it/jobs/{job['id']}/apply", json={})).status_code == 404  # AC1

    await _approver(client, db_session)
    queue = (await client.get(QUEUE, params={"limit": 100})).json()
    row = next(r for r in queue["items"] if r["id"] == job["id"])
    assert row["source"] == "employer" and row["can_decide"] is True and row["submitted_at"]
    approved = await client.post(f"{BASE}/{job['id']}/approve", json={"note": "Looks good"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["requirement"]["status"] == "requirement_received"  # AC2

    await _login(client, student.email)
    assert (await client.post(f"/api/v1/workflows/it/jobs/{job['id']}/apply", json={})).status_code == 201
    rows = (await db_session.scalars(select(JobStatusHistory).where(JobStatusHistory.job_id == uuid.UUID(job["id"])).order_by(JobStatusHistory.created_at))).all()
    assert [(r.from_status, r.to_status) for r in rows] == [(None, "new"), ("new", "pending_approval"), ("pending_approval", "requirement_received")]
    assert rows[-1].note == "Approved: Looks good"
    actions = set(await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == job["id"])))
    assert {"recruiter_requirement.submit", "recruiter_requirement.approve"} <= actions


# --- - scenario: nobody approves their own job; no grant = 403 ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_recruiter_approving_their_own_job_gets_403(client, db_session):
    await _require(db_session, "recruiter", True)
    recruiter, req = await _recruiter_job(client, db_session)
    assert (await client.post(f"{BASE}/{req['id']}/submit", json={})).status_code == 200
    assert (await client.post(f"{BASE}/{req['id']}/approve", json={})).status_code == 403  # no grant
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.put("/api/v1/admin/roles/placement_team/permissions", json={"permissions": [*rbac.DEFAULT_GRANTS["placement_team"], "jobs.approve"]})).status_code == 200
    try:
        await login(client, recruiter)
        response = await client.post(f"{BASE}/{req['id']}/approve", json={})
        assert response.status_code == 403 and "own" in response.json()["detail"]
        assert next(r for r in (await client.get(QUEUE, params={"limit": 100})).json()["items"] if r["id"] == req["id"])["can_decide"] is False
    finally:
        await as_role(client, db_session, "super_admin", "global")
        await client.put("/api/v1/admin/roles/placement_team/permissions", json={"permissions": list(rbac.DEFAULT_GRANTS["placement_team"])})


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["placement_manager", "employer", "it_student", "placement_officer"])
async def test_the_queue_and_decisions_need_the_approve_grant(client, db_session, role):
    await as_role(client, db_session, role, "it")
    assert (await client.get(QUEUE)).status_code == 403
    assert (await client.post(f"{BASE}/{uuid.uuid4()}/approve", json={})).status_code == 403


@pytest.mark.asyncio
async def test_approver_gets_404_for_a_missing_job_and_409_for_one_not_pending(client, db_session):
    _, req = await _recruiter_job(client, db_session)  # approval off for recruiters: stays a draft
    await _approver(client, db_session)
    assert (await client.post(f"{BASE}/{uuid.uuid4()}/approve", json={})).status_code == 404
    assert (await client.post(f"{BASE}/{req['id']}/approve", json={})).status_code == 409
    assert (await client.post(f"{BASE}/{req['id']}/reject", json={"reason": "No"})).status_code == 409


# --- AC3: a rejected job returns to draft with a reason ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rejecting_returns_the_job_to_draft_with_the_reason(client, db_session):
    job = await _employer_pending_job(client)
    await _approver(client, db_session)
    assert (await client.post(f"{BASE}/{job['id']}/reject", json={})).status_code == 422  # a reason is required
    assert (await client.post(f"{BASE}/{job['id']}/reject", json={"reason": "   "})).status_code == 422
    rejected = await client.post(f"{BASE}/{job['id']}/reject", json={"reason": "Salary missing"})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["requirement"]["status"] == "new"
    last = await db_session.scalar(select(JobStatusHistory).where(JobStatusHistory.job_id == uuid.UUID(job["id"])).order_by(JobStatusHistory.created_at.desc()).limit(1))
    assert (last.from_status, last.to_status, last.note) == ("pending_approval", "new", "Rejected: Salary missing")
    assert job["id"] not in {r["id"] for r in (await client.get(QUEUE, params={"limit": 100})).json()["items"]}


# --- A7: the gate; A6: submit ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_while_approval_applies_a_draft_cannot_open_without_it(client, db_session):
    await _require(db_session, "recruiter", True)
    _, req = await _recruiter_job(client, db_session)
    assert req["approval"] == {"required": True, "submitted_by": None, "submitted_at": None, "can_submit": True, "can_decide": False}
    assert not {s["key"] for s in req["allowed_statuses"]} & set(JOB_OPEN_STATUSES)
    response = await _set_status(client, req["id"], "requirement_received")
    assert response.status_code == 409 and "approval" in response.json()["detail"]
    submitted = await client.post(f"{BASE}/{req['id']}/submit", json={"note": "Ready"})
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()["requirement"]
    assert body["status"] == "pending_approval" and body["phase"] == "pending_approval" and body["approval"]["can_submit"] is False
    assert [s["key"] for s in body["allowed_statuses"]] == ["cancelled"]
    assert (await client.post(f"{BASE}/{req['id']}/submit", json={})).status_code == 409  # already pending


@pytest.mark.asyncio
async def test_submit_is_refused_when_the_source_needs_no_approval(client, db_session):
    _, req = await _recruiter_job(client, db_session)
    assert req["approval"]["required"] is False
    assert (await client.post(f"{BASE}/{req['id']}/submit", json={})).status_code == 409
    assert (await _set_status(client, req["id"], "requirement_received")).status_code == 200  # today's behaviour is unchanged


# --- E: the setting is turned off while jobs are pending ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_turning_the_setting_off_leaves_pending_jobs_pending_and_decidable(client, db_session):
    await _require(db_session, "recruiter", True)
    _, req = await _recruiter_job(client, db_session)
    await client.post(f"{BASE}/{req['id']}/submit", json={})
    await as_role(client, db_session, "super_admin", "global")
    turned = await client.put(f"{QUEUE}/settings", json={"recruiter": False})
    assert turned.status_code == 200 and turned.json()["settings"]["recruiter"] is False
    detail = (await client.get(f"{BASE}/{req['id']}")).json()["requirement"]
    assert detail["status"] == "pending_approval"
    await _approver(client, db_session)
    assert (await client.post(f"{BASE}/{req['id']}/approve", json={})).json()["requirement"]["status"] == "requirement_received"


@pytest.mark.asyncio
async def test_only_super_admin_changes_the_approval_settings(client, db_session):
    await _approver(client, db_session)
    assert (await client.get(f"{QUEUE}/settings")).json()["settings"] == SEEDED
    assert (await client.put(f"{QUEUE}/settings", json={"employer": False})).status_code == 403
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.put(f"{QUEUE}/settings", json={"bogus": True})).status_code == 422
    assert (await client.put(f"{QUEUE}/settings", json={"legacy": True})).json()["settings"]["legacy"] is True
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "recruiter_requirement.approval_settings").limit(1))


# --- AC4: history is kept after closure; A5: approved once is approved ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_history_survives_closure_and_a_reopen_needs_no_second_approval(client, db_session):
    await _require(db_session, "recruiter", True)
    recruiter, req = await _recruiter_job(client, db_session)
    await client.post(f"{BASE}/{req['id']}/submit", json={})
    await _approver(client, db_session)
    await client.post(f"{BASE}/{req['id']}/approve", json={})
    await login(client, recruiter)
    assert (await _set_status(client, req["id"], "on_hold")).status_code == 200
    assert (await _set_status(client, req["id"], "sourcing")).status_code == 200  # A5
    assert (await _set_status(client, req["id"], "closed")).status_code == 200
    history = (await client.get(f"{BASE}/{req['id']}")).json()["requirement"]["status_history"]
    assert {"pending_approval", "requirement_received", "closed"} <= {h["to_status"] for h in history}
    assert history[0]["to_status"] == "closed"


# --- A11: Filled ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_last_vacancy_joining_fills_the_job(client, db_session):
    recruiter, req = await _recruiter_job(client, db_session, vacancies=1)
    await _set_status(client, req["id"], "requirement_received")
    student = await make_user(db_session, "it_student", "it")
    application = await student_application(db_session, uuid.UUID(req["id"]), student, status="selected")
    await db_session.commit()
    moved = await client.post(f"/api/v1/recruiter/applications/{application.id}/status", json={"status": "joined"})
    assert moved.status_code == 200, moved.text
    detail = (await client.get(f"{BASE}/{req['id']}")).json()["requirement"]
    assert detail["status"] == "filled" and detail["status_label"] == "Filled" and detail["phase"] == "filled"
    assert detail["status_history"][0]["note"] == "All vacancies filled"
    assert {s["key"] for s in detail["allowed_statuses"]} == {"requirement_received", "closed"}


@pytest.mark.asyncio
async def test_a_job_with_seats_left_is_not_filled_and_can_be_filled_by_hand(client, db_session):
    _, req = await _recruiter_job(client, db_session, vacancies=2)
    await _set_status(client, req["id"], "requirement_received")
    student = await make_user(db_session, "it_student", "it")
    application = await student_application(db_session, uuid.UUID(req["id"]), student, status="selected")
    await db_session.commit()
    await client.post(f"/api/v1/recruiter/applications/{application.id}/status", json={"status": "joined"})
    assert (await client.get(f"{BASE}/{req['id']}")).json()["requirement"]["status"] == "requirement_received"
    assert (await _set_status(client, req["id"], "filled")).json()["requirement"]["status"] == "filled"
    job = await db_session.get(Job, uuid.UUID(req["id"]))
    await db_session.refresh(job)
    assert job.status not in JOB_OPEN_STATUSES  # no new applications


# --- A2: the PDF's seven phases ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_catalogue_maps_every_status_to_one_of_seven_phases(client, db_session):
    await _recruiter_job(client, db_session)
    statuses = (await client.get(f"{BASE}/statuses")).json()["statuses"]
    phases = {s["key"]: s["phase"] for s in statuses}
    assert phases["new"] == "draft" and phases["pending_approval"] == "pending_approval" and phases["sourcing"] == "open"
    assert phases["selected"] == "open" and phases["joined"] == "filled" and phases["filled"] == "filled"
    assert set(phases.values()) == {"draft", "pending_approval", "open", "on_hold", "filled", "closed", "cancelled"}
    assert {s["phase_label"] for s in statuses} == {"Draft", "Pending Approval", "Open", "On Hold", "Filled", "Closed", "Cancelled"}


@pytest.mark.asyncio
async def test_legacy_staff_open_word_submits_when_legacy_approval_is_on(client, db_session):
    await _require(db_session, "legacy", True)
    await as_role(client, db_session, "it_admin", "it")
    company = await _company(db_session)
    created = await client.post("/api/v1/workflows/it/jobs", json={"company_id": str(company.id), "title": f"Legacy {uuid.uuid4().hex[:6]}"})
    assert created.status_code == 201 and created.json()["status"] == "pending_approval"
    job = await db_session.get(Job, uuid.UUID(created.json()["id"]))
    assert job.source == "legacy"

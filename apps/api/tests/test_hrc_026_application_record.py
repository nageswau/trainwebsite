"""hrc-026 -- application record completion (DEC-SCOPE-394; design docs/superpowers/specs/2026-11-04-hrc-026-application-record-design.md):
a human Application ID, source and owner, a structured rejection reason, a receipt on apply, and candidate-visible stages. Names are unique
per test (the database is shared and never truncated)."""

import re
import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, JobApplication, JobApplicationStatusHistory, Notification
from app.services import applications as svc
from tests.rec001_helpers import login, make_user
from tests.test_rec_017_tracking import APPS, REQ, _add, _candidate, _requirement, _team

WF = "/api/v1/workflows/it"
CODE = re.compile(r"^JA-\d{6,}$")


async def _status(client, app_id, status, **body):
    return await client.post(f"{APPS}/{app_id}/status", json={"status": status, **body})


async def _fresh(db, app_id) -> JobApplication:
    return await db.scalar(select(JobApplication).where(JobApplication.id == uuid.UUID(str(app_id))).execution_options(populate_existing=True))


async def _student_on_board(client, db):
    _, recruiter = await _team(client, db)
    job = await _requirement(db, recruiter)
    student = await make_user(db, "it_student", "it")
    candidate = await _candidate(db, recruiter, user_id=student.id, opted_in=True)
    app_id = (await _add(client, job, candidate)).json()["application"]["id"]
    return recruiter, job, student, app_id


async def _notices(db, user) -> list[Notification]:
    return list((await db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at))).all())


# --- AC1: a unique human ID -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_every_application_gets_a_unique_human_code(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    first = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]
    second = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]
    assert CODE.match(first["code"]) and CODE.match(second["code"]) and first["code"] != second["code"]
    board = (await client.get(f"{REQ}/{job.id}/candidates")).json()["items"]
    assert {a["code"] for a in board} == {first["code"], second["code"]}


@pytest.mark.asyncio
async def test_a_directly_inserted_application_is_numbered_by_the_database(db_session):
    recruiter = await make_user(db_session, "placement_team", "it")
    job = await _requirement(db_session, recruiter)
    candidate = await _candidate(db_session, recruiter)
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, status="sourced")
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    assert CODE.match(application.application_code) and application.source == "recruiter" and application.candidate_status == "sourced"


# --- source and owner -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_recruiter_added_application_is_sourced_by_and_owned_by_the_recruiter(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    item = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]
    assert item["source"] == "recruiter" and item["source_label"] == "Recruiter"
    assert item["owner"] == {"id": str(recruiter.id), "full_name": recruiter.full_name}


@pytest.mark.asyncio
async def test_a_student_application_comes_from_the_portal_and_is_owned_by_the_requirement_recruiter(client, db_session):
    recruiter = await make_user(db_session, "placement_team", "it")
    job = await _requirement(db_session)
    job.assigned_recruiter_user_id = recruiter.id
    await db_session.commit()
    student = await make_user(db_session, "it_student", "it")
    await login(client, student)
    response = await client.post(f"{WF}/jobs/{job.id}/apply", json={})
    assert response.status_code == 201
    application = await _fresh(db_session, response.json()["id"])
    assert application.source == "portal" and application.owner_user_id == recruiter.id
    assert CODE.match(response.json()["code"])


# --- AC4: a receipt on apply ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_applying_from_the_portal_sends_a_receipt_with_the_code(client, db_session):
    job = await _requirement(db_session)
    student = await make_user(db_session, "it_student", "it")
    await login(client, student)
    response = await client.post(f"{WF}/jobs/{job.id}/apply", json={})
    code = response.json()["code"]
    notices = await _notices(db_session, student)
    assert len(notices) == 1 and notices[0].title == "Application received"
    assert code in notices[0].body and job.title in notices[0].body
    assert notices[0].action_url == "/it/student/job-applications"


@pytest.mark.asyncio
async def test_a_recruiter_added_application_sends_no_receipt(client, db_session):
    _, job, student, _ = await _student_on_board(client, db_session)
    assert await _notices(db_session, student) == []


# --- AC2: internal stages never reach the candidate --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_profile_shared_sends_no_candidate_notice_and_the_portal_keeps_the_last_visible_stage(client, db_session):
    _, job, student, app_id = await _student_on_board(client, db_session)
    assert (await _status(client, app_id, "shortlisted")).status_code == 200
    assert len(await _notices(db_session, student)) == 1
    moved = await _status(client, app_id, "profile_shared")
    assert moved.status_code == 200 and moved.json()["application"]["status"] == "profile_shared"
    assert len(await _notices(db_session, student)) == 1  # no notice for the internal stage
    assert (await _fresh(db_session, app_id)).candidate_status == "shortlisted"
    await login(client, student)
    rows = (await client.get("/api/v1/portal/it/student/job-applications")).json()["rows"]
    assert [r["status"] for r in rows] == ["Shortlisted"]
    assert rows[0]["code"] == (await _fresh(db_session, app_id)).application_code


@pytest.mark.asyncio
async def test_returning_from_an_internal_stage_to_the_same_visible_stage_sends_nothing(client, db_session):
    _, _, student, app_id = await _student_on_board(client, db_session)
    await _status(client, app_id, "shortlisted")
    await _status(client, app_id, "profile_shared")
    await _status(client, app_id, "shortlisted")
    assert len(await _notices(db_session, student)) == 1
    await _status(client, app_id, "interview")
    notices = await _notices(db_session, student)
    assert len(notices) == 2 and notices[-1].event_type == "it.application.updated"  # hrc-032 (N5): fixed text, the stage stays in the portal


@pytest.mark.asyncio
async def test_the_catalogue_says_which_stages_the_candidate_sees(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    statuses = {s["key"]: s for s in (await client.get(f"{REQ}/{job.id}/candidates")).json()["statuses"]}
    assert statuses["profile_shared"]["candidate_visible"] is False
    assert all(s["candidate_visible"] for k, s in statuses.items() if k != "profile_shared")
    assert statuses["sourced"]["candidate_label"] == "Received" and statuses["screened"]["candidate_label"] == "Screening"


@pytest.mark.asyncio
async def test_the_portal_uses_the_candidate_wording(client, db_session):
    job = await _requirement(db_session)
    student = await make_user(db_session, "it_student", "it")
    await login(client, student)
    await client.post(f"{WF}/jobs/{job.id}/apply", json={})
    rows = (await client.get("/api/v1/portal/it/student/job-applications")).json()["rows"]
    assert [r["status"] for r in rows] == ["Received"]


# --- AC3: rejection requires a reason ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rejecting_without_a_reason_is_refused(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    refused = await _status(client, app_id, "rejected")
    assert refused.status_code == 422 and "reason" in refused.text.lower()
    assert (await _fresh(db_session, app_id)).status == "sourced"
    assert (await _status(client, app_id, "rejected", rejection_reason="not_a_reason")).status_code == 422


@pytest.mark.asyncio
async def test_other_needs_a_note(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    assert (await _status(client, app_id, "rejected", rejection_reason="other")).status_code == 422
    assert (await _status(client, app_id, "rejected", rejection_reason="other", note="Joined a competitor")).status_code == 200


@pytest.mark.asyncio
async def test_a_reason_is_stored_shown_audited_and_kept_in_history_then_cleared_on_reopen(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    response = await _status(client, app_id, "rejected", rejection_reason="skills_mismatch")
    item = response.json()["application"]
    assert item["rejection_reason"] == "skills_mismatch" and item["rejection_reason_label"] == "Skills do not match"
    history = (await client.get(f"{APPS}/{app_id}/history")).json()["items"]
    assert history[0]["rejection_reason_label"] == "Skills do not match"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == app_id, AuditLog.action == "recruiter_application.status"))
    assert audit.metadata_json["rejection_reason"] == "skills_mismatch"
    reopened = (await _status(client, app_id, "sourced")).json()["application"]
    assert reopened["rejection_reason"] is None


@pytest.mark.asyncio
async def test_a_reason_on_a_move_that_is_not_a_rejection_is_refused(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    assert (await _status(client, app_id, "screened", rejection_reason="skills_mismatch")).status_code == 422


@pytest.mark.asyncio
async def test_the_legacy_patch_also_needs_a_reason(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    assert (await client.patch(f"{WF}/job-applications/{app_id}", json={"status": "rejected"})).status_code == 422
    ok = await client.patch(f"{WF}/job-applications/{app_id}", json={"status": "rejected", "rejection_reason": "not_reachable"})
    assert ok.status_code == 200 and (await _fresh(db_session, app_id)).rejection_reason == "not_reachable"


@pytest.mark.asyncio
async def test_a_screening_rejection_records_its_own_reason(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    saved = await client.put(f"{APPS}/{app_id}/screening", json={"result": "rejected", "remarks": "Weak fundamentals"})
    assert saved.status_code == 200, saved.text
    assert (await _fresh(db_session, app_id)).rejection_reason == "screening_not_cleared"


@pytest.mark.asyncio
async def test_follow_into_rejected_sets_the_interview_reason(db_session):
    recruiter = await make_user(db_session, "placement_team", "it")
    job = await _requirement(db_session, recruiter)
    candidate = await _candidate(db_session, recruiter)
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, status="interview")
    db_session.add(application)
    await db_session.flush()
    assert svc.follow(db_session, recruiter, application, "rejected", "Interview: Rejected") is True
    await db_session.commit()
    assert application.rejection_reason == "interview_not_cleared" and application.candidate_status == "rejected"
    row = await db_session.scalar(select(JobApplicationStatusHistory).where(JobApplicationStatusHistory.application_id == application.id, JobApplicationStatusHistory.to_status == "rejected"))
    assert row.rejection_reason == "interview_not_cleared"


@pytest.mark.asyncio
async def test_the_reason_never_reaches_the_student(client, db_session):
    _, _, student, app_id = await _student_on_board(client, db_session)
    await _status(client, app_id, "rejected", rejection_reason="salary_mismatch")
    notices = await _notices(db_session, student)
    assert notices[-1].event_type == "it.application.updated" and "reject" not in notices[-1].body.lower()  # hrc-032 (N5)
    await login(client, student)
    portal = (await client.get("/api/v1/portal/it/student/job-applications")).text
    assert "salary" not in portal.lower() and "Salary expectations" not in portal

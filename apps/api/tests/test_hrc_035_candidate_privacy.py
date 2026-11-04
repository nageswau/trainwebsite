"""hrc-035 (DEC-SCOPE-396, spec docs/superpowers/specs/2026-11-04-hrc-035-candidate-privacy-design.md): the basis recorded per source
(K1/K2, AC1), the candidate's deletion request and the HR Manager's decision (K6/K7, AC2/AC6), the anonymiser (K3/K4, AC3), the offer hold
(K5, AC4), the retention rule (K8, AC5) and what a deactivated staff member gives up (K9, AC7)."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import (
    AuditLog,
    Candidate,
    CandidateAssignmentHistory,
    CandidateCollaborator,
    CandidateConsent,
    CandidateNote,
    CandidateResume,
    CandidateRetentionSetting,
    Company,
    DataSubjectRequest,
    JobApplication,
    JobOffer,
    User,
)
from app.services import candidate_privacy as privacy
from app.services.storage import storage
from tests.rec038_helpers import _recruiter, _user, add, make_candidate, make_job, tag
from tests.tel026_helpers import headers
from tests.test_hrc_013_import import _csv, _send, _source
from tests.test_hrc_022_candidate_portal import PASSWORD, _verified

pytestmark = pytest.mark.asyncio
API = "/api/v1"
QUEUE = f"{API}/recruiter/candidate-data-requests"
RETENTION = f"{API}/recruiter/candidate-retention"
PRIVACY = f"{API}/candidate/me/privacy"
ERASE = f"{API}/candidate/me/erasure-request"


async def _staff(db):
    hr_manager, super_admin = await _user(db, "hr_manager", "it"), await _user(db, "super_admin", "global")
    manager = await _user(db, "placement_manager", "global")
    recruiter = await _recruiter(db, manager)
    await db.commit()
    return {"hr": hr_manager, "super": super_admin, "mgr": manager, "rec": recruiter}


async def _fresh(db, model, row_id):
    return await db.get(model, row_id, populate_existing=True)


@pytest_asyncio.fixture
async def retention_off(db_session):
    """The retention rule is one global row: each test that changes it puts it back to off."""
    yield
    row = await db_session.get(CandidateRetentionSetting, 1, populate_existing=True)
    if row is not None:
        row.months = None
        await db_session.commit()


# --- K1/K2: the basis per source ---------------------------------------------------------------------------------------------------
async def test_a_recruiter_records_the_basis_and_the_detail_shows_it(client, db_session):
    staff = await _staff(db_session)
    source = await _source(db_session)
    body = {"name": "Basis Person", "email": f"{tag('b35-')}@example.com", "source_id": source}
    made = await client.post(f"{API}/recruiter/candidates", json={**body, "lawful_basis": "provided_for_placement"}, headers=headers(staff["rec"]))
    assert made.status_code == 201, made.text
    consent = made.json()["consent"]
    assert (consent["source"], consent["lawful_basis"], consent["consent_version"]) == ("manual", "provided_for_placement", privacy.STAFF_CONSENT_VERSION)

    older = await client.post(f"{API}/recruiter/candidates", json={**body, "email": f"{tag('b35-')}@example.com"}, headers=headers(staff["rec"]))
    assert older.status_code == 201 and older.json()["consent"] is None  # an older client sends none: nothing invented
    bad = await client.post(f"{API}/recruiter/candidates", json={**body, "email": f"{tag('b35-')}@example.com", "lawful_basis": "because"}, headers=headers(staff["rec"]))
    assert bad.status_code == 422


async def test_an_import_records_the_basis_for_each_created_candidate(client, db_session):
    staff = await _staff(db_session)
    rows = [{"name": "Imp One", "email": f"{tag('i35-')}@example.com"}, {"name": "Imp Two", "email": f"{tag('i35-')}@example.com"}]
    data = {"source_id": await _source(db_session), "lawful_basis": "consent"}
    response = await client.post(f"{API}/recruiter/candidate-imports", data=data, files={"file": ("p.csv", _csv(rows), "text/csv")},
                                 headers=headers(staff["rec"]) | {"Idempotency-Key": tag("k35-")})  # fmt: skip
    assert response.status_code == 201, response.text
    ids = [r["candidate"]["id"] for r in response.json()["rows"] if r["status"] == "created"]
    assert len(ids) == 2
    found = (await db_session.execute(select(CandidateConsent.source, CandidateConsent.lawful_basis).where(CandidateConsent.candidate_id.in_(ids)))).all()
    assert sorted(found) == [("import", "consent")] * 2
    bad = await _send(client, db_session, staff["rec"], _csv(rows), key=tag("k35-"))  # no basis: the older client still works
    assert bad.status_code == 201


async def test_portal_and_website_rows_carry_their_source(client, db_session):
    _, candidate = await _verified(client, db_session)
    row = await db_session.scalar(select(CandidateConsent).where(CandidateConsent.candidate_id == candidate.id))
    assert (row.source, row.lawful_basis) == ("portal", "consent")


# --- K6/K7: the request and the decision -------------------------------------------------------------------------------------------
async def test_request_is_idempotent_and_a_rejection_reaches_the_candidate(client, db_session):
    staff = await _staff(db_session)
    user, _ = await _verified(client, db_session)
    first = await client.post(ERASE, headers=headers(user))
    assert first.status_code == 201 and first.json()["erasure"]["status"] == "in_progress"
    again = await client.post(ERASE, headers=headers(user))
    assert again.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(DataSubjectRequest).where(DataSubjectRequest.requesting_user_id == user.id)) == 1

    queue = (await client.get(QUEUE, headers=headers(staff["hr"]))).json()["items"]
    mine = next(r for r in queue if r["candidate"] and r["candidate"]["email"] == user.email)
    assert mine["status"] == "in_progress" and mine["held"] is False
    decision = f"{QUEUE}/{mine['id']}/decision"
    assert (await client.post(decision, json={"decision": "reject"}, headers=headers(staff["hr"]))).status_code == 422
    assert (await client.post(decision, json={"decision": "reject", "reason": "x" * 501}, headers=headers(staff["hr"]))).status_code == 422
    rejected = await client.post(decision, json={"decision": "reject", "reason": "An active placement contract needs these records"}, headers=headers(staff["hr"]))
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert (await client.post(decision, json={"decision": "approve"}, headers=headers(staff["hr"]))).status_code == 409  # decided once
    shown = (await client.get(PRIVACY, headers=headers(user))).json()["erasure"]
    assert shown["status"] == "rejected" and shown["rejection_reason"].startswith("An active placement")
    decided = (await client.get(f"{QUEUE}?state=decided", headers=headers(staff["hr"]))).json()["items"]
    assert any(r["id"] == mine["id"] for r in decided)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == mine["id"], AuditLog.action == "candidate.erasure_rejected"))
    assert "reason" not in audit.metadata_json  # no free text in the audit row


@pytest.mark.parametrize("role", ["placement_manager", "placement_officer", "hr_team", "it_admin", "candidate"])
async def test_only_erasers_read_the_queue(client, db_session, role):
    user = await _user(db_session, role, "global" if role == "placement_manager" else "it")
    await db_session.commit()
    assert (await client.get(QUEUE, headers=headers(user))).status_code == 403
    assert (await client.get(RETENTION, headers=headers(user))).status_code == 403


async def test_staff_cannot_use_the_candidate_route(client, db_session):
    staff = await _staff(db_session)
    assert (await client.post(ERASE, headers=headers(staff["rec"]))).status_code == 403
    assert (await client.post(ERASE)).status_code == 401


async def test_the_it_admin_fulfil_refuses_a_candidate_subject(client, db_session):
    user, _ = await _verified(client, db_session)
    item = await add(db_session, DataSubjectRequest(requesting_user_id=user.id, type="delete", status="in_progress", idempotency_key=tag("k-")))
    admin = await _user(db_session, "super_admin", "global")
    await db_session.commit()
    response = await client.patch(f"{API}/admin/data-requests/{item.id}", json={"decision": "fulfil"}, headers=headers(admin))
    assert response.status_code == 409 and "HR Manager" in response.json()["detail"]


# --- K3/K4/K5: approve anonymises; an offer holds ------------------------------------------------------------------------------------
async def _with_history(db, staff, candidate):
    """A resume file, a note, an application on a requirement (the report row that must survive) and an audit row with values."""
    key = f"candidate-resumes/{tag('r35')}"
    storage.write_bytes(key, b"%PDF-1.4 hrc035", "application/pdf")
    await add(db, CandidateResume(candidate_id=candidate.id, version=1, storage_key=key, content_type="application/pdf", size_bytes=14, uploaded_by_user_id=staff["rec"].id))
    await add(db, CandidateNote(candidate_id=candidate.id, author_user_id=staff["rec"].id, body="Called Asha on her mobile"))
    company = await add(db, Company(name=f"C35 {tag()}", assigned_recruiter_user_id=staff["rec"].id, created_by_user_id=staff["rec"].id))
    job = await make_job(db, company, staff["rec"])
    application = await add(db, JobApplication(job_id=job.id, candidate_id=candidate.id, added_by_user_id=staff["rec"].id, status="rejected"))
    db.add(AuditLog(user_id=staff["rec"].id, action="candidate.update", entity_type="candidates", entity_id=str(candidate.id),
                    metadata_json={"fields": ["email"], "changes": {"email": ["a@x.com", "b@x.com"]}}))  # fmt: skip
    await db.commit()
    return key, job, application


async def test_approve_anonymises_the_candidate_everywhere_but_reports_keep_counting(client, db_session):
    staff = await _staff(db_session)
    user, candidate = await _verified(client, db_session)
    key, job, application = await _with_history(db_session, staff, candidate)
    await client.post(ERASE, headers=headers(user))
    request_id = (await db_session.scalar(select(DataSubjectRequest.id).where(DataSubjectRequest.requesting_user_id == user.id)))
    email = user.email

    approved = await client.post(f"{QUEUE}/{request_id}/decision", json={"decision": "approve"}, headers=headers(staff["hr"]))
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "fulfilled" and approved.json()["candidate"]["anonymised"] is True

    row = await _fresh(db_session, Candidate, candidate.id)
    assert row.name == privacy.ANONYMISED_NAME and row.email.endswith("@deleted.local") and row.mobile is None and row.anonymised_reason == "request"
    assert row.archived_at is not None
    assert storage.local_file(key) is None
    assert await db_session.scalar(select(func.count()).select_from(CandidateResume).where(CandidateResume.candidate_id == candidate.id)) == 0
    assert await db_session.scalar(select(func.count()).select_from(CandidateNote).where(CandidateNote.candidate_id == candidate.id)) == 0
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(candidate.id), AuditLog.action == "candidate.update"))
    assert "changes" not in audit.metadata_json and audit.metadata_json["fields"] == ["email"]
    assert await _fresh(db_session, JobApplication, application.id) is not None  # the requirement's history still counts it

    assert (await client.get(f"{API}/recruiter/candidates/{candidate.id}", headers=headers(staff["rec"]))).status_code == 404
    for archived in ("false", "true"):  # not even among the archived (so it can never be restored)
        found = await client.get(f"{API}/recruiter/candidates?q={candidate.candidate_code}&archived={archived}", headers=headers(staff["rec"]))
        assert found.status_code == 200 and found.json()["items"] == []
    account = await _fresh(db_session, User, user.id)
    assert account.active is False and account.email != email
    login = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD, "division": "it"})
    assert login.status_code == 401
    assert (await client.get(PRIVACY, headers=headers(user))).status_code == 401  # the old session ended


async def test_an_offer_in_progress_holds_the_approval(client, db_session):
    staff = await _staff(db_session)
    user, candidate = await _verified(client, db_session)
    _, _, application = await _with_history(db_session, staff, candidate)
    application.status = "selected"
    await add(db_session, JobOffer(application_id=application.id, status="offer_pending"))
    await db_session.commit()
    await client.post(ERASE, headers=headers(user))
    queue = (await client.get(QUEUE, headers=headers(staff["hr"]))).json()["items"]
    mine = next(r for r in queue if r["candidate"] and r["candidate"]["id"] == str(candidate.id))
    assert mine["held"] is True and mine["open_applications"] == 1
    held = await client.post(f"{QUEUE}/{mine['id']}/decision", json={"decision": "approve"}, headers=headers(staff["super"]))
    assert held.status_code == 409 and held.json()["detail"] == privacy.HELD
    assert (await _fresh(db_session, Candidate, candidate.id)).anonymised_at is None
    assert (await _fresh(db_session, DataSubjectRequest, mine["id"])).status == "in_progress"


# --- K8: retention -------------------------------------------------------------------------------------------------------------------
async def test_retention_is_off_by_default_and_only_super_admin_sets_it(client, db_session, retention_off):
    staff = await _staff(db_session)
    shown = (await client.get(RETENTION, headers=headers(staff["hr"]))).json()
    assert shown["months"] is None and shown["can_edit"] is False and shown["due_now"] == 0
    assert (await client.put(RETENTION, json={"months": 24}, headers=headers(staff["hr"]))).status_code == 403
    for bad in (3, 121, "24", True):
        assert (await client.put(RETENTION, json={"months": bad}, headers=headers(staff["super"]))).status_code == 422
    saved = await client.put(RETENTION, json={"months": 24}, headers=headers(staff["super"]))
    assert saved.status_code == 200 and saved.json()["months"] == 24 and saved.json()["can_edit"] is True
    assert (await client.put(RETENTION, json={"months": None}, headers=headers(staff["super"]))).json()["months"] is None
    assert await privacy.sweep(db_session) == 0  # off: nothing happens


async def test_the_sweep_anonymises_only_inactive_unheld_external_candidates(client, db_session, retention_off):
    staff = await _staff(db_session)
    old = datetime.now(UTC) - timedelta(days=800)
    stale = await make_candidate(db_session, staff["rec"])
    recent = await make_candidate(db_session, staff["rec"])
    busy = await make_candidate(db_session, staff["rec"])
    student_user = await _user(db_session, "it_student", "it")
    student = await make_candidate(db_session, staff["rec"], user_id=student_user.id)
    _, _, application = await _with_history(db_session, staff, busy)
    application.status = "interview"  # an open application keeps the candidate
    await db_session.commit()
    for row in (stale, busy, student):
        await db_session.execute(Candidate.__table__.update().where(Candidate.id == row.id).values(updated_at=old))
    await db_session.execute(JobApplication.__table__.update().where(JobApplication.id == application.id).values(updated_at=old))
    setting = await db_session.get(CandidateRetentionSetting, 1) or await add(db_session, CandidateRetentionSetting(id=1))
    setting.months = 24
    await db_session.commit()

    assert (await client.get(RETENTION, headers=headers(staff["hr"]))).json()["due_now"] >= 1
    assert await privacy.sweep(db_session, batch=2) >= 1
    states = {c.id: (await _fresh(db_session, Candidate, c.id)).anonymised_reason for c in (stale, recent, busy, student)}
    assert states == {stale.id: "retention", recent.id: None, busy.id: None, student.id: None}
    run = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.retention_run").order_by(AuditLog.created_at.desc()).limit(1))
    assert run.metadata_json["months"] == 24 and run.user_id is None


def test_the_retention_job_runs_daily_at_two_ist():
    from app.worker import celery

    entry = celery.conf.beat_schedule["hrc035-candidate-retention"]
    assert entry["task"] == "app.worker.candidate_retention_task"
    assert (entry["schedule"].hour, entry["schedule"].minute) == ({20}, {30})  # UTC 20:30 = 02:00 IST


# --- K9: staff leaving ---------------------------------------------------------------------------------------------------------------
async def test_deactivating_a_placement_officer_releases_their_candidates_and_ends_the_session(client, db_session):
    staff = await _staff(db_session)
    officer = await _user(db_session, "placement_officer", "it")
    owned = await make_candidate(db_session, staff["rec"], placement_officer_user_id=officer.id)
    shared = await make_candidate(db_session, staff["rec"])
    await add(db_session, CandidateCollaborator(candidate_id=shared.id, user_id=officer.id, added_by_user_id=staff["rec"].id))
    await db_session.commit()
    before = officer.session_version
    response = await client.patch(f"{API}/admin/users/{officer.id}", json={"active": False}, headers=headers(staff["super"]))
    assert response.status_code == 200, response.text
    assert (await _fresh(db_session, Candidate, owned.id)).placement_officer_user_id is None
    assert await db_session.scalar(select(func.count()).select_from(CandidateCollaborator).where(CandidateCollaborator.user_id == officer.id)) == 0
    kinds = (await db_session.scalars(select(CandidateAssignmentHistory.kind).where(CandidateAssignmentHistory.from_user_id == officer.id))).all()
    assert sorted(kinds) == ["collaborator_removed", "placement_officer"]
    assert (await _fresh(db_session, User, officer.id)).session_version == before + 1

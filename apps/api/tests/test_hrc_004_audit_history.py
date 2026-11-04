"""hrc-004 (DEC-SCOPE-372) -- before/after audit for recruitment records: the itc-001 diff at the Job, JD, Candidate, Application and
Interview write sites (compensation, contact and feedback text recorded as "changed"), and the job/candidate History reads (B1-B8)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, Job
from app.services import audit_changes, recruitment_history
from tests.rec001_helpers import login, make_recruiter, make_user
from tests.test_rec_017_tracking import _candidate, _requirement, _tag, _team
from tests.test_rec_020_interviews import _at, _interview, _move, _setup, _to_past
from tests.test_rec_021_feedback import FULL, _completed, _save

REQ = "/api/v1/recruiter/requirements"
CANDIDATES = "/api/v1/recruiter/candidates"
INTERVIEWS = "/api/v1/recruiter/interviews"


async def _audits(db, entity_type: str, entity_id, action: str) -> list[dict]:
    rows = await db.scalars(select(AuditLog).where(AuditLog.entity_type == entity_type, AuditLog.entity_id == str(entity_id),
                                                   AuditLog.action == action).order_by(AuditLog.created_at))
    return [r.metadata_json for r in rows]


# --- the helper (B4) ----------------------------------------------------------------------------------------------------------
def test_redacted_fields_are_recorded_as_changed():
    diff = audit_changes.changes({"salary_min": 300000, "title": "A"}, {"salary_min": 450000, "title": "B"}, redact={"salary_min"})
    assert diff == {"salary_min": "changed", "title": ["A", "B"]}


def test_the_default_redaction_is_unchanged():
    assert audit_changes.changes({"salary_min": 1}, {"salary_min": 2}) == {"salary_min": [1, 2]}


def test_recruitment_redacts_compensation_contact_and_feedback_text():
    before = {f: "old" for f in ("salary", "salary_min", "salary_max", "current_salary", "expected_salary", "mobile", "email", "linkedin",
                                 "meeting_url", "contact_id", "strengths", "weaknesses", "recruiter_comments", "company_feedback")}
    after = {f: "new" for f in before}
    assert set(recruitment_history.diff(before, after).values()) == {"changed"}
    assert recruitment_history.diff({"location": "Pune"}, {"location": "Chennai"}) == {"location": ["Pune", "Chennai"]}


# --- Job and JD write sites -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_job_edit_records_old_and_new_values_and_salary_as_changed(client, db_session):
    """AC1 + AC2 at the write site; `fields` stays for hrc-003 (B3)."""
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    old_title = job.title
    saved = await client.patch(f"{REQ}/{job.id}", json={"title": "Senior Java Dev", "salary_min": 400000, "salary_max": 600000})
    assert saved.status_code == 200, saved.text
    [meta] = await _audits(db_session, "job", job.id, "recruiter_requirement.update")
    assert meta["fields"] == ["salary_max", "salary_min", "title"]
    assert meta["changes"] == {"title": [old_title, "Senior Java Dev"], "salary_min": "changed", "salary_max": "changed"}


@pytest.mark.asyncio
async def test_a_skills_only_edit_records_the_skill_lists(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    skill = f"Kotlin {_tag()}"
    assert (await client.patch(f"{REQ}/{job.id}", json={"required_skills": [skill]})).status_code == 200
    [meta] = await _audits(db_session, "job", job.id, "recruiter_requirement.update")
    assert meta["fields"] == ["skills"]
    assert meta["changes"] == {"required_skills": ["", skill]}


@pytest.mark.asyncio
async def test_a_status_move_records_from_and_to(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    assert (await client.post(f"{REQ}/{job.id}/status", json={"status": "sourcing"})).status_code == 200
    [meta] = await _audits(db_session, "job", job.id, "recruiter_requirement.status")
    assert meta["from"] == "requirement_received" and meta["changes"] == {"status": ["requirement_received", "sourcing"]}


@pytest.mark.asyncio
async def test_an_assignment_records_the_recruiters_by_name(client, db_session):
    manager, recruiter = await _team(client, db_session)
    other = await make_recruiter(db_session, manager)
    job = await _requirement(db_session, recruiter)
    await login(client, manager)
    assert (await client.post(f"{REQ}/{job.id}/assign", json={"recruiter_user_id": str(other.id)})).status_code == 200
    [meta] = await _audits(db_session, "job", job.id, "recruiter_requirement.assign")
    assert meta["to_user_id"] == str(other.id) and meta["changes"] == {"recruiter": [None, other.full_name]}  # _requirement leaves it unassigned


@pytest.mark.asyncio
async def test_a_bulk_reassignment_records_one_row_per_job(client, db_session):
    """E: rec-037's reassignment moves each job with its own audit row and values."""
    manager, recruiter = await _team(client, db_session)
    other = await make_recruiter(db_session, manager)
    company = Company(name=f"Bulk Co {_tag()}", assigned_recruiter_user_id=recruiter.id)
    db_session.add(company)
    await db_session.flush()
    jobs = []
    for _ in range(2):
        job = Job(company_id=company.id, title=f"Bulk {_tag()}", location="Pune", description="", skills=[], status="sourcing",
                  assigned_recruiter_user_id=recruiter.id)
        db_session.add(job)
        jobs.append(job)
    await db_session.commit()
    await login(client, manager)
    moved = await client.post("/api/v1/recruiter/manager/reassign", json={"from_user_id": str(recruiter.id), "to_user_id": str(other.id)})
    assert moved.status_code == 200, moved.text
    for job in jobs:
        [meta] = await _audits(db_session, "job", job.id, "recruiter_requirement.assign")
        assert meta["changes"] == {"recruiter": [recruiter.full_name, other.full_name]}


@pytest.mark.asyncio
async def test_a_new_jd_version_records_the_changed_fields(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    first = await client.post(f"{REQ}/{job.id}/jd", json={"role": "Backend developer", "salary": "6 LPA", "location": "Pune"})
    assert first.status_code == 201, first.text
    second = await client.post(f"{REQ}/{job.id}/jd", json={"role": "Backend engineer", "salary": "8 LPA", "location": "Pune",
                                                           "expected_version": first.json()["versions"][0]["version"]})
    assert second.status_code == 201, second.text
    first_meta, second_meta = await _audits(db_session, "job", job.id, "job_description.create")
    assert first_meta["changes"]["role"][1] == "Backend developer" and first_meta["changes"]["salary"] == "changed"
    assert second_meta["changes"] == {"role": ["Backend developer", "Backend engineer"], "salary": "changed"}


# --- Candidate, Application and Interview write sites ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_candidate_edit_records_values_with_contact_and_salary_redacted(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    digits = str(uuid.uuid4().int)[:9]  # the shared test database is never truncated
    candidate = await _candidate(db_session, recruiter, location="Pune", mobile=f"9{digits}", expected_salary=500000)
    body = {"location": "Chennai", "mobile": f"8{digits}", "expected_salary": 650000, "email": f"{_tag()}@example.org"}
    saved = await client.patch(f"{CANDIDATES}/{candidate.id}", json=body)
    assert saved.status_code == 200, saved.text
    [meta] = await _audits(db_session, "candidates", candidate.id, "candidate.update")
    assert meta["fields"] == ["email", "expected_salary", "location", "mobile"]
    assert meta["changes"] == {"location": ["Pune", "Chennai"], "mobile": "changed", "expected_salary": "changed", "email": "changed"}


@pytest.mark.asyncio
async def test_a_candidate_source_change_is_recorded_by_name(client, db_session):
    from app.models import RecCandidateSource
    _manager, recruiter = await _team(client, db_session)
    candidate = await _candidate(db_session, recruiter)
    other = await db_session.scalar(select(RecCandidateSource).where(RecCandidateSource.active.is_(True), RecCandidateSource.id != candidate.source_id))
    assert (await client.patch(f"{CANDIDATES}/{candidate.id}", json={"source_id": str(other.id)})).status_code == 200
    [meta] = await _audits(db_session, "candidates", candidate.id, "candidate.update")
    assert meta["changes"] == {"source": ["Referral", other.name]}


@pytest.mark.asyncio
async def test_an_application_status_move_records_from_and_to(client, db_session):
    s = await _setup(client, db_session)
    application_id = s["application"]["id"]
    moved = await client.post(f"/api/v1/recruiter/applications/{application_id}/status", json={"status": "screened"})
    assert moved.status_code == 200, moved.text
    [meta] = await _audits(db_session, "job_application", application_id, "recruiter_application.status")
    assert meta["changes"] == {"status": [s["application"]["status"], "screened"]}


@pytest.mark.asyncio
async def test_interview_edits_record_values_with_the_meeting_link_redacted(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"], meeting_url="https://meet.example.com/a")
    edited = await client.patch(f"{INTERVIEWS}/{item['id']}", json={"meeting_url": "https://meet.example.com/b", "interviewer": "Asha"})
    assert edited.status_code == 200, edited.text
    [meta] = await _audits(db_session, "interview", item["id"], "recruiter_interview.update")
    assert meta["changes"] == {"meeting_url": "changed", "interviewer": [None, "Asha"]}

    new_time = _at(days=3)
    assert (await client.post(f"{INTERVIEWS}/{item['id']}/reschedule", json={"scheduled_at": new_time, "notify": False})).status_code == 200
    [meta] = await _audits(db_session, "interview", item["id"], "recruiter_interview.reschedule")
    assert meta["changes"]["status"] == ["scheduled", "rescheduled"]
    old, new = meta["changes"]["scheduled_at"]
    assert old != new and new.startswith(new_time[:16])

    await _to_past(db_session, item["id"])
    assert (await _move(client, item["id"], "completed")).status_code == 200
    [meta] = await _audits(db_session, "interview", item["id"], "recruiter_interview.status")
    assert meta["changes"] == {"status": ["rescheduled", "completed"]}


@pytest.mark.asyncio
async def test_interview_feedback_text_is_recorded_as_changed_and_ratings_as_values(client, db_session):
    _s, item = await _completed(client, db_session)
    assert (await _save(client, item["id"])).status_code == 200
    [meta] = await _audits(db_session, "interview", item["id"], "recruiter_interview.feedback")
    changes = meta["changes"]
    assert [changes[f] for f in ("strengths", "weaknesses", "recruiter_comments", "company_feedback")] == ["changed"] * 4
    assert changes["overall_rating"] == [None, FULL["overall_rating"]] and changes["final_decision"] == [None, "selected"]


# --- the History reads (B1, B6) ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_ac2_a_requirements_history_shows_the_title_values_and_the_salary_as_changed(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    old_title = job.title
    assert (await client.patch(f"{REQ}/{job.id}", json={"title": "Senior Java Dev", "salary_max": 900000})).status_code == 200
    assert (await client.post(f"{REQ}/{job.id}/status", json={"status": "sourcing"})).status_code == 200
    db_session.add(AuditLog(user_id=recruiter.id, action="job_description.download", entity_type="job", entity_id=str(job.id), metadata_json={}))
    await db_session.commit()

    response = await client.get(f"{REQ}/{job.id}/history")
    assert response.status_code == 200, response.text
    assert "no-store" in response.headers["cache-control"]
    body = response.json()
    assert body["total"] == 2 and body["limit"] == 20 and body["offset"] == 0  # the download is a read, not a change
    status, edit = body["items"]  # newest first
    assert status["action"] == "recruiter_requirement.status" and status["changes"] == {"status": ["requirement_received", "sourcing"]}
    assert edit["changes"] == {"title": [old_title, "Senior Java Dev"], "salary_max": "changed"}  # AC1, AC2
    assert edit["fields"] == ["salary_max", "title"]
    assert edit["actor"] == {"id": str(recruiter.id), "full_name": recruiter.full_name}
    assert set(edit) == {"id", "action", "created_at", "actor", "changes", "fields"}  # raw metadata never leaves


@pytest.mark.asyncio
async def test_history_pages_and_validates_its_paging(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    for n in range(3):
        assert (await client.patch(f"{REQ}/{job.id}", json={"title": f"Title {n} {_tag()}"})).status_code == 200
    page = (await client.get(f"{REQ}/{job.id}/history", params={"limit": 2, "offset": 2})).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["limit"] == 2 and page["offset"] == 2
    assert (await client.get(f"{REQ}/{job.id}/history", params={"limit": 101})).status_code == 422


@pytest.mark.asyncio
async def test_a_requirements_history_follows_its_read_scope(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    await login(client, await make_recruiter(db_session))  # another team: the requirement does not exist for them
    assert (await client.get(f"{REQ}/{job.id}/history")).status_code == 404
    await login(client, await make_user(db_session, "telecaller", "it"))
    assert (await client.get(f"{REQ}/{job.id}/history")).status_code == 403


@pytest.mark.asyncio
async def test_a_candidates_history_shows_values_redacts_contact_and_follows_the_reader_roles(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    candidate = await _candidate(db_session, recruiter, location="Pune")
    assert (await client.patch(f"{CANDIDATES}/{candidate.id}", json={"location": "Chennai", "email": f"{_tag()}@example.org"})).status_code == 200
    db_session.add(AuditLog(user_id=recruiter.id, action="candidate.resume_download", entity_type="candidates", entity_id=str(candidate.id), metadata_json={}))
    await db_session.commit()

    await login(client, await make_user(db_session, "hr_team", "it"))  # a reader (rec-009)
    body = (await client.get(f"{CANDIDATES}/{candidate.id}/history")).json()
    [edit] = body["items"]
    assert edit["changes"] == {"location": ["Pune", "Chennai"], "email": "changed"}

    await login(client, await make_user(db_session, "telecaller", "it"))
    assert (await client.get(f"{CANDIDATES}/{candidate.id}/history")).status_code == 403
    await login(client, recruiter)
    assert (await client.get(f"{CANDIDATES}/{uuid.uuid4()}/history")).status_code == 404

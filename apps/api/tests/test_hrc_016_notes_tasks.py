"""hrc-016 (DEC-SCOPE-387, spec docs/superpowers/specs/2026-11-04-hrc-016-candidate-notes-tasks-timeline-design.md): private candidate
notes (T2, AC1), assignable candidate tasks (T3-T7), "My tasks" (T8, AC2), the timeline's new kinds (T9, AC3) and merge (T10)."""

import pathlib
import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, CandidateNote, CandidateTask, Company, JobApplication, Notification
from tests.rec038_helpers import _recruiter, _user, add, make_candidate, make_job, tag
from tests.tel026_helpers import headers

pytestmark = pytest.mark.asyncio
CANDIDATES = "/api/v1/recruiter/candidates"
TASKS = "/api/v1/recruiter/candidate-tasks"


def soon(hours: int = 2) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


async def _world(db):
    manager = await _user(db, "placement_manager", "global")
    rec, rec2 = await _recruiter(db, manager), await _recruiter(db, manager)
    hr = await _user(db, "hr_team", "it")
    candidate = await make_candidate(db, rec, owner_user_id=rec.id)
    company = await add(db, Company(name=f"H16 Co {tag()}", assigned_recruiter_user_id=rec.id, created_by_user_id=rec.id))
    job = await make_job(db, company, rec)
    application = await add(db, JobApplication(job_id=job.id, candidate_id=candidate.id, added_by_user_id=rec.id, status="sourced"))
    await db.commit()
    return {"mgr": manager, "rec": rec, "rec2": rec2, "hr": hr, "candidate": candidate, "job": job, "application": application, "company": company}


def _task(w, **extra) -> dict:
    return {"task_type": "resume_screening", "title": "Screen the resume", "due_at": soon(), "assignee_user_id": str(w["rec2"].id), **extra}


# --- notes (T2, AC1) -------------------------------------------------------------------------------------------------------------
async def test_writer_adds_a_note_and_readers_read_it(client, db_session):
    w = await _world(db_session)
    url = f"{CANDIDATES}/{w['candidate'].id}/notes"
    created = await client.post(url, json={"body": "  Prefers Pune, call after 6  "}, headers=headers(w["rec"]))
    assert created.status_code == 201, created.text
    assert created.json()["body"] == "Prefers Pune, call after 6" and created.json()["author"]["id"] == str(w["rec"].id)
    for reader in ("rec2", "mgr", "hr"):
        page = await client.get(url, headers=headers(w[reader]))
        assert page.status_code == 200 and page.json()["total"] == 1 and page.json()["items"][0]["body"] == "Prefers Pune, call after 6"
        assert "no-store" in page.headers["cache-control"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate_note.create", AuditLog.entity_id == created.json()["id"]))
    assert audit is not None and "Pune" not in str(audit.metadata_json)


@pytest.mark.parametrize("body", ["", "   ", "x" * 2001])
async def test_note_body_is_validated(client, db_session, body):
    w = await _world(db_session)
    response = await client.post(f"{CANDIDATES}/{w['candidate'].id}/notes", json={"body": body}, headers=headers(w["rec"]))
    assert response.status_code == 422


async def test_hr_team_cannot_add_notes_and_others_cannot_read(client, db_session):
    w = await _world(db_session)
    url = f"{CANDIDATES}/{w['candidate'].id}/notes"
    assert (await client.post(url, json={"body": "x"}, headers=headers(w["hr"]))).status_code == 403
    for role in ("employer", "it_student", "placement_officer", "hr_manager"):
        other = await _user(db_session, role, "it")
        await db_session.commit()
        assert (await client.get(url, headers=headers(other))).status_code == 403
    assert (await client.get(url)).status_code == 401


async def test_archived_candidate_takes_no_note(client, db_session):
    w = await _world(db_session)
    w["candidate"].archived_at = datetime.now(UTC)
    await db_session.commit()
    response = await client.post(f"{CANDIDATES}/{w['candidate'].id}/notes", json={"body": "x"}, headers=headers(w["rec"]))
    assert response.status_code == 409


async def test_note_never_leaves_through_another_candidate_response(client, db_session):
    """AC1: the note's text is in no candidate read but its own route and the timeline (the candidate-facing reads are checked below)."""
    w = await _world(db_session)
    marker = tag("SECRETNOTE")
    await client.post(f"{CANDIDATES}/{w['candidate'].id}/notes", json={"body": marker}, headers=headers(w["rec"]))
    for url in (f"{CANDIDATES}/{w['candidate'].id}", f"{CANDIDATES}?q={w['candidate'].candidate_code}", f"{CANDIDATES}/{w['candidate'].id}/history",
                f"{CANDIDATES}/{w['candidate'].id}/journey"):  # fmt: skip
        response = await client.get(url, headers=headers(w["rec"]))
        assert response.status_code == 200 and marker not in response.text, url
    search = await client.post(f"{CANDIDATES}/search", json={}, headers=headers(w["rec"]))
    assert marker not in search.text


async def test_only_internal_modules_read_the_notes_table():
    """AC1, structurally: the employer, student, public and portal modules never import the note model."""
    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    allowed = {"models.py", "candidate_notes_tasks.py", "recruiter_candidate_notes_tasks.py", "recruiter_timeline.py", "candidate_merge.py"}
    readers = {p.name for p in app_dir.rglob("*.py") if re.search(r"\bCandidateNote\b",p.read_text(encoding="utf-8"))}
    assert readers <= allowed, readers - allowed


# --- tasks (T3-T7) ---------------------------------------------------------------------------------------------------------------
async def test_task_is_created_listed_and_notified(client, db_session):
    w = await _world(db_session)
    created = await client.post(f"{CANDIDATES}/{w['candidate'].id}/tasks", json=_task(w, application_id=str(w["application"].id)), headers=headers(w["rec"]))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "open" and body["assignee"]["id"] == str(w["rec2"].id) and body["application_id"] == str(w["application"].id)
    assert body["requirement"]["id"] == str(w["job"].id)  # T3: the job comes from the application
    assert body["candidate"]["candidate_code"] == w["candidate"].candidate_code and body["can_change"] is True
    page = await client.get(f"{CANDIDATES}/{w['candidate'].id}/tasks", headers=headers(w["hr"]))
    assert page.status_code == 200 and [t["id"] for t in page.json()["items"]] == [body["id"]] and page.json()["items"][0]["can_change"] is False
    notice = await db_session.scalar(select(Notification).where(Notification.user_id == w["rec2"].id, Notification.event_type == "it.candidate.task_assigned"))
    assert notice is not None and w["candidate"].name not in (notice.title + notice.body)
    assert await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate_task.create", AuditLog.entity_id == body["id"])) is not None


async def test_self_assigned_task_sends_no_notice(client, db_session):
    w = await _world(db_session)
    response = await client.post(f"{CANDIDATES}/{w['candidate'].id}/tasks", json=_task(w, assignee_user_id=str(w["rec"].id)), headers=headers(w["rec"]))
    assert response.status_code == 201
    assert await db_session.scalar(select(Notification).where(Notification.user_id == w["rec"].id, Notification.event_type == "it.candidate.task_assigned")) is None


async def test_assignee_must_be_an_active_team_member(client, db_session):
    """T4 and the +/−/E line: a deactivated user, another role or an unknown id is one 422."""
    w = await _world(db_session)
    gone = await _recruiter(db_session, w["mgr"])
    gone.active = False
    officer = await _user(db_session, "placement_officer", "it")
    await db_session.commit()
    for assignee in (gone.id, officer.id, w["hr"].id, "00000000-0000-0000-0000-000000000000"):
        response = await client.post(f"{CANDIDATES}/{w['candidate'].id}/tasks", json=_task(w, assignee_user_id=str(assignee)), headers=headers(w["rec"]))
        assert response.status_code == 422 and response.json()["detail"] == "Choose an active recruiter or manager"
    manager_task = await client.post(f"{CANDIDATES}/{w['candidate'].id}/tasks", json=_task(w, assignee_user_id=str(w["mgr"].id)), headers=headers(w["rec"]))
    assert manager_task.status_code == 201


async def test_task_links_and_fields_are_validated(client, db_session):
    w = await _world(db_session)
    other = await make_candidate(db_session, w["rec"])
    foreign = await add(db_session, JobApplication(job_id=w["job"].id, candidate_id=other.id, added_by_user_id=w["rec"].id, status="sourced"))
    other_job = await make_job(db_session, w["company"], w["rec"])
    await db_session.commit()
    url = f"{CANDIDATES}/{w['candidate'].id}/tasks"
    cases = [
        _task(w, application_id=str(foreign.id)),  # another candidate's application
        _task(w, application_id=str(w["application"].id), job_id=str(other_job.id)),  # a job that is not the application's
        _task(w, job_id="00000000-0000-0000-0000-000000000000"),
        _task(w, task_type="lunch"),
        _task(w, title=""),
        _task(w, due_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat()),
    ]
    for payload in cases:
        assert (await client.post(url, json=payload, headers=headers(w["rec"]))).status_code == 422, payload
    with_job = await client.post(url, json=_task(w, job_id=str(other_job.id)), headers=headers(w["rec"]))
    assert with_job.status_code == 201 and with_job.json()["requirement"]["id"] == str(other_job.id) and with_job.json()["application_id"] is None


async def test_task_edit_reassign_complete_cancel(client, db_session):
    w = await _world(db_session)
    task = (await client.post(f"{CANDIDATES}/{w['candidate'].id}/tasks", json=_task(w), headers=headers(w["rec"]))).json()
    # T5: any candidate writer changes it; hr_team reads only
    assert (await client.patch(f"{TASKS}/{task['id']}", json={"title": "x"}, headers=headers(w["hr"]))).status_code == 403
    edited = await client.patch(f"{TASKS}/{task['id']}", json={"title": "Call the employer", "assignee_user_id": str(w["mgr"].id)}, headers=headers(w["rec2"]))
    assert edited.status_code == 200 and edited.json()["title"] == "Call the employer" and edited.json()["assignee"]["id"] == str(w["mgr"].id)
    assert await db_session.scalar(select(Notification).where(Notification.user_id == w["mgr"].id, Notification.event_type == "it.candidate.task_assigned"))
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate_task.update", AuditLog.entity_id == task["id"]))
    assert audit.metadata_json["fields"] == ["assignee_user_id", "title"]
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    assert (await client.patch(f"{TASKS}/{task['id']}", json={"due_at": past}, headers=headers(w["rec"]))).status_code == 422
    done = await client.post(f"{TASKS}/{task['id']}/complete", headers=headers(w["mgr"]))
    assert done.status_code == 200 and done.json()["status"] == "done" and done.json()["completed_by"]["id"] == str(w["mgr"].id) and done.json()["can_change"] is False
    for again in (client.post(f"{TASKS}/{task['id']}/complete", headers=headers(w["mgr"])), client.post(f"{TASKS}/{task['id']}/cancel", headers=headers(w["mgr"])),
                  client.patch(f"{TASKS}/{task['id']}", json={"title": "y"}, headers=headers(w["mgr"]))):  # fmt: skip
        assert (await again).status_code == 409
    second = (await client.post(f"{CANDIDATES}/{w['candidate'].id}/tasks", json=_task(w), headers=headers(w["rec"]))).json()
    cancelled = await client.post(f"{TASKS}/{second['id']}/cancel", headers=headers(w["rec"]))
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled" and cancelled.json()["cancelled_at"]
    assert (await client.patch(f"{TASKS}/00000000-0000-0000-0000-000000000000", json={"title": "y"}, headers=headers(w["rec"]))).status_code == 404


async def test_deactivated_assignee_shows_inactive_and_can_be_replaced(client, db_session):
    w = await _world(db_session)
    task = (await client.post(f"{CANDIDATES}/{w['candidate'].id}/tasks", json=_task(w), headers=headers(w["rec"]))).json()
    w["rec2"].active = False
    await db_session.commit()
    row = (await client.get(f"{CANDIDATES}/{w['candidate'].id}/tasks", headers=headers(w["rec"]))).json()["items"][0]
    assert row["assignee"]["active"] is False
    moved = await client.patch(f"{TASKS}/{task['id']}", json={"assignee_user_id": str(w["rec"].id)}, headers=headers(w["rec"]))
    assert moved.status_code == 200 and moved.json()["assignee"]["id"] == str(w["rec"].id)


# --- My tasks (T8, AC2) ----------------------------------------------------------------------------------------------------------
async def test_my_tasks_lists_only_the_assignees_open_tasks(client, db_session):
    w = await _world(db_session)
    url = f"{CANDIDATES}/{w['candidate'].id}/tasks"
    today = (await client.post(url, json=_task(w, due_at=(datetime.now(UTC) + timedelta(minutes=1)).isoformat()), headers=headers(w["rec"]))).json()
    later = (await client.post(url, json=_task(w, due_at=soon(24 * 5)), headers=headers(w["rec"]))).json()
    await client.post(url, json=_task(w, assignee_user_id=str(w["rec"].id)), headers=headers(w["rec"]))  # someone else's
    overdue = await add(db_session, CandidateTask(candidate_id=w["candidate"].id, task_type="follow_up", title="Late", due_at=datetime.now(UTC) - timedelta(hours=3),
                                                  assignee_user_id=w["rec2"].id, created_by_user_id=w["rec"].id))  # fmt: skip
    await db_session.commit()
    upcoming = (await client.get(f"{TASKS}?due=upcoming", headers=headers(w["rec2"]))).json()
    ids = {t["id"] for t in upcoming["items"]}
    assert later["id"] in ids and today["id"] not in ids
    listed = (await client.get(f"{TASKS}?due=overdue", headers=headers(w["rec2"]))).json()
    assert str(overdue.id) in {t["id"] for t in listed["items"]} and all(t["overdue"] for t in listed["items"])
    assert listed["counts"]["upcoming"] >= 1 and listed["counts"]["overdue"] >= 1 and "day" in listed
    await client.post(f"{TASKS}/{later['id']}/complete", headers=headers(w["rec2"]))
    assert later["id"] not in {t["id"] for t in (await client.get(f"{TASKS}?due=upcoming", headers=headers(w["rec2"]))).json()["items"]}
    refused = await client.get(TASKS, headers=headers(w["hr"]))
    assert refused.status_code == 403 and refused.json()["detail"] == "Your role has no candidate tasks"  # QA-01


async def test_assignee_lookup(client, db_session):
    w = await _world(db_session)
    found = await client.get(f"{TASKS}/assignees", params={"q": w["rec2"].full_name}, headers=headers(w["rec"]))
    assert found.status_code == 200 and [p["id"] for p in found.json()] == [str(w["rec2"].id)]
    assert (await client.get(f"{TASKS}/assignees", headers=headers(w["hr"]))).status_code == 403


# --- timeline (T9, AC3) and merge (T10) ------------------------------------------------------------------------------------------
async def test_timeline_shows_every_new_activity_kind(client, db_session):
    w = await _world(db_session)
    cid = w["candidate"].id
    await client.post(f"{CANDIDATES}/{cid}/notes", json={"body": "Spoke to the candidate"}, headers=headers(w["rec"]))
    task = (await client.post(f"{CANDIDATES}/{cid}/tasks", json=_task(w), headers=headers(w["rec"]))).json()
    await client.post(f"{TASKS}/{task['id']}/complete", headers=headers(w["rec2"]))
    assert (await client.patch(f"{CANDIDATES}/{cid}", json={"location": "Chennai"}, headers=headers(w["rec"]))).status_code == 200
    assert (await client.put(f"{CANDIDATES}/{cid}/ownership", json={"owner_user_id": str(w["rec2"].id)}, headers=headers(w["rec"]))).status_code == 200
    screened = await client.put(f"/api/v1/recruiter/applications/{w['application'].id}/screening", json={"result": "hold"}, headers=headers(w["rec"]))
    assert screened.status_code == 200, screened.text
    page = (await client.get(f"{CANDIDATES}/{cid}/timeline?limit=100", headers=headers(w["hr"]))).json()
    by_kind = {}
    for row in page["items"]:
        by_kind.setdefault(row["kind"], []).append(row)
    assert {"note", "task", "assignment", "profile", "screening"} <= set(by_kind)
    assert by_kind["note"][0]["reason"] == "Spoke to the candidate"
    assert {r["event"] for r in by_kind["task"]} == {"scheduled", "done"}
    scheduled = next(r for r in by_kind["task"] if r["event"] == "scheduled")
    assert scheduled["from_value"] == "resume_screening" and scheduled["subject"] == "Screen the resume" and scheduled["to_label"] == w["rec2"].full_name
    owner = next(r for r in by_kind["assignment"] if r["event"] == "owner")
    assert owner["from_label"] == w["rec"].full_name and owner["to_label"] == w["rec2"].full_name
    assert {r["event"] for r in by_kind["profile"]} >= {"update"} and next(r for r in by_kind["profile"] if r["event"] == "update")["to_value"] == "1"
    screening = by_kind["screening"][0]
    assert screening["to_value"] == "hold" and screening["to_label"] == "Hold" and screening["context"] == w["company"].name


async def test_merge_moves_notes_and_tasks(client, db_session):
    w = await _world(db_session)
    victim = await make_candidate(db_session, w["rec"])
    await db_session.commit()
    body = tag("victim note ")
    await client.post(f"{CANDIDATES}/{victim.id}/notes", json={"body": body}, headers=headers(w["rec"]))
    await client.post(f"{CANDIDATES}/{victim.id}/tasks", json=_task(w), headers=headers(w["rec"]))
    merged = await client.post(f"{CANDIDATES}/{w['candidate'].id}/merge", json={"victim_code": victim.candidate_code}, headers=headers(w["mgr"]))
    assert merged.status_code == 200, merged.text
    assert merged.json()["moved"]["notes"] == 1 and merged.json()["moved"]["tasks"] == 1
    assert await db_session.scalar(select(CandidateNote.candidate_id).where(CandidateNote.body == body)) == w["candidate"].id

"""pob-019 (DEC-SCOPE-439, spec docs/superpowers/specs/2026-11-08-pob-019-candidate-tags-bulk-actions-design.md): free candidate tags from an
admin list (T1/T2), the tag filter (T4), the enriched result cards within a fixed query budget (T5/T6, AC1), bulk shortlist (T7/T8, AC2) and
bulk tasks (T9). Every test makes its own skills, tags and candidates; the shared database is never truncated."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select

from app.core.database import engine
from app.models import (
    REC_CATALOGUE_MODELS,
    AuditLog,
    CandidateTagLink,
    CandidateTask,
    Company,
    JobApplication,
    Notification,
    ProfileShare,
    ProfileShareItem,
    RecCandidateSource,
    RecCandidateTag,
    RecruiterCall,
    SkillCategory,
)
from tests.rec038_helpers import _recruiter, _user, add, make_candidate, make_job, tag
from tests.tel026_helpers import headers
from tests.test_rec_013_find_candidates import World

pytestmark = pytest.mark.asyncio
CANDIDATES = "/api/v1/recruiter/candidates"
SEARCH = f"{CANDIDATES}/search"
TASKS = "/api/v1/recruiter/candidate-tasks/bulk"


async def _world(db):
    manager = await _user(db, "placement_manager", "global")
    rec, rec2 = await _recruiter(db, manager), await _recruiter(db, manager)
    hr = await _user(db, "hr_team", "it")
    company = await add(db, Company(name=f"P19 Co {tag()}", assigned_recruiter_user_id=rec.id, created_by_user_id=rec.id))
    job = await make_job(db, company, rec)
    hot, old = await add(db, RecCandidateTag(name=f"Hot {tag()}")), await add(db, RecCandidateTag(name=f"Old {tag()}", active=False))
    await db.commit()
    return {"mgr": manager, "rec": rec, "rec2": rec2, "hr": hr, "company": company, "job": job, "hot": hot, "old": old}


async def _skills(db, w) -> World:
    category = await db.scalar(select(SkillCategory.id).where(SkillCategory.name == "Programming"))
    source = await db.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "Referral"))
    return World(db, w["rec"], category, source)


def _tags_url(candidate) -> str:
    return f"{CANDIDATES}/{candidate.id}/tags"


# --- T1: the managed list ----------------------------------------------------------------------------------------------------------
async def test_candidate_tags_are_a_recruiter_managed_list(client, db_session):
    w = await _world(db_session)
    assert REC_CATALOGUE_MODELS["candidate-tags"] is RecCandidateTag
    url = "/api/v1/recruiter/catalogue/candidate-tags"
    created = await client.post(url, json={"name": f"Referred {tag()}"}, headers=headers(w["mgr"]))
    assert created.status_code == 201, created.text
    assert (await client.post(url, json={"name": f"X {tag()}"}, headers=headers(w["rec"]))).status_code == 403
    names = {row["name"] for row in (await client.get(f"{url}?limit=100", headers=headers(w["rec"]))).json()["items"]}
    assert w["old"].name not in names  # a recruiter reads active tags only


# --- T2: a candidate's tags ----------------------------------------------------------------------------------------------------------
async def test_writer_replaces_the_set_and_readers_read_it(client, db_session):
    w = await _world(db_session)
    candidate = await make_candidate(db_session, w["rec"])
    await db_session.commit()
    saved = await client.put(_tags_url(candidate), json={"tag_ids": [str(w["hot"].id), str(w["hot"].id)]}, headers=headers(w["rec"]))
    assert saved.status_code == 200, saved.text
    assert [t["id"] for t in saved.json()["items"]] == [str(w["hot"].id)] and saved.json()["can_edit"] is True
    read = await client.get(_tags_url(candidate), headers=headers(w["hr"]))
    assert read.status_code == 200 and [t["name"] for t in read.json()["items"]] == [w["hot"].name] and read.json()["can_edit"] is False
    assert (await client.put(_tags_url(candidate), json={"tag_ids": []}, headers=headers(w["hr"]))).status_code == 403
    cleared = await client.put(_tags_url(candidate), json={"tag_ids": []}, headers=headers(w["rec2"]))
    assert cleared.status_code == 200 and cleared.json()["items"] == []
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "candidate.tags", AuditLog.entity_id == str(candidate.id)))).all()
    assert [a.metadata_json for a in audits] == [{"added": [str(w["hot"].id)], "removed": []}, {"added": [], "removed": [str(w["hot"].id)]}]


async def test_an_inactive_tag_may_stay_but_not_be_added(client, db_session):
    w = await _world(db_session)
    candidate = await make_candidate(db_session, w["rec"])
    await add(db_session, CandidateTagLink(candidate_id=candidate.id, tag_id=w["old"].id, added_by_user_id=w["rec"].id))
    other = await make_candidate(db_session, w["rec"])
    await db_session.commit()
    kept = await client.put(_tags_url(candidate), json={"tag_ids": [str(w["old"].id), str(w["hot"].id)]}, headers=headers(w["rec"]))
    assert kept.status_code == 200, kept.text
    assert {t["id"]: t["active"] for t in kept.json()["items"]} == {str(w["old"].id): False, str(w["hot"].id): True}
    refused = await client.put(_tags_url(other), json={"tag_ids": [str(w["old"].id)]}, headers=headers(w["rec"]))
    assert refused.status_code == 422 and "active" in refused.text
    unknown = await client.put(_tags_url(other), json={"tag_ids": [str(uuid.uuid4())]}, headers=headers(w["rec"]))
    assert unknown.status_code == 422


async def test_tags_are_capped_and_an_archived_candidate_is_refused(client, db_session):
    w = await _world(db_session)
    candidate = await make_candidate(db_session, w["rec"], archived_at=datetime.now(UTC))
    await db_session.commit()
    many = {"tag_ids": [str(uuid.uuid4()) for _ in range(21)]}
    assert (await client.put(_tags_url(candidate), json=many, headers=headers(w["rec"]))).status_code == 422
    assert (await client.put(_tags_url(candidate), json={"tag_ids": [str(w["hot"].id)]}, headers=headers(w["rec"]))).status_code == 409
    assert (await client.get(f"{CANDIDATES}/{uuid.uuid4()}/tags", headers=headers(w["rec"]))).status_code == 404


# --- T4/T5/T6: the filter and the cards --------------------------------------------------------------------------------------------
async def test_tag_filter_alone_or_with_a_skill(client, db_session):
    w = await _world(db_session)
    world = await _skills(db_session, w)
    java = await world.skill("Java")
    tagged = await make_candidate(db_session, w["rec"])
    plain = await make_candidate(db_session, w["rec"])
    await add(db_session, CandidateTagLink(candidate_id=tagged.id, tag_id=w["hot"].id, added_by_user_id=w["rec"].id))
    await db_session.commit()
    assert plain.id != tagged.id
    alone = await client.post(SEARCH, json={"tag_ids": [str(w["hot"].id)]}, headers=headers(w["rec"]))
    assert alone.status_code == 200, alone.text
    assert {i["id"] for i in alone.json()["items"]} == {str(tagged.id)}
    with_skill = await client.post(SEARCH, json={"all": [java.name], "tag_ids": [str(w["hot"].id)]}, headers=headers(w["rec"]))
    assert with_skill.status_code == 200 and with_skill.json()["total"] == 0  # nobody holds the skill
    assert (await client.post(SEARCH, json={"tag_ids": [str(uuid.uuid4()) for _ in range(11)]}, headers=headers(w["rec"]))).status_code == 422


async def test_cards_carry_the_five_facts_and_the_tags(client, db_session):
    w = await _world(db_session)
    world = await _skills(db_session, w)
    java = await world.skill("Java")
    rich = await world.candidate(java, experience_months=30, owner_user_id=w["rec2"].id, location="Pune")
    bare = await world.candidate(java, experience_months=0)
    await add(db_session, CandidateTagLink(candidate_id=rich.id, tag_id=w["hot"].id, added_by_user_id=w["rec"].id))
    called = datetime.now(UTC) - timedelta(days=2)
    await add(db_session, RecruiterCall(candidate_id=rich.id, caller_user_id=w["rec"].id, occurred_at=called, direction="outgoing", outcome="connected"))
    other = await make_job(db_session, w["company"], w["rec"])
    active = await add(db_session, JobApplication(job_id=w["job"].id, candidate_id=rich.id, added_by_user_id=w["rec"].id, status="interview"))
    await add(db_session, JobApplication(job_id=other.id, candidate_id=rich.id, added_by_user_id=w["rec"].id, status="rejected"))
    share = await add(db_session, ProfileShare(job_id=w["job"].id, company_id=w["company"].id, channel="portal", shared_by_user_id=w["rec"].id))
    await add(db_session, ProfileShareItem(share_id=share.id, candidate_id=rich.id, application_id=active.id))
    await db_session.commit()
    response = await client.post(SEARCH, json={"all": [java.name]}, headers=headers(w["rec"]))
    assert response.status_code == 200, response.text
    cards = {c["id"]: c for c in response.json()["items"]}
    r, b = cards[str(rich.id)], cards[str(bare.id)]
    assert r["owner"] == {"id": str(w["rec2"].id), "full_name": w["rec2"].full_name}
    assert datetime.fromisoformat(r["last_contacted_at"]) == called.replace(microsecond=called.microsecond)
    assert r["active_applications"] == 1 and r["prior_submissions"] == 1
    assert r["tags"] == [{"id": str(w["hot"].id), "name": w["hot"].name, "active": True}]
    assert {"kind": "experience", "label": "1–3 years"} in r["system_tags"]
    assert {"kind": "skill_category", "label": "Programming"} in r["system_tags"]  # the category of a skill the candidate holds
    assert b["owner"] is None and b["last_contacted_at"] is None and b["active_applications"] == 0 and b["prior_submissions"] == 0
    assert b["tags"] == [] and b["system_tags"] == [{"kind": "experience", "label": "Fresher"}, {"kind": "skill_category", "label": "Programming"}]
    assert r["engagement"] is not None  # hrc-021 stays


async def test_enrichment_keeps_the_query_count_fixed(client, db_session):
    w = await _world(db_session)
    world = await _skills(db_session, w)
    small, big = await world.skill("Small"), await world.skill("Big")
    await world.candidate(small, big)
    for _ in range(6):
        c = await world.candidate(big, owner_user_id=w["rec"].id)
        await add(db_session, CandidateTagLink(candidate_id=c.id, tag_id=w["hot"].id, added_by_user_id=w["rec"].id))
    await db_session.commit()
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        assert (await client.post(SEARCH, json={"all": [small.name]}, headers=headers(w["rec"]))).json()["total"] == 1
        one = len([s for s in statements if s.lstrip().upper().startswith("SELECT")])
        statements.clear()
        assert (await client.post(SEARCH, json={"all": [big.name]}, headers=headers(w["rec"]))).json()["total"] == 7
        assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == one
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)


# --- T7/T8: bulk shortlist (AC2) ---------------------------------------------------------------------------------------------------
def _bulk_url(job) -> str:
    return f"/api/v1/recruiter/requirements/{job.id}/candidates/bulk"


async def test_bulk_shortlist_of_twenty_in_one_transaction(client, db_session):
    w = await _world(db_session)
    people = [await make_candidate(db_session, w["rec"]) for _ in range(20)]
    await db_session.commit()
    ids = [str(c.id) for c in people]
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        response = await client.post(_bulk_url(w["job"]), json={"candidate_ids": ids, "note": "Strong Java"}, headers=headers(w["rec"]))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert response.status_code == 200, response.text
    body = response.json()
    assert {a["candidate_id"] for a in body["added"]} == set(ids) and body["skipped"] == []
    assert len([s for s in statements if s.strip().upper() == "COMMIT"]) <= 1
    rows = (await db_session.scalars(select(JobApplication).where(JobApplication.job_id == w["job"].id))).all()
    assert len(rows) == 20 and {r.status for r in rows} == {"shortlisted"}


async def test_bulk_shortlist_skips_with_reasons(client, db_session):
    w = await _world(db_session)
    fresh = await make_candidate(db_session, w["rec"])
    there = await make_candidate(db_session, w["rec"])
    dnc = await make_candidate(db_session, w["rec"], status="do_not_contact")
    archived = await make_candidate(db_session, w["rec"], archived_at=datetime.now(UTC))
    await add(db_session, JobApplication(job_id=w["job"].id, candidate_id=there.id, added_by_user_id=w["rec"].id, status="sourced"))
    await db_session.commit()
    missing = uuid.uuid4()
    ids = [str(x) for x in (fresh.id, there.id, dnc.id, archived.id, missing)]
    response = await client.post(_bulk_url(w["job"]), json={"candidate_ids": ids}, headers=headers(w["rec"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert [a["candidate_id"] for a in body["added"]] == [str(fresh.id)]
    assert {s["candidate_id"]: s["reason"] for s in body["skipped"]} == {
        str(there.id): "already_added", str(dnc.id): "do_not_contact", str(archived.id): "unavailable", str(missing): "unavailable",
    }
    assert all(s["message"] for s in body["skipped"])
    audit = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "recruiter_application.add",
                                                                                     AuditLog.metadata_json["job_id"].as_string() == str(w["job"].id)))
    assert audit == 1


async def test_bulk_shortlist_is_refused_for_readers_closed_requirements_and_bad_bodies(client, db_session):
    w = await _world(db_session)
    c = await make_candidate(db_session, w["rec"])
    await db_session.commit()
    body = {"candidate_ids": [str(c.id)]}
    assert (await client.post(_bulk_url(w["job"]), json=body, headers=headers(w["hr"]))).status_code in (403, 404)
    assert (await client.post(_bulk_url(w["job"]), json={"candidate_ids": []}, headers=headers(w["rec"]))).status_code == 422
    too_many = {"candidate_ids": [str(uuid.uuid4()) for _ in range(51)]}
    assert (await client.post(_bulk_url(w["job"]), json=too_many, headers=headers(w["rec"]))).status_code == 422
    w["job"].status = "closed"
    await db_session.commit()
    assert (await client.post(_bulk_url(w["job"]), json=body, headers=headers(w["rec"]))).status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(JobApplication).where(JobApplication.job_id == w["job"].id)) == 0


# --- T9: bulk tasks ----------------------------------------------------------------------------------------------------------------
def _task(w, ids, **extra) -> dict:
    due = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    return {"task_type": "follow_up", "title": "Call about the Java role", "due_at": due, "assignee_user_id": str(w["rec2"].id),
            "candidate_ids": [str(i) for i in ids], **extra}  # fmt: skip


async def test_bulk_task_creates_one_each_and_notifies_once(client, db_session):
    w = await _world(db_session)
    people = [await make_candidate(db_session, w["rec"]) for _ in range(3)]
    archived = await make_candidate(db_session, w["rec"], archived_at=datetime.now(UTC))
    await db_session.commit()
    response = await client.post(TASKS, json=_task(w, [*(p.id for p in people), archived.id], job_id=str(w["job"].id)), headers=headers(w["rec"]))
    assert response.status_code == 201, response.text
    body = response.json()
    assert {c["candidate_id"] for c in body["created"]} == {str(p.id) for p in people}
    assert body["skipped"] == [{"candidate_id": str(archived.id), "reason": "unavailable", "message": body["skipped"][0]["message"]}]
    tasks = (await db_session.scalars(select(CandidateTask).where(CandidateTask.candidate_id.in_([p.id for p in people])))).all()
    assert len(tasks) == 3 and {t.job_id for t in tasks} == {w["job"].id} and {t.assignee_user_id for t in tasks} == {w["rec2"].id}
    notices = await db_session.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == w["rec2"].id, Notification.event_type == "it.candidate.task_assigned"))
    assert notices == 1


async def test_bulk_task_validates_and_refuses_readers(client, db_session):
    w = await _world(db_session)
    c = await make_candidate(db_session, w["rec"])
    await db_session.commit()
    assert (await client.post(TASKS, json=_task(w, [c.id]), headers=headers(w["hr"]))).status_code == 403
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert (await client.post(TASKS, json=_task(w, [c.id], due_at=past), headers=headers(w["rec"]))).status_code == 422
    assert (await client.post(TASKS, json=_task(w, [c.id], assignee_user_id=str(w["hr"].id)), headers=headers(w["rec"]))).status_code == 422
    assert (await client.post(TASKS, json=_task(w, [c.id], application_id=str(uuid.uuid4())), headers=headers(w["rec"]))).status_code == 422
    mine = await client.post(TASKS, json=_task(w, [c.id], assignee_user_id=str(w["rec"].id)), headers=headers(w["rec"]))
    assert mine.status_code == 201
    assert await db_session.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == w["rec"].id, Notification.event_type == "it.candidate.task_assigned")) == 0

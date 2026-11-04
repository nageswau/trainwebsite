"""hrc-014 (DEC-SCOPE-377, spec docs/superpowers/specs/2026-11-04-hrc-014-candidate-duplicate-merge-design.md): probable duplicates go to
a review queue (D1/D2), the `candidates.merge` grant guards it (D3), and a merge moves every child record to the survivor (AC1), resolves
the (candidate, job) pair (AC2, D6), refuses student logins (D5), archives the victim with `merged_into_id` (D8) and is audited (AC3)."""

import random
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models import (
    AuditLog,
    Candidate,
    CandidateConsent,
    CandidateDocument,
    CandidateDocumentRequest,
    CandidateDuplicate,
    CandidateResume,
    CandidateSkill,
    Company,
    JobApplication,
    ProfileShare,
    ProfileShareItem,
    RecruiterCall,
    RecruiterMessage,
    Skill,
    SkillCategory,
    UserPermissionOverride,
)
from app.services.applications import candidate_for_student
from tests.rec038_helpers import _recruiter, _user, add, make_candidate, make_job, tag
from tests.tel026_helpers import headers

pytestmark = pytest.mark.asyncio
CANDIDATES = "/api/v1/recruiter/candidates"
QUEUE = "/api/v1/recruiter/candidate-duplicates"


def _mobile() -> str:
    return "9" + "".join(random.choices("0123456789", k=9))


async def _team(db):
    manager = await _user(db, "placement_manager", "global")
    recruiter = await _recruiter(db, manager)
    await db.commit()
    return manager, recruiter


async def _source(db) -> str:
    from app.models import RecCandidateSource

    return str(await db.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "Referral")))


async def _create(client, db, user, **fields) -> dict:
    body = {"name": f"Asha {tag()}", "email": f"{tag('h14-')}@example.com", "source_id": await _source(db), **fields}
    response = await client.post(CANDIDATES, json=body, headers=headers(user))
    assert response.status_code == 201, response.text
    return response.json()


async def _raw(db, creator, **fields) -> Candidate:
    """A candidate inserted directly (no detection runs), as before hrc-014."""
    from app.services.candidates import next_code

    return await add(db, Candidate(candidate_code=await next_code(db), source_id=UUID(await _source(db)), created_by_user_id=creator.id,
                                   email=f"{tag('h14-')}@example.com", preferred_locations=[], **fields))  # fmt: skip


async def _pairs(client, user, status="open") -> list[dict]:
    response = await client.get(QUEUE, params={"status": status, "limit": 100}, headers=headers(user))
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _pair_of(items, a, b):
    ids = {a, b}
    return next((p for p in items if {p["candidate"]["id"], p["other"]["id"]} == ids), None)


async def _probable(client, db, user):
    """Two candidates with the same name, location and college (D1), created through the API."""
    name, college = f"Meera {tag()}", f"College {tag()}"
    a = await _create(client, db, user, name=name, location="Pune", college=college)
    b = await _create(client, db, user, name=f"  {name.upper()} ", location="pune", college=college.lower())
    return a, b


# --- D1/D2: detection --------------------------------------------------------------------------------------------------------------
async def test_same_name_location_and_college_is_queued_on_create(client, db_session):
    manager, recruiter = await _team(db_session)
    a, b = await _probable(client, db_session, recruiter)
    pair = _pair_of(await _pairs(client, manager), a["id"], b["id"])
    assert pair is not None and pair["signals"] == ["name_location_college"] and pair["status"] == "open"
    assert pair["candidate"]["id"] == a["id"]  # browser QA-01: the older record is listed first (the merge screen keeps it by default)
    assert set(pair["candidate"]) == {"id", "candidate_code", "name", "location", "college", "status", "archived"}  # no contact data


async def test_a_phone_variant_is_queued(client, db_session):
    manager, recruiter = await _team(db_session)
    number = _mobile()
    a = await _create(client, db_session, recruiter, mobile=number)
    b = await _create(client, db_session, recruiter, mobile=f"+44 {number}")  # another country code: not the exact-match block
    pair = _pair_of(await _pairs(client, manager), a["id"], b["id"])
    assert pair is not None and pair["signals"] == ["phone_variant"]


async def test_different_people_are_not_paired(client, db_session):
    manager, recruiter = await _team(db_session)
    name = f"Ravi {tag()}"
    a = await _create(client, db_session, recruiter, name=name, location="Pune", college=f"A {tag()}")
    b = await _create(client, db_session, recruiter, name=name, location="Pune", college=f"B {tag()}")
    assert _pair_of(await _pairs(client, manager), a["id"], b["id"]) is None


async def test_an_edit_that_makes_a_match_queues_the_pair(client, db_session):
    manager, recruiter = await _team(db_session)
    name, college = f"Kiran {tag()}", f"College {tag()}"
    a = await _create(client, db_session, recruiter, name=name, location="Pune", college=college)
    b = await _create(client, db_session, recruiter, name=name, location="Chennai", college=college)
    assert _pair_of(await _pairs(client, manager), a["id"], b["id"]) is None
    assert (await client.patch(f"{CANDIDATES}/{b['id']}", json={"location": "Pune"}, headers=headers(recruiter))).status_code == 200
    assert _pair_of(await _pairs(client, manager), a["id"], b["id"]) is not None


async def test_dismiss_closes_the_pair_and_it_never_comes_back(client, db_session):
    manager, recruiter = await _team(db_session)
    a, b = await _probable(client, db_session, recruiter)
    pair = _pair_of(await _pairs(client, manager), a["id"], b["id"])
    response = await client.post(f"{QUEUE}/{pair['id']}/dismiss", json={"note": "Different fathers' names"}, headers=headers(manager))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "dismissed" and response.json()["decided_by"]["id"] == str(manager.id)
    again = await client.post(f"{QUEUE}/{pair['id']}/dismiss", json={}, headers=headers(manager))
    assert again.status_code == 409
    assert (await client.patch(f"{CANDIDATES}/{b['id']}", json={"location": "PUNE"}, headers=headers(recruiter))).status_code == 200
    assert (await client.post(f"{QUEUE}/scan", headers=headers(manager))).status_code == 200
    assert _pair_of(await _pairs(client, manager), a["id"], b["id"]) is None
    assert _pair_of(await _pairs(client, manager, "dismissed"), a["id"], b["id"]) is not None
    [meta] = [r.metadata_json for r in await db_session.scalars(select(AuditLog).where(AuditLog.action == "candidate.duplicate_dismiss",
                                                                                         AuditLog.entity_id == pair["id"]))]
    assert meta["candidate_ids"] == sorted([a["id"], b["id"]]) and "note" not in meta  # the note text stays off the audit row


async def test_the_scan_finds_pairs_that_existed_before(client, db_session):
    manager, recruiter = await _team(db_session)
    name, college = f"Old {tag()}", f"College {tag()}"
    a = await _raw(db_session, recruiter, name=name, location="Pune", college=college)
    b = await _raw(db_session, recruiter, name=name, location="Pune", college=college)
    await db_session.commit()
    assert _pair_of(await _pairs(client, manager), str(a.id), str(b.id)) is None
    response = await client.post(f"{QUEUE}/scan", headers=headers(manager))
    assert response.status_code == 200 and response.json()["created"] >= 1
    assert _pair_of(await _pairs(client, manager), str(a.id), str(b.id)) is not None


async def test_archived_candidates_never_pair_and_an_archived_side_leaves_the_open_queue(client, db_session):
    manager, recruiter = await _team(db_session)
    a, b = await _probable(client, db_session, recruiter)
    assert (await client.post(f"{CANDIDATES}/{b['id']}/archive", headers=headers(recruiter))).status_code == 200
    assert _pair_of(await _pairs(client, manager), a["id"], b["id"]) is None
    name, college = f"Arch {tag()}", f"College {tag()}"
    c = await _raw(db_session, recruiter, name=name, location="Pune", college=college)
    d = await _raw(db_session, recruiter, name=name, location="Pune", college=college, archived_at=datetime.now(UTC))
    await db_session.commit()
    await client.post(f"{QUEUE}/scan", headers=headers(manager))
    assert await db_session.scalar(select(CandidateDuplicate).where(CandidateDuplicate.candidate_id.in_([c.id, d.id]))) is None


# --- D3: the grant ------------------------------------------------------------------------------------------------------------------
async def test_the_queue_and_merge_need_the_grant_and_a_writer_role(client, db_session):
    manager, recruiter = await _team(db_session)
    hr = await _user(db_session, "hr_team", "it")
    await db_session.commit()
    a, b = await _probable(client, db_session, recruiter)
    pair = _pair_of(await _pairs(client, manager), a["id"], b["id"])
    for user in (recruiter, hr):
        assert (await client.get(QUEUE, headers=headers(user))).status_code == 403
        assert (await client.post(f"{QUEUE}/scan", headers=headers(user))).status_code == 403
        assert (await client.post(f"{QUEUE}/{pair['id']}/dismiss", json={}, headers=headers(user))).status_code == 403
        assert (await client.get(f"{CANDIDATES}/{a['id']}/merge", params={"victim": b["candidate_code"]}, headers=headers(user))).status_code == 403
        assert (await client.post(f"{CANDIDATES}/{a['id']}/merge", json={"victim_code": b["candidate_code"]}, headers=headers(user))).status_code == 403
    assert (await client.get(QUEUE)).status_code == 401
    # an authorised recruiter: the per-user allow override
    await add(db_session, UserPermissionOverride(user_id=recruiter.id, resource="candidates", action="merge", effect="allow", reason="hrc-014 test"))
    await db_session.commit()
    assert (await client.get(QUEUE, headers=headers(recruiter))).status_code == 200
    # a grant never lets a reader role write
    await add(db_session, UserPermissionOverride(user_id=hr.id, resource="candidates", action="merge", effect="allow", reason="hrc-014 test"))
    await db_session.commit()
    assert (await client.get(QUEUE, headers=headers(hr))).status_code == 403
    sup = await _user(db_session, "super_admin", "global")
    await db_session.commit()
    assert (await client.get(QUEUE, headers=headers(sup))).status_code == 200


async def test_the_status_filter_is_validated(client, db_session):
    manager, _ = await _team(db_session)
    assert (await client.get(QUEUE, params={"status": "bogus"}, headers=headers(manager))).status_code == 422


# --- the merge ------------------------------------------------------------------------------------------------------------------------
async def _merge_world(db, recruiter):
    """The survivor `s` and the victim `v`, each with a resume; `v` has one of every child record."""
    s = await make_candidate(db, recruiter, location=None, college="IIT", experience_months=24)
    v = await make_candidate(db, recruiter, location="Pune", college="NIT", experience_months=36, current_company="Acme")
    company = await add(db, Company(name=f"H14 Co {tag()}", assigned_recruiter_user_id=recruiter.id, created_by_user_id=recruiter.id))
    job = await make_job(db, company, recruiter)
    application = await add(db, JobApplication(job_id=job.id, candidate_id=v.id, added_by_user_id=recruiter.id, status="sourced"))
    old = datetime.now(UTC) - timedelta(days=30)
    await add(db, CandidateResume(candidate_id=s.id, version=1, storage_key="candidate-resumes/s1", content_type="application/pdf", size_bytes=1,
                                  uploaded_by_user_id=recruiter.id))  # fmt: skip
    v_resume = await add(db, CandidateResume(candidate_id=v.id, version=1, storage_key="candidate-resumes/v1", content_type="application/pdf",
                                             size_bytes=1, uploaded_by_user_id=recruiter.id, created_at=old))  # fmt: skip
    category = await db.scalar(select(SkillCategory.id).where(SkillCategory.name == "Programming"))
    shared_skill = await add(db, Skill(name=f"Go {tag()}", category_id=category))
    own_skill = await add(db, Skill(name=f"Rust {tag()}", category_id=category))
    for cand, skill in ((s, shared_skill), (v, shared_skill), (v, own_skill)):
        await add(db, CandidateSkill(candidate_id=cand.id, skill_id=skill.id, level="advanced", added_by_user_id=recruiter.id, status="claimed"))
    await add(db, RecruiterCall(candidate_id=v.id, caller_user_id=recruiter.id, occurred_at=old, direction="outgoing", outcome="connected"))
    await add(db, RecruiterMessage(candidate_id=v.id, sender_user_id=recruiter.id, channel="whatsapp", body="Hi", sent_at=old))
    share = await add(db, ProfileShare(job_id=job.id, company_id=company.id, channel="portal", shared_by_user_id=recruiter.id))
    await add(db, ProfileShareItem(share_id=share.id, candidate_id=v.id, application_id=application.id, resume_id=v_resume.id))
    await db.commit()
    return s, v, job, application


async def _merge(client, user, survivor, victim_code, **body):
    return await client.post(f"{CANDIDATES}/{survivor}/merge", json={"victim_code": victim_code, **body}, headers=headers(user))


async def _count(db, model, candidate_id) -> int:
    from sqlalchemy import func

    return await db.scalar(select(func.count()).select_from(model).where(model.candidate_id == candidate_id))


async def test_ac1_every_child_record_moves_to_the_survivor(client, db_session):
    manager, recruiter = await _team(db_session)
    s, v, _job, application = await _merge_world(db_session, recruiter)
    response = await _merge(client, manager, s.id, v.candidate_code, use_victim=["college"], reason="Same person, two emails")
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["id"] == str(s.id) and out["victim_code"] == v.candidate_code and out["kept_applications"] == []
    assert out["moved"] == {"applications": 1, "share_items": 1, "calls": 1, "messages": 1, "consents": 0, "documents": 0, "document_requests": 0,
                            "skills": 1, "resumes": 1}  # fmt: skip
    for model in (JobApplication, ProfileShareItem, RecruiterCall, RecruiterMessage, CandidateResume):
        assert await _count(db_session, model, v.id) == 0, model.__name__
    assert await _count(db_session, CandidateSkill, s.id) == 2 and await _count(db_session, CandidateSkill, v.id) == 1  # the shared skill stays
    assert (await db_session.get(JobApplication, application.id, populate_existing=True)).candidate_id == s.id
    # D7: resumes renumbered by upload time -- the victim's older one is v1, the survivor's newer one is current (v2)
    resumes = (await db_session.scalars(select(CandidateResume).where(CandidateResume.candidate_id == s.id).order_by(CandidateResume.version))).all()
    assert [(r.version, r.storage_key) for r in resumes] == [(1, "candidate-resumes/v1"), (2, "candidate-resumes/s1")]
    survivor, victim = await db_session.get(Candidate, s.id, populate_existing=True), await db_session.get(Candidate, v.id, populate_existing=True)
    # D4: chosen field (college), empty-fill (location, current_company); survivor kept elsewhere (experience)
    assert (survivor.college, survivor.location, survivor.current_company, survivor.experience_months) == ("NIT", "Pune", "Acme", 24)
    assert victim.merged_into_id == s.id and victim.archived_at is not None and victim.merged_by_user_id == manager.id
    assert victim.email is not None  # D4: contact stays on the victim


async def test_hrc015_documents_and_requests_move_and_a_second_pending_request_is_cancelled(client, db_session):
    """hrc-015's candidate documents move; one pending request per type (its partial unique index): the victim's duplicate is cancelled."""
    manager, recruiter = await _team(db_session)
    s, v, *_ = await _merge_world(db_session, recruiter)
    mine = await add(db_session, CandidateDocumentRequest(candidate_id=s.id, document_type="payslip", status="pending", requested_by_user_id=recruiter.id))
    clash = await add(db_session, CandidateDocumentRequest(candidate_id=v.id, document_type="payslip", status="pending", requested_by_user_id=recruiter.id))
    other = await add(db_session, CandidateDocumentRequest(candidate_id=v.id, document_type="id_proof", status="pending", requested_by_user_id=recruiter.id))
    document = await add(db_session, CandidateDocument(candidate_id=v.id, document_type="certificate", storage_key="candidate-documents/x",
                                                         content_type="application/pdf", size_bytes=1, uploaded_by_user_id=recruiter.id))  # fmt: skip
    await db_session.commit()
    response = await _merge(client, manager, s.id, v.candidate_code)
    assert response.status_code == 200, response.text
    assert response.json()["moved"]["documents"] == 1 and response.json()["moved"]["document_requests"] == 2
    rows = {r.id: r for r in await db_session.scalars(select(CandidateDocumentRequest).where(CandidateDocumentRequest.id.in_([mine.id, clash.id, other.id]))
                                                      .execution_options(populate_existing=True))}  # fmt: skip
    assert {r.candidate_id for r in rows.values()} == {s.id}
    assert (rows[mine.id].status, rows[clash.id].status, rows[other.id].status) == ("pending", "cancelled", "pending")
    assert rows[clash.id].cancelled_by_user_id == manager.id
    assert (await db_session.get(CandidateDocument, document.id, populate_existing=True)).candidate_id == s.id


async def test_ac3_the_merge_is_audited_on_both_records(client, db_session):
    manager, recruiter = await _team(db_session)
    s, v, *_ = await _merge_world(db_session, recruiter)
    assert (await _merge(client, manager, s.id, v.candidate_code, reason="secret reason text")).status_code == 200
    [meta] = [r.metadata_json for r in await db_session.scalars(select(AuditLog).where(AuditLog.action == "candidate.merge", AuditLog.entity_id == str(s.id)))]
    assert meta["victim_id"] == str(v.id) and meta["victim_code"] == v.candidate_code and meta["moved"]["applications"] == 1
    assert meta["changes"]["location"] == [None, "Pune"]
    assert "secret reason text" not in str(meta)  # reasons are free text: kept on the victim's row only
    [victim_meta] = [r.metadata_json for r in await db_session.scalars(select(AuditLog).where(AuditLog.action == "candidate.merged_into", AuditLog.entity_id == str(v.id)))]
    assert victim_meta["survivor_id"] == str(s.id) and victim_meta["reason"] == "secret reason text"
    history = await client.get(f"{CANDIDATES}/{s.id}/history", headers=headers(manager))
    assert history.status_code == 200 and history.json()["total"] >= 1


async def test_ac2_an_open_application_on_the_same_job_blocks_and_a_closed_one_stays_with_the_victim(client, db_session):
    manager, recruiter = await _team(db_session)
    s, v, job, application = await _merge_world(db_session, recruiter)
    mine = await add(db_session, JobApplication(job_id=job.id, candidate_id=s.id, added_by_user_id=recruiter.id, status="shortlisted"))
    await db_session.commit()
    preview = await client.get(f"{CANDIDATES}/{s.id}/merge", params={"victim": v.candidate_code}, headers=headers(manager))
    assert preview.status_code == 200 and preview.json()["conflicts"][0]["blocking"] is True
    blocked = await _merge(client, manager, s.id, v.candidate_code)
    assert blocked.status_code == 409 and job.title in blocked.json()["detail"]
    application.status = "withdrawn"
    await db_session.commit()
    done = await _merge(client, manager, s.id, v.candidate_code)
    assert done.status_code == 200, done.text
    assert done.json()["kept_applications"] == [str(application.id)] and done.json()["moved"]["applications"] == 0
    assert done.json()["moved"]["share_items"] == 0  # the share item follows its application
    assert (await db_session.get(JobApplication, application.id, populate_existing=True)).candidate_id == v.id
    assert (await db_session.get(JobApplication, mine.id, populate_existing=True)).candidate_id == s.id


async def test_moved_applications_follow_the_survivors_login(client, db_session):
    manager, recruiter = await _team(db_session)
    student = await _user(db_session, "it_student", "it")
    s = await candidate_for_student(db_session, student)
    s.opted_in = True
    v = await make_candidate(db_session, recruiter)
    company = await add(db_session, Company(name=f"H14 Co {tag()}", assigned_recruiter_user_id=recruiter.id, created_by_user_id=recruiter.id))
    job = await make_job(db_session, company, recruiter)
    application = await add(db_session, JobApplication(job_id=job.id, candidate_id=v.id, added_by_user_id=recruiter.id, status="sourced"))
    await add(db_session, CandidateConsent(candidate_id=s.id, user_id=student.id, action="opt_in", consent_version="v1"))
    await db_session.commit()
    assert (await _merge(client, manager, s.id, v.candidate_code)).status_code == 200
    assert (await db_session.get(JobApplication, application.id, populate_existing=True)).student_id == student.id
    assert await _count(db_session, CandidateConsent, s.id) == 1  # the survivor's consent history is untouched


async def test_d5_student_logins(client, db_session):
    manager, recruiter = await _team(db_session)
    students = [await _user(db_session, "it_student", "it") for _ in range(2)]
    linked = []
    for student in students:
        cand = await candidate_for_student(db_session, student)
        cand.opted_in = True
        linked.append(cand)
    external = await make_candidate(db_session, recruiter)
    await db_session.commit()
    other_way = await _merge(client, manager, external.id, linked[0].candidate_code)
    assert other_way.status_code == 409 and "instead" in other_way.json()["detail"]
    both = await _merge(client, manager, linked[0].id, linked[1].candidate_code)
    assert both.status_code == 409 and "student logins" in both.json()["detail"]


async def test_merge_errors(client, db_session):
    manager, recruiter = await _team(db_session)
    s, v, *_ = await _merge_world(db_session, recruiter)
    assert (await _merge(client, manager, s.id, s.candidate_code)).status_code == 422
    assert (await _merge(client, manager, s.id, "CAN-999999999")).status_code == 404
    assert (await _merge(client, manager, s.id, v.candidate_code, use_victim=["email"])).status_code == 422  # contact never moves (D4)
    assert (await _merge(client, manager, "00000000-0000-0000-0000-000000000000", v.candidate_code)).status_code == 404
    assert (await _merge(client, manager, s.id, v.candidate_code)).status_code == 200
    again = await _merge(client, manager, s.id, v.candidate_code)
    assert again.status_code == 409  # the victim is archived now
    into_victim = await _merge(client, manager, v.id, s.candidate_code)
    assert into_victim.status_code == 409


async def test_d8_a_merged_candidate_points_at_the_survivor_and_cannot_be_restored(client, db_session):
    manager, recruiter = await _team(db_session)
    s, v, *_ = await _merge_world(db_session, recruiter)
    assert (await _merge(client, manager, s.id, v.candidate_code)).status_code == 200
    detail = await client.get(f"{CANDIDATES}/{v.id}", headers=headers(recruiter))
    assert detail.json()["merged_into"] == {"id": str(s.id), "candidate_code": s.candidate_code}
    assert (await client.get(f"{CANDIDATES}/{s.id}", headers=headers(recruiter))).json()["merged_into"] is None
    restore = await client.post(f"{CANDIDATES}/{v.id}/restore", headers=headers(recruiter))
    assert restore.status_code == 409 and s.candidate_code in restore.json()["detail"]


async def test_d9_the_merge_closes_the_victims_queue_rows(client, db_session):
    manager, recruiter = await _team(db_session)
    name, college = f"Tri {tag()}", f"College {tag()}"
    a = await _create(client, db_session, recruiter, name=name, location="Pune", college=college)
    b = await _create(client, db_session, recruiter, name=name, location="Pune", college=college)
    c = await _create(client, db_session, recruiter, name=name, location="Pune", college=college)
    assert (await _merge(client, manager, a["id"], b["candidate_code"])).status_code == 200
    open_pairs = await _pairs(client, manager)
    assert _pair_of(open_pairs, a["id"], b["id"]) is None and _pair_of(open_pairs, b["id"], c["id"]) is None
    assert _pair_of(open_pairs, a["id"], c["id"]) is not None  # still a probable pair against the survivor
    merged = _pair_of(await _pairs(client, manager, "merged"), a["id"], b["id"])
    assert merged is not None and merged["decided_by"]["id"] == str(manager.id)


async def test_the_preview_shows_both_sides_and_what_moves(client, db_session):
    manager, recruiter = await _team(db_session)
    s, v, *_ = await _merge_world(db_session, recruiter)
    response = await client.get(f"{CANDIDATES}/{s.id}/merge", params={"victim": v.candidate_code}, headers=headers(manager))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["survivor"]["id"] == str(s.id) and body["victim"]["candidate_code"] == v.candidate_code
    assert body["victim"]["college"] == "NIT" and "email" in body["victim"]
    assert body["moved"]["applications"] == 1 and body["moved"]["resumes"] == 1 and body["conflicts"] == []
    assert body["fields"][0] == "name"


async def test_the_preview_hides_compensation_without_its_grant(client, db_session):
    manager, recruiter = await _team(db_session)
    s, v, *_ = await _merge_world(db_session, recruiter)
    await add(db_session, UserPermissionOverride(user_id=manager.id, resource="candidates.compensation", action="view", effect="deny", reason="hrc-014 test"))
    await db_session.commit()
    body = (await client.get(f"{CANDIDATES}/{s.id}/merge", params={"victim": v.candidate_code}, headers=headers(manager))).json()
    assert "expected_salary" not in body["survivor"] and "expected_salary" not in body["victim"]


async def test_merge_by_id_in_the_queue_marks_the_detected_pair(client, db_session):
    """A merge started from the queue marks that very row merged (whichever side stays)."""
    manager, recruiter = await _team(db_session)
    a, b = await _probable(client, db_session, recruiter)
    assert (await _merge(client, manager, b["id"], a["candidate_code"])).status_code == 200
    row = await db_session.scalar(select(CandidateDuplicate).where(CandidateDuplicate.candidate_id == min(UUID(a["id"]), UUID(b["id"])),
                                                                   CandidateDuplicate.other_id == max(UUID(a["id"]), UUID(b["id"]))))
    assert row.status == "merged"

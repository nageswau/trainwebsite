"""rec-038 matrix rows: the candidates group -- requirements (rec-007), JDs (rec-008), the candidate master and resumes (rec-009), pool
consent (rec-010), candidate skills (rec-011), resume extraction (rec-012), Find Candidates (rec-013/014), talent pools (rec-015),
matching (rec-016), program skill tags and the journey (rec-036), and a requirement's candidates (rec-017's two requirement routes).

Requirement routes resolve through `recruiter_requirements.load_scoped` (caller_scope first: placement_team, placement_manager,
super_admin, bdm; every other role 403), so a role with a requirement scope but outside this requirement reads it as missing (404, RM4)
even on a write it could not make; the action check (`require`, rec-007 §2.55) then refuses the in-scope manager and BDM with 403.
The candidate pool has no ownership scope (R11): every recruiter and manager reads and writes any candidate, hr_team reads."""

import random
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select

from app.models import (
    CandidateDocument,
    CandidateDocumentRequest,
    CandidateResume,
    CandidateRoutingRule,
    CandidateSkill,
    CandidateTask,
    EscalationRule,
    Job,
    JobAssignment,
    JobRevision,
    JobSkill,
    Program,
    RecCandidateSource,
    RequirementTask,
    SavedCandidateSearch,
    Skill,
    TalentPool,
    User,
)
from app.services import candidates as candidate_svc
from app.services import job_descriptions
from app.services.candidate_portal import DEFAULT_FIELDS
from tests.rec038_helpers import PDF, R, add, allow, make_candidate, now, tag
from tests.test_rec_012_resume_extract import SOURCE, _pdf

REQ_SCOPE = ("rec", "rec_out", "mgr", "mgr_out", "super", "bdm", "bdm_out")  # rec-007 caller_scope roles (every one reads the lists)
REQ_READ = {**allow(200, "rec", "mgr", "super", "bdm"), **allow(404, "rec_out", "mgr_out", "bdm_out")}  # the requirement's readers
OUT = allow(404, "rec_out", "mgr_out", "bdm_out")  # a scoped role outside this requirement: 404 before the action check (RM4)
# hrc-006 (DEC-SCOPE-384 O4): a placement officer has a requirement scope (the jobs it co-owns) on the requirement and JD routes only;
# the world's officer co-owns nothing, so it lists none and every requirement there is 404. Every other route keeps refusing it (403).
OWN = {**REQ_READ, **allow(404, "officer")}
OWN_OUT = {**OUT, **allow(404, "officer")}
READERS = ("rec", "rec_out", "mgr", "mgr_out", "super", "hr")  # rec-009 candidates.READERS (R11: the whole pool)
WRITERS = ("rec", "rec_out", "mgr", "mgr_out", "super")  # rec-009 candidates.WRITERS; hr_team reads only
POOL_WRITERS = ("mgr", "mgr_out", "super")  # rec-015 P6: division-global pools
TAG_EDITORS = ("it_admin", "super")  # rec-036 CI1
RESUME = _pdf(SOURCE)  # a real text PDF, so Extract reads skills (rec-012 AC1)


def _mobile() -> str:
    return "9" + "".join(random.choices("0123456789", k=9))


def _new_candidate(w) -> dict:
    return {"name": f"Rahul {tag()}", "mobile": _mobile(), "email": f"{tag('c38n-')}@example.com", "source_id": w["candidates_source"]}


def _new_requirement(w) -> dict:
    return {"company_id": w["company"], "title": f"Python {tag()}", "location": "Hyderabad"}


def _weights(w) -> dict:
    return {"weights": [{"id": w["candidates_job_skill"], "weight": 5}]}


def _file(_w):
    return {}, {"file": ("r.pdf", PDF, "application/pdf")}


def _document(_w):
    return {"document_type": "certificate"}, {"file": ("c.pdf", PDF, "application/pdf")}


ROWS = [
    # rec-007 job requirements (§2.55): the manager creates and assigns but never edits or moves the status
    R("get", "/recruiter/requirements/statuses", **allow(200, *REQ_SCOPE, "officer")),
    R("get", "/recruiter/requirements", **allow(200, *REQ_SCOPE, "officer")),
    # rec_out / mgr_out: the world's company is outside their company scope (rec-003 load_scoped, 404 before the create)
    R("post", "/recruiter/requirements", _new_requirement, **allow(201, "rec", "mgr", "super"), rec_out=404, mgr_out=404),
    R("get", "/recruiter/requirements/{requirement}", **OWN),
    R("get", "/recruiter/requirements/{requirement}/history", **OWN),  # hrc-004 B1: the record's readers
    R("get", "/recruiter/requirements/{requirement}/revisions", **OWN),  # pob-002 (DEC-SCOPE-407 R5): the record's readers
    # pob-016 (DEC-SCOPE-419, §2.311): the record's readers read, its writers answer; a Team Lead overrides (409 here: the rule is off) and sets the company's rule; super the global rule
    R("get", "/recruiter/requirements/{requirement}/checklist", **OWN),
    R("put", "/recruiter/requirements/{requirement}/checklist/items/{checklist_item}", {"status": "confirmed"}, **allow(200, "rec", "super"), **OWN_OUT),
    R("post", "/recruiter/requirements/{requirement}/checklist/override", {"reason": "Client is away"}, **allow(409, "mgr", "super"), **OWN_OUT),
    R("put", "/recruiter/companies/{company}/checklist-rule", {"block_sourcing": None}, **allow(200, "mgr", "super"), mgr_out=404),
    R("put", "/recruiter/requirement-checklist/settings", {"block_sourcing": False}, super=200),
    # pob-017 (DEC-SCOPE-429, §2.320): the record's readers read the plan and funnel; its writers save it
    R("get", "/recruiter/requirements/{requirement}/sourcing", **OWN),
    R("put", "/recruiter/requirements/{requirement}/sourcing", {"target_found": 3}, **allow(200, "rec", "super"), **OWN_OUT),
    # pob-027 (DEC-SCOPE-434, §2.325): the record's readers list its tasks; the assignee (rec) or a writer completes one; the template and
    # the escalation rules are the Team Lead's and super_admin's
    R("get", "/recruiter/requirements/{requirement}/tasks", **OWN),
    R("post", "/recruiter/requirements/{requirement}/tasks/{requirement_task}/complete", **allow(200, "rec", "super"), **OWN_OUT),
    R("get", "/recruiter/intake-automation/settings", **allow(200, "mgr", "mgr_out", "super")),
    R("put", "/recruiter/intake-automation/settings", {"task_template": [{"kind": "sourcing", "title": "Prepare the sourcing plan", "due_in_hours": 24},
      {"kind": "screening", "title": "Screen the first shortlisted profiles", "due_in_hours": 72}]}, **allow(200, "mgr", "mgr_out", "super")),
    R("get", "/recruiter/escalation-rules", **allow(200, "mgr", "mgr_out", "super")),
    R("post", "/recruiter/escalation-rules", {"event_type": "follow_up_overdue", "after_hours": 24, "notify": "reporting_manager"}, **allow(201, "mgr", "mgr_out", "super")),
    R("patch", "/recruiter/escalation-rules/{escalation_rule}", {"active": False}, **allow(200, "mgr", "mgr_out", "super")),
    R("get", "/recruiter/requirements/{requirement}/revisions/{candidates_revision}", **OWN),
    R("patch", "/recruiter/requirements/{requirement}", {"location": "Bengaluru"}, **allow(200, "rec", "super"), **OWN_OUT),
    R("post", "/recruiter/requirements/{requirement}/assign", lambda w: {"recruiter_user_id": w["rec2_id"]}, **allow(200, "mgr", "super"), **OUT),
    R("post", "/recruiter/requirements/{requirement}/status", {"status": "shortlisting"}, **allow(200, "rec", "super"), **OWN_OUT),
    # hrc-007 (DEC-SCOPE-380, §2.278): submit follows `can_edit` (the world's recruiter jobs need no approval: 409); approve / reject and the
    # queue need `jobs.approve` (the HR Manager by default, super_admin) -- the world's requirement is not pending (409); settings: super only
    R("post", "/recruiter/requirements/{requirement}/submit", {}, **allow(409, "rec", "super"), **OWN_OUT),
    R("post", "/recruiter/requirements/{requirement}/approve", {}, **allow(409, "hr_mgr", "super")),
    R("post", "/recruiter/requirements/{requirement}/reject", {"reason": "Not now"}, **allow(409, "hr_mgr", "super")),
    R("get", "/recruiter/requirement-approvals", **allow(200, "hr_mgr", "super")),
    R("get", "/recruiter/requirement-approvals/settings", **allow(200, "hr_mgr", "super")),
    R("put", "/recruiter/requirement-approvals/settings", {"legacy": False}, super=200),
    # hrc-035 (DEC-SCOPE-396, §2.290): `candidates.erase` (the HR Manager by default, super_admin) -- the world's application id is no
    # request (404); only super_admin sets the retention period (null = off, the default)
    R("get", "/recruiter/candidate-data-requests", **allow(200, "hr_mgr", "super")),
    R("post", "/recruiter/candidate-data-requests/{application}/decision", {"decision": "approve"}, **allow(404, "hr_mgr", "super")),
    R("get", "/recruiter/candidate-retention", **allow(200, "hr_mgr", "super")),
    R("put", "/recruiter/candidate-retention", {"months": None}, super=200),
    # hrc-008 (DEC-SCOPE-385, §2.281): `jobs.publish` (placement managers by default, super_admin), division-wide like `jobs.approve`
    R("put", "/recruiter/requirements/{requirement}/visibility", {"visibility": "portal"}, **allow(200, "mgr", "mgr_out", "super")),
    # rec-017 a requirement's candidates (§2.62): its readers list, the requirement's editors add
    R("get", "/recruiter/requirements/{requirement}/candidates", **REQ_READ),
    R("post", "/recruiter/requirements/{requirement}/candidates", lambda w: {"candidate_id": w["candidates_spare"]}, **allow(201, "rec", "super"), **OUT),
    # rec-008 JD (§2.58): the requirement's scope; writes follow `can_edit`
    R("get", "/recruiter/requirements/{requirement}/jd", **OWN),
    R("post", "/recruiter/requirements/{requirement}/jd", {"role": "Backend developer"}, **allow(201, "rec", "super"), **OWN_OUT),
    R("put", "/recruiter/requirements/{requirement}/jd/file", form=_file, **allow(201, "rec", "super"), **OWN_OUT),
    R("get", "/recruiter/requirements/{requirement}/jd/{candidates_jd_version}/file", **OWN),
    # hrc-006 co-owners (§2.280): the history is the record's; the owners are managed by the primary (`rec`), the manager in scope and
    # super_admin (the in-scope BDM 403). The world's requirement has a collaborator, `candidates_co_owner`, to remove.
    R("get", "/recruiter/requirements/{requirement}/assignment-history", **OWN),
    R("get", "/recruiter/requirements/{requirement}/assignment-options?role=collaborator", **allow(200, "rec", "mgr", "super"), **OWN_OUT),
    R("post", "/recruiter/requirements/{requirement}/assignments", lambda w: {"user_id": w["rec2_id"], "role": "collaborator"}, **allow(201, "rec", "mgr", "super"), **OWN_OUT),
    R("delete", "/recruiter/requirements/{requirement}/assignments/{candidates_co_owner}", **allow(200, "rec", "mgr", "super"), **OWN_OUT),
    # rec-016 matching (§2.83): candidate readers first (bdm 403), then the requirement scope (hr_team has none: 403)
    R("get", "/recruiter/requirements/{requirement}/matches", **allow(200, "rec", "mgr", "super"), rec_out=404, mgr_out=404),
    R("put", "/recruiter/requirements/{requirement}/skill-weights", _weights, **allow(200, "rec", "super"), **OUT),
    # hrc-018 (DEC-SCOPE-392 E3): candidate readers see the match factor weights; only super_admin changes them
    R("get", "/recruiter/match-settings", **allow(200, *READERS)),
    R("put", "/recruiter/match-settings", {"weights": {"skills": 40, "experience": 20, "qualification": 15, "location": 10, "role": 10, "salary": 5}}, super=200),
    # rec-009 candidate master (§2.48): one pool (R11); hr_team reads and downloads, never writes or runs the duplicate check
    R("get", "/recruiter/candidates", **allow(200, *READERS)),
    R("post", "/recruiter/candidates", _new_candidate, **allow(201, *WRITERS)),
    R("get", "/recruiter/candidates/duplicate-check?email=nobody@example.com", **allow(200, *WRITERS)),
    R("get", "/recruiter/candidates/website-registrations", **allow(200, *READERS, "hr_mgr")),  # hrc-025 N2: the HR Manager reads this list
    R("get", "/recruiter/candidates/{candidate}", **allow(200, *READERS)),
    R("get", "/recruiter/candidates/{candidate}/history", **allow(200, *READERS)),  # hrc-004 B1
    R("patch", "/recruiter/candidates/{candidate}", {"location": "Pune"}, **allow(200, *WRITERS)),
    # pob-018 (§2.319): verify and the outreach status are the writers'; readers see them on the candidate
    R("post", "/recruiter/candidates/{candidate}/verify", **allow(200, *WRITERS)),
    R("put", "/recruiter/candidates/{candidate}/outreach", {"status": "contacted"}, **allow(200, *WRITERS)),
    R("get", "/recruiter/candidates/{candidate}/applications", **allow(200, *READERS)),  # rec-017: every candidate reader sees every row
    R("post", "/recruiter/candidates/{candidates_spare}/archive", **allow(200, *WRITERS)),
    R("post", "/recruiter/candidates/{candidates_archived}/restore", **allow(200, *WRITERS)),
    R("put", "/recruiter/candidates/{candidates_cv}/resume", form=_file, **allow(201, *WRITERS)),
    R("get", "/recruiter/candidates/{candidates_cv}/resume/{candidates_version}", **allow(200, *READERS)),
    # rec-012 resume extraction (§2.76): writers only (Extract writes the resume row)
    R("post", "/recruiter/candidates/{candidates_cv}/resume/{candidates_version}/extract", **allow(200, *WRITERS)),
    R("post", "/recruiter/candidates/{candidates_cv}/resume/{candidates_version}/apply", {"location": "Pune"}, **allow(200, *WRITERS)),
    # hrc-015 (§2.277): signed links, documents and document requests -- readers read and get links, writers change
    R("get", "/recruiter/candidates/{candidates_cv}/resume/{candidates_version}/link", **allow(200, *READERS)),
    R("get", "/recruiter/candidates/{candidates_cv}/documents", **allow(200, *READERS)),
    R("post", "/recruiter/candidates/{candidates_cv}/documents", form=_document, **allow(201, *WRITERS)),
    R("get", "/recruiter/candidates/{candidates_cv}/documents/{candidates_document}/link", **allow(200, *READERS)),
    R("post", "/recruiter/candidates/{candidates_cv}/document-requests", {"document_type": "payslip"}, **allow(201, *WRITERS)),
    R("post", "/recruiter/candidates/{candidates_cv}/document-requests/{candidates_request}/cancel", **allow(200, *WRITERS)),
    # hrc-012 (§2.279): the primary recruiter (`rec` owns the world's candidate) or any manager / super_admin changes ownership; another
    # recruiter is refused. The pickers are for writers; the shared-ownership switch is read by readers and changed by managers.
    R("put", "/recruiter/candidates/{candidate}/ownership", lambda w: {"placement_officer_user_id": w["officer_id"]}, **allow(200, "rec", "mgr", "mgr_out", "super")),
    R("get", "/recruiter/candidates/assignees?kind=recruiter", **allow(200, *WRITERS)),
    R("get", "/recruiter/candidate-ownership-settings", **allow(200, *READERS)),
    R("put", "/recruiter/candidate-ownership-settings", {"shared_ownership": False}, **allow(200, "mgr", "mgr_out", "super")),
    # hrc-022 (DEC-SCOPE-386 C7, §2.282): the candidate self-service allow-list -- read like the ownership setting, changed by managers
    # hrc-024 (DEC-SCOPE-393 R11, §2.287): candidate routing is the placement manager's and super_admin's alone
    R("get", "/recruiter/candidate-routing", **allow(200, "mgr", "mgr_out", "super")),
    R("put", "/recruiter/candidate-routing", {"default_recruiter_user_id": None, "strategy": "round_robin"}, **allow(200, "mgr", "mgr_out", "super")),
    R("post", "/recruiter/candidate-routing/rules", lambda w: {"kind": "location", "location": tag("R38 City "), "recruiter_user_id": w["rec_id"]},
      **allow(201, "mgr", "mgr_out", "super")),
    R("delete", "/recruiter/candidate-routing/rules/{candidates_routing_rule}", **allow(204, "mgr", "mgr_out", "super")),
    R("get", "/recruiter/candidate-self-service-settings", **allow(200, *READERS)),
    R("put", "/recruiter/candidate-self-service-settings", {"fields": list(DEFAULT_FIELDS)}, **allow(200, "mgr", "mgr_out", "super")),
    # hrc-016 (§2.283): notes and tasks follow the candidate rule -- readers read, writers write; My tasks and the picker are writers'
    R("get", "/recruiter/candidates/{candidate}/notes", **allow(200, *READERS)),
    R("post", "/recruiter/candidates/{candidate}/notes", {"body": "Internal note"}, **allow(201, *WRITERS)),
    R("get", "/recruiter/candidates/{candidate}/tasks", **allow(200, *READERS)),
    R("post", "/recruiter/candidates/{candidate}/tasks", lambda w: {"task_type": "follow_up", "title": "Call", "due_at": (now() + timedelta(days=1)).isoformat(),
                                                          "assignee_user_id": w["rec_id"]}, **allow(201, *WRITERS)),  # fmt: skip
    R("get", "/recruiter/candidate-tasks", **allow(200, *WRITERS)),
    R("get", "/recruiter/candidate-tasks/assignees", **allow(200, *WRITERS)),
    R("patch", "/recruiter/candidate-tasks/{candidates_task}", {"title": "Call again"}, **allow(200, *WRITERS)),
    R("post", "/recruiter/candidate-tasks/{candidates_task}/complete", **allow(200, *WRITERS)),
    R("post", "/recruiter/candidate-tasks/{candidates_task}/cancel", **allow(200, *WRITERS)),
    # rec-013 / rec-014 Find Candidates (§2.77, §2.80): read only, hr_team included
    R("post", "/recruiter/candidates/search", {"all": ["Java"]}, **allow(200, *READERS)),
    # hrc-020 (§2.294): saved searches for every reader; only the owner (rec) or super_admin changes the shared one, others 403. The
    # export needs `candidates.export` (placement managers by default, super_admin implicitly).
    R("get", "/recruiter/candidates/saved-searches", **allow(200, *READERS)),
    R("post", "/recruiter/candidates/saved-searches", lambda w: {"name": tag("R38 Search "), "filters": {"all": ["Java"]}}, **allow(201, *READERS)),
    R("patch", "/recruiter/candidates/saved-searches/{candidates_saved_search}", {"shared": True},
      **{**allow(403, "rec_out", "mgr", "mgr_out", "hr"), **allow(200, "rec", "super")}),  # fmt: skip
    R("delete", "/recruiter/candidates/saved-searches/{candidates_saved_search}", **{**allow(403, "rec_out", "mgr", "mgr_out", "hr"), **allow(204, "rec", "super")}),
    R("post", "/recruiter/candidates/search/export?format=csv", {"all": ["Java"]}, **{**allow(403, "rec", "rec_out", "hr"), **allow(200, "mgr", "mgr_out", "super")}),
    # rec-036 the candidate journey (§2.105)
    R("get", "/recruiter/candidates/{candidate}/journey", **allow(200, *READERS)),
    # nehn-016 the candidate's training progress, read only (§2.223): the writers, never hr_team (nehn-017)
    R("get", "/recruiter/candidates/{candidate}/training", **allow(200, *WRITERS)),
    # rec-011 candidate skills (§2.63): the master's roles
    R("get", "/recruiter/candidates/{candidates_cv}/skills", **allow(200, *READERS)),
    R("post", "/recruiter/candidates/{candidates_cv}/skills", {"skill": "MySQL", "level": "advanced"}, **allow(201, *WRITERS)),
    R("patch", "/recruiter/candidates/{candidates_cv}/skills/{candidates_skill}", {"level": "expert"}, **allow(200, *WRITERS)),
    R("delete", "/recruiter/candidates/{candidates_cv}/skills/{candidates_skill}", **allow(204, *WRITERS)),
    R("post", "/recruiter/candidates/{candidates_cv}/skills/{candidates_skill}/status", {"status": "verified"}, **allow(200, *WRITERS)),
    # rec-015 talent pools (§2.85): candidate readers read active pools; managers and super_admin change any pool
    R("get", "/recruiter/pools", **allow(200, *READERS)),
    R("post", "/recruiter/pools", lambda w: {"name": f"R38 Pool {tag()}", "all": ["Java"]}, **allow(201, *POOL_WRITERS)),
    R("patch", "/recruiter/pools/{candidates_pool}", lambda w: {"name": f"R38 Pool {tag()}"}, **allow(200, *POOL_WRITERS)),
    R("get", "/recruiter/pools/{candidates_pool}/candidates", **allow(200, *READERS)),
    # rec-036 program skill tags (§2.105): it_admin and super_admin
    R("get", "/admin/programs/skill-options", **allow(200, *TAG_EDITORS)),
    R("get", "/admin/programs/{candidates_program}/skills", **allow(200, *TAG_EDITORS)),
    R("put", "/admin/programs/{candidates_program}/skills", lambda w: {"skill_ids": [w["candidates_java"]]}, **allow(200, *TAG_EDITORS)),
    # rec-010 the IT student's own pool consent (§2.64): no user id, only the caller (the world's student is opted in; both moves are 200)
    R("get", "/account/placement-pool", student=200),
    R("post", "/account/placement-pool/opt-in", {"consent_version": "v1"}, student=200),
    R("post", "/account/placement-pool/opt-out", student=200),
    # hrc-011 (DEC-SCOPE-375) manual exchange rates: candidates.require_reader reads, recruiter.require_manager sets (the rate is global).
    R("get", "/recruiter/catalogue/exchange-rates", **allow(200, *READERS)),
    R("put", "/recruiter/catalogue/exchange-rates/{fx_currency}", {"inr_per_unit": "83.25"}, **allow(200, "mgr", "mgr_out", "super")),
    # hrc-015 (§2.277): the student's own documents (the world's student is in the pool); another candidate's document is a 404
    R("get", "/account/candidate-documents", student=200),
    R("post", "/account/candidate-documents", form=_document, student=201),
    R("get", "/account/candidate-documents/{candidates_document}/link", student=404),
]
_POOL: dict[str, UUID] = {}
PATH_VALUES = {"checklist_item": "openings", "candidates_version": 1, "fx_currency": "USD"}  # the candidate's first (and only) resume version; a rate's currency


async def build(client, db, w) -> None:
    """A spare and an archived external candidate, one with a resume (v1, extracted) and a claimed Java skill, a requirement skill and
    a JD version with a file on `requirement`, an active talent pool and a program."""
    rec, mgr = w["users"]["rec"], w["users"]["mgr"]
    source = await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == "referral"))
    java = await db.scalar(select(Skill).where(Skill.name == "Java"))
    spare = await make_candidate(db, rec)
    archived = await make_candidate(db, rec, archived_at=func.now(), archived_by_user_id=rec.id)
    cv = await make_candidate(db, rec)
    await add(db, CandidateResume(candidate_id=cv.id, version=1, storage_key=candidate_svc.store(RESUME, "application/pdf"), content_type="application/pdf",
                                  file_name="r.pdf", size_bytes=len(RESUME), uploaded_by_user_id=rec.id,
                                  extracted_text="", extraction_json={"skills": [], "truncated": False}))  # fmt: skip
    document = await add(db, CandidateDocument(candidate_id=cv.id, document_type="certificate", storage_key=candidate_svc.store(PDF, "application/pdf", candidate_svc.DOCUMENT_PREFIX),
                                               content_type="application/pdf", file_name="c.pdf", size_bytes=len(PDF), uploaded_by_user_id=rec.id))  # fmt: skip
    request = await add(db, CandidateDocumentRequest(candidate_id=cv.id, document_type="education", status="pending", requested_by_user_id=rec.id))
    skill = await add(db, CandidateSkill(candidate_id=cv.id, skill_id=java.id, level="beginner", added_by_user_id=rec.id))
    job = await db.get(Job, UUID(w["requirement"]))
    job_skill = await add(db, JobSkill(job_id=job.id, name=tag("R38 Skill "), kind="required", weight=2, position=0))
    stored = {"storage_key": job_descriptions.store(PDF, "application/pdf"), "file_name": "jd.pdf", "content_type": "application/pdf", "size_bytes": len(PDF)}
    jd = await job_descriptions.add_version(db, rec, job, None, stored)
    co_owner = await add(db, User(email=f"{tag('r38-co-')}@example.local", password_hash="!", full_name=f"Co-owner {tag()}", role="placement_officer",
                                  division="it", active=True, email_verified=True))  # fmt: skip
    await add(db, JobAssignment(job_id=job.id, user_id=co_owner.id, role="collaborator", added_by_user_id=rec.id))  # hrc-006
    await add(db, JobRevision(job_id=job.id, revision=1, snapshot={"title": job.title}, changed_fields=[], author_user_id=rec.id))  # pob-002
    if "id" not in _POOL:  # one pool per run: the pool list counts every active pool's members, so a pool per world makes it crawl
        _POOL["id"] = (await add(db, TalentPool(name=tag("R38 Pool "), all_terms=["Java"], any_terms=[], active=True, created_by_user_id=mgr.id,
                                                updated_by_user_id=mgr.id))).id  # fmt: skip
    program = await add(db, Program(slug=tag("r38-"), category="Software Development", title=f"R38 Program {tag()}", summary="", duration="8 weeks",
                                     eligibility="", fees=0, certification="Cert", curriculum=[], placement_assistance="", trainer_name="T", active=True))  # fmt: skip
    # hrc-016: an open task on the world's candidate (each write cell runs on its own world, so complete and cancel both succeed)
    task = await add(db, CandidateTask(candidate_id=UUID(w["candidate"]), task_type="follow_up", title="Call back", due_at=func.now() + timedelta(days=1),
                                       assignee_user_id=rec.id, created_by_user_id=rec.id))  # fmt: skip
    rule = await add(db, CandidateRoutingRule(kind="location", location=tag("R38 City "), recruiter_user_id=rec.id))  # hrc-024
    # pob-027: an open task for the recruiter on the world's requirement, and a switched-off escalation rule
    requirement_task = await add(db, RequirementTask(job_id=job.id, kind="sourcing", title="R38 task", due_at=func.now() + timedelta(days=1), assignee_user_id=rec.id))
    escalation_rule = await add(db, EscalationRule(event_type="follow_up_overdue", after_hours=24, notify="reporting_manager", active=False, created_by_user_id=mgr.id))
    saved = await add(db, SavedCandidateSearch(owner_user_id=rec.id, name=tag("R38 Saved "), filters={"all": ["Java"]}, shared=True))  # hrc-020
    await db.commit()
    w.update({
        "requirement_task": str(requirement_task.id), "escalation_rule": str(escalation_rule.id),
        "candidates_task": str(task.id), "candidates_routing_rule": str(rule.id), "candidates_saved_search": str(saved.id),
        "candidates_source": str(source.id), "candidates_java": str(java.id), "candidates_spare": str(spare.id), "candidates_archived": str(archived.id),
        "candidates_cv": str(cv.id), "candidates_document": str(document.id), "candidates_request": str(request.id), "candidates_skill": str(skill.id), "candidates_job_skill": str(job_skill.id), "candidates_jd_version": str(jd.version),
        "candidates_pool": str(_POOL["id"]), "candidates_program": str(program.id), "candidates_co_owner": str(co_owner.id), "candidates_revision": "1",
    })  # fmt: skip

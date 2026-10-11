"""rec-038 matrix rows: the candidates group -- requirements (rec-007), JDs (rec-008), the candidate master and resumes (rec-009), pool
consent (rec-010), candidate skills (rec-011), resume extraction (rec-012), Find Candidates (rec-013/014), talent pools (rec-015),
matching (rec-016), program skill tags and the journey (rec-036), and a requirement's candidates (rec-017's two requirement routes).

Requirement routes resolve through `recruiter_requirements.load_scoped` (caller_scope first: placement_team, placement_manager,
super_admin, bdm; every other role 403), so a role with a requirement scope but outside this requirement reads it as missing (404, RM4)
even on a write it could not make; the action check (`require`, rec-007 §2.55) then refuses the in-scope manager and BDM with 403.
The candidate pool has no ownership scope (R11): every recruiter and manager reads and writes any candidate, hr_team reads."""

import random
from uuid import UUID

from sqlalchemy import func, select

from app.models import CandidateResume, CandidateSkill, Job, JobSkill, Program, RecCandidateSource, Skill, TalentPool
from app.services import candidates as candidate_svc
from app.services import job_descriptions
from tests.rec038_helpers import PDF, R, add, allow, make_candidate, tag
from tests.test_rec_012_resume_extract import SOURCE, _pdf

REQ_SCOPE = ("rec", "rec_out", "mgr", "mgr_out", "super", "bdm", "bdm_out")  # rec-007 caller_scope roles (every one reads the lists)
REQ_READ = {**allow(200, "rec", "mgr", "super", "bdm"), **allow(404, "rec_out", "mgr_out", "bdm_out")}  # the requirement's readers
OUT = allow(404, "rec_out", "mgr_out", "bdm_out")  # a scoped role outside this requirement: 404 before the action check (RM4)
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


ROWS = [
    # rec-007 job requirements (§2.55): the manager creates and assigns but never edits or moves the status
    R("get", "/recruiter/requirements/statuses", **allow(200, *REQ_SCOPE)),
    R("get", "/recruiter/requirements", **allow(200, *REQ_SCOPE)),
    # rec_out / mgr_out: the world's company is outside their company scope (rec-003 load_scoped, 404 before the create)
    R("post", "/recruiter/requirements", _new_requirement, **allow(201, "rec", "mgr", "super"), rec_out=404, mgr_out=404),
    R("get", "/recruiter/requirements/{requirement}", **REQ_READ),
    R("patch", "/recruiter/requirements/{requirement}", {"location": "Bengaluru"}, **allow(200, "rec", "super"), **OUT),
    R("post", "/recruiter/requirements/{requirement}/assign", lambda w: {"recruiter_user_id": w["rec2_id"]}, **allow(200, "mgr", "super"), **OUT),
    R("post", "/recruiter/requirements/{requirement}/status", {"status": "shortlisting"}, **allow(200, "rec", "super"), **OUT),
    # rec-017 a requirement's candidates (§2.62): its readers list, the requirement's editors add
    R("get", "/recruiter/requirements/{requirement}/candidates", **REQ_READ),
    R("post", "/recruiter/requirements/{requirement}/candidates", lambda w: {"candidate_id": w["candidates_spare"]}, **allow(201, "rec", "super"), **OUT),
    # rec-008 JD (§2.58): the requirement's scope; writes follow `can_edit`
    R("get", "/recruiter/requirements/{requirement}/jd", **REQ_READ),
    R("post", "/recruiter/requirements/{requirement}/jd", {"role": "Backend developer"}, **allow(201, "rec", "super"), **OUT),
    R("put", "/recruiter/requirements/{requirement}/jd/file", form=_file, **allow(201, "rec", "super"), **OUT),
    R("get", "/recruiter/requirements/{requirement}/jd/{candidates_jd_version}/file", **REQ_READ),
    # rec-016 matching (§2.83): candidate readers first (bdm 403), then the requirement scope (hr_team has none: 403)
    R("get", "/recruiter/requirements/{requirement}/matches", **allow(200, "rec", "mgr", "super"), rec_out=404, mgr_out=404),
    R("put", "/recruiter/requirements/{requirement}/skill-weights", _weights, **allow(200, "rec", "super"), **OUT),
    # rec-009 candidate master (§2.48): one pool (R11); hr_team reads and downloads, never writes or runs the duplicate check
    R("get", "/recruiter/candidates", **allow(200, *READERS)),
    R("post", "/recruiter/candidates", _new_candidate, **allow(201, *WRITERS)),
    R("get", "/recruiter/candidates/duplicate-check?email=nobody@example.com", **allow(200, *WRITERS)),
    R("get", "/recruiter/candidates/{candidate}", **allow(200, *READERS)),
    R("patch", "/recruiter/candidates/{candidate}", {"location": "Pune"}, **allow(200, *WRITERS)),
    R("get", "/recruiter/candidates/{candidate}/applications", **allow(200, *READERS)),  # rec-017: every candidate reader sees every row
    R("post", "/recruiter/candidates/{candidates_spare}/archive", **allow(200, *WRITERS)),
    R("post", "/recruiter/candidates/{candidates_archived}/restore", **allow(200, *WRITERS)),
    R("put", "/recruiter/candidates/{candidates_cv}/resume", form=_file, **allow(201, *WRITERS)),
    R("get", "/recruiter/candidates/{candidates_cv}/resume/{candidates_version}", **allow(200, *READERS)),
    # rec-012 resume extraction (§2.76): writers only (Extract writes the resume row)
    R("post", "/recruiter/candidates/{candidates_cv}/resume/{candidates_version}/extract", **allow(200, *WRITERS)),
    R("post", "/recruiter/candidates/{candidates_cv}/resume/{candidates_version}/apply", {"location": "Pune"}, **allow(200, *WRITERS)),
    # rec-013 / rec-014 Find Candidates (§2.77, §2.80): read only, hr_team included
    R("post", "/recruiter/candidates/search", {"all": ["Java"]}, **allow(200, *READERS)),
    # rec-036 the candidate journey (§2.105)
    R("get", "/recruiter/candidates/{candidate}/journey", **allow(200, *READERS)),
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
]
_POOL: dict[str, UUID] = {}
PATH_VALUES = {"candidates_version": 1}  # the candidate's first (and only) resume version


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
    skill = await add(db, CandidateSkill(candidate_id=cv.id, skill_id=java.id, level="beginner", added_by_user_id=rec.id))
    job = await db.get(Job, UUID(w["requirement"]))
    job_skill = await add(db, JobSkill(job_id=job.id, name=tag("R38 Skill "), kind="required", weight=2, position=0))
    stored = {"storage_key": job_descriptions.store(PDF, "application/pdf"), "file_name": "jd.pdf", "content_type": "application/pdf", "size_bytes": len(PDF)}
    jd = await job_descriptions.add_version(db, rec, job, None, stored)
    if "id" not in _POOL:  # one pool per run: the pool list counts every active pool's members, so a pool per world makes it crawl
        _POOL["id"] = (await add(db, TalentPool(name=tag("R38 Pool "), all_terms=["Java"], any_terms=[], active=True, created_by_user_id=mgr.id,
                                                updated_by_user_id=mgr.id))).id  # fmt: skip
    program = await add(db, Program(slug=tag("r38-"), category="Software Development", title=f"R38 Program {tag()}", summary="", duration="8 weeks",
                                     eligibility="", fees=0, certification="Cert", curriculum=[], placement_assistance="", trainer_name="T", active=True))  # fmt: skip
    await db.commit()
    w.update({
        "candidates_source": str(source.id), "candidates_java": str(java.id), "candidates_spare": str(spare.id), "candidates_archived": str(archived.id),
        "candidates_cv": str(cv.id), "candidates_skill": str(skill.id), "candidates_job_skill": str(job_skill.id), "candidates_jd_version": str(jd.version),
        "candidates_pool": str(_POOL["id"]), "candidates_program": str(program.id),
    })  # fmt: skip

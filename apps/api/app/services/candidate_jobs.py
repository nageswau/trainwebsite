"""hrc-027 (DEC-SCOPE-398 J1-J12, spec docs/superpowers/specs/2026-11-05-hrc-027-candidate-job-recommendations-design.md): the open jobs
an IT student or an external candidate may see, in three views, scored by hrc-018's rule run candidate -> jobs, and the one apply gate.

Visible = what hrc-008 lets a student apply to (open, deadline not passed, portal/public/their segments); anything else is the same 404 as
a missing job. A card never carries a salary (no job salary is published, hrc-018 E9). Reading never creates a candidate (J9).

Cost: three reads for every visible job (jobs + company, their skills, the caller's applications) and one for the caller's skills with
their related skills; hrc-018's full `spec`/`facts` only for the jobs that share a skill with the caller or switch a hard filter on."""

import logging
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JOB_OPEN_STATUSES, AuditLog, Candidate, CandidateSkill, Company, Job, JobApplication, JobSkill, SkillRelated, User
from app.services import applications, job_visibility, matching, portal_events
from app.services import candidate_portal as portal

logger = logging.getLogger("app.candidate_jobs")

VIEWS = ("recommended", "matching", "all")
RECOMMENDED_MIN_SCORE = 50  # J3 (NEEDS_CONFIRMATION): no admin setting yet
NOT_FOUND = "Open job not found"
ALREADY_APPLIED = "Already applied"
CANDIDATE_JOBS_URL = "/it/careers/portal/jobs"
EMPTY_FACTS = {"skills": {}, "degrees": [], "experience_months": None, "relevant_months": None, "location": None, "preferred_locations": [],
               "roles": [], "expected_annual_inr": None, "available_from": None, "notice_days": None}  # fmt: skip


def _gap_text(spec: matching.Spec, key: str) -> str:
    """A hard filter the caller misses, in their words; the salary one names no amount (the budget is not published)."""
    if key == "experience":
        return f"at least {matching.years(spec.experience[0])} of experience"
    if key == "qualification":
        return f"the qualification: {spec.qualification.strip()}"
    if key == "location":
        return f"being in or preferring {spec.location}"
    return "an expected salary within the job's budget"


async def own_candidate(db: AsyncSession, user: User) -> Candidate | None:
    return await db.scalar(select(Candidate).where(Candidate.user_id == user.id, Candidate.merged_into_id.is_(None)))


async def _visible(db: AsyncSession, user: User) -> tuple:
    return (Job.status.in_(JOB_OPEN_STATUSES), or_(Job.closes_on.is_(None), Job.closes_on >= date.today()), await job_visibility.student_filter(db, user))


def _search(q: str) -> tuple:
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    named = exists(select(JobSkill.id).where(JobSkill.job_id == Job.id, JobSkill.name.ilike(like, escape="\\")))
    return (or_(Job.title.ilike(like, escape="\\"), Company.name.ilike(like, escape="\\"), Job.location.ilike(like, escape="\\"), named),)


async def _accepted(db: AsyncSession, candidate: Candidate | None) -> set[UUID]:
    """The caller's skills and their related skills: a job skill can only be met through one of these."""
    if candidate is None:
        return set()
    held = set((await db.scalars(select(CandidateSkill.skill_id).where(CandidateSkill.candidate_id == candidate.id))).all())
    if not held:
        return set()
    pairs = await db.execute(select(SkillRelated.skill_a_id, SkillRelated.skill_b_id).where(or_(SkillRelated.skill_a_id.in_(held), SkillRelated.skill_b_id.in_(held))))
    return held.union(*({a, b} for a, b in pairs.all()))


def _hard_on(job: Job) -> bool:
    return any(getattr(job, f"match_hard_{k}") for k in matching.HARD_FILTERS)


async def _assess(db: AsyncSession, job: Job, candidate: Candidate | None) -> dict:
    """hrc-018's rule for one job: the candidate-audience result, the skill hits and the unmet hard filters."""
    spec = await matching.spec(db, job)
    facts = (await matching.facts(db, [candidate], spec))[candidate.id] if candidate else dict(EMPTY_FACTS)
    hits = matching.skill_hits(spec, facts)
    required = [s for s in spec.skills if s["kind"] == "required"]
    group = required or spec.skills
    return {
        "result": matching.evaluate(spec, facts, today=matching._today(), audience="candidate") if spec.skills else None,
        "held": {s["name"] for s in spec.skills if hits[s["id"]]},
        "matches": any(hits[s["id"]] for s in group),
        "blocked": [_gap_text(spec, k) for k in matching.hard_filter_gaps(spec, facts)],
    }


def _skills_text(required: list[str], preferred: list[str], held: set[str]) -> str:
    names, kind = (required, "required") if required else (preferred, "preferred")
    if not names:
        return "No skills are listed for this job"
    missing = [n for n in names if n not in held]
    tail = f" (missing {', '.join(missing)})" if missing else ""
    return f"Matches {len(names) - len(missing)} of {len(names)} {kind} skills{tail}"


async def listing(db: AsyncSession, user: User, *, view: str, q: str | None, limit: int, offset: int) -> dict:
    where = (*await _visible(db, user), *(_search(q.strip()) if q and q.strip() else ()))
    rows = (await db.execute(select(Job, Company).join(Company, Company.id == Job.company_id).where(*where).order_by(Job.created_at.desc(), Job.id.desc()))).all()
    ids = select(Job.id).join(Company, Company.id == Job.company_id).where(*where)
    skills: dict[UUID, list[JobSkill]] = {}
    for s in (await db.scalars(select(JobSkill).where(JobSkill.job_id.in_(ids)).order_by(JobSkill.position))).all():
        skills.setdefault(s.job_id, []).append(s)
    candidate = await own_candidate(db, user)
    accepted = await _accepted(db, candidate)
    applied = {}
    if candidate:
        applied = {a.job_id: a for a in (await db.scalars(select(JobApplication).where(JobApplication.candidate_id == candidate.id, JobApplication.job_id.in_(ids)))).all()}
    cards = []
    for job, company in rows:
        own = skills.get(job.id, [])
        assessed = await _assess(db, job, candidate) if _hard_on(job) or any(s.skill_id in accepted for s in own) else None
        result = assessed["result"] if assessed else None
        required = [s.name for s in own if s.kind == "required"]
        preferred = [s.name for s in own if s.kind == "preferred"]
        application = applied.get(job.id)
        blocked = assessed["blocked"] if assessed else []
        cards.append({
            "id": job.id, "title": job.title, "company": job_visibility.client_name(job, company), "location": job.location, "work_mode": job.work_mode,
            "employment_type": job.employment_type, "required_skills": required, "preferred_skills": preferred,
            "experience_min_months": job.experience_min_months, "experience_max_months": job.experience_max_months, "closes_on": job.closes_on,
            "match": {"score": result["score"], "explanation": result["explanation"]} if result else None,
            "skills_text": _skills_text(required, preferred, assessed["held"] if assessed else set()),
            "matches_skills": bool(assessed and assessed["matches"]),
            "recommended": bool(result and result["score"] >= RECOMMENDED_MIN_SCORE),
            "application": {"code": application.application_code, "status_label": applications.candidate_label(application.candidate_status)} if application else None,
            "can_apply": application is None and not blocked,
            "blocked": blocked,
        })  # fmt: skip
    groups = {
        "recommended": sorted((c for c in cards if c["recommended"]), key=lambda c: -c["match"]["score"]),
        "matching": sorted((c for c in cards if c["matches_skills"]), key=lambda c: -c["match"]["score"] if c["match"] else 1),
        "all": cards,
    }  # sorted() is stable, so equal scores stay newest first; unscored matching jobs follow the scored ones
    chosen = groups[view]
    await portal_events.record(db, user.id, portal_events.JOB_VIEW, [card["id"] for card in chosen[offset: offset + limit]])  # hrc-034 (I3): the route commits
    logger.info("candidate_jobs_listed", extra={"extra_fields": {"user_id": str(user.id), "view": view, "visible": len(cards), "shown": len(chosen)}})
    return {
        "view": view, "q": q, "items": chosen[offset: offset + limit], "total": len(chosen), "limit": limit, "offset": offset,
        "counts": {k: len(v) for k, v in groups.items()}, "reason": None if accepted else matching.NO_SKILLS,
        "disclaimer": matching.DISCLAIMER, "threshold": RECOMMENDED_MIN_SCORE,
    }  # fmt: skip


async def check_eligible(db: AsyncSession, job: Job, candidate: Candidate) -> None:
    """J7: 422 naming each switched-on hard filter the candidate misses (required skills only rank)."""
    blocked = (await _assess(db, job, candidate))["blocked"] if _hard_on(job) else []
    if blocked:
        raise HTTPException(422, f"Your profile does not meet this job's requirements: {'; '.join(blocked)}. Update your profile or ask your recruiter.")


async def apply(db: AsyncSession, user: User, job_id: UUID) -> JobApplication:
    job = await db.scalar(select(Job).where(Job.id == job_id, *await _visible(db, user)))
    if job is None:
        raise HTTPException(404, NOT_FOUND)
    # hrc-034 (I3): committed before the gates, so a refused attempt stays as a real drop-off
    await portal_events.record(db, user.id, portal_events.APPLY_START, [job.id])
    await db.commit()
    student = user.role == "it_student"
    candidate = await applications.candidate_for_student(db, user) if student else await portal.own(db, user)
    if await db.scalar(select(JobApplication.id).where(JobApplication.job_id == job.id, JobApplication.candidate_id == candidate.id)):
        raise HTTPException(409, ALREADY_APPLIED)
    await check_eligible(db, job, candidate)
    note = "Applied from the student portal" if student else "Applied from the candidate portal"
    item = await applications.create(db, user, job, candidate, "sourced", note, resume_url=user.profile.get("resume_url") if student else None)
    await applications.send_receipt(db, item, job)  # hrc-026 (AC4)
    await portal_events.record(db, user.id, portal_events.APPLY_SUBMIT, [job.id])  # hrc-034 (I3)
    db.add(AuditLog(user_id=user.id, action="job.apply", entity_type="job_application", entity_id=str(item.id), metadata_json={"job_id": str(job.id)}))
    logger.info("candidate_job_applied", extra={"extra_fields": {"user_id": str(user.id), "job_id": str(job.id), "application_id": str(item.id)}})
    return item

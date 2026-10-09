"""rec-016 (DEC-SCOPE-157, M1-M8): requirement → candidate matching and the weighted match score.

`allocate` is the pure scoring rule: experience and location fit are worth 10 points each when they apply, the skills share the rest in
proportion to their `job_skills.weight`, and every share is a whole number (largest remainder), so a full match is exactly 100 and a
breakdown always adds up to its score. `matches` is read only: SQL decides every match once -- each item's flag is a selected column and
the ranking orders by the same flags -- and Python only adds up the points. Only ids and bound values reach SQL."""

import logging
from uuid import UUID

from sqlalchemy import and_, case, exists, false, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Candidate, Job, JobApplication, JobSkill, SkillRelated, User
from app.services import applications
from app.services.candidate_search import _has
from app.services.candidates import pool_filter

logger = logging.getLogger("app.matching")

EXPERIENCE_POINTS = 10  # M1 (the source's "Experience – 10%")
LOCATION_POINTS = 10  # M1 (Q-14: location fit)
NO_SKILLS = "no_skills"
PAGE_SIZE = 20


def allocate(weights: list[int], *, experience: bool, location: bool) -> tuple[list[int], int, int]:
    """(points per skill, experience points, location points). A weight of 0 (a skill not in the Skills Master) earns nothing."""
    exp, loc = EXPERIENCE_POINTS if experience else 0, LOCATION_POINTS if location else 0
    share, total = 100 - exp - loc, sum(weights)
    if not total:
        return [0] * len(weights), exp, loc
    points = [share * w // total for w in weights]
    leftover = share - sum(points)
    by_remainder = sorted(range(len(weights)), key=lambda i: (-(share * weights[i] % total), i))
    for i in by_remainder[:leftover]:
        points[i] += 1
    return points, exp, loc


def _flag(condition):
    return func.coalesce(condition, false())


async def _related(db: AsyncSession, skill_ids: set[UUID]) -> dict[UUID, set[UUID]]:
    """Each skill with its related skills, both directions (M3), in one query."""
    out = {i: {i} for i in skill_ids}
    pairs = await db.execute(select(SkillRelated.skill_a_id, SkillRelated.skill_b_id).where(or_(SkillRelated.skill_a_id.in_(skill_ids), SkillRelated.skill_b_id.in_(skill_ids))))
    for a, b in pairs.all():
        if a in out:
            out[a].add(b)
        if b in out:
            out[b].add(a)
    return out


async def plan(db: AsyncSession, job: Job) -> dict:
    """The criteria (what the page shows) and the scored items (key, label, kind, points, flag). No Skills-Master skill = no items."""
    skills = (await db.scalars(select(JobSkill).where(JobSkill.job_id == job.id).order_by(JobSkill.kind.desc(), JobSkill.position))).all()
    has_experience = job.experience_min_months is not None or job.experience_max_months is not None
    place = (job.location or "").strip()
    has_location = job.work_mode != "remote" and bool(place)
    skill_points, exp_points, loc_points = allocate([s.weight if s.skill_id else 0 for s in skills], experience=has_experience, location=has_location)
    criteria = {
        "skills": [
            {"id": s.id, "name": s.name, "kind": s.kind, "weight": s.weight, "points": p, "in_master": s.skill_id is not None}
            for s, p in zip(skills, skill_points, strict=True)
        ],
        "experience": {"min_months": job.experience_min_months, "max_months": job.experience_max_months, "points": exp_points} if has_experience else None,
        "location": {"value": place, "points": loc_points} if has_location else None,
    }
    resolved = [(s, p) for s, p in zip(skills, skill_points, strict=True) if s.skill_id]
    if not resolved:
        return {"criteria": criteria, "items": [], "filter": []}
    related = await _related(db, {s.skill_id for s, _ in resolved})
    items = [
        {"key": f"skill:{s.id}", "label": s.name, "kind": s.kind, "points": p, "flag": _has(related[s.skill_id], False)} for s, p in resolved
    ]
    required = [item["flag"] for item in items if item["kind"] == "required"]
    where = required or [or_(*(item["flag"] for item in items))]  # M4: every required skill, else at least one preferred one
    if has_experience:
        bounds = [Candidate.experience_months >= job.experience_min_months] if job.experience_min_months is not None else []
        bounds += [Candidate.experience_months <= job.experience_max_months] if job.experience_max_months is not None else []
        items.append({"key": "experience", "label": "Experience", "kind": "experience", "points": exp_points, "flag": _flag(and_(*bounds))})
    if has_location:
        key = place.lower()
        wanted = func.json_array_elements_text(Candidate.preferred_locations).table_valued("value")
        preferred = exists(select(literal(1)).select_from(wanted).where(func.lower(func.trim(wanted.c.value)) == key))
        items.append({"key": "location", "label": "Location", "kind": "location", "points": loc_points,
                      "flag": _flag(or_(func.lower(func.trim(Candidate.location)) == key, preferred))})
    return {"criteria": criteria, "items": items, "filter": where}


async def matches(db: AsyncSession, job: Job, *, limit: int, offset: int) -> dict:
    planned = await plan(db, job)
    items = planned["items"]
    if not items:
        return {"criteria": planned["criteria"], "reason": NO_SKILLS, "items": [], "total": 0, "limit": limit, "offset": offset}
    where = [*pool_filter(), Candidate.archived_at.is_(None), *planned["filter"]]
    total = await db.scalar(select(func.count()).select_from(Candidate).where(*where)) or 0
    flags = [item["flag"].label(f"m{n}") for n, item in enumerate(items)]
    score = sum((case((item["flag"], item["points"]), else_=0) for item in items), literal(0))
    rows = (await db.execute(
        select(Candidate, *flags).where(*where).order_by(score.desc(), Candidate.created_at.desc(), Candidate.id.desc()).limit(limit).offset(offset)
    )).all()
    on_job = {}
    if rows:
        found = await db.scalars(select(JobApplication).where(JobApplication.job_id == job.id, JobApplication.candidate_id.in_([r[0].id for r in rows])))
        on_job = {a.candidate_id: a for a in found.all()}
    out = []
    for candidate, *matched in rows:
        breakdown = [
            {"key": item["key"], "label": item["label"], "kind": item["kind"], "points": item["points"] if hit else 0, "max": item["points"], "matched": bool(hit)}
            for item, hit in zip(items, matched, strict=True)
        ]
        application = on_job.get(candidate.id)
        out.append({
            "id": candidate.id, "candidate_code": candidate.candidate_code, "name": candidate.name, "preferred_role": candidate.preferred_role,
            "current_company": candidate.current_company, "experience_months": candidate.experience_months, "location": candidate.location,
            "notice_days": candidate.notice_days, "status": candidate.status, "score": sum(b["points"] for b in breakdown), "breakdown": breakdown,
            "application": {"id": application.id, "status": application.status, "status_label": applications.label(application.status)} if application else None,
        })
    return {"criteria": planned["criteria"], "reason": None, "items": out, "total": total, "limit": limit, "offset": offset}


def log(user: User, job: Job, total: int) -> None:
    """Ids and counts only -- never a candidate."""
    logger.info("requirement_matches", extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(job.id), "total": total}})

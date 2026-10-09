"""rec-012 (DEC-SCOPE-150, spec §3-§4): extract a stored resume's suggestions and apply the ones the recruiter ticks. The parsing is
services/resume_extract (pure); this module feeds it the Skills Master's terms, runs it off the event loop under a time limit, stores the
result on the resume row and shapes the response. Roles, the pool, the archived rule and the audit/log helpers are rec-009's
(services/candidates); adding a skill follows rec-011's rules (services/candidate_skills).

Functions only; nothing here commits -- the route owns the transaction. Logs and audit rows carry ids and counts, never resume text."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Candidate, CandidateResume, CandidateSkill, Skill, SkillAlias, SkillCategory, User
from app.schemas import ResumeApply
from app.services import candidate_skills, candidates
from app.services import resume_extract as rx
from app.services import skills as skills_master

TIMEOUT_SECONDS = 20  # EX8
TOO_LONG = "Reading this resume took too long. Try a shorter file, or add the details by hand."
NOT_EXTRACTED = "Extract this resume before saving its details"
NOTHING = "Choose at least one suggestion to save"
GONE = "is not in the Skills Master any more. Extract the resume again."


async def load_resume(db: AsyncSession, candidate: Candidate, version: int) -> CandidateResume:
    resume = await db.scalar(select(CandidateResume).where(CandidateResume.candidate_id == candidate.id, CandidateResume.version == version))
    if resume is None:
        raise HTTPException(404, "Resume version not found")
    return resume


async def extractable(db: AsyncSession, candidate_id: UUID) -> Candidate:
    """An archived candidate's resumes are read only (rec-009). Unlike Apply (candidate_skills.writable, which locks the row), Extract
    takes no lock, so a slow file never holds the candidate's lock."""
    candidate = await candidates.load(db, candidate_id)
    if candidate.archived_at is not None:
        raise HTTPException(409, candidates.ARCHIVED)
    return candidate


async def _terms(db: AsyncSession) -> list[tuple[str, UUID]]:
    """Every active skill's name and aliases, as (term, skill id)."""
    names = (await db.execute(select(Skill.name, Skill.id).where(Skill.active.is_(True)))).all()
    aliases = (await db.execute(select(SkillAlias.alias, Skill.id).join(Skill, Skill.id == SkillAlias.skill_id).where(Skill.active.is_(True)))).all()
    return [(term, skill_id) for term, skill_id in (*names, *aliases)]


async def extract(db: AsyncSession, resume: CandidateResume) -> None:
    """Read the stored file and suggest, in a thread under TIMEOUT_SECONDS (the thread itself is bounded by the page and size caps), then
    store the text and the suggestions on the resume. A file that cannot be read is a 422 with the extractor's sentence."""
    terms = await _terms(db)
    content_type = resume.content_type

    def work() -> tuple[str, bool, dict]:
        text, truncated = rx.read_text(candidates.read_file(resume), content_type)
        return text, truncated, rx.suggest(text, terms)

    try:
        text, truncated, found = await asyncio.wait_for(asyncio.to_thread(work), TIMEOUT_SECONDS)
    except rx.ExtractError as exc:
        raise HTTPException(422, str(exc)) from None
    except TimeoutError:
        raise HTTPException(422, TOO_LONG) from None
    resume.extracted_text = text
    resume.extraction_json = {**found, "skills": [{**s, "skill_id": str(s["skill_id"])} for s in found["skills"]], "truncated": truncated}
    resume.extracted_at = datetime.now(UTC)


async def extraction_out(db: AsyncSession, candidate: Candidate, resume: CandidateResume) -> dict:
    """The stored suggestions with each skill's current name and category. A skill merged away or deactivated since is left out (Apply
    would refuse it); `on_profile` is worked out now, so a skill added since shows as already on the profile."""
    stored = resume.extraction_json
    ids = [UUID(s["skill_id"]) for s in stored["skills"]]
    rows = {
        skill.id: (skill, category)
        for skill, category in (
            await db.execute(select(Skill, SkillCategory).join(SkillCategory, SkillCategory.id == Skill.category_id).where(Skill.id.in_(ids), Skill.active.is_(True)))
        ).all()
    } if ids else {}  # fmt: skip
    have = set((await db.scalars(select(CandidateSkill.skill_id).where(CandidateSkill.candidate_id == candidate.id))).all())
    skills = [
        {"skill": skills_master.ref(rows[i][0]), "category": {"id": rows[i][1].id, "name": rows[i][1].name}, "matched": s["matched"], "on_profile": i in have}
        for i, s in zip(ids, stored["skills"], strict=True)
        if i in rows
    ]
    return {
        "version": resume.version,
        "no_text": resume.extracted_text == "",
        "truncated": stored["truncated"],
        "text_chars": len(resume.extracted_text or ""),
        "extracted_at": resume.extracted_at,
        "skills": skills,
        **{key: stored[key] for key in ("qualification", "experience_months", "location", "job_titles", "certifications", "industries")},
    }


async def apply(db: AsyncSession, user: User, candidate: Candidate, resume: CandidateResume, body: ResumeApply) -> dict:
    """EX6/EX7, under the candidate's row lock: every ticked skill becomes a `resume` / `claimed` row with its level, through rec-011's
    rules (409 already there, 422 over the cap); the ticked fields are set. Any refusal raises before the commit, so nothing is kept."""
    if resume.extraction_json is None:
        raise HTTPException(409, NOT_EXTRACTED)
    fields = body.model_dump(exclude_unset=True, exclude={"skills"})
    if not body.skills and not fields:
        raise HTTPException(422, NOTHING)
    ids = [p.skill_id for p in body.skills]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Each skill can be chosen once")
    # FOR SHARE: a concurrent merge or deactivation of these skills waits for this commit (rec-011 skill_for_add).
    found = {s.id: s for s in (await db.scalars(select(Skill).where(Skill.id.in_(ids)).with_for_update(read=True))).all()} if ids else {}
    for pick in body.skills:
        skill = found.get(pick.skill_id)
        if skill is None or not skill.active:
            raise HTTPException(422, f"{skill.name if skill else 'This skill'} {GONE}")
    added = []
    for pick in body.skills:
        skill = found[pick.skill_id]
        await candidate_skills.check_free(db, candidate, skill)
        row = CandidateSkill(candidate_id=candidate.id, skill_id=skill.id, level=pick.level, source="resume", added_by_user_id=user.id)
        db.add(row)
        await candidate_skills.flush_new(db, skill)
        candidate_skills.audit(db, user, "add", candidate, row)
        added.append(row)
    changed = candidates.apply_fields(candidate, fields)
    if added or changed:
        candidate.updated_by_user_id = user.id
    candidates.audit(db, user, "resume_apply", candidate, {"version": resume.version, "skill_ids": [str(r.skill_id) for r in added], "fields": changed})
    return {"skills_added": len(added), "fields": changed}

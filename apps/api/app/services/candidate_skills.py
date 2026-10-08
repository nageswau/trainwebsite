"""rec-011 (DEC-SCOPE-137, spec §3-§4): a candidate's skills -- the rules and output shapes. Roles, the pool, the archived rule and the
audit/log helpers are rec-009's (services/candidates); the skill text resolves through the Skills Master (services/skills.resolve).

Functions only; nothing here commits -- the route owns the transaction. Logs and audit rows carry ids, never a name."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Candidate, CandidateSkill, Skill, SkillCategory, User
from app.services import candidates
from app.services import skills as skills_master

MAX_SKILLS = 100  # SK6
UNIQUE_INDEX = "uq_candidate_skills_skill"
NOT_FOUND = "Skill not found on this candidate"
STATUS_RANK = {"claimed": 0, "verified": 1, "assessed": 2}  # the stronger evidence wins a merge clash (SK7)


async def writable(db: AsyncSession, candidate_id: UUID) -> Candidate:
    """The candidate row locked FOR UPDATE: every write on its skills is serialised, and an archived candidate is read-only."""
    candidate = await candidates.load(db, candidate_id, lock=True)
    if candidate.archived_at is not None:
        raise HTTPException(409, candidates.ARCHIVED)
    return candidate


async def skill_for_add(db: AsyncSession, text: str) -> Skill:
    """SK5: the active skill the text names (a name or an alias), re-read FOR SHARE so a concurrent merge or deactivation of it waits
    for this commit -- or, if it won, this add sees the skill gone or inactive and answers the same 422."""
    found = await skills_master.resolve(db, text)
    skill = await db.scalar(select(Skill).where(Skill.id == found.id).with_for_update(read=True)) if found else None
    if skill is None or not skill.active:
        raise HTTPException(422, f"“{skills_master.normalise(text)}” is not in the Skills Master. Pick a listed skill, or ask your manager to add it or an alias.")
    return skill


async def check_free(db: AsyncSession, candidate: Candidate, skill: Skill) -> None:
    if await db.scalar(select(CandidateSkill.id).where(CandidateSkill.candidate_id == candidate.id, CandidateSkill.skill_id == skill.id)):
        raise HTTPException(409, f"{skill.name} is already on this candidate's skills")
    count = await db.scalar(select(func.count()).select_from(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id))
    if count >= MAX_SKILLS:
        raise HTTPException(422, f"A candidate can have at most {MAX_SKILLS} skills")


async def flush_new(db: AsyncSession, skill: Skill) -> None:
    """Two adds of one skill at once: the unique pair decides, the transaction rolls back and the loser gets the same 409."""
    name = skill.name
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if UNIQUE_INDEX in str(exc.orig):
            raise HTTPException(409, f"{name} is already on this candidate's skills") from None
        raise


async def load_item(db: AsyncSession, candidate: Candidate, item_id: UUID) -> CandidateSkill:
    """A row of this candidate only: another candidate's skill id is a 404, never a cross-candidate write."""
    row = await db.scalar(select(CandidateSkill).where(CandidateSkill.id == item_id, CandidateSkill.candidate_id == candidate.id))
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row


def apply_fields(row: CandidateSkill, values: dict) -> list[str]:
    changed = [key for key, value in values.items() if getattr(row, key) != value]
    for key in changed:
        setattr(row, key, values[key])
    return sorted(changed)


def set_status(row: CandidateSkill, user: User, status: str) -> str:
    """AC3: verified or assessed records who and when; claimed clears both (the audit row keeps the history). Returns the old status."""
    if row.status == status:
        raise HTTPException(409, f"This skill is already {status}")
    old = row.status
    row.status = status
    row.verified_by_user_id, row.verified_at = (None, None) if status == "claimed" else (user.id, datetime.now(UTC))
    row.updated_by_user_id = user.id
    return old


def audit(db: AsyncSession, user: User, action: str, candidate: Candidate, row: CandidateSkill, **metadata) -> None:
    candidates.audit(db, user, f"skill_{action}", candidate, {"candidate_skill_id": str(row.id), "skill_id": str(row.skill_id), **metadata})


def log(event: str, user: User, candidate: Candidate, row: CandidateSkill, **extra) -> None:
    candidates.log(event, user, candidate, candidate_skill_id=str(row.id), skill_id=str(row.skill_id), **extra)


async def repoint(db: AsyncSession, source_id: UUID, target_id: UUID) -> tuple[int, int]:
    """SK7 merge: every candidate row on the source skill moves to the target. A candidate who has both keeps the stronger status
    (the target's row on a tie); the other row is deleted first, so the unique pair is never hit. Returns (moved, dropped)."""
    moving = (await db.scalars(select(CandidateSkill).where(CandidateSkill.skill_id == source_id).with_for_update())).all()
    targets = (
        {
            r.candidate_id: r
            for r in (await db.scalars(select(CandidateSkill).where(CandidateSkill.skill_id == target_id, CandidateSkill.candidate_id.in_([m.candidate_id for m in moving])).with_for_update())).all()
        }
        if moving
        else {}
    )
    kept, dropped = [], 0
    for row in moving:
        clash = targets.get(row.candidate_id)
        wins = clash is None or STATUS_RANK[row.status] > STATUS_RANK[clash.status]
        if clash is not None:
            await db.delete(clash if wins else row)
            dropped += 1
        if wins:
            kept.append(row)
    await db.flush()
    for row in kept:
        row.skill_id = target_id
    await db.flush()
    return len(kept), dropped


def _person(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name} if user else None


async def items_out(db: AsyncSession, candidate_id: UUID, only: UUID | None = None) -> list[dict]:
    """The candidate's skills (or the one row `only`) with skill, category, adder and verifier in one query, ordered by skill name."""
    adder, verifier = aliased(User), aliased(User)
    stmt = (
        select(CandidateSkill, Skill, SkillCategory, adder, verifier)
        .join(Skill, Skill.id == CandidateSkill.skill_id)
        .join(SkillCategory, SkillCategory.id == Skill.category_id)
        .outerjoin(adder, adder.id == CandidateSkill.added_by_user_id)
        .outerjoin(verifier, verifier.id == CandidateSkill.verified_by_user_id)
        .where(CandidateSkill.candidate_id == candidate_id)
        .order_by(func.lower(Skill.name), CandidateSkill.id)
        .execution_options(populate_existing=True)
    )
    if only is not None:
        stmt = stmt.where(CandidateSkill.id == only)
    return [
        {
            "id": row.id,
            "skill": skills_master.ref(skill),
            "category": {"id": category.id, "name": category.name},
            "level": row.level,
            "experience_months": row.experience_months,
            "last_used_year": row.last_used_year,
            "source": row.source,
            "status": row.status,
            "verified_by": _person(verified_by),
            "verified_at": row.verified_at,
            "added_by": _person(added_by),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row, skill, category, added_by, verified_by in (await db.execute(stmt)).all()
    ]


async def item_out(db: AsyncSession, candidate_id: UUID, item_id: UUID) -> dict:
    return (await items_out(db, candidate_id, only=item_id))[0]

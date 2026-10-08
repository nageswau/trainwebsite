"""rec-006 (DEC-SCOPE-118, spec §3): the Skills Master rules and `resolve`, the single normaliser rec-007/011/012/013 call.

Functions only; nothing here commits -- the route owns the transaction. A skill name and an alias share one case-insensitive term space:
each table's unique index decides duplicates within it, and every write that sets a name or an alias first takes one advisory lock and
checks the other table, so the cross-table rule holds under concurrency too."""

import re

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Skill, SkillAlias, SkillCategory, SkillCategoryTag, SkillRelated, User

READERS = frozenset({"placement_team", "placement_manager", "super_admin"})  # S3: hr_team / it_admin are not readers (Q-28)
WRITERS = frozenset({"placement_manager", "super_admin"})
TERM_LOCK = 290_118  # pg_advisory_xact_lock key serialising skill-name and alias writes (a fixed constant, bound as a parameter)
SKILL_NAME_INDEX, ALIAS_INDEX, CATEGORY_NAME_INDEX = "uq_skills_name", "uq_skill_aliases_alias", "uq_skill_categories_name"
_WHITESPACE = re.compile(r"\s+")


def normalise(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


async def resolve(db: AsyncSession, value: str) -> Skill | None:
    """The active skill whose name -- or else one of whose aliases -- equals `value`, ignoring case and spacing."""
    term = normalise(value).lower()
    if not term:
        return None
    by_name = await db.scalar(select(Skill).where(func.lower(Skill.name) == term, Skill.active.is_(True)))
    if by_name:
        return by_name
    return await db.scalar(
        select(Skill).join(SkillAlias, SkillAlias.skill_id == Skill.id).where(func.lower(SkillAlias.alias) == term, Skill.active.is_(True))
    )


def require_reader(user: User) -> None:
    if user.role not in READERS:
        raise HTTPException(403, "Your role cannot view the Skills Master")


def require_writer(user: User) -> None:
    if user.role not in WRITERS:
        raise HTTPException(403, "Placement manager role required")


def sees_inactive(user: User) -> bool:
    return user.role in WRITERS


async def lock_terms(db: AsyncSession) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": TERM_LOCK})


async def check_name_free(db: AsyncSession, name: str) -> None:
    """Under `lock_terms`: a skill name may not equal any alias (spec §2). Another skill's name is the unique index's job."""
    if await db.scalar(select(SkillAlias.id).where(func.lower(SkillAlias.alias) == name.lower())):
        raise HTTPException(409, f"“{name}” is already an alias — remove the alias first")


async def check_alias_free(db: AsyncSession, alias: str, skill: Skill) -> None:
    """Under `lock_terms`: an alias may not repeat its own skill's name (422) or equal another skill's name (409, AC3)."""
    if alias.lower() == skill.name.lower():
        raise HTTPException(422, "An alias cannot repeat the skill's name")
    if await db.scalar(select(Skill.id).where(func.lower(Skill.name) == alias.lower())):
        raise HTTPException(409, f"“{alias}” is already a skill name")


async def locked_active_categories(db: AsyncSession, ids) -> dict:
    """FOR SHARE: a concurrent deactivation of these categories waits for this write's commit (the tel-002 P4 idiom)."""
    rows = (await db.scalars(select(SkillCategory).where(SkillCategory.id.in_(list(ids))).with_for_update(read=True))).all()
    if len(rows) != len(set(ids)) or not all(c.active for c in rows):
        raise HTTPException(422, "Choose an active category")
    return {c.id: c for c in rows}


def ref(row, name: str | None = None) -> dict:
    return {"id": row.id, "name": name or row.name, "active": row.active}


async def skills_out(db: AsyncSession, skills: list[Skill], *, active_only: bool) -> list[dict]:
    """The page's skills with category, tags, aliases and related skills -- four batched queries, never one per row."""
    if not skills:
        return []
    ids = [s.id for s in skills]
    categories = {c.id: c for c in (await db.scalars(select(SkillCategory).where(SkillCategory.id.in_({s.category_id for s in skills})))).all()}
    tags: dict = {i: [] for i in ids}
    for skill_id, category in (await db.execute(
        select(SkillCategoryTag.skill_id, SkillCategory).join(SkillCategory, SkillCategory.id == SkillCategoryTag.category_id)
        .where(SkillCategoryTag.skill_id.in_(ids)).order_by(SkillCategory.sort_order, func.lower(SkillCategory.name))
    )).all():
        tags[skill_id].append(ref(category))
    aliases: dict = {i: [] for i in ids}
    for alias in (await db.scalars(select(SkillAlias).where(SkillAlias.skill_id.in_(ids)).order_by(func.lower(SkillAlias.alias)))).all():
        aliases[alias.skill_id].append({"id": alias.id, "alias": alias.alias})
    related: dict = {i: [] for i in ids}
    pairs = (await db.execute(select(SkillRelated).where(or_(SkillRelated.skill_a_id.in_(ids), SkillRelated.skill_b_id.in_(ids))))).scalars().all()
    linked = {p.skill_a_id for p in pairs} | {p.skill_b_id for p in pairs}
    names = {s.id: s for s in (await db.scalars(select(Skill).where(Skill.id.in_(linked)))).all()} if linked else {}
    for pair in pairs:
        for mine, other in ((pair.skill_a_id, pair.skill_b_id), (pair.skill_b_id, pair.skill_a_id)):
            if mine in related and (not active_only or names[other].active):
                related[mine].append(ref(names[other]))
    for items in related.values():
        items.sort(key=lambda r: r["name"].lower())
    return [
        {"id": s.id, "name": s.name, "active": s.active, "category": ref(categories[s.category_id]), "tags": tags[s.id], "aliases": aliases[s.id], "related": related[s.id]}
        for s in skills
    ]

"""rec-006 -- services/skills.py: `normalise` and `resolve`, the single normaliser rec-007/011/012/013 call (spec §3; AC2, AC6)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Skill, SkillAlias, SkillCategory
from app.services.skills import normalise, resolve


def test_normalise_trims_and_collapses_inner_whitespace():
    assert normalise("  React \t  JS \n") == "React JS"
    assert normalise("Java") == "Java"


async def _skill(db, name: str, *, active: bool = True, aliases: tuple[str, ...] = ()) -> Skill:
    category = await db.scalar(select(SkillCategory).order_by(SkillCategory.sort_order).limit(1))
    skill = Skill(name=name, category_id=category.id, active=active)
    db.add(skill)
    await db.flush()
    db.add_all(SkillAlias(skill_id=skill.id, alias=a) for a in aliases)
    await db.commit()
    return skill


@pytest.mark.asyncio
async def test_seeded_aliases_resolve_to_their_skill_ignoring_case_and_spacing(db_session):
    """AC2 against the 0102 seed."""
    java = await resolve(db_session, "Java")
    assert java is not None and java.name == "Java"
    assert (await resolve(db_session, "j2ee")).id == java.id
    assert (await resolve(db_session, "  java   21 ")).id == java.id
    assert (await resolve(db_session, "reactjs")).name == "React"


@pytest.mark.asyncio
async def test_unknown_text_and_blank_resolve_to_nothing(db_session):
    assert await resolve(db_session, f"Nope {uuid.uuid4().hex[:6]}") is None
    assert await resolve(db_session, "   ") is None


@pytest.mark.asyncio
async def test_an_inactive_skill_resolves_to_nothing_by_name_or_alias(db_session):
    """AC6: deactivating takes a skill out of resolve()."""
    tag = uuid.uuid4().hex[:6]
    await _skill(db_session, f"Gone {tag}", active=False, aliases=(f"Gone alias {tag}",))
    assert await resolve(db_session, f"gone {tag}") is None
    assert await resolve(db_session, f"gone alias {tag}") is None

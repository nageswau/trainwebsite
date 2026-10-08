"""rec-006 (DEC-SCOPE-118, spec §4): the recruiter Skills Master -- categories, skills, aliases and related skills. Placement managers
and super_admin write; recruiters read active rows (S2, S3). The catalogue is global, so there is no row scope -- only the role checks.

Bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-001 idiom). Each
write has one commit and one audit row; skills and categories are deactivated, never deleted (no DELETE route -> 405)."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import AuditLog, Skill, SkillAlias, SkillCategory, SkillCategoryTag, SkillRelated, User
from app.schemas import (
    SKILL_FIELD_LABELS,
    SkillAliasCreate,
    SkillCategoryCreate,
    SkillCategoryOut,
    SkillCategoryPage,
    SkillCategoryUpdate,
    SkillCreate,
    SkillOut,
    SkillPage,
    SkillRelatedCreate,
    SkillUpdate,
)
from app.services.skills import (
    ALIAS_INDEX,
    CATEGORY_NAME_INDEX,
    SKILL_NAME_INDEX,
    active_filters,
    check_alias_free,
    check_name_free,
    lock_terms,
    locked_active_categories,
    require_reader,
    require_writer,
    sees_inactive,
    skills_out,
)
from app.services.telecaller import _parse
from app.services.telecaller_catalogue import apply_changes, flush_unique

router = APIRouter(prefix="/recruiter", tags=["recruiter-skills"])
RELATED_PK = "skill_related_pkey"


def _body(model, payload):
    return _parse(model, payload, "The request body must be an object", SKILL_FIELD_LABELS)


def _audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata))


def _category_out(category: SkillCategory) -> dict:
    return {"id": category.id, "name": category.name, "active": category.active, "sort_order": category.sort_order}


async def _locked(db: AsyncSession, model, row_id: UUID, noun: str):
    row = await db.scalar(select(model).where(model.id == row_id).with_for_update())
    if not row:
        raise HTTPException(404, f"{noun} not found")
    return row


async def _one_out(db: AsyncSession, skill: Skill, user: User) -> dict:
    return (await skills_out(db, [skill], active_only=not sees_inactive(user)))[0]


# --- categories -----------------------------------------------------------------------------------------------------------------
@router.get("/skill-categories", response_model=SkillCategoryPage)
async def categories(
    active: bool | None = None, q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """The §2 order for the seed (sort order), then name."""
    require_reader(user)
    stmt = select(SkillCategory).where(*active_filters(user, SkillCategory.active, active), *_matching(like_pattern(q), SkillCategory.name))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.scalars(stmt.order_by(SkillCategory.sort_order, func.lower(SkillCategory.name), SkillCategory.id).limit(limit).offset(offset))).all()
    return {"items": [_category_out(c) for c in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("/skill-categories", response_model=SkillCategoryOut, status_code=201)
async def create_category(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    data = _body(SkillCategoryCreate, payload)
    last = await db.scalar(select(func.max(SkillCategory.sort_order)))
    category = SkillCategory(name=data.name, sort_order=(last or 0) + 1, active=True)
    db.add(category)
    await flush_unique(db, CATEGORY_NAME_INDEX, f"A category named “{data.name}” already exists")
    _audit(db, user, "recruiter.skill_category_create", "skill_category", category.id, {"fields": ["name", "sort_order"]})
    out = _category_out(category)
    await db.commit()
    return out


@router.patch("/skill-categories/{category_id}", response_model=SkillCategoryOut)
async def update_category(category_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A rename keeps the id; deactivating hides the category from new picks while skills keep it."""
    require_writer(user)
    category = await _locked(db, SkillCategory, category_id, "Category")
    fields = apply_changes(category, _body(SkillCategoryUpdate, payload).model_dump(exclude_unset=True))
    await flush_unique(db, CATEGORY_NAME_INDEX, f"A category named “{category.name}” already exists")
    if fields:
        _audit(db, user, "recruiter.skill_category_update", "skill_category", category.id, {"fields": fields})
    out = _category_out(category)
    await db.commit()
    return out


# --- skills -----------------------------------------------------------------------------------------------------------------------
@router.get("/skills", response_model=SkillPage)
async def skills(
    q: str | None = SEARCH, category_id: UUID | None = None, active: bool | None = None, limit: int = LIMIT, offset: int = OFFSET,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """`q` matches a name or an alias (EXISTS, so a skill with several matching aliases is listed once); `category_id` matches the
    primary category or a tag. Ordered by name."""
    require_reader(user)
    filters = active_filters(user, Skill.active, active)
    pattern = like_pattern(q)
    if pattern:
        alias_hit = exists().where(SkillAlias.skill_id == Skill.id, SkillAlias.alias.ilike(pattern, escape="\\"))
        filters.append(or_(Skill.name.ilike(pattern, escape="\\"), alias_hit))
    if category_id:
        tagged = exists().where(SkillCategoryTag.skill_id == Skill.id, SkillCategoryTag.category_id == category_id)
        filters.append(or_(Skill.category_id == category_id, tagged))
    stmt = select(Skill).where(*filters)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.scalars(stmt.order_by(func.lower(Skill.name), Skill.id).limit(limit).offset(offset))).all()
    return {"items": await skills_out(db, list(rows), active_only=not sees_inactive(user)), "total": total or 0, "limit": limit, "offset": offset}


@router.get("/skills/{skill_id}", response_model=SkillOut)
async def skill(skill_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """An inactive skill is a 404 for a reader, like an unknown one."""
    require_reader(user)
    row = await db.get(Skill, skill_id)
    if not row or not (row.active or sees_inactive(user)):
        raise HTTPException(404, "Skill not found")
    return await _one_out(db, row, user)


async def _current_tags(db: AsyncSession, skill_id: UUID) -> set[UUID]:
    return set((await db.scalars(select(SkillCategoryTag.category_id).where(SkillCategoryTag.skill_id == skill_id))).all())


def _check_tags(primary: UUID, tags: set[UUID]) -> None:
    if primary in tags:
        raise HTTPException(422, "A skill's own category cannot also be a tag")


@router.post("/skills", response_model=SkillOut, status_code=201)
async def create_skill(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    data = _body(SkillCreate, payload)
    tags = set(data.tag_category_ids)
    _check_tags(data.category_id, tags)
    await locked_active_categories(db, {data.category_id} | tags)
    await lock_terms(db)
    await check_name_free(db, data.name)
    last = await db.scalar(select(func.max(Skill.sort_order)).where(Skill.category_id == data.category_id))
    row = Skill(name=data.name, category_id=data.category_id, sort_order=(last or 0) + 1, active=True)
    db.add(row)
    await flush_unique(db, SKILL_NAME_INDEX, f"A skill named “{data.name}” already exists")
    db.add_all(SkillCategoryTag(skill_id=row.id, category_id=c) for c in tags)
    _audit(db, user, "recruiter.skill_create", "skill", row.id, {"fields": ["name", "category_id", "tag_category_ids"]})
    await db.flush()
    out = await _one_out(db, row, user)
    await db.commit()
    return out


@router.patch("/skills/{skill_id}", response_model=SkillOut)
async def update_skill(skill_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A rename keeps the id (AC6). A new category -- primary or tag -- must be active; keeping a since-deactivated one is allowed.
    `tag_category_ids` replaces the set."""
    require_writer(user)
    row = await _locked(db, Skill, skill_id, "Skill")
    changes = _body(SkillUpdate, payload).model_dump(exclude_unset=True)
    current_tags = await _current_tags(db, row.id)
    new_tags = set(changes.pop("tag_category_ids")) if "tag_category_ids" in changes else current_tags
    _check_tags(changes.get("category_id", row.category_id), new_tags)
    added = new_tags - current_tags
    if changes.get("category_id", row.category_id) != row.category_id:
        added |= {changes["category_id"]}
    if added:
        await locked_active_categories(db, added)
    if changes.get("name") and changes["name"].lower() != row.name.lower():
        await lock_terms(db)
        await check_name_free(db, changes["name"])
    fields = apply_changes(row, changes)
    await flush_unique(db, SKILL_NAME_INDEX, f"A skill named “{row.name}” already exists")
    if new_tags != current_tags:
        await db.execute(delete(SkillCategoryTag).where(SkillCategoryTag.skill_id == row.id, SkillCategoryTag.category_id.not_in(new_tags)))
        db.add_all(SkillCategoryTag(skill_id=row.id, category_id=c) for c in new_tags - current_tags)
        fields = sorted([*fields, "tag_category_ids"])
    if fields:
        _audit(db, user, "recruiter.skill_update", "skill", row.id, {"fields": fields})
    await db.flush()
    out = await _one_out(db, row, user)
    await db.commit()
    return out


# --- aliases ------------------------------------------------------------------------------------------------------------------------
@router.post("/skills/{skill_id}/aliases", response_model=SkillOut, status_code=201)
async def add_alias(skill_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC3: unique across every alias and every skill name, ignoring case; the unique index is the final arbiter under a race."""
    require_writer(user)
    row = await _locked(db, Skill, skill_id, "Skill")
    alias = _body(SkillAliasCreate, payload).alias
    await lock_terms(db)
    await check_alias_free(db, alias, row)
    db.add(SkillAlias(skill_id=row.id, alias=alias))
    await flush_unique(db, ALIAS_INDEX, f"“{alias}” is already an alias")
    _audit(db, user, "recruiter.skill_alias_add", "skill", row.id, {"alias": alias})
    out = await _one_out(db, row, user)
    await db.commit()
    return out


@router.delete("/skills/{skill_id}/aliases/{alias_id}", status_code=204)
async def remove_alias(skill_id: UUID, alias_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    alias = await db.scalar(select(SkillAlias).where(SkillAlias.id == alias_id, SkillAlias.skill_id == skill_id).with_for_update())
    if not alias:
        raise HTTPException(404, "Alias not found")
    await db.delete(alias)
    _audit(db, user, "recruiter.skill_alias_remove", "skill", skill_id, {"alias": alias.alias})
    await db.commit()
    return Response(status_code=204)


# --- related skills -------------------------------------------------------------------------------------------------------------
def _pair(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    return (a, b) if a < b else (b, a)


@router.post("/skills/{skill_id}/related", response_model=SkillOut, status_code=201)
async def add_related(skill_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """S4: one row per unordered pair, read both ways. The other skill must be active (FOR SHARE, so it is not deactivated mid-write)."""
    require_writer(user)
    row = await _locked(db, Skill, skill_id, "Skill")
    other_id = _body(SkillRelatedCreate, payload).skill_id
    if other_id == row.id:
        raise HTTPException(422, "A skill cannot be related to itself")
    other = await db.scalar(select(Skill).where(Skill.id == other_id).with_for_update(read=True))
    if not other or not other.active:
        raise HTTPException(422, "Choose an active skill")
    a, b = _pair(row.id, other.id)
    db.add(SkillRelated(skill_a_id=a, skill_b_id=b))
    await flush_unique(db, RELATED_PK, "These skills are already related")
    _audit(db, user, "recruiter.skill_related_add", "skill", row.id, {"related_skill_id": str(other.id)})
    out = await _one_out(db, row, user)
    await db.commit()
    return out


@router.delete("/skills/{skill_id}/related/{other_id}", status_code=204)
async def remove_related(skill_id: UUID, other_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    a, b = _pair(skill_id, other_id)
    link = await db.scalar(select(SkillRelated).where(SkillRelated.skill_a_id == a, SkillRelated.skill_b_id == b).with_for_update())
    if not link:
        raise HTTPException(404, "These skills are not related")
    await db.delete(link)
    _audit(db, user, "recruiter.skill_related_remove", "skill", skill_id, {"related_skill_id": str(other_id)})
    await db.commit()
    return Response(status_code=204)

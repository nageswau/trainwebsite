"""rec-015 (DEC-SCOPE-159, spec §1/§4): talent pools. A pool's rule is a saved rec-013 expression plus an experience band; its members are
computed on read through services/candidate_search, so a candidate joins or leaves the moment their skills change (P1, AC1).

Functions only; nothing here commits -- the route owns the transaction. Logs and audit rows carry ids, counts and field names only."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Candidate, TalentPool, User
from app.schemas import CandidateSearch
from app.services import candidate_search
from app.services.candidates import READERS
from app.services.recruiter import MANAGER_ROLE

logger = logging.getLogger("app.talent_pools")

WRITERS = frozenset({MANAGER_ROLE, "super_admin"})  # P6: division-global, like the pool itself (R11)
NOT_FOUND = "Talent pool not found"
DUPLICATE = "A talent pool with this name already exists"
NAME_INDEX = "uq_talent_pools_name"


def require_reader(user: User) -> None:
    if user.role not in READERS:
        raise HTTPException(403, "Your role cannot view talent pools")


def require_writer(user: User) -> None:
    if user.role not in WRITERS:
        raise HTTPException(403, "Only a placement manager can change talent pools")


def can_manage(user: User) -> bool:
    return user.role in WRITERS


async def load(db: AsyncSession, user: User, pool_id: UUID, *, lock: bool = False) -> TalentPool:
    """An inactive pool exists only for its writers; for a reader it is the same 404 as an unknown id."""
    stmt = select(TalentPool).where(TalentPool.id == pool_id)
    pool = await db.scalar(stmt.with_for_update() if lock else stmt)
    if pool is None or (not pool.active and not can_manage(user)):
        raise HTTPException(404, NOT_FOUND)
    return pool


def _search(all_terms: list, any_groups: list, low: int | None = None, high: int | None = None) -> CandidateSearch:
    """A rule as a search body. Built without validation: the rule was checked when it was saved, and CandidateSearch alone would refuse
    an experience-only rule (it requires a skill or resume text)."""
    return CandidateSearch.model_construct(all=list(all_terms), any=[list(g) for g in any_groups], experience_min_months=low, experience_max_months=high)


def rule(pool: TalentPool) -> CandidateSearch:
    return _search(pool.all_terms, pool.any_terms, pool.experience_min_months, pool.experience_max_months)


async def canonical(db: AsyncSession, all_terms: list[str], any_groups: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """P4: every term must be an active skill or alias now (rec-013's 422 with suggestions otherwise); the skill's name is stored, each
    list without repeats (an alias and its skill are one skill)."""
    terms = await candidate_search.resolve_terms(db, _search(all_terms, any_groups))

    def names(values: list[str]) -> list[str]:
        return list(dict.fromkeys(terms[v.lower()]["skill"]["name"] for v in values))

    return names(all_terms), [names(group) for group in any_groups]


async def resolve(db: AsyncSession, pools: list[TalentPool]) -> dict[str, dict]:
    """All the pools' terms in one resolution (two queries); a term that is no longer an active skill resolves to nobody (P5)."""
    return await candidate_search.resolve_terms(db, _search([t for p in pools for t in p.all_terms], [g for p in pools for g in p.any_terms]), strict=False)


def unavailable(pool: TalentPool, terms: dict[str, dict]) -> list[str]:
    every = [*pool.all_terms, *(t for group in pool.any_terms for t in group)]
    return list(dict.fromkeys(t for t in every if terms[t.lower()]["skill"] is None))


async def counts(db: AsyncSession, pools: list[TalentPool], terms: dict[str, dict]) -> dict[UUID, int]:
    """P8: every pool's member count in one pass over the candidates -- one FILTERed count per pool."""
    if not pools:
        return {}
    columns = [func.count().filter(and_(*candidate_search.filters(rule(p), terms))) for p in pools]
    row = (await db.execute(select(*columns).select_from(Candidate))).one()
    return {p.id: row[i] for i, p in enumerate(pools)}


async def members(db: AsyncSession, pool: TalentPool, terms: dict[str, dict], *, limit: int, offset: int) -> tuple[int, list[dict]]:
    """The pool's members as rec-013 cards, newest first (P8)."""
    where = candidate_search.filters(rule(pool), terms)
    total = await db.scalar(select(func.count()).select_from(Candidate).where(*where))
    return total or 0, await candidate_search.page(db, where, terms, limit, offset)


async def creators(db: AsyncSession, pools: list[TalentPool]) -> dict[UUID, dict]:
    ids = {p.created_by_user_id for p in pools if p.created_by_user_id}
    if not ids:
        return {}
    return {u.id: {"id": u.id, "name": u.full_name} for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()}


def out(pool: TalentPool, count: int, terms: dict[str, dict], people: dict[UUID, dict]) -> dict:
    return {
        "id": pool.id, "name": pool.name, "all": pool.all_terms, "any": pool.any_terms, "experience_min_months": pool.experience_min_months,
        "experience_max_months": pool.experience_max_months, "active": pool.active, "members": count, "unavailable": unavailable(pool, terms),
        "created_by": people.get(pool.created_by_user_id), "updated_at": pool.updated_at,
    }


async def pool_out(db: AsyncSession, pool: TalentPool) -> dict:
    terms = await resolve(db, [pool])
    return out(pool, (await counts(db, [pool], terms))[pool.id], terms, await creators(db, [pool]))


def audit(db: AsyncSession, user: User, action: str, pool: TalentPool, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=f"talent_pool.{action}", entity_type="talent_pools", entity_id=str(pool.id), metadata_json=metadata))


def log(event: str, user: User, pool: TalentPool, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "pool_id": str(pool.id), **extra}})

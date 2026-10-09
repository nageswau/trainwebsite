"""rec-015 (DEC-SCOPE-158, spec §3): talent pools. Candidate readers (rec-009) read the active pools and their members; placement
managers and super_admin create and change any pool (P6). The role check runs before anything is read.

Bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-002 idiom). Each write
is one transaction: role, row lock, rules, change, audit row, one commit here, then the log line. The unique index settles a duplicate
name, even under a race (409)."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.telecaller_catalogue import NOT_AN_OBJECT
from app.core.database import get_db
from app.models import TalentPool, User
from app.schemas import TALENT_POOL_LABELS, TalentPoolCreate, TalentPoolUpdate, check_pool_rule
from app.services import talent_pools as svc
from app.services.telecaller import _parse
from app.services.telecaller_catalogue import apply_changes, flush_unique

router = APIRouter(prefix="/recruiter/pools", tags=["recruiter-pools"])


@router.get("")
async def list_pools(include_inactive: bool = False, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """By name, each with its member count (one query for all pools) and its unavailable terms. `include_inactive` is a writer's."""
    svc.require_reader(user)
    stmt = select(TalentPool).order_by(func.lower(TalentPool.name))
    if not (include_inactive and svc.can_manage(user)):
        stmt = stmt.where(TalentPool.active.is_(True))
    pools = list((await db.scalars(stmt)).all())
    terms = await svc.resolve(db, pools)
    counts = await svc.counts(db, pools, terms)
    people = await svc.creators(db, pools)
    return {"items": [svc.out(p, counts[p.id], terms, people) for p in pools], "can_manage": svc.can_manage(user)}


@router.post("", status_code=201)
async def create_pool(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_writer(user)
    body = _parse(TalentPoolCreate, payload, NOT_AN_OBJECT, TALENT_POOL_LABELS)
    all_terms, any_terms = await svc.canonical(db, body.all, body.any)
    pool = TalentPool(
        name=body.name, all_terms=all_terms, any_terms=any_terms, experience_min_months=body.experience_min_months,
        experience_max_months=body.experience_max_months, active=body.active, created_by_user_id=user.id, updated_by_user_id=user.id,
    )
    db.add(pool)
    await flush_unique(db, svc.NAME_INDEX, svc.DUPLICATE)
    svc.audit(db, user, "create", pool, {"terms": len(all_terms) + sum(len(g) for g in any_terms), "groups": len(any_terms)})
    await db.commit()
    await db.refresh(pool)
    svc.log("talent_pool_created", user, pool)
    return await svc.pool_out(db, pool)


@router.patch("/{pool_id}")
async def update_pool(pool_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Partial; the merged rule is checked again (a pool keeps at least one skill or an experience bound)."""
    svc.require_writer(user)
    changes = _parse(TalentPoolUpdate, payload, NOT_AN_OBJECT, TALENT_POOL_LABELS).model_dump(exclude_unset=True)
    pool = await svc.load(db, user, pool_id, lock=True)
    all_terms, any_terms = changes.pop("all", pool.all_terms), changes.pop("any", pool.any_terms)
    low = changes.pop("experience_min_months", pool.experience_min_months)
    high = changes.pop("experience_max_months", pool.experience_max_months)
    try:
        check_pool_rule(all_terms, any_terms, low, high)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    all_terms, any_terms = await svc.canonical(db, all_terms, any_terms)
    changes |= {"all_terms": all_terms, "any_terms": any_terms, "experience_min_months": low, "experience_max_months": high}
    fields = apply_changes(pool, changes)
    if fields:
        pool.updated_by_user_id = user.id
        await flush_unique(db, svc.NAME_INDEX, svc.DUPLICATE)
        svc.audit(db, user, "update", pool, {"fields": fields})
    await db.commit()
    await db.refresh(pool)
    if fields:
        svc.log("talent_pool_updated", user, pool, fields=fields)
    return await svc.pool_out(db, pool)


@router.get("/{pool_id}/candidates")
async def pool_candidates(pool_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """P8: the members, newest first, as rec-013 cards (no phone or email), with the pool itself and its resolved terms."""
    svc.require_reader(user)
    pool = await svc.load(db, user, pool_id)
    terms = await svc.resolve(db, [pool])
    total, items = await svc.members(db, pool, terms, limit=limit, offset=offset)
    people = await svc.creators(db, [pool])
    return {
        "pool": svc.out(pool, total, terms, people),
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "terms": [{"term": t["term"], "skill": t["skill"], "also": t["also"]} for t in terms.values()],
        "can_manage": svc.can_manage(user),
    }

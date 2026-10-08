"""rec-005 (DEC-SCOPE-123, spec §4): the company B2B pipeline -- the only writer of `companies.stage`.

Requirement-side items call `apply_event`; people call `person_move`, `mark_lost` and `reopen`. All work on a row the caller locked
(`recruiter_companies.load_scoped(lock=True)`), so concurrent changes serialise. Functions only; nothing here commits -- the route owns
the transaction. Logs carry ids, stage keys and the event, never the reason text."""

import logging

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Company, CompanyStageHistory, User
from app.recruiter_stages import DRIVEN, EVENTS, KINDS, ORDER, STAGES, START, label
from app.services.recruiter import MANAGER_ROLE
from app.services.recruiter_companies import _allowed, person

logger = logging.getLogger("app.recruiter")

STAGE_UNKNOWN = "Choose a stage of the company pipeline"
STAGE_START = "New Lead is the starting stage"
STAGE_DRIVEN = "This stage moves with the company's requirements"
STAGE_PAST = "This company's stage now moves with its requirements"
STAGE_SAME = "The company is already at this stage"
REASON_BACK = "Add a reason to move a company back"
REOPEN_FORBIDDEN = "Only a placement manager can reopen this company"
ARCHIVED = "Restore this company first"
LOST_CONFLICT = {"message": "This company is marked lost. A placement manager can reopen it.", "code": "company_lost"}
NOT_LOST_CONFLICT = {"message": "This company is not marked lost.", "code": "company_not_lost"}
LOST = "lost"  # the board's Lost bucket
BOARD_STAGE_UNKNOWN = "Choose a stage of this pipeline"


def _invalid(field: str, msg: str, value) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


async def _record(db: AsyncSession, company: Company, to_stage: str, event: str, actor: User | None, reason: str | None) -> None:
    from_stage = company.stage
    if to_stage != from_stage:
        company.stage, company.stage_changed_at = to_stage, await db.scalar(select(func.now()))
    db.add(CompanyStageHistory(company_id=company.id, from_stage=from_stage, to_stage=to_stage, event=event, actor_user_id=actor.id if actor else None, reason=reason))
    logger.info("company_stage_changed", extra={"extra_fields": {
        "company_id": str(company.id), "from_stage": from_stage, "to_stage": to_stage, "event": event, "actor_id": str(actor.id) if actor else None}})


async def apply_event(db: AsyncSession, company: Company, event: str, actor: User | None = None, reason: str | None = None) -> bool:
    """P2/P3: move the locked company if it is in the event's from-set; otherwise (already past it) leave it. A Lost or archived company
    never moves. Returns whether it moved, so a repeated event never fires twice. An unknown event is a KeyError: a caller bug."""
    sources, to_stage = EVENTS[event]
    if company.lost_at is not None or company.archived_at is not None or company.stage not in sources:
        return False
    await _record(db, company, to_stage, event, actor, reason)
    return True


def can_move(user: User, company: Company) -> bool:
    """P6: rec-003's `can_edit` holders (the assigned recruiter, super_admin), on an active company that is not Lost."""
    return _allowed(user, company, "can_edit") and company.archived_at is None and company.lost_at is None


def can_reopen(user: User, company: Company) -> bool:
    return user.role in (MANAGER_ROLE, "super_admin") and company.archived_at is None and company.lost_at is not None


def _require_writer(user: User, company: Company) -> None:
    """403 for the wrong person, then 409 archived, then 409 Lost (the same order as rec-003's `require`)."""
    if not _allowed(user, company, "can_edit"):
        raise HTTPException(403, "Only the assigned recruiter can change this company's stage")
    if company.archived_at is not None:
        raise HTTPException(409, ARCHIVED)
    if company.lost_at is not None:
        raise HTTPException(409, LOST_CONFLICT)


async def person_move(db: AsyncSession, user: User, company: Company, from_stage: str, to_stage: str, reason: str | None) -> bool:
    """AC2 / P4: a manual stage only, from New Lead or a manual stage; back needs a reason. A stale `from_stage` (someone else moved it)
    is 409 `stage_changed`. Returns whether the move was backward."""
    _require_writer(user, company)
    if from_stage != company.stage:
        raise HTTPException(409, {"message": f"This company moved to {label(company.stage)} meanwhile", "code": "stage_changed", "current_stage": company.stage})
    kind = KINDS.get(to_stage)
    if kind is None:
        raise _invalid("to_stage", STAGE_UNKNOWN, to_stage)
    if kind == START:
        raise _invalid("to_stage", STAGE_START, to_stage)
    if kind == DRIVEN:
        raise _invalid("to_stage", STAGE_DRIVEN, to_stage)
    if KINDS[company.stage] == DRIVEN:
        raise _invalid("to_stage", STAGE_PAST, to_stage)
    if to_stage == company.stage:
        raise _invalid("to_stage", STAGE_SAME, to_stage)
    backward = ORDER.index(to_stage) < ORDER.index(company.stage)
    if backward and reason is None:
        raise _invalid("reason", REASON_BACK, reason)
    await _record(db, company, to_stage, "manual", user, reason)
    return backward


async def mark_lost(db: AsyncSession, user: User, company: Company, reason: str) -> None:
    """AC4 / P5: a flag with a reason on top of the stage, which is kept."""
    _require_writer(user, company)
    company.lost_at, company.lost_reason = await db.scalar(select(func.now())), reason
    await _record(db, company, company.stage, "lost", user, reason)


async def reopen(db: AsyncSession, user: User, company: Company, reason: str) -> None:
    """P5 (tel-004 T13): a manager (or super_admin) clears the flag; the company is back at the stage it was lost at."""
    if user.role not in (MANAGER_ROLE, "super_admin"):
        raise HTTPException(403, REOPEN_FORBIDDEN)
    if company.archived_at is not None:
        raise HTTPException(409, ARCHIVED)
    if company.lost_at is None:
        raise HTTPException(409, NOT_LOST_CONFLICT)
    company.lost_at, company.lost_reason = None, None
    await _record(db, company, company.stage, "reopen", user, reason)


def pipeline_out(user: User, company: Company) -> dict:
    current = ORDER.index(company.stage)

    def state(i: int) -> str:
        return "done" if i < current else "current" if i == current else "upcoming"

    return {
        "stage": company.stage,
        "stage_label": label(company.stage),
        "stage_changed_at": company.stage_changed_at,
        "lost": {"at": company.lost_at, "reason": company.lost_reason} if company.lost_at else None,
        "can_move": can_move(user, company),
        "can_reopen": can_reopen(user, company),
        "steps": [{"key": key, "label": text, "kind": kind, "state": state(i)} for i, (key, text, kind) in enumerate(STAGES)],
    }


async def history_page(db: AsyncSession, company: Company, limit: int, offset: int) -> dict:
    """Newest first; the actor is null for the system."""
    where = CompanyStageHistory.company_id == company.id
    total = await db.scalar(select(func.count()).select_from(CompanyStageHistory).where(where))
    stmt = select(CompanyStageHistory, User).outerjoin(User, User.id == CompanyStageHistory.actor_user_id).where(where)
    rows = (await db.execute(stmt.order_by(CompanyStageHistory.position.desc()).limit(limit).offset(offset))).all()
    items = [
        {
            "id": h.id, "event": h.event, "from_stage": h.from_stage, "from_label": label(h.from_stage), "to_stage": h.to_stage,
            "to_label": label(h.to_stage), "reason": h.reason, "actor": {"id": actor.id, "full_name": actor.full_name} if actor else None,
            "created_at": h.created_at,
        }
        for h, actor in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


async def board(db: AsyncSession, filters: list, stage: str | None, limit: int, offset: int) -> dict:
    """P7: one grouped count over the caller's scope (archived left out; Lost counted apart), then one page of one stage, `lost`, or every
    open company."""
    if stage is not None and stage != LOST and stage not in KINDS:
        raise HTTPException(422, BOARD_STAGE_UNKNOWN)
    scope = [*filters, Company.archived_at.is_(None)]
    is_lost = Company.lost_at.is_not(None)
    grouped = (await db.execute(select(Company.stage, is_lost, func.count()).where(*scope).group_by(Company.stage, is_lost))).all()
    counts = {key: n for key, lost, n in grouped if not lost}
    page = [*scope, is_lost if stage == LOST else Company.lost_at.is_(None)]
    if stage not in (None, LOST):
        page.append(Company.stage == stage)
    total = await db.scalar(select(func.count()).select_from(Company).where(*page))
    recruiter = aliased(User)
    stmt = select(Company, recruiter).outerjoin(recruiter, recruiter.id == Company.assigned_recruiter_user_id).where(*page)
    rows = (await db.execute(stmt.order_by(func.lower(Company.name), Company.id).limit(limit).offset(offset))).all()
    return {
        "stages": [{"key": key, "label": text, "kind": kind, "count": counts.get(key, 0)} for key, text, kind in STAGES],
        "lost_count": sum(n for _, lost, n in grouped if lost),
        "items": [
            {
                "id": c.id, "code": c.company_code, "name": c.name, "city": c.city, "priority": c.priority, "assigned_recruiter": person(r),
                "stage": c.stage, "stage_label": label(c.stage), "lost": c.lost_at is not None,
            }
            for c, r in rows
        ],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }

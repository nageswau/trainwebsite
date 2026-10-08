"""upc-007 (DEC-SCOPE-125, spec §3): the partnership stage engine -- the single writer of `universities.stage` and the Lost flag, the stage
history and the Kanban board.

Functions only; nothing here commits -- the route owns the transaction (upc-003's rule). Every write runs on the row locked by
`partnership_universities.load(lock=True)` after `require(...)`. History notes are kept; audit metadata and logs carry stage keys and flags
only, never the note or reason text."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Country, University, UniversityStageHistory, User
from app.partnership_stages import COLUMN_LABELS, COLUMNS, STAGE_KEYS, STAGES, column_of, label_of
from app.schemas import UniversityStageMove
from app.services.telecaller import person_ref

LOST = "lost"  # the board's Lost bucket (PS11)
STAGE_UNKNOWN = "Choose a partnership stage"
STAGE_SAME = "The university is already at this stage"
NOTE_REQUIRED = "Add a note to move a university back"
COLUMN_UNKNOWN = "Choose a pipeline column"
LOST_CONFLICT = {"message": "This university is marked lost. Reopen it first.", "code": "university_lost"}
NOT_LOST_CONFLICT = {"message": "This university is not marked lost.", "code": "university_not_lost"}
_CATALOGUE = [{"key": s.key, "label": s.label, "column": s.column} for s in STAGES]
_COLUMN_STAGES = {c: [s.key for s in STAGES if s.column == c] for c in COLUMNS}


def pipeline_out(uni: University) -> dict:
    column = column_of(uni.stage)
    return {
        "stage": uni.stage,
        "stage_label": label_of(uni.stage),
        "column": column,
        "column_label": COLUMN_LABELS[column],
        "changed_at": uni.stage_changed_at,
        "lost": {"at": uni.lost_at, "reason": uni.lost_reason} if uni.lost_at else None,
        "stages": _CATALOGUE,
    }


def _invalid(field: str, msg: str, value) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def _check_move(uni: University, payload: UniversityStageMove) -> bool:
    """PS4/PS8 on the locked row (the route already ran require: 403, inactive 409). Returns whether the move is backward."""
    if uni.lost_at is not None:
        raise HTTPException(409, LOST_CONFLICT)
    if payload.from_stage != uni.stage:
        raise HTTPException(409, {"message": f"This university moved to {label_of(uni.stage)} meanwhile", "code": "stage_changed", "current_stage": uni.stage})
    if payload.to_stage not in STAGE_KEYS:
        raise _invalid("to_stage", STAGE_UNKNOWN, payload.to_stage)
    if payload.to_stage == uni.stage:
        raise _invalid("to_stage", STAGE_SAME, payload.to_stage)
    backward = STAGE_KEYS.index(payload.to_stage) < STAGE_KEYS.index(uni.stage)
    if backward and payload.note is None:
        raise _invalid("note", NOTE_REQUIRED, payload.note)
    return backward


def _record(db: AsyncSession, user: User, uni: University, kind: str, from_stage: str, to_stage: str, note: str | None) -> None:
    db.add(UniversityStageHistory(university_id=uni.id, actor_user_id=user.id, kind=kind, from_stage=from_stage, to_stage=to_stage, note=note))


def move(db: AsyncSession, user: User, uni: University, payload: UniversityStageMove) -> bool:
    """Checks, then changes the stage and writes the history row. Returns whether the move was backward."""
    backward = _check_move(uni, payload)
    from_stage = uni.stage
    uni.stage, uni.stage_changed_at = payload.to_stage, datetime.now(UTC)
    _record(db, user, uni, "move", from_stage, payload.to_stage, payload.note)
    return backward


def set_lost(db: AsyncSession, user: User, uni: University, reason: str, lost: bool) -> str:
    """PS1/PS6: Lost is a flag with a reason on top of the kept stage; reopen clears it. Returns the history kind."""
    if lost and uni.lost_at is not None:
        raise HTTPException(409, LOST_CONFLICT)
    if not lost and uni.lost_at is None:
        raise HTTPException(409, NOT_LOST_CONFLICT)
    uni.lost_at, uni.lost_reason = (datetime.now(UTC), reason) if lost else (None, None)
    kind = "lost" if lost else "reopened"
    _record(db, user, uni, kind, uni.stage, uni.stage, reason)
    return kind


async def history_page(db: AsyncSession, university_id: UUID, limit: int, offset: int) -> dict:
    where = UniversityStageHistory.university_id == university_id
    total = await db.scalar(select(func.count()).select_from(UniversityStageHistory).where(where))
    stmt = select(UniversityStageHistory, User).join(User, User.id == UniversityStageHistory.actor_user_id).where(where)
    rows = (await db.execute(stmt.order_by(UniversityStageHistory.position.desc()).limit(limit).offset(offset))).all()
    items = [
        {
            "id": e.id, "kind": e.kind, "from_stage": e.from_stage, "from_label": label_of(e.from_stage), "to_stage": e.to_stage,
            "to_label": label_of(e.to_stage), "note": e.note, "actor": {"id": actor.id, "full_name": actor.full_name}, "created_at": e.created_at,
        }
        for e, actor in rows
    ]  # fmt: skip
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


async def board(db: AsyncSession, filters: list, column: str | None, limit: int, offset: int) -> dict:
    """PS11: one grouped count over (stage, lost) folded into the 9 columns, then one page. Inactive universities are excluded; lost ones
    are counted only in lost_count and listed only under column=lost (Appendix B: excluded from the Kanban)."""
    if column is not None and column != LOST and column not in COLUMN_LABELS:
        raise HTTPException(422, COLUMN_UNKNOWN)
    scope = [*filters, University.active.is_(True)]
    is_lost = University.lost_at.is_not(None)
    grouped = (await db.execute(select(University.stage, is_lost, func.count()).where(*scope).group_by(University.stage, is_lost))).all()
    counts = dict.fromkeys(COLUMNS, 0)
    lost_count = 0
    for stage, lost, n in grouped:
        if lost:
            lost_count += n
        else:
            counts[column_of(stage)] += n
    page = [*scope, is_lost if column == LOST else University.lost_at.is_(None)]
    if column not in (None, LOST):
        page.append(University.stage.in_(_COLUMN_STAGES[column]))
    total = await db.scalar(select(func.count()).select_from(University).where(*page))
    primary = aliased(User)
    stmt = (
        select(University, Country.name, primary)
        .join(Country, Country.id == University.country_id)
        .outerjoin(primary, primary.id == University.primary_manager_user_id)
        .where(*page)
        .order_by(University.name, University.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    return {
        "columns": [{"key": c, "label": COLUMN_LABELS[c], "stages": _COLUMN_STAGES[c], "count": counts[c]} for c in COLUMNS],
        "lost_count": lost_count,
        "items": [
            {
                "id": uni.id,
                "university_code": uni.university_code,
                "name": uni.name,
                "city": uni.city,
                "country_name": country_name,
                "stage": uni.stage,
                "stage_label": label_of(uni.stage),
                "column": column_of(uni.stage),
                "lost": uni.lost_at is not None,
                "primary_manager": person_ref(manager) if manager else None,
            }
            for uni, country_name, manager in rows
        ],  # fmt: skip
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }

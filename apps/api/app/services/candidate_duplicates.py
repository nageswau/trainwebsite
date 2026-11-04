"""hrc-014 (DEC-SCOPE-377 D1-D3, D9): the probable-duplicate review queue. Exact mobile/email matches stay blocked by rec-009 (Q-07); the
probable ones below are only queued, never blocked, because two real people can share them.

Detection is two equality self-joins (one per signal, so each is a hash join rather than a nested loop) over active, in-pool candidates,
optionally limited to pairs involving one candidate; new pairs are inserted lower id first with ON CONFLICT DO NOTHING, so a pair is queued
once and a dismissed pair is never queued again. Functions only; nothing here commits. Logs and audit rows carry ids and counts only."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AuditLog, Candidate, CandidateDuplicate, User
from app.services import candidates as svc
from app.services.permissions import user_has_grant

logger = logging.getLogger("app.candidates")

NOT_FOUND = "Duplicate pair not found"
NO_MERGE = "Your role cannot review or merge duplicate candidates"
NOT_OPEN = "This pair has already been reviewed"
# The fields that make a detection worth re-running after an edit.
WATCHED = frozenset({"name", "location", "college", "mobile"})


async def require_merger(db: AsyncSession, user: User) -> None:
    """D3: a candidate writer holding `candidates.merge` (a grant never lets a reader role write)."""
    svc.require_writer(user)
    if not await user_has_grant(db, user, "candidates", "merge"):
        raise HTTPException(403, NO_MERGE)


def _name(column):
    return func.lower(func.regexp_replace(func.btrim(column), r"\s+", " ", "g"))


def _text(column):
    return func.lower(func.btrim(column))


def _phone(column):
    """The mobile's last ten digits (None when it has fewer): `98765 43210` and `+44 9876543210` agree."""
    digits = func.regexp_replace(column, "[^0-9]", "", "g")
    return func.right(digits, 10)


SIGNALS = {
    "name_location_college": lambda c: (_name(c.name), _text(c.location), _text(c.college)),
    "phone_variant": lambda c: (_phone(c.mobile),),
}


def _active(c) -> list:
    return [c.archived_at.is_(None), or_(c.user_id.is_(None), c.opted_in.is_(True))]


def _present(signal: str, c) -> list:
    if signal == "phone_variant":
        return [func.length(func.regexp_replace(c.mobile, "[^0-9]", "", "g")) >= 10]
    return [func.btrim(c.name) != "", func.btrim(c.location) != "", func.btrim(c.college) != ""]


async def detect(db: AsyncSession, candidate_id: UUID | None = None) -> int:
    """Queue every new probable pair (all of them, or those involving `candidate_id`). Returns how many pairs were added."""
    found: dict[tuple[UUID, UUID], list[str]] = {}
    for signal, keys in SIGNALS.items():
        a, b = aliased(Candidate), aliased(Candidate)
        stmt = select(a.id, b.id).join(b, and_(a.id < b.id, *(x == y for x, y in zip(keys(a), keys(b), strict=True)))).where(
            *_active(a), *_active(b), *_present(signal, a), *_present(signal, b)
        )
        if candidate_id is not None:
            stmt = stmt.where(or_(a.id == candidate_id, b.id == candidate_id))
        for first, second in (await db.execute(stmt)).all():
            found.setdefault((first, second), []).append(signal)
    if not found:
        return 0
    rows = [{"candidate_id": first, "other_id": second, "signals": signals, "status": "open"} for (first, second), signals in found.items()]
    stmt = insert(CandidateDuplicate).values(rows).on_conflict_do_nothing(constraint="uq_candidate_duplicates_pair").returning(CandidateDuplicate.id)
    created = len((await db.execute(stmt)).all())
    if created:
        logger.info("candidate_duplicates_queued", extra={"extra_fields": {"candidate_id": str(candidate_id) if candidate_id else None, "created": created}})
    return created


def _side(c: Candidate) -> dict:
    return {"id": c.id, "candidate_code": c.candidate_code, "name": c.name, "location": c.location, "college": c.college, "status": c.status,
            "archived": c.archived_at is not None}  # fmt: skip


def _person(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name} if user else None


def _out(row: CandidateDuplicate, first: Candidate, second: Candidate, decider: User | None) -> dict:
    """The older record first (browser QA-01): the merge screen keeps `candidate` by default."""
    first, second = sorted((first, second), key=lambda c: (c.created_at, c.candidate_code))
    return {"id": row.id, "signals": row.signals, "status": row.status, "created_at": row.created_at, "decided_at": row.decided_at,
            "decided_by": _person(decider), "candidate": _side(first), "other": _side(second)}  # fmt: skip


async def queue(db: AsyncSession, status: str, limit: int, offset: int) -> dict:
    """Oldest first. Both sides must still be in the pool; an open pair also needs both sides active (an archived side has nothing to do)."""
    a, b = aliased(Candidate), aliased(Candidate)
    pool = [or_(c.user_id.is_(None), c.opted_in.is_(True)) for c in (a, b)]
    if status == "open":
        pool += [a.archived_at.is_(None), b.archived_at.is_(None)]
    stmt = (
        select(CandidateDuplicate, a, b, User)
        .join(a, a.id == CandidateDuplicate.candidate_id)
        .join(b, b.id == CandidateDuplicate.other_id)
        .outerjoin(User, User.id == CandidateDuplicate.decided_by_user_id)
        .where(CandidateDuplicate.status == status, *pool)
    )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = (CandidateDuplicate.created_at, CandidateDuplicate.id) if status == "open" else (CandidateDuplicate.decided_at.desc(), CandidateDuplicate.id)
    rows = (await db.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()
    return {"items": [_out(*row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


async def dismiss(db: AsyncSession, user: User, pair_id: UUID, note: str | None) -> dict:
    """"Not the same person": the open pair closes for good (the detector never re-queues it). 409 when it is no longer open."""
    row = await db.scalar(select(CandidateDuplicate).where(CandidateDuplicate.id == pair_id).with_for_update())
    first = await db.scalar(select(Candidate).where(Candidate.id == row.candidate_id, *svc.pool_filter())) if row else None
    second = await db.scalar(select(Candidate).where(Candidate.id == row.other_id, *svc.pool_filter())) if row else None
    if row is None or first is None or second is None:
        raise HTTPException(404, NOT_FOUND)
    if row.status != "open":
        raise HTTPException(409, NOT_OPEN)
    row.status, row.note, row.decided_by_user_id, row.decided_at = "dismissed", note, user.id, datetime.now(UTC)
    db.add(AuditLog(user_id=user.id, action="candidate.duplicate_dismiss", entity_type="candidate_duplicates", entity_id=str(row.id),
                    metadata_json={"candidate_ids": sorted([str(row.candidate_id), str(row.other_id)])}))  # fmt: skip
    await db.flush()
    return _out(row, first, second, user)


async def close_for_merge(db: AsyncSession, user: User, victim_id: UUID) -> None:
    """D9: every open pair naming the victim closes as merged (the merged pair included). The caller re-runs `detect` for the survivor."""
    await db.execute(
        update(CandidateDuplicate)
        .where(CandidateDuplicate.status == "open", or_(CandidateDuplicate.candidate_id == victim_id, CandidateDuplicate.other_id == victim_id))
        .values(status="merged", decided_by_user_id=user.id, decided_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )

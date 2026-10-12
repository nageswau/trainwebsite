"""mgmt-014 (DEC-SCOPE-189 MI1-MI14): EVID-017 §23's investment register -- what EduSphere invested and what it produced.

Partner-only (M13): the routes refuse everyone else before calling in here. Every create and change writes its `mgmt.investment` audit
row in the same transaction (mgmt-002 MA10). Spec: docs/superpowers/specs/2026-10-12-mgmt-014-investment-register-design.md.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import INVESTMENT_CODE_SEQ, Investment, User
from app.schemas import InvestmentCreate, InvestmentUpdate
from app.services import management_audit

CENT = Decimal("0.01")
NOT_FOUND = "Investment not found"
NO_PARTNER = "Choose the partner who invested"
NOT_A_PARTNER = "Choose an active partner as the investor"
COMPANY_HAS_NO_PARTNER = "A company investment has no partner investor"


def roi(amount: Decimal, actual_return: Decimal | None) -> Decimal | None:
    """MI7 (Appendix B I1): (actual - amount) / amount x 100, to 2 decimals; unknown until the actual return is."""
    if actual_return is None:
        return None
    return ((actual_return - amount) / amount * 100).quantize(CENT, rounding=ROUND_HALF_UP)


async def _code(db: AsyncSession) -> str:
    return f"INV-{await db.scalar(select(INVESTMENT_CODE_SEQ.next_value())):06d}"


async def _check_partner(db: AsyncSession, user_id: UUID) -> None:
    if not await db.scalar(select(User.id).where(User.id == user_id, User.role == "partner", User.active.is_(True))):
        raise HTTPException(422, NOT_A_PARTNER)


async def _investor(db: AsyncSession, kind: str, user_id: UUID | None, current: UUID | None = None) -> UUID | None:
    """MI4: a company investment has no investor; a partner investment names an active partner (one already on the record is kept
    even if they have since left)."""
    if kind == "company":
        if user_id is not None:
            raise HTTPException(422, COMPANY_HAS_NO_PARTNER)
        return None
    if user_id is None:
        raise HTTPException(422, NO_PARTNER)
    if user_id != current:
        await _check_partner(db, user_id)
    return user_id


def _audit_value(value):
    return value.isoformat() if isinstance(value, date) else value


async def create(db: AsyncSession, actor: User, body: InvestmentCreate) -> Investment:
    data = body.model_dump()
    data["investor_user_id"] = await _investor(db, data["investor_kind"], data["investor_user_id"])
    investment = Investment(code=await _code(db), created_by_user_id=actor.id, updated_by_user_id=actor.id, **data)
    db.add(investment)
    await db.flush()
    fields = [name for name, value in data.items() if value is not None]
    management_audit.record(db, actor, "mgmt.investment", "create", str(investment.id), fields=fields, values={name: (None, _audit_value(data[name])) for name in fields})
    await db.commit()
    return investment


async def get(db: AsyncSession, investment_id: UUID, *, lock: bool = False) -> Investment:
    query = select(Investment).where(Investment.id == investment_id)
    investment = await db.scalar(query.with_for_update() if lock else query)
    if investment is None:
        raise HTTPException(404, NOT_FOUND)
    return investment


async def update(db: AsyncSession, actor: User, investment_id: UUID, body: InvestmentUpdate) -> Investment:
    """MI10/MI11: the row is locked so two partners' edits serialise; only the fields that really change are written and audited."""
    investment = await get(db, investment_id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    if "investor_kind" in changes or "investor_user_id" in changes:
        kind = changes.get("investor_kind", investment.investor_kind)
        if "investor_user_id" in changes:
            user_id = changes["investor_user_id"]
        else:  # switching to company drops the partner; switching to partner needs one named (or already on the record)
            user_id = investment.investor_user_id if kind == "partner" else None
        changes["investor_kind"] = kind
        changes["investor_user_id"] = await _investor(db, kind, user_id, investment.investor_user_id)
    changed = {name: (getattr(investment, name), value) for name, value in changes.items() if getattr(investment, name) != value}
    if not changed:
        await db.rollback()  # release the lock; nothing to write or audit
        return await get(db, investment_id)
    for name, (_, value) in changed.items():
        setattr(investment, name, value)
    investment.updated_by_user_id = actor.id
    management_audit.record(
        db, actor, "mgmt.investment", "update", str(investment.id), fields=list(changed), values={name: (_audit_value(before), _audit_value(after)) for name, (before, after) in changed.items()}
    )
    await db.commit()
    return investment


def _filters(date_from: date | None, date_to: date | None, vertical: str | None, status: str | None) -> list:
    where = []
    if date_from:
        where.append(Investment.invested_on >= date_from)
    if date_to:
        where.append(Investment.invested_on <= date_to)
    if vertical:
        where.append(Investment.vertical == vertical)
    if status:
        where.append(Investment.status == status)
    return where


async def totals(db: AsyncSession, where: list) -> dict:
    """MI8: over every matching investment except cancelled ones; the overall ROI counts only those whose actual return is known."""
    known = Investment.actual_return.is_not(None)
    row = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(Investment.amount), 0),
                func.coalesce(func.sum(Investment.actual_return), 0),
                func.sum(case((known, Investment.amount))),
            ).where(*where, Investment.status != "cancelled")
        )
    ).one()
    count, invested, returned, invested_known = row
    return {
        "count": count,
        "invested": Decimal(invested).quantize(CENT),
        "actual_return": Decimal(returned).quantize(CENT),
        "roi": roi(invested_known, Decimal(returned)) if invested_known else None,
    }


async def people(db: AsyncSession, ids: set[UUID]) -> dict[UUID, dict]:
    rows = (await db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all() if ids else []
    return {user_id: {"id": user_id, "full_name": name} for user_id, name in rows}


def out(investment: Investment, names: dict[UUID, dict]) -> dict:
    return {
        "id": investment.id,
        "code": investment.code,
        "invested_on": investment.invested_on,
        "investor_kind": investment.investor_kind,
        "investor": names.get(investment.investor_user_id),
        "amount": investment.amount,
        "purpose": investment.purpose,
        "vertical": investment.vertical,
        "expected_return": investment.expected_return,
        "actual_return": investment.actual_return,
        "roi": roi(investment.amount, investment.actual_return),
        "status": investment.status,
        "notes": investment.notes,
        "created_by": names[investment.created_by_user_id],
        "updated_by": names[investment.updated_by_user_id],
        "created_at": investment.created_at,
        "updated_at": investment.updated_at,
    }


async def one(db: AsyncSession, investment: Investment) -> dict:
    await db.refresh(investment)  # the server-set timestamps
    ids = {investment.created_by_user_id, investment.updated_by_user_id, investment.investor_user_id} - {None}
    return out(investment, await people(db, ids))


async def page(db: AsyncSession, *, date_from: date | None = None, date_to: date | None = None, vertical: str | None = None, status: str | None = None, limit: int = 25, offset: int = 0) -> dict:
    """MI9: newest `invested_on` first, then code; the totals cover every match, not just the page."""
    where = _filters(date_from, date_to, vertical, status)
    total = await db.scalar(select(func.count()).select_from(Investment).where(*where))
    rows = (await db.scalars(select(Investment).where(*where).order_by(Investment.invested_on.desc(), Investment.code.desc()).limit(limit).offset(offset))).all()
    ids = {i for r in rows for i in (r.created_by_user_id, r.updated_by_user_id, r.investor_user_id)} - {None}
    names = await people(db, ids)
    investors = (await db.execute(select(User.id, User.full_name).where(User.role == "partner", User.active.is_(True)).order_by(User.full_name))).all()
    return {
        "items": [out(r, names) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "totals": await totals(db, where),
        "investors": [{"id": user_id, "full_name": name} for user_id, name in investors],
    }

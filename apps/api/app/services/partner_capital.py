"""mgmt-015 (spec CP1-CP15): EVID-017 §24's partner capital accounts -- each partner's capital movements, share % and the eight figures.

Partner-only (M13): the routes refuse everyone else before calling in here. Entries are never edited or deleted (CP4). Every write and
its `mgmt.capital` audit row commit together (mgmt-002 MA10). The profit share is indicative only: nothing is distributed (M8, CP9).
Spec: docs/superpowers/specs/2026-10-14-mgmt-015-partner-capital-accounts-design.md.
"""

import logging
from collections.abc import Iterable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, union
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PartnerCapitalEntry, PartnerShare, User
from app.schemas import CAPITAL_EARLIEST, CapitalEntryCreate, CapitalSharesIn
from app.services import management_audit, management_pnl
from app.services.investments import people
from app.services.management_expenses import month_key, next_month
from app.services.management_it_revenue import period_range

logger = logging.getLogger(__name__)
CENT = Decimal("0.01")
ENTRIES_PAGE = 25
NOT_A_PARTNER = "Choose an active partner"
FUTURE_DATE = "The entry date can't be in the future"
MONTH_RANGE = "Choose a month from January 2000 to 12 months ahead"
SHARE_RACE = "The shares were changed at the same time. Reload and try again."


def _money(value: Decimal | int) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def figures(sums: dict[str, Decimal], *, share_pct: Decimal | None, commitment: Decimal | None, profit_share: Decimal | None) -> dict:
    """CP8 (AC2): balance = invested + additional - withdrawals; returns (distributions) never change it. Outstanding contribution is
    the commitment not yet put in, never below 0, unknown without a commitment."""
    invested, additional, withdrawals, returns = (_money(sums.get(kind, 0)) for kind in ("initial", "additional", "withdrawal", "profit_distribution"))
    return {
        "invested": invested,
        "additional": additional,
        "withdrawals": withdrawals,
        "balance": invested + additional - withdrawals,
        "returns": returns,
        "share_pct": share_pct,
        "commitment": commitment,
        "outstanding": None if commitment is None else max(_money(commitment) - invested - additional, Decimal("0.00")),
        "profit_share": profit_share,
    }


def _in_force(history: Iterable[tuple[date, Decimal | None]], day: date) -> Decimal | None:
    """CP5: the latest share whose month starts on or before `day`; `history` is oldest first."""
    found = None
    for effective_from, value in history:
        if effective_from <= day:
            found = value
    return found


def profit_share(months: list[tuple[date, Decimal]], history: list[tuple[date, Decimal]]) -> Decimal | None:
    """CP9 (AC3): Σ month's net profit × the share in force on its first day ÷ 100, rounded half-up once; none if no month had a share."""
    parts = [profit * pct / 100 for month, profit in months if (pct := _in_force(history, month)) is not None]
    return _money(sum(parts, Decimal(0))) if parts else None


def totals(accounts: list[dict]) -> dict:
    """The Total column: money summed; share % summed (0 when none is set, so AC1's warning shows); an unknown figure is left out, and a
    column with nothing known stays unknown."""

    def known(key: str) -> Decimal | None:
        values = [a[key] for a in accounts if a[key] is not None]
        return sum(values, Decimal("0.00")) if values else None

    out = {key: known(key) for key in ("commitment", "outstanding", "profit_share")}
    out.update({key: sum((a[key] for a in accounts), Decimal("0.00")) for key in ("invested", "additional", "withdrawals", "balance", "returns")})
    out["share_pct"] = sum((a["share_pct"] for a in accounts if a["share_pct"] is not None), Decimal("0.00"))
    return out


def _add_months(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


async def _active_partners(db: AsyncSession, ids: Iterable[UUID]) -> set[UUID]:
    return set(await db.scalars(select(User.id).where(User.id.in_(list(ids)), User.role == "partner", User.active.is_(True))))


def _audit_value(value):
    return value.isoformat() if isinstance(value, date) else value


async def add_entry(db: AsyncSession, actor: User, body: CapitalEntryCreate, today: date) -> PartnerCapitalEntry:
    """CP3/CP12: an active partner's entry dated up to today (IST), audited with its values. A withdrawal over the balance is allowed (CP11)."""
    if not await _active_partners(db, [body.partner_id]):
        raise HTTPException(422, NOT_A_PARTNER)
    if body.entry_date > today:
        raise HTTPException(422, FUTURE_DATE)
    data = {"partner_user_id": body.partner_id, "entry_date": body.entry_date, "kind": body.kind, "amount": body.amount, "note": body.note}
    entry = PartnerCapitalEntry(created_by_user_id=actor.id, **data)
    db.add(entry)
    await db.flush()
    fields = [name for name, value in data.items() if value is not None]
    management_audit.record(db, actor, "mgmt.capital", "create", str(entry.id), fields=fields, values={name: (None, _audit_value(data[name])) for name in fields})
    await db.commit()
    logger.info("capital_entry_recorded", extra={"extra_fields": {"actor_id": str(actor.id), "entry_id": str(entry.id), "kind": entry.kind}})
    return entry


async def set_shares(db: AsyncSession, actor: User, body: CapitalSharesIn, today: date) -> None:
    """CP5/CP6/CP12/CP14: one row per sent partner for the month, replacing that month's row; only real changes are written and audited.
    The month's rows are locked, and a concurrent first insert that loses the unique race is a 409."""
    month = date(int(body.effective_from[:4]), int(body.effective_from[5:]), 1)
    if not CAPITAL_EARLIEST <= month <= _add_months(today.replace(day=1), 12):
        raise HTTPException(422, MONTH_RANGE)
    ids = [row.partner_id for row in body.shares]
    if len(await _active_partners(db, ids)) != len(ids):
        raise HTTPException(422, NOT_A_PARTNER)
    query = select(PartnerShare).where(PartnerShare.partner_user_id.in_(ids), PartnerShare.effective_from == month).with_for_update()
    existing = {row.partner_user_id: row for row in await db.scalars(query)}
    written = 0
    try:
        for row in body.shares:
            after = {"share_pct": row.share_pct, "commitment": row.commitment}
            current = existing.get(row.partner_id)
            if current is None:
                share = PartnerShare(partner_user_id=row.partner_id, effective_from=month, created_by_user_id=actor.id, updated_by_user_id=actor.id, **after)
                db.add(share)
                await db.flush()
                created = {"partner_user_id": row.partner_id, "effective_from": month, **after}
                fields = [name for name, value in created.items() if value is not None]
                management_audit.record(db, actor, "mgmt.capital", "create", str(share.id), fields=fields, values={name: (None, _audit_value(created[name])) for name in fields})
                written += 1
                continue
            changed = {name: (getattr(current, name), value) for name, value in after.items() if getattr(current, name) != value}
            if changed:
                for name, (_, value) in changed.items():
                    setattr(current, name, value)
                current.updated_by_user_id = actor.id
                management_audit.record(db, actor, "mgmt.capital", "update", str(current.id), fields=list(changed), values=changed)
                written += 1
        await db.commit()
    except IntegrityError:  # another partner's first save of the same month won the unique (partner, month) race (at the flush or the commit)
        await db.rollback()
        raise HTTPException(409, SHARE_RACE) from None
    logger.info("capital_shares_saved", extra={"extra_fields": {"actor_id": str(actor.id), "month": month_key(month), "changed": written}})


async def share_history(db: AsyncSession, today: date) -> list[dict]:
    """Every share row, newest month first; `in_force` marks each partner's row in force today."""
    rows = list(await db.scalars(select(PartnerShare).order_by(PartnerShare.effective_from.desc(), PartnerShare.partner_user_id)))
    names = await people(db, {i for r in rows for i in (r.partner_user_id, r.updated_by_user_id)})
    current: dict[UUID, UUID] = {}
    for r in rows:
        if r.effective_from <= today:
            current.setdefault(r.partner_user_id, r.id)
    return [
        {
            "id": r.id, "partner": names[r.partner_user_id], "effective_from": r.effective_from, "share_pct": r.share_pct, "commitment": r.commitment,
            "in_force": current.get(r.partner_user_id) == r.id, "updated_by": names[r.updated_by_user_id], "updated_at": r.updated_at,
        }
        for r in rows
    ]  # fmt: skip


async def entries_out(db: AsyncSession, rows: list[PartnerCapitalEntry]) -> list[dict]:
    names = await people(db, {i for r in rows for i in (r.partner_user_id, r.created_by_user_id)})
    return [
        {"id": r.id, "partner": names[r.partner_user_id], "entry_date": r.entry_date, "kind": r.kind, "amount": r.amount, "note": r.note,
         "created_by": names[r.created_by_user_id], "created_at": r.created_at}
        for r in rows
    ]  # fmt: skip


async def _entries(db: AsyncSession, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(PartnerCapitalEntry))
    query = select(PartnerCapitalEntry).order_by(PartnerCapitalEntry.entry_date.desc(), PartnerCapitalEntry.created_at.desc(), PartnerCapitalEntry.id.desc())
    rows = list(await db.scalars(query.limit(ENTRIES_PAGE).offset(offset)))
    return {"items": await entries_out(db, rows), "total": total, "limit": ENTRIES_PAGE, "offset": offset}


async def view(db: AsyncSession, user: User, month_start: date, period: str, offset: int, today: date) -> dict:
    """CP1/CP8-CP10: the accounts as of today and the profit share over the period, the entries page and the share history."""
    with_records = union(select(PartnerCapitalEntry.partner_user_id), select(PartnerShare.partner_user_id))
    is_partner = and_(User.role == "partner", User.active.is_(True))
    listed = (await db.execute(select(User.id, User.full_name, is_partner).where(or_(is_partner, User.id.in_(with_records))).order_by(User.full_name, User.id))).all()

    sums: dict[UUID, dict[str, Decimal]] = {}
    grouped = await db.execute(
        select(PartnerCapitalEntry.partner_user_id, PartnerCapitalEntry.kind, func.sum(PartnerCapitalEntry.amount)).group_by(PartnerCapitalEntry.partner_user_id, PartnerCapitalEntry.kind)
    )
    for partner_id, kind, amount in grouped.all():
        sums.setdefault(partner_id, {})[kind] = amount

    histories: dict[UUID, list[tuple[date, Decimal, Decimal | None]]] = {}
    for share in await db.scalars(select(PartnerShare).order_by(PartnerShare.effective_from)):
        histories.setdefault(share.partner_user_id, []).append((share.effective_from, share.share_pct, share.commitment))

    start, end = period_range(month_start, period)
    months, month = [], start
    while month < end:
        months.append((month, (await management_pnl.dashboard(db, user, month, "month"))["total"]["contribution"]))
        month = next_month(month)

    accounts = []
    for partner_id, full_name, active in listed:
        history = histories.get(partner_id, [])
        pct_history = [(day, pct) for day, pct, _ in history]
        commitment = _in_force([(day, c) for day, _, c in history], today)
        figures_ = figures(sums.get(partner_id, {}), share_pct=_in_force(pct_history, today), commitment=commitment, profit_share=profit_share(months, pct_history))
        accounts.append({"partner": {"id": partner_id, "full_name": full_name, "active": active}, **figures_})

    return {
        "as_of": today,
        "month": month_key(month_start),
        "period": period,
        "label": management_pnl._label(month_start, start, period),  # mgmt-009's own period wording, unchanged
        "net_profit": _money(sum((profit for _, profit in months), Decimal(0))),
        "accounts": accounts,
        "totals": totals(accounts),
        "partners": [{"id": i, "full_name": n} for i, n, active in listed if active],
        "entries": await _entries(db, offset),
        "shares": await share_history(db, today),
    }

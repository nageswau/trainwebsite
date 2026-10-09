"""upc-021 (DEC-SCOPE-144, spec §2, §4): monthly partnership targets -- who reads and sets them, the per-manager sheet, the team comparison
and the batch save.

Functions only; nothing here commits -- the route owns the transaction. The month rules are bdm-016's (TG2-TG5). Actuals are never stored:
`partnership_metrics.target_actuals` derives them. Every change is audited in the same transaction, one row per manager, with KPI keys and
numbers only (Q-23: history kept)."""

import logging
from collections import defaultdict
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, PartnershipProfile, PartnershipTarget, User
from app.partnership_target_kpis import KPIS
from app.schemas import PartnershipTargetItem
from app.services.bdm_metrics import month_range
from app.services.bdm_targets import _percent, edit_refusal, month_status, month_text
from app.services.partnership import partnership_context, team_filter
from app.services.partnership_metrics import target_actuals

logger = logging.getLogger("app.partnership")

READERS = frozenset({"partnership_manager", "partnership_head", "super_admin"})
MANAGER_NOT_FOUND = "Partnership manager not found"
INACTIVE = "This partnership manager is inactive, so their targets can't be changed"
KPI_DEFS = [{"key": k.key, "label": k.label, "definition": k.definition, "tracked": k.tracked} for k in KPIS]


async def require_reader(db: AsyncSession, user: User) -> None:
    """TG7: managers (with a profile), heads and super_admin; every other role is a 403."""
    if user.role == "partnership_manager":
        await partnership_context(db, user)
    elif user.role not in READERS:
        raise HTTPException(403, "Partnership targets are for partnership managers and heads")


def require_setter(user: User) -> None:
    """TG6: only a head or super_admin sets targets; a manager setting their own is a 403 (backlog negative scenario)."""
    if user.role not in ("partnership_head", "super_admin"):
        raise HTTPException(403, "Only a partnership head can set targets")


def _scope(user: User) -> list:
    """A manager sees only themself; a head their direct reports; super_admin every manager."""
    if user.role == "partnership_manager":
        return [User.id == user.id]
    return team_filter(user)


def _managers(user: User):
    return select(User).join(PartnershipProfile, PartnershipProfile.user_id == User.id).where(User.role == "partnership_manager", *_scope(user))


async def manager_in_scope(db: AsyncSession, user: User, manager_id: UUID) -> User:
    manager = await db.scalar(_managers(user).where(User.id == manager_id))
    if manager is None:
        raise HTTPException(404, MANAGER_NOT_FOUND)
    return manager


async def _figures(db: AsyncSession, manager_ids: list[UUID], month: date, status: str) -> tuple[dict, dict]:
    """(targets, actuals) by manager: targets {kpi: value}; actuals {kpi: count} -- none before the month starts (TG5)."""
    targets: dict[UUID, dict[str, int]] = defaultdict(dict)
    if manager_ids:
        rows = await db.execute(
            select(PartnershipTarget.manager_user_id, PartnershipTarget.kpi_key, PartnershipTarget.target).where(PartnershipTarget.manager_user_id.in_(manager_ids), PartnershipTarget.month == month)
        )
        for manager, kpi, target in rows.all():
            targets[manager][kpi] = target
    actuals = {} if status == "future" else await target_actuals(db, manager_ids, month)
    return targets, actuals


def _value(key: str, target: int | None, achieved: int | None) -> dict:
    return {"key": key, "target": target, "achieved": achieved, "percent": _percent(target, achieved)}


def _row(targets: dict[str, int], actuals: dict[str, int] | None) -> list[dict]:
    return [_value(k.key, targets.get(k.key), actuals.get(k.key) if actuals is not None and k.tracked else None) for k in KPIS]


async def sheet(db: AsyncSession, user: User, manager: User, month: date, current: date) -> dict:
    status = month_status(month, current)
    targets, actuals = await _figures(db, [manager.id], month, status)
    editable = user.role != "partnership_manager" and manager.active and edit_refusal(user, month, current) is None
    kpis = [d | v for d, v in zip(KPI_DEFS, _row(targets[manager.id], actuals.get(manager.id)), strict=True)]
    return {"month": month_text(month), "month_status": status, "editable": editable, "manager": {"id": manager.id, "full_name": manager.full_name}, "kpis": kpis}


async def team(db: AsyncSession, user: User, month: date, current: date) -> dict:
    """TG11/TG12: managers in scope who existed by the month's end, active or holding a target that month; then the team row."""
    _, end = month_range(month)
    has_target = select(PartnershipTarget.id).where(PartnershipTarget.manager_user_id == User.id, PartnershipTarget.month == month).exists()
    stmt = _managers(user).where(User.created_at < end, or_(User.active.is_(True), has_target)).order_by(User.full_name, User.id)
    managers = list((await db.scalars(stmt)).all())
    status = month_status(month, current)
    targets, actuals = await _figures(db, [m.id for m in managers], month, status)
    rows = [{"manager": {"id": m.id, "full_name": m.full_name}, "active": m.active, "kpis": _row(targets[m.id], actuals.get(m.id))} for m in managers]
    totals = []
    for i, kpi in enumerate(KPIS):
        set_targets = [r["kpis"][i]["target"] for r in rows if r["kpis"][i]["target"] is not None]
        achieved = [r["kpis"][i]["achieved"] for r in rows if r["kpis"][i]["achieved"] is not None]
        tracked = kpi.tracked and status != "future"
        totals.append(_value(kpi.key, sum(set_targets) if set_targets else None, sum(achieved) if tracked else None))
    editable = user.role != "partnership_manager" and edit_refusal(user, month, current) is None
    return {"month": month_text(month), "month_status": status, "editable": editable, "kpis": KPI_DEFS, "managers": rows, "team": totals}


def check_editable(user: User, month: date, current: date) -> None:
    if refusal := edit_refusal(user, month, current):
        raise HTTPException(422, refusal)


async def save(db: AsyncSession, actor: User, month: date, items: list[PartnershipTargetItem]) -> int:
    """Validate the whole batch first (nothing is written on any refusal), then upsert / clear only the values that change."""
    ids = {i.manager_user_id for i in items}
    managers = {m.id: m for m in (await db.scalars(_managers(actor).where(User.id.in_(ids)))).all()}
    if set(managers) != ids:
        raise HTTPException(404, MANAGER_NOT_FOUND)
    if any(not m.active for m in managers.values()):
        raise HTTPException(422, INACTIVE)
    pairs = [(i.manager_user_id, i.kpi_key) for i in items]
    existing = await db.execute(
        select(PartnershipTarget.manager_user_id, PartnershipTarget.kpi_key, PartnershipTarget.target)
        .where(PartnershipTarget.month == month, tuple_(PartnershipTarget.manager_user_id, PartnershipTarget.kpi_key).in_(pairs))
        .with_for_update()
    )
    old = {(manager, kpi): target for manager, kpi, target in existing.all()}
    changes: dict[UUID, list[dict]] = defaultdict(list)
    for item in items:
        before = old.get((item.manager_user_id, item.kpi_key))
        if before == item.target:
            continue
        changes[item.manager_user_id].append({"kpi": item.kpi_key, "from": before, "to": item.target})
        if item.target is None:
            await db.execute(delete(PartnershipTarget).where(PartnershipTarget.manager_user_id == item.manager_user_id, PartnershipTarget.month == month, PartnershipTarget.kpi_key == item.kpi_key))
            continue
        values = {"target": item.target, "set_by_user_id": actor.id, "set_at": func.now(), "updated_at": func.now()}
        # Two heads saving the same new KPI at once: the unique key turns the second insert into an update (last write wins).
        await db.execute(
            insert(PartnershipTarget)
            .values(manager_user_id=item.manager_user_id, month=month, kpi_key=item.kpi_key, **values)
            .on_conflict_do_update(constraint="uq_partnership_targets_manager_month_kpi", set_=values)
        )
    for manager_id, changed in changes.items():
        db.add(AuditLog(user_id=actor.id, action="partnership_target.set", entity_type="partnership_targets", entity_id=str(manager_id),
                        metadata_json={"month": month_text(month), "changes": changed}))  # fmt: skip
    return sum(len(c) for c in changes.values())


def log(event: str, actor: User, month: date, count: int) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(actor.id), "month": month_text(month), "count": count}})

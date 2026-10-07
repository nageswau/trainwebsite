"""bdm-016 (DEC-SCOPE-100, spec §2, §5): monthly target rules, the target sheet, the batch save and the copy.

Functions only; nothing here commits -- the route owns the transaction. Achieved is never stored: the sheet reads it live from
`bdm_metrics.monthly_counts`. Every change is audited in the same transaction, one row per BDM, with KPI keys and numbers only."""

import logging
from collections import defaultdict
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, BdmProfile, BdmTarget, User
from app.schemas import BdmTargetItem
from app.services.bdm import team_filter
from app.services.bdm_metrics import TARGET_KPIS, TARGET_METRICS, monthly_counts

logger = logging.getLogger("app.bdm")

MONTHS_AHEAD = 12  # R3
PAST_LOCKED = "Past months' targets can only be changed by a super admin"
TOO_FAR = f"Targets can be set up to {MONTHS_AHEAD} months ahead"
INACTIVE = "This BDM is inactive, so their targets can't be changed"
BDM_NOT_FOUND = "BDM not found"
TYPE_LABEL = {"agent": "Agent", "school": "School", "college": "College"}


def parse_month(raw: str | None, current: date) -> date:
    """`YYYY-MM` (the route's pattern already checked the shape) → the month's first day; none → the current IST month."""
    return date(int(raw[:4]), int(raw[5:]), 1) if raw else current


def month_text(month: date) -> str:
    return month.strftime("%Y-%m")


def shift(month: date, months: int) -> date:
    index = month.year * 12 + month.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _ahead(month: date, current: date) -> int:
    return (month.year - current.year) * 12 + month.month - current.month


def month_status(month: date, current: date) -> str:
    ahead = _ahead(month, current)
    return "past" if ahead < 0 else "current" if ahead == 0 else "future"


def edit_refusal(user: User, month: date, current: date) -> str | None:
    """R3 (AC4): the current month and up to 12 ahead; a past month only by super_admin."""
    ahead = _ahead(month, current)
    if ahead > MONTHS_AHEAD:
        return TOO_FAR
    if ahead < 0 and user.role != "super_admin":
        return PAST_LOCKED
    return None


def check_editable(user: User, month: date, current: date) -> None:
    if refusal := edit_refusal(user, month, current):
        raise HTTPException(422, refusal)


def _percent(target: int | None, achieved: int | None) -> int | None:
    """R5: achieved ÷ target as a whole percent; no target, a target of 0 or no achieved figure → none ("—")."""
    return round(achieved * 100 / target) if target and achieved is not None else None


async def sheet(db: AsyncSession, bdm: User, bdm_type: str, month: date, current: date, *, editable: bool) -> dict:
    """The BDM's KPIs for the month: target (set or not), achieved live (none before the month starts, R6), percent."""
    rows = await db.execute(select(BdmTarget.kpi_key, BdmTarget.target).where(BdmTarget.bdm_user_id == bdm.id, BdmTarget.month == month))
    targets = dict(rows.all())
    status = month_status(month, current)
    kpis = await monthly_counts(db, bdm.id, bdm_type, month, future=status == "future")
    for kpi in kpis:
        kpi["target"] = targets.get(kpi["key"])
        kpi["percent"] = _percent(kpi["target"], kpi["achieved"])
    return {"month": month_text(month), "month_status": status, "editable": editable, "bdm": {"id": bdm.id, "full_name": bdm.full_name},
            "bdm_type": bdm_type, "kpis": kpis}


async def targets_set(db: AsyncSession, bdm_ids: list[UUID], month: date) -> dict[UUID, int]:
    rows = await db.execute(select(BdmTarget.bdm_user_id, func.count()).where(BdmTarget.bdm_user_id.in_(bdm_ids), BdmTarget.month == month)
                            .group_by(BdmTarget.bdm_user_id))
    return dict(rows.all())


async def _team_members(db: AsyncSession, actor: User, bdm_ids: set[UUID]) -> dict[UUID, tuple[User, BdmProfile]]:
    """R9: every BDM named must be in the actor's team (404 otherwise, as a missing one) and active (422)."""
    rows = await db.execute(select(User, BdmProfile).join(BdmProfile, BdmProfile.user_id == User.id).where(User.id.in_(bdm_ids), *team_filter(actor)))
    members = {user.id: (user, profile) for user, profile in rows.all()}
    if set(members) != bdm_ids:
        raise HTTPException(404, BDM_NOT_FOUND)
    if any(not user.active for user, _ in members.values()):
        raise HTTPException(422, INACTIVE)
    return members


def _check_kpi(item: BdmTargetItem, bdm_type: str) -> None:
    """AC2: a KPI outside the BDM type's catalogue is refused by name."""
    if item.kpi_key not in TARGET_KPIS[bdm_type]:
        name = TARGET_METRICS[item.kpi_key][0] if item.kpi_key in TARGET_METRICS else item.kpi_key
        raise HTTPException(422, f"{name} is not a target KPI for {TYPE_LABEL[bdm_type]} BDMs")


async def save(db: AsyncSession, actor: User, month: date, items: list[BdmTargetItem]) -> int:
    """Validate the whole batch first (nothing is written on any refusal), then upsert / clear only the values that change."""
    members = await _team_members(db, actor, {i.bdm_user_id for i in items})
    for item in items:
        _check_kpi(item, members[item.bdm_user_id][1].bdm_type)
    pairs = [(i.bdm_user_id, i.kpi_key) for i in items]
    existing = await db.execute(
        select(BdmTarget.bdm_user_id, BdmTarget.kpi_key, BdmTarget.target)
        .where(BdmTarget.month == month, tuple_(BdmTarget.bdm_user_id, BdmTarget.kpi_key).in_(pairs))
        .with_for_update()
    )
    old = {(bdm, kpi): target for bdm, kpi, target in existing.all()}
    changes: dict[UUID, list[dict]] = defaultdict(list)
    for item in items:
        before = old.get((item.bdm_user_id, item.kpi_key))
        if before == item.target:
            continue
        changes[item.bdm_user_id].append({"kpi": item.kpi_key, "from": before, "to": item.target})
        if item.target is None:
            await db.execute(delete(BdmTarget).where(BdmTarget.bdm_user_id == item.bdm_user_id, BdmTarget.month == month, BdmTarget.kpi_key == item.kpi_key))
            continue
        values = {"target": item.target, "set_by_user_id": actor.id, "set_at": func.now(), "updated_at": func.now()}
        # Two managers saving the same new KPI at once: the unique key turns the second insert into an update (last write wins).
        await db.execute(insert(BdmTarget).values(bdm_user_id=item.bdm_user_id, month=month, kpi_key=item.kpi_key, **values)
                         .on_conflict_do_update(constraint="uq_bdm_targets_bdm_month_kpi", set_=values))
    for bdm_id, changed in changes.items():
        _audit(db, actor, "set", bdm_id, {"month": month_text(month), "changes": changed})
    return sum(len(c) for c in changes.values())


async def copy_previous(db: AsyncSession, actor: User, month: date) -> int:
    """R8: last month's targets of the actor's active team BDMs, into `month`, only where no target is set yet and only catalogue KPIs."""
    source = shift(month, -1)
    rows = await db.execute(
        select(BdmTarget.bdm_user_id, BdmTarget.kpi_key, BdmTarget.target, BdmProfile.bdm_type)
        .join(BdmProfile, BdmProfile.user_id == BdmTarget.bdm_user_id)
        .join(User, User.id == BdmTarget.bdm_user_id)
        .where(BdmTarget.month == source, User.active.is_(True), *team_filter(actor))
    )
    values = [{"bdm_user_id": bdm, "month": month, "kpi_key": kpi, "target": target, "set_by_user_id": actor.id}
              for bdm, kpi, target, bdm_type in rows.all() if kpi in TARGET_KPIS[bdm_type]]
    if not values:
        return 0
    inserted = await db.execute(
        insert(BdmTarget).values(values).on_conflict_do_nothing(constraint="uq_bdm_targets_bdm_month_kpi").returning(BdmTarget.bdm_user_id, BdmTarget.kpi_key)
    )
    copied: dict[UUID, list[str]] = defaultdict(list)
    for bdm, kpi in inserted.all():
        copied[bdm].append(kpi)
    for bdm_id, kpis in copied.items():
        _audit(db, actor, "copied", bdm_id, {"month": month_text(month), "from_month": month_text(source), "kpis": sorted(kpis)})
    return sum(len(k) for k in copied.values())


def _audit(db: AsyncSession, actor: User, action: str, bdm_id: UUID, metadata: dict) -> None:
    """Same transaction as the write (fail closed). The entity is the BDM whose targets changed."""
    db.add(AuditLog(user_id=actor.id, action=f"bdm_target.{action}", entity_type="bdm_targets", entity_id=str(bdm_id), metadata_json=metadata))


def log(event: str, actor: User, month: date, count: int) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(actor.id), "month": month_text(month), "count": count}})

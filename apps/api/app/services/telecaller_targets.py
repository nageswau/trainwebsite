"""tel-022 (DEC-SCOPE-078, spec §4-§5): target subjects, the date rules and effective-target resolution -- the one function tel-021's
dashboard and tel-023's comparison will call for "achieved / target".

Functions only; nothing here commits -- the route owns the transaction. Audit rows carry ids and KPI keys only."""

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TEL_TARGET_KPIS, AuditLog, TelecallerProfile, TelTarget, User
from app.schemas import TelTargetSet

NOT_FOUND = "Telecaller not found"


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month(day: date) -> date:
    return (month_start(day) + timedelta(days=32)).replace(day=1)


def earliest_from(period: str, today: date) -> date:
    """G2 / T28: a change applies from the next day (daily) or the next month (monthly) -- never to today or this month."""
    return today + timedelta(days=1) if period == "daily" else next_month(today)


def check_effective_from(period: str, chosen: date | None, today: date) -> date:
    earliest = earliest_from(period, today)
    if chosen is None:
        return earliest
    if period == "monthly" and chosen.day != 1:
        raise HTTPException(422, "A monthly target starts on the 1st of a month")
    if chosen < earliest:
        raise HTTPException(422, f"{period.capitalize()} targets can start on {earliest:%d %b %Y} or later")
    return chosen


def check_shape(data: TelTargetSet) -> None:
    if data.scope == "team":
        if data.team is None:
            raise HTTPException(422, "Choose a team")
        if data.user_id is not None:
            raise HTTPException(422, "A team default cannot name a telecaller")
        if any(value is None for value in data.values.values()):
            raise HTTPException(422, "A team default cannot be removed; enter a number")
    else:
        if data.user_id is None:
            raise HTTPException(422, "Choose a telecaller")
        if data.team is not None:
            raise HTTPException(422, "A telecaller override cannot name a team")


async def telecaller_in_scope(db: AsyncSession, actor: User, user_id, *, lock: bool = False) -> tuple[User, TelecallerProfile]:
    """T23: a manager's subjects are exactly their direct reports; super_admin's are every telecaller. Anyone else's id is a 404, so a
    manager cannot learn who reports to someone else. `lock` reads the profile FOR SHARE: a concurrent change of manager waits."""
    stmt = select(TelecallerProfile, User).join(User, User.id == TelecallerProfile.user_id).where(TelecallerProfile.user_id == user_id, User.role == "telecaller")
    if actor.role != "super_admin":
        stmt = stmt.where(TelecallerProfile.reporting_manager_user_id == actor.id)
    if lock:
        stmt = stmt.with_for_update(read=True, of=TelecallerProfile)
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(404, NOT_FOUND)
    profile, user = row
    return user, profile


async def save_targets(db: AsyncSession, actor: User, data: TelTargetSet, effective_from: date) -> None:
    """One upsert per KPI on the subject's partial unique index: re-saving a pending date replaces it (AC8), and two managers saving
    the same date at once cannot race into a duplicate. The date rule above guarantees only future rows are ever updated."""
    team_scope = data.scope == "team"
    subject = {"team": data.team} if team_scope else {"user_id": data.user_id}
    rows = [{"scope": data.scope, **subject, "period": data.period, "kpi": kpi, "value": value, "effective_from": effective_from, "set_by_user_id": actor.id} for kpi, value in data.values.items()]
    stmt = insert(TelTarget).values(rows)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["team" if team_scope else "user_id", "period", "kpi", "effective_from"],
            index_where=TelTarget.scope == data.scope,
            set_={"value": stmt.excluded.value, "set_by_user_id": stmt.excluded.set_by_user_id, "updated_at": func.now()},
        )
    )
    db.add(
        AuditLog(
            user_id=actor.id,
            action="telecaller.target_set",
            entity_type="tel_target_subject",
            entity_id=str(data.team or data.user_id),
            metadata_json={"scope": data.scope, "period": data.period, "effective_from": effective_from.isoformat(), "kpis": sorted(data.values)},
        )
    )


async def _latest(db: AsyncSession, subject, day: date) -> dict[tuple[str, str], int | None]:
    """The newest row per (period, KPI) on or before each period's key date: the day itself (daily) or its month's 1st (monthly)."""
    stmt = (
        select(TelTarget.period, TelTarget.kpi, TelTarget.value)
        .where(subject, ((TelTarget.period == "daily") & (TelTarget.effective_from <= day)) | ((TelTarget.period == "monthly") & (TelTarget.effective_from <= month_start(day))))
        .distinct(TelTarget.period, TelTarget.kpi)
        .order_by(TelTarget.period, TelTarget.kpi, TelTarget.effective_from.desc())
    )
    return {(period, kpi): value for period, kpi, value in (await db.execute(stmt)).all()}


async def effective_targets(db: AsyncSession, team: str, user_id, day: date) -> dict[str, list[dict]]:
    """AC1: a non-null override beats the team default; a null override (removed) or none falls back to the team's current value."""
    team_values = await _latest(db, (TelTarget.scope == "team") & (TelTarget.team == team), day)
    user_values = await _latest(db, (TelTarget.scope == "user") & (TelTarget.user_id == user_id), day) if user_id else {}

    def resolve(period: str, kpi: str) -> dict:
        if user_values.get((period, kpi)) is not None:
            return {"kpi": kpi, "value": user_values[(period, kpi)], "source": "user"}
        value = team_values.get((period, kpi))
        return {"kpi": kpi, "value": value, "source": "team" if value is not None else None}

    return {period: [resolve(period, kpi) for kpi in TEL_TARGET_KPIS] for period in ("daily", "monthly")}

"""tel-022 (DEC-SCOPE-078, spec §5): daily + monthly targets. Managers and super_admin set team defaults (both teams, G3) and
overrides for their direct reports (T23); a telecaller reads only their own effective targets (§22 line 713: never writes).

Inline checks per the 2026-09-28 convention: role first, then scope (an out-of-scope telecaller is a 404), then the write. Days are
IST calendar days on the database clock (G1: every day counts; no working-day calendar)."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import TelecallerProfile, TelTarget, User
from app.schemas import TEL_TARGET_FIELD_LABELS, TelTargetEffectiveOut, TelTargetKpi, TelTargetPage, TelTargetPeriod, TelTargetSet, TelTargetSetOut
from app.services.bdm_appointments import db_now, today_ist
from app.services.telecaller import _parse, require_manager
from app.services.telecaller_targets import check_effective_from, check_shape, effective_targets, month_start, save_targets, telecaller_in_scope

router = APIRouter(prefix="/telecaller", tags=["telecaller-targets"])
Subject, SetBy = aliased(User), aliased(User)


def _person(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name} if user else None


@router.post("/targets", response_model=TelTargetSetOut)
async def set_targets(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """An idempotent upsert keyed by (subject, period, KPI, date), hence 200. A null value removes an override from its date (AC7)."""
    require_manager(user)
    data = _parse(TelTargetSet, payload, "The request body must be an object", TEL_TARGET_FIELD_LABELS)
    check_shape(data)
    subject = None
    if data.scope == "user":
        subject, _profile = await telecaller_in_scope(db, user, data.user_id, lock=True)
        if not subject.active:
            raise HTTPException(422, "This telecaller is inactive")
    effective_from = check_effective_from(data.period, data.effective_from, today_ist(await db_now(db)))
    await save_targets(db, user, data, effective_from)
    out = {"scope": data.scope, "team": data.team, "user": _person(subject), "period": data.period, "effective_from": effective_from, "values": data.values}
    await db.commit()
    return out


@router.get("/targets", response_model=TelTargetPage)
async def target_history(
    scope: Literal["team", "user"] | None = None,
    team: Literal["it", "overseas"] | None = None,
    user_id: UUID | None = None,
    period: TelTargetPeriod | None = None,
    kpi: TelTargetKpi | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T28 history, newest start first. A manager sees every team row plus their direct reports' rows; super_admin sees all."""
    require_manager(user)
    filters = []
    if user_id:
        await telecaller_in_scope(db, user, user_id)
        filters.append(TelTarget.user_id == user_id)
    elif user.role != "super_admin":
        reports = select(TelecallerProfile.user_id).where(TelecallerProfile.reporting_manager_user_id == user.id)
        filters.append(or_(TelTarget.scope == "team", TelTarget.user_id.in_(reports)))
    for column, value in ((TelTarget.scope, scope), (TelTarget.team, team), (TelTarget.period, period), (TelTarget.kpi, kpi)):
        if value:
            filters.append(column == value)
    stmt = select(TelTarget, Subject, SetBy).outerjoin(Subject, Subject.id == TelTarget.user_id).join(SetBy, SetBy.id == TelTarget.set_by_user_id).where(*filters)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = (TelTarget.effective_from.desc(), TelTarget.period, TelTarget.kpi, TelTarget.id)
    rows = (await db.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()
    items = [
        {
            "id": t.id,
            "scope": t.scope,
            "team": t.team,
            "user": _person(subject),
            "period": t.period,
            "kpi": t.kpi,
            "value": t.value,
            "effective_from": t.effective_from,
            "set_by": _person(set_by),
            "updated_at": t.updated_at,
        }
        for t, subject, set_by in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


@router.get("/targets/effective", response_model=TelTargetEffectiveOut)
async def targets_in_effect(
    user_id: UUID | None = None,
    team: Literal["it", "overseas"] | None = None,
    date: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A telecaller: their own targets only (another user or a team → 403). A manager: exactly one of a direct report or a team."""
    day = date or today_ist(await db_now(db))
    subject = None
    if user.role == "telecaller":
        if team is not None or user_id not in (None, user.id):
            raise HTTPException(403, "You can only view your own targets")
        profile = await db.scalar(select(TelecallerProfile).where(TelecallerProfile.user_id == user.id))
        if not profile:
            raise HTTPException(403, "Telecaller profile not set up — contact your administrator")
        subject, team = user, profile.team
    else:
        require_manager(user)
        if (user_id is None) == (team is None):
            raise HTTPException(422, "Choose either a telecaller or a team")
        if user_id is not None:
            subject, profile = await telecaller_in_scope(db, user, user_id)
            team = profile.team
    targets = await effective_targets(db, team, subject.id if subject else None, day)
    return {"date": day, "month": month_start(day), "team": team, "user": _person(subject), **targets}

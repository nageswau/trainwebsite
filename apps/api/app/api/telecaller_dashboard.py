"""tel-021 (DEC-SCOPE-105, API §12X): the telecaller dashboard and the daily activity -- every figure computed by
`services/telecaller_metrics.py` (T27: nothing typed). Read-only routes; each is one request for the page that shows it.

Scope (DB6, T24): a telecaller reads only their own figures (another user id → 403); a manager reads a direct report's activity and
super_admin any telecaller's (an id out of scope → 404, as tel-022). Every other role → 403.

tel-023 (DEC-SCOPE-112, API §12AF): the performance comparison and its CSV, for managers, division admins and super_admin (PF1)."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE, to_csv
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, User
from app.services import telecaller_metrics as metrics
from app.services import telecaller_performance as performance
from app.services.bdm_appointments import db_now, today_ist
from app.services.telecaller import require_manager, telecaller_context
from app.services.telecaller_targets import telecaller_in_scope

router = APIRouter(prefix="/telecaller", tags=["telecaller-dashboard"])

FUTURE_DAY = "Daily activity can't be shown for a future date"
OWN_ONLY = "You can only view your own activity"


@router.get("/dashboard")
async def dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§1 + §15: today's ten tiles, target progress (today and month to date) and today's appointments (DB3)."""
    profile = await telecaller_context(db, user)
    now = await db_now(db)
    return {
        "day": today_ist(now),
        "tiles": await metrics.tiles(db, user.id, profile.team, now),
        "targets": await metrics.target_progress(db, user.id, profile.team, now),
        "appointments": await metrics.appointments_today(db, user.id, now),
    }


@router.get("/activity")
async def activity(
    date: date | None = None,
    user_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """§14: the 13 counts for one IST day (default today) beside that day's daily targets."""
    if user.role == "telecaller":
        if user_id not in (None, user.id):
            raise HTTPException(403, OWN_ONLY)
        subject, team = user, (await telecaller_context(db, user)).team
    else:
        require_manager(user)
        if user_id is None:
            raise HTTPException(422, "Choose a telecaller")
        subject, profile = await telecaller_in_scope(db, user, user_id)
        team = profile.team
    now = await db_now(db)
    day = date or today_ist(now)
    if day > today_ist(now):
        raise HTTPException(422, FUTURE_DAY)
    counts = await metrics.daily_activity(db, subject.id, day, now)
    return {
        "day": day,
        "user": {"id": subject.id, "full_name": subject.full_name},
        "counts": counts,
        "targets": await metrics.day_targets(db, subject.id, team, day, counts),
    }


async def _performance(
    date_from: date | None = None,
    date_to: date | None = None,
    team: Literal["it", "overseas"] | None = None,
    sort: Literal[performance.SORTS] = "calls",
    direction: Literal["asc", "desc"] = Query("desc", alias="dir"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, dict]:
    scoped = performance.scope(user, team)  # 403 before the range rules
    first, last = performance.date_range(date_from, date_to, today_ist(await db_now(db)))
    return user, await performance.performance(db, scoped, team=team, first=first, last=last, sort=sort, direction=direction)


# Registered before the JSON route, as the reports routers do.
@router.get("/manager/performance.csv")
async def performance_csv(read: tuple[User, dict] = Depends(_performance), db: AsyncSession = Depends(get_db)):
    """CSV = the screen (same columns, rows, order and Total). One audit row, committed before the file is returned (fail closed)."""
    user, payload = read
    body = to_csv(payload)
    db.add(AuditLog(user_id=user.id, action="telecaller_performance.export", entity_type="telecaller_performance", entity_id="performance", metadata_json={
        "date_from": payload["date_from"].isoformat(), "date_to": payload["date_to"].isoformat(), "team": payload["team"],
        "sort": payload["sort"], "dir": payload["dir"], "rows": len(payload["items"]),
    }))
    await db.commit()
    filename = f"telecaller-performance-{payload['date_from']}-to-{payload['date_to']}.csv"
    return Response(content=body, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"', **NO_STORE})


@router.get("/manager/performance")
async def performance_report(response: Response, read: tuple[User, dict] = Depends(_performance)):
    """§16: P1-P6 per telecaller in scope over the range, sorted, with a Total row."""
    response.headers.update(NO_STORE)
    return read[1]

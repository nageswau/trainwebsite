"""pob-009 (spec docs/superpowers/specs/2026-11-07-pob-009-po-targets-reports-design.md): PO targets, territories, target companies, the
daily plan and daily/weekly activity reports.

T1: the PO routes are `placement_team`'s own (`recruiter_context`); `/manager/*` is the Team Lead's (`placement_manager`) and super_admin's,
on direct reports only (a PO outside the team is 404). Every write is one transaction: rules (422 / 404 / 409), change, audit, one commit
here, log."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import RecruiterActivityReport, User
from app.schemas import BDM_TARGET_MONTH_PATTERN, PoPlanItemAdd, PoPlanItemPatch, PoReportSubmit, PoTargetCompaniesAdd, PoTargetsPut, PoTerritoryPut
from app.services import recruiter_metrics as metrics
from app.services import recruiter_po_work as svc
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.bdm_targets import check_editable, edit_refusal, parse_month
from app.services.recruiter import recruiter_context, require_manager

router = APIRouter(prefix="/recruiter", tags=["recruiter-po-work"])
MONTH = Query(None, pattern=BDM_TARGET_MONTH_PATTERN, description="IST month, YYYY-MM (default the current month)")
Period = Literal["daily", "weekly"]


async def _today(db: AsyncSession) -> date:
    return india_date(await db_now(db))


# --- T3 targets (AC2), T4 territory, T5 target companies -----------------------------------------------------------------------------
@router.get("/targets")
async def my_targets(month: str | None = MONTH, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await recruiter_context(db, user)
    today = await _today(db)
    current = today.replace(day=1)
    return await svc.sheet(db, user, profile, parse_month(month, current), current, today, editable=False)


@router.get("/manager/targets")
async def team_targets(month: str | None = MONTH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    today = await _today(db)
    current = today.replace(day=1)
    return await svc.team_sheet(db, user, parse_month(month, current), current, today, limit, offset)


@router.get("/manager/targets/{recruiter_user_id}")
async def member_targets(recruiter_user_id: UUID, month: str | None = MONTH, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    po, profile = await svc.team_member(db, user, recruiter_user_id)
    today = await _today(db)
    current = today.replace(day=1)
    chosen = parse_month(month, current)
    return await svc.sheet(db, po, profile, chosen, current, today, editable=po.active and edit_refusal(user, chosen, current) is None)


@router.put("/manager/targets")
async def save_targets(payload: PoTargetsPut, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Batch upsert (a null target clears it). All or nothing: any refusal writes nothing."""
    require_manager(user)
    current = (await _today(db)).replace(day=1)
    month = parse_month(payload.month, current)
    check_editable(user, month, current)
    changed = await svc.save_targets(db, user, month, payload.items)
    await db.commit()
    svc.log("recruiter_targets_saved", user, month=payload.month, changed=changed)
    return {"month": payload.month, "changed": changed}


@router.put("/manager/team/{recruiter_user_id}/territory")
async def set_territory(recruiter_user_id: UUID, payload: PoTerritoryPut, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    out = await svc.set_territory(db, user, recruiter_user_id, payload.territory)
    await db.commit()
    svc.log("recruiter_territory_set", user, recruiter=recruiter_user_id)
    return out


@router.post("/manager/target-companies", status_code=201)
async def add_target_companies(payload: PoTargetCompaniesAdd, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    current = (await _today(db)).replace(day=1)
    month = parse_month(payload.month, current)
    check_editable(user, month, current)
    added = await svc.add_target_companies(db, user, payload.recruiter_user_id, month, payload.company_ids, payload.territory)
    await db.commit()
    svc.log("recruiter_target_companies_added", user, recruiter=payload.recruiter_user_id, added=added)
    return {"month": payload.month, "added": added}


@router.delete("/manager/target-companies/{row_id}", status_code=204)
async def remove_target_company(row_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.remove_target_company(db, user, row_id)
    await db.commit()
    svc.log("recruiter_target_company_removed", user, row=row_id)


# --- T6 the daily plan ---------------------------------------------------------------------------------------------------------------
@router.get("/daily-plan")
async def my_plan(day: date | None = Query(None, alias="date", description="IST date (default today)"), user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    await recruiter_context(db, user)
    today = await _today(db)
    return await svc.plan(db, user, day or today, today)


@router.post("/daily-plan/items", status_code=201)
async def add_plan_item(payload: PoPlanItemAdd, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await recruiter_context(db, user)
    today = await _today(db)
    await svc.lock_plan(db, user)
    item = await svc.add_plan_item(db, user, today, payload.follow_up_id, payload.company_id)
    try:
        await db.flush()
    except IntegrityError as exc:  # the partial unique indexes back the duplicate check
        await db.rollback()
        raise HTTPException(409, svc.ALREADY_PLANNED) from exc
    await db.commit()
    svc.log("recruiter_plan_item_added", user, item=item.id)
    return svc.plan_item_out(item)


@router.patch("/daily-plan/items/{item_id}")
async def mark_plan_item(item_id: UUID, payload: PoPlanItemPatch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await recruiter_context(db, user)
    item = await svc.own_plan_item(db, user, item_id, await _today(db))
    item.done_at = await db_now(db) if payload.done else None
    await db.commit()
    return svc.plan_item_out(item)


@router.delete("/daily-plan/items/{item_id}", status_code=204)
async def remove_plan_item(item_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await recruiter_context(db, user)
    item = await svc.own_plan_item(db, user, item_id, await _today(db))
    await db.delete(item)
    await db.commit()


# --- T7 activity reports (AC3), T8 the drill-down (AC1) ------------------------------------------------------------------------------
@router.get("/activity-reports/{period}/{start}")
async def my_report(period: Period, start: date, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await recruiter_context(db, user)
    today = await _today(db)
    svc.period_dates(period, start, today)
    return await svc.report_out(db, user, period, start, today, await svc.submitted(db, user.id, period, start))


@router.post("/activity-reports/{period}/{start}/submit", status_code=201)
async def submit_report(period: Period, start: date, payload: PoReportSubmit, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """T7: the counts are frozen at submission; a second submission is 409 (the unique key backs the check)."""
    await recruiter_context(db, user)
    today = await _today(db)
    first, last = svc.period_dates(period, start, today)
    if await svc.submitted(db, user.id, period, first):
        raise HTTPException(409, svc.ALREADY_SUBMITTED)
    report = RecruiterActivityReport(recruiter_user_id=user.id, period=period, period_start=first, note=payload.note or None,
                                     counts=await svc.live_counts(db, user, period, first, last, today))
    db.add(report)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, svc.ALREADY_SUBMITTED) from exc
    svc.audit(db, user, "recruiter_activity_report.submitted", "recruiter_activity_reports", report.id, {"period": period, "period_start": str(first)})
    await db.commit()
    svc.log("recruiter_activity_report_submitted", user, period=period, start=first)
    return await svc.report_out(db, user, period, first, today, report)


@router.get("/activity-contacts")
async def activity_contacts(period: Period, start: date, recruiter_id: UUID | None = None, limit: int = LIMIT, offset: int = OFFSET,
                            user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    po = await svc.subject(db, user, recruiter_id)
    today = await _today(db)
    first, last = svc.period_dates(period, start, today)
    return {"recruiter": {"id": po.id, "full_name": po.full_name}} | await metrics.po_contacts(db, po.id, first, min(last, today), limit=limit, offset=offset)


@router.get("/manager/activity-reports")
async def team_reports(period: Period, start: date, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    return await svc.team_reports(db, user, period, start, await _today(db), limit, offset)


@router.get("/manager/activity-reports/{recruiter_user_id}/{period}/{start}")
async def member_report(recruiter_user_id: UUID, period: Period, start: date, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    po, _ = await svc.team_member(db, user, recruiter_user_id)
    today = await _today(db)
    svc.period_dates(period, start, today)
    return await svc.report_out(db, po, period, start, today, await svc.submitted(db, po.id, period, start))

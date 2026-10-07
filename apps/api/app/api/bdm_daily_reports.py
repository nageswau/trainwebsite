"""bdm-015 (DEC-SCOPE-096, spec §5): the BDM daily activity report.

A BDM reads and submits only their own report (`bdm_context`; no route names another BDM, so "submitting for another BDM" is the 403
of every non-BDM caller). Managers read their team's reports and comment (`require_manager` + `team_filter`; a BDM outside the team
is the same 404 as a missing one). Every write is one transaction: lock, rules (422 / 409), change, audit, one commit here."""

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmDailyReport, BdmProfile, User
from app.schemas import BdmDailyReportCommentIn, BdmDailyReportGrid, BdmDailyReportOut, BdmDailyReportSubmit
from app.services import bdm_daily_reports as svc
from app.services.bdm import bdm_context, require_manager, team_filter
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.bdm_metrics import daily_counts

router = APIRouter(prefix="/bdm", tags=["bdm-daily-reports"])
GRID_DAYS = 7  # R8: the chosen day and the six before it


@router.get("/daily-reports/{report_date}", response_model=BdmDailyReportOut)
async def my_report(report_date: date, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await bdm_context(db, user)
    today = india_date(await db_now(db))
    svc.check_not_future(report_date, today)
    return await svc.report_out(db, user, profile.bdm_type, report_date, today, await svc.submitted(db, user.id, report_date))


@router.post("/daily-reports/{report_date}/submit", status_code=201, response_model=BdmDailyReportOut)
async def submit_report(report_date: date, payload: BdmDailyReportSubmit, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await bdm_context(db, user)
    today = india_date(await db_now(db))
    svc.check_not_future(report_date, today)
    if not svc.can_submit(report_date, today):
        raise HTTPException(422, svc.TOO_OLD)
    await svc.lock_day(db, user.id, report_date)  # R5: no activity write of this day runs between the counts and the insert
    if await svc.submitted(db, user.id, report_date):
        raise HTTPException(409, svc.ALREADY_SUBMITTED)
    report = BdmDailyReport(bdm_user_id=user.id, report_date=report_date, bdm_type=profile.bdm_type, note=payload.note, counts=await daily_counts(db, user.id, profile.bdm_type, report_date))
    db.add(report)
    try:
        await db.flush()
    except IntegrityError as exc:  # the unique constraint is the backstop behind the lock
        await db.rollback()
        raise HTTPException(409, svc.ALREADY_SUBMITTED) from exc
    svc.audit(db, user, "submitted", report)
    await db.commit()
    svc.log("bdm_daily_report_submitted", user, report)
    return await svc.report_out(db, user, profile.bdm_type, report_date, today, report)


async def _member(db: AsyncSession, manager: User, bdm_user_id: UUID) -> tuple[User, BdmProfile]:
    row = (await db.execute(select(User, BdmProfile).join(BdmProfile, BdmProfile.user_id == User.id).where(User.id == bdm_user_id, *team_filter(manager)))).first()
    if row is None:
        raise HTTPException(404, svc.BDM_NOT_FOUND)
    return row[0], row[1]


@router.get("/manager/daily-reports", response_model=BdmDailyReportGrid)
async def team_reports(
    day: date | None = Query(None, alias="date", description="IST date, YYYY-MM-DD; the grid's last day (default today)"),
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """R8: active team BDMs × seven days. Two queries: the page of BDMs, then their reports in the window."""
    require_manager(user)
    today = india_date(await db_now(db))
    last = day or today
    svc.check_not_future(last, today)
    dates = [last - timedelta(days=n) for n in range(GRID_DAYS - 1, -1, -1)]
    members = select(User, BdmProfile).join(BdmProfile, BdmProfile.user_id == User.id).where(User.active.is_(True), *team_filter(user))
    total = await db.scalar(select(func.count()).select_from(members.subquery()))
    rows = (await db.execute(members.order_by(User.full_name, User.id).limit(limit).offset(offset))).all()
    reports = {}
    if rows:
        found = await db.execute(
            select(BdmDailyReport.bdm_user_id, BdmDailyReport.report_date, BdmDailyReport.submitted_at).where(
                BdmDailyReport.bdm_user_id.in_([u.id for u, _ in rows]), BdmDailyReport.report_date.between(dates[0], dates[-1])
            )
        )
        reports = {(bdm_id, d): at for bdm_id, d, at in found}

    def status(member: User, profile: BdmProfile, d: date) -> dict:
        at = reports.get((member.id, d))
        if at is not None:
            return {"report_date": d, "status": "submitted", "submitted_at": at}
        started = d >= india_date(profile.created_at)  # no "missing" for days before the BDM's profile existed
        return {"report_date": d, "status": "missing" if started else "not_started", "submitted_at": None}

    items = [{"bdm": {"id": m.id, "full_name": m.full_name}, "bdm_type": p.bdm_type, "days": [status(m, p, d) for d in dates]} for m, p in rows]
    return {"dates": dates, "items": items, "total": total or 0, "limit": limit, "offset": offset}


@router.get("/manager/daily-reports/{bdm_user_id}/{report_date}", response_model=BdmDailyReportOut)
async def team_report(bdm_user_id: UUID, report_date: date, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    member, profile = await _member(db, user, bdm_user_id)
    today = india_date(await db_now(db))
    svc.check_not_future(report_date, today)
    report = await svc.submitted(db, member.id, report_date)
    return await svc.report_out(db, member, profile.bdm_type, report_date, today, report, submitter=False)


@router.put("/manager/daily-reports/{bdm_user_id}/{report_date}/comment", response_model=BdmDailyReportOut)
async def comment_report(bdm_user_id: UUID, report_date: date, payload: BdmDailyReportCommentIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """R7 (D22): one comment per submitted report; a later comment replaces it."""
    require_manager(user)
    member, profile = await _member(db, user, bdm_user_id)
    report = await svc.submitted(db, member.id, report_date, lock=True)
    if report is None:
        raise HTTPException(409, svc.NOT_SUBMITTED)
    now = await db_now(db)
    report.manager_comment, report.manager_comment_by_user_id, report.manager_commented_at = payload.comment, user.id, now
    svc.audit(db, user, "commented", report)
    await db.commit()
    svc.log("bdm_daily_report_commented", user, report)
    return await svc.report_out(db, member, profile.bdm_type, report_date, india_date(now), report, submitter=False)

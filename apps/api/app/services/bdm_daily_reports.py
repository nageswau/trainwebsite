"""bdm-015 (DEC-SCOPE-099, spec §5): daily report rules, the day lock, the report shape and audit.

Functions only; nothing here commits -- the route owns the transaction. A report row exists only once submitted; before that the report
is a live preview of `bdm_metrics.daily_counts`. Submitting and every activity write for the same BDM and IST day take one advisory
lock (`lock_day`), so an activity is either in the snapshot or refused. Audit rows and logs carry ids and dates -- never the note or
the comment."""

import logging
from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, BdmDailyReport, User
from app.services.bdm_activities import BACKDATE_DAYS, FUTURE_DAY
from app.services.bdm_metrics import daily_counts

logger = logging.getLogger("app.bdm")

SUBMIT_WINDOW_DAYS = BACKDATE_DAYS  # R3: the activity log's backdate window
TOO_OLD = f"Reports can be submitted up to {SUBMIT_WINDOW_DAYS} days back"
ALREADY_SUBMITTED = "This day's report has already been submitted"
DAY_LOCKED = "This day's report has been submitted, so its activities can't be changed"
NOT_SUBMITTED = "This report hasn't been submitted yet"
BDM_NOT_FOUND = "BDM not found"


def check_not_future(day: date, today: date) -> None:
    if day > today:
        raise HTTPException(422, FUTURE_DAY)


def can_submit(day: date, today: date) -> bool:
    return today - timedelta(days=SUBMIT_WINDOW_DAYS) <= day <= today


async def lock_day(db: AsyncSession, bdm_user_id: UUID, day: date) -> None:
    """Serializes a submit with every activity write of the same BDM and day (transaction-scoped; released at commit/rollback)."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"bdm_daily_report:{bdm_user_id}:{day}"})


async def submitted(db: AsyncSession, bdm_user_id: UUID, day: date, *, lock: bool = False) -> BdmDailyReport | None:
    stmt = select(BdmDailyReport).where(BdmDailyReport.bdm_user_id == bdm_user_id, BdmDailyReport.report_date == day)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(stmt)


async def check_day_open(db: AsyncSession, bdm_user_id: UUID, day: date) -> None:
    """bdm-009 AC4 / R5: an activity write onto a submitted day is refused. Takes the day lock first."""
    await lock_day(db, bdm_user_id, day)
    if await submitted(db, bdm_user_id, day):
        raise HTTPException(409, DAY_LOCKED)


async def report_out(db: AsyncSession, bdm: User, bdm_type: str, day: date, today: date, report: BdmDailyReport | None, *, submitter: bool = True) -> dict:
    """`submitter` is False for a manager's read: only the BDM submits, so `can_submit` is never offered there."""
    comment = None
    if report and report.manager_comment:
        author = (await db.execute(select(User).where(User.id == report.manager_comment_by_user_id))).scalar_one()
        comment = {"text": report.manager_comment, "by": {"id": author.id, "full_name": author.full_name}, "at": report.manager_commented_at}
    return {
        "report_date": day,
        "bdm": {"id": bdm.id, "full_name": bdm.full_name},
        "bdm_type": report.bdm_type if report else bdm_type,
        "status": "submitted" if report else "draft",
        "submitted_at": report.submitted_at if report else None,
        "note": report.note if report else None,
        "counts": report.counts if report else await daily_counts(db, bdm.id, bdm_type, day),
        "can_submit": submitter and report is None and can_submit(day, today),
        "submit_window_days": SUBMIT_WINDOW_DAYS,
        "manager_comment": comment,
    }


def audit(db: AsyncSession, actor: User, action: str, report: BdmDailyReport) -> None:
    """Same transaction as the write (fail closed); the report's date only."""
    db.add(AuditLog(user_id=actor.id, action=f"bdm_daily_report.{action}", entity_type="bdm_daily_report", entity_id=str(report.id), metadata_json={"report_date": str(report.report_date)}))


def log(event: str, actor: User, report: BdmDailyReport) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(actor.id), "bdm_user_id": str(report.bdm_user_id), "report_date": str(report.report_date)}})

"""itc-016 (DEC-SCOPE-358; backlog §itc-016, source §6/§9): the IT Admin's fee-reminder schedule and the daily reminder sweep.

- Schedule (F3): one `fee_reminder_settings` row (no row = `FEE_REMINDER_DEFAULTS`): remind `days_before` days before a due date (0 =
  off) and on each of `overdue_days` days after it (empty = off). A rule fires on the IST calendar day it names; a missed day is not caught
  up, so an outage or a deploy never floods old reminders.
- Installments (F2): the itc-013 fee rows -- IT `enrollment_fee` payments still owed, with a due date and an amount. "Overdue" is derived
  (F1), never stored, so `student_access`, the accounts dashboard and `record_payment` are untouched.
- Sending (F4/F5): the student gets `it.fee.payment_due` or `it.fee.payment_overdue`; on an overdue rule the itc-003 counselor also gets
  `it.fee.student_overdue` (itc-002: in-app + email, WhatsApp/SMS only if opted in, fixed amount-free text). Each reminder's log row and
  its notices share one savepoint, so a failure sends nothing; the log's unique (payment, rule, day) key makes a rerun or an overlapping
  run send nothing twice (AC1). Logs carry counts only.
"""

import logging
from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FEE_REMINDER_DEFAULTS, FeeReminderLog, FeeReminderSetting, ItStudentCounselor, Payment, User
from app.notifications.events import notify
from app.services.audit_changes import audit_change
from app.services.fee_accounts import FEE_REFERENCES, OWED, india_today

logger = logging.getLogger("app.fee_reminders")

ADMINS_ONLY = "Only the IT Admin can see or change the fee reminder schedule"
SETTINGS_UPDATED = "it.fee_reminders.settings_update"
STUDENT_EVENTS = {"due_soon": "it.fee.payment_due", "overdue": "it.fee.payment_overdue"}


# --- the schedule --------------------------------------------------------------------------------------------------------------------
def require_admin(user: User) -> None:
    if (user.role, user.division) != ("it_admin", "it"):
        raise HTTPException(403, ADMINS_ONLY)


async def schedule(db: AsyncSession) -> dict:
    row = await db.get(FeeReminderSetting, 1)
    return {"days_before": row.days_before, "overdue_days": list(row.overdue_days)} if row else dict(FEE_REMINDER_DEFAULTS)


async def save_schedule(db: AsyncSession, admin: User, days_before: int, overdue_days: list[int]) -> dict:
    """Locks the row (two saves serialise; last write wins) and audits before/after (itc-001). Applies from the next daily run."""
    require_admin(admin)
    before = await schedule(db)
    row = await db.get(FeeReminderSetting, 1, with_for_update=True)
    if row is None:
        row = FeeReminderSetting(id=1)
        db.add(row)
    row.days_before, row.overdue_days, row.updated_by_user_id = days_before, overdue_days, admin.id
    after = {"days_before": days_before, "overdue_days": overdue_days}
    audit_change(db, admin, SETTINGS_UPDATED, "fee_reminder_settings", 1, before, after)
    await db.commit()
    return after


# --- the sweep -----------------------------------------------------------------------------------------------------------------------
def _rules(plan: dict, today: date) -> dict[date, tuple[str, int]]:
    """The due date each rule looks for today -> (kind, offset days). Before-due dates are future and overdue dates past: no clash."""
    rules = {today - timedelta(days=n): ("overdue", n) for n in plan["overdue_days"]}
    if plan["days_before"]:
        rules[today + timedelta(days=plan["days_before"])] = ("due_soon", plan["days_before"])
    return rules


async def _send(db: AsyncSession, payment_id: UUID, student_id: UUID, due: date, kind: str, offset: int, today: date) -> bool:
    """One reminder in one savepoint; True when the counselor was notified too."""
    async with db.begin_nested():
        log = FeeReminderLog(payment_id=payment_id, student_id=student_id, kind=kind, offset_days=offset, reminder_date=today, due_date=due, counselor_notified=False)
        db.add(log)
        await db.flush()  # the unique (payment, rule, day) key refuses a second reminder here, before anything is sent
        await notify(db, [await db.get(User, student_id)], STUDENT_EVENTS[kind], payment_id, action_url="/it/student/fees")
        if kind == "overdue":
            counselor = await db.scalar(select(User).join(ItStudentCounselor, ItStudentCounselor.counselor_user_id == User.id).where(ItStudentCounselor.student_user_id == student_id))
            log.counselor_notified = bool(await notify(db, [counselor], "it.fee.student_overdue", payment_id, action_url=f"/it/counselor/students/{student_id}/profile"))
    return log.counselor_notified


async def sweep(db: AsyncSession, *, today: date) -> dict[str, int]:
    """One bounded pass (the target due dates only, `ix_payments_status_due_date`); idempotent per IST day."""
    counts = {"sent": 0, "counselor": 0, "duplicate": 0, "failed": 0}
    rules = _rules(await schedule(db), today)
    rows = []
    if rules:
        stmt = (
            select(Payment.id, Payment.user_id, Payment.due_date)
            .join(User, User.id == Payment.user_id)
            .where(Payment.division == "it", Payment.reference_type.in_(FEE_REFERENCES), Payment.reference_id.is_not(None), Payment.status.in_(OWED),
                   Payment.amount > 0, Payment.due_date.in_(list(rules)), User.active.is_(True))
            .order_by(Payment.due_date, Payment.id)
        )  # fmt: skip
        rows = (await db.execute(stmt)).all()  # plain values: they outlive a rolled-back reminder
    for payment_id, student_id, due in rows:
        kind, offset = rules[due]
        try:
            counselor = await _send(db, payment_id, student_id, due, kind, offset, today)
            await db.commit()
            counts["sent"] += 1
            counts["counselor"] += counselor
        except IntegrityError:  # already reminded today (a rerun or an overlapping run)
            await db.rollback()
            counts["duplicate"] += 1
        except Exception:
            await db.rollback()
            counts["failed"] += 1
            logger.exception("itc016_fee_reminder_failed", extra={"extra_fields": {"payment_id": str(payment_id)}})
    logger.info("itc016_fee_reminders_done", extra={"extra_fields": {"today": today.isoformat(), **counts}})
    return counts


async def run_fee_reminders() -> dict[str, int]:
    """The beat task's entry point: its own session, today's IST date."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await sweep(db, today=india_today())

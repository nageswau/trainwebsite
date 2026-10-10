"""upc-015 (DEC-SCOPE-164, spec §2): the partnership alerts (EVID-020 §14 expiry, §6 delayed milestones, §20 overdue follow-ups, §32
"Alerts"), raised by an hourly beat that acts from 09:00 IST (AL3), each one in-app notice plus one email (AL10).

An alert is a `notifications` row whose `dedupe_key` is `upc015:<kind>:<event>:<user>` (AL1): the partial unique index is the "sent" record
(bdm-012 R1), so a rerun, a late run or an overlapping run is a no-op and the Alerts page lists the caller's rows by that prefix. Recipients
are read at fire time and must be active (AL9). Bodies carry names, MoU numbers and dates only; logs carry counts and ids only.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, PartnershipProfile, PartnershipTask, University, UniversityAgreement, UniversityMilestone, User
from app.notifications.dispatch import queue_deliveries
from app.partnership_milestones import MILESTONES
from app.services import partnership_milestones as milestones
from app.services.bdm_reminders import INDIA, _chunks, _day, clean
from app.services.partnership_tasks import band_filter
from app.services.university_agreements import TYPE_LABELS

logger = logging.getLogger(__name__)

PREFIX = "upc015"
KINDS = ("agreement_expiry", "milestone_delayed", "overdue_digest")  # AL2
MORNING = time(9, 0)  # AL3
THRESHOLDS = (90, 60, 30, 7)  # AL4: days before expiry (§14)
EXPIRY_STATUSES = ("signed", "active")  # AL4: a renewed agreement has a successor; Expiring / Expired are derived, never stored
DELAY_LOOKBACK = 7  # AL6: "newly" delayed = the target fell within the last week
CHANNELS = ["email"]  # AL10: in-app + email, even for a user opted in to WhatsApp / SMS
TASKS_URL = "/partnership/tasks?band=overdue"
MILESTONE_LABELS = {m.key: m.label for m in MILESTONES}


@dataclass(frozen=True)
class Alert:
    kind: str
    event: str  # the record and its event time, so a new time is a new alert
    title: str
    body: str
    url: str
    link: str

    def dedupe_key(self, user_id: UUID) -> str:
        return f"{PREFIX}:{self.kind}:{self.event}:{user_id}"


def _university_url(u: University, anchor: str) -> str:
    return f"/partnership/universities/{u.id}#{anchor}"


def expiry_alert(a: UniversityAgreement, u: University, days: int) -> Alert:
    """AL5: the §14 sentence exactly, then which agreement and when."""
    body = (f"⚠️ {clean(u.name, 200)} partnership expires in {days} days. Renewal action required. "
            f"{a.mou_number} ({TYPE_LABELS[a.agreement_type]}) expires on {_day(a.expiry_date)}.")  # fmt: skip
    event = f"{a.id}:{a.expiry_date.isoformat()}:{days}"
    return Alert("agreement_expiry", event, f"Agreement expires in {days} days", body, _university_url(u, "uni-agreements"), "View agreements")


def milestone_alert(m: UniversityMilestone, u: University) -> Alert:
    assert m.target_date is not None
    body = f"{clean(u.name, 200)}: the {MILESTONE_LABELS[m.kind]} milestone was due on {_day(m.target_date)} and is not complete."
    url = _university_url(u, f"timeline-{u.id}-heading")
    return Alert("milestone_delayed", f"{m.id}:{m.target_date.isoformat()}", "Milestone delayed", body, url, "View timeline")


def digest_alert(today: date, count: int, oldest: date) -> Alert:
    if count == 1:
        body = f"You have 1 overdue follow-up or task. It was due on {_day(oldest)}."
    else:
        body = f"You have {count} overdue follow-ups or tasks. The oldest was due on {_day(oldest)}."
    return Alert("overdue_digest", today.isoformat(), "Overdue follow-ups", body, TASKS_URL, "View overdue follow-ups")


# --- delivery -------------------------------------------------------------------------------------------------------------------


async def _remind(db: AsyncSession, counts: dict, alert: Alert, user: User) -> None:
    """One alert in a savepoint, claimed by the partial unique index: a second insert of the same key is a no-op, never a read-then-write
    race. A failure is counted and logged with ids only, never raised, so one bad row never stops the run (AL11)."""
    try:
        async with db.begin_nested():
            new_id = await db.scalar(
                pg_insert(Notification)
                .values(id=uuid4(), user_id=user.id, title=alert.title, body=alert.body, read=False, action_url=alert.url, dedupe_key=alert.dedupe_key(user.id))
                .on_conflict_do_nothing(index_elements=["dedupe_key"], index_where=Notification.dedupe_key.isnot(None))
                .returning(Notification.id)
            )
            if new_id is not None:
                context = {"kind": "partnership_alert", "links": [{"label": alert.link, "path": alert.url}]}
                await queue_deliveries(db, await db.get_one(Notification, new_id), user, context=context, channels=CHANNELS)
        counts["created" if new_id is not None else "duplicate"] += 1
    except Exception:
        counts["failed"] += 1
        logger.exception("upc015_alert_failed", extra={"extra_fields": {"kind": alert.kind, "event": alert.event, "user_id": str(user.id)}})


async def _send(db: AsyncSession, counts: dict, alert: Alert, user_ids: Iterable[UUID | None]) -> None:
    """AL9: each active recipient once; nobody active is counted as skipped."""
    ids = list(dict.fromkeys(i for i in user_ids if i is not None))
    users = (await db.scalars(select(User).where(User.id.in_(ids), User.active.is_(True)))).all() if ids else []
    if not users:
        counts["skipped"] += 1
        logger.info("upc015_alert_no_recipient", extra={"extra_fields": {"kind": alert.kind, "event": alert.event}})
    for user in users:
        await _remind(db, counts, alert, user)


# --- the three passes -----------------------------------------------------------------------------------------------------------


async def _expiry(db: AsyncSession, counts: dict, today: date) -> None:
    """AL4: exactly 90 / 60 / 30 / 7 days before the expiry of a signed or active agreement of an active university (the
    (status, expiry_date) index); to the primary, the backup and the primary's reporting head."""
    days_left = {today + timedelta(days=n): n for n in THRESHOLDS}
    query = (
        select(UniversityAgreement, University, PartnershipProfile.reporting_head_user_id)
        .join(University, University.id == UniversityAgreement.university_id)
        .outerjoin(PartnershipProfile, PartnershipProfile.user_id == University.primary_manager_user_id)
        .where(UniversityAgreement.status.in_(EXPIRY_STATUSES), UniversityAgreement.expiry_date.in_(tuple(days_left)), University.active.is_(True))
    )
    async for rows in _chunks(db, query, UniversityAgreement.id):
        for a, u, head_id in rows:
            await _send(db, counts, expiry_alert(a, u, days_left[a.expiry_date]), (u.primary_manager_user_id, u.backup_manager_user_id, head_id))
        await db.commit()


async def _milestones(db: AsyncSession, counts: dict, today: date) -> None:
    """AL6: a recorded target within the last week, judged by upc-008's own status rule (an event may have achieved it); live
    universities only; to the primary and the backup."""
    query = (
        select(UniversityMilestone, University)
        .join(University, University.id == UniversityMilestone.university_id)
        .where(
            UniversityMilestone.achieved_on.is_(None),
            UniversityMilestone.target_date.between(today - timedelta(days=DELAY_LOOKBACK), today - timedelta(days=1)),
            University.active.is_(True),
            University.lost_at.is_(None),
        )
    )
    async for rows in _chunks(db, query, UniversityMilestone.id):
        for m, u in rows:
            items = milestones._items(await milestones._rows(db, u.id), await milestones._derived(db, u.id), today)
            if next(i["status"] for i in items if i["kind"] == m.kind) == "delayed":
                await _send(db, counts, milestone_alert(m, u), (u.primary_manager_user_id, u.backup_manager_user_id))
        await db.commit()


async def _digest(db: AsyncSession, counts: dict, today: date) -> None:
    """AL8: one digest a day per active assignee of an overdue task (upc-020's band rule)."""
    query = (
        select(User, func.count(PartnershipTask.id), func.min(PartnershipTask.due_on))
        .join(PartnershipTask, PartnershipTask.assignee_user_id == User.id)
        .where(band_filter("overdue", today), User.active.is_(True))
        .group_by(User.id)
    )
    async for rows in _chunks(db, query, User.id):
        for user, count, oldest in rows:
            await _remind(db, counts, digest_alert(today, count, oldest), user)
        await db.commit()


async def send_partnership_alerts(db: AsyncSession, *, now: datetime) -> dict[str, int]:
    local = now.astimezone(INDIA)
    counts = {"created": 0, "duplicate": 0, "failed": 0, "skipped": 0}
    if local.time() >= MORNING:
        today = local.date()
        await _expiry(db, counts, today)
        await _milestones(db, counts, today)
        await _digest(db, counts, today)
    logger.info("upc015_alerts_done", extra={"extra_fields": {"at": now.isoformat(), **counts}})
    return counts


async def run_partnership_alerts() -> dict[str, int]:
    """The beat task's entry point: its own session, the current time."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await send_partnership_alerts(db, now=datetime.now(UTC))


# --- the Alerts page (AL12) -----------------------------------------------------------------------------------------------------


async def page(db: AsyncSession, user: User, kind: str, limit: int, offset: int) -> dict:
    """The caller's own alerts, newest first; `unread` counts every kind (the nav badge)."""
    mine = Notification.user_id == user.id
    all_kinds = Notification.dedupe_key.startswith(f"{PREFIX}:", autoescape=True)
    chosen = all_kinds if kind == "all" else Notification.dedupe_key.startswith(f"{PREFIX}:{kind}:", autoescape=True)
    total = await db.scalar(select(func.count()).select_from(Notification).where(mine, chosen))
    unread = await db.scalar(select(func.count()).select_from(Notification).where(mine, all_kinds, Notification.read.is_(False)))
    rows = await db.scalars(select(Notification).where(mine, chosen).order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).offset(offset))
    items = [
        {"id": n.id, "kind": (n.dedupe_key or "").split(":")[1], "title": n.title, "body": n.body, "read": n.read, "action_url": n.action_url, "created_at": n.created_at}
        for n in rows
    ]  # fmt: skip
    return {"items": items, "total": total or 0, "unread": unread or 0, "limit": limit, "offset": offset}

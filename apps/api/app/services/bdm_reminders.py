"""bdm-012 (DEC-SCOPE-098): the BDM reminder engine, run by beat every 5 minutes.

Six kinds, IST (D18/D19): an appointment at 09:00 the day before and exactly 1 h before; a trip at 09:00 the day before; a follow-up or
task at 09:00 on its due day; an MoU follow-up every 5 days while Proposal Sent / Draft Shared; an MoU renewal 30 days before an Active
MoU's valid-until. A 09:00 reminder can still go out later that IST day, the hour-before one until the start (R4).

Each reminder is one in-app notification plus an email delivery (D6, R8). `notifications.dedupe_key` is the "sent" record (R1): the key
is the kind, the record and its event time, so a rerun or an overlapping run is a no-op and a new time is a new reminder (AC3/AC4).
The owner is read at fire time and must be active (R6). Bodies carry no contact phone or email; logs carry counts and ids only.
"""

import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BdmAppointment, BdmMou, BdmOrganization, BdmTask, BdmTrip, Notification, User
from app.notifications.dispatch import queue_deliveries

logger = logging.getLogger(__name__)

INDIA = ZoneInfo("Asia/Kolkata")
MORNING = time(9, 0)  # D18: the 09:00 IST reminders
CHUNK = 200  # R12: rows read per query, committed per chunk
CHANNELS = ["email"]  # D6: in-app + email only, even for a user opted in to WhatsApp / SMS
OPEN_APPOINTMENT = ("scheduled", "confirmed", "rescheduled")
MOU_FOLLOW_UP = {"proposal_sent": "the proposal was sent", "draft_shared": "the draft was shared"}
MOU_EVERY_DAYS = 5  # D19
RENEWAL_DAYS = 30  # D19


@dataclass(frozen=True)
class Reminder:
    kind: str
    entity_id: UUID
    fire_key: str
    title: str
    body: str
    url: str
    links: list[dict]

    @property
    def dedupe_key(self) -> str:
        return f"bdm012:{self.kind}:{self.entity_id}:{self.fire_key}"


def clean(value: str | None, limit: int = 120) -> str:
    """BDM-typed text bound for an email: control characters (CR/LF included) become spaces, runs collapse, a trailing full stop goes
    (the sentence adds its own), then a hard cap."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in value or "").split()).rstrip(".")[:limit]


def _clock(value: datetime) -> str:
    return value.astimezone(INDIA).strftime("%I:%M %p")


def _day(value: date) -> str:
    return value.strftime("%d %b %Y")


def _start_of(day: date) -> datetime:
    return datetime.combine(day, time(0), INDIA).astimezone(UTC)


def _link(label: str, path: str) -> dict:
    return {"label": label, "path": path}


async def _chunks(db: AsyncSession, query: Select, id_column) -> AsyncIterator[Sequence[Any]]:
    """Keyset pages of `query` by `id_column`; the caller commits after each page."""
    last = None
    while True:
        page = query if last is None else query.where(id_column > last)
        rows = (await db.execute(page.order_by(id_column).limit(CHUNK))).all()
        if not rows:
            return
        yield rows
        last = rows[-1][0].id


async def _remind(db: AsyncSession, counts: dict, reminder: Reminder, user: User) -> None:
    """One reminder in a savepoint, claimed by the partial unique index: a second insert of the same key is a no-op, never a
    read-then-write race. A failure is counted and logged with ids only, never raised (R12)."""
    try:
        async with db.begin_nested():
            new_id = await db.scalar(
                pg_insert(Notification)
                .values(id=uuid4(), user_id=user.id, title=reminder.title, body=reminder.body, read=False, action_url=reminder.url, dedupe_key=reminder.dedupe_key)
                .on_conflict_do_nothing(index_elements=["dedupe_key"], index_where=Notification.dedupe_key.isnot(None))
                .returning(Notification.id)
            )
            if new_id is not None:
                note = await db.get_one(Notification, new_id)
                await queue_deliveries(db, note, user, context={"kind": "bdm_reminder", "links": reminder.links}, channels=CHANNELS)
        counts["created" if new_id is not None else "duplicate"] += 1
    except Exception:
        counts["failed"] += 1
        logger.exception("bdm012_reminder_failed", extra={"extra_fields": {"kind": reminder.kind, "entity_id": str(reminder.entity_id), "user_id": str(user.id)}})


# --- appointments (§6) ------------------------------------------------------------------------------------------------------------------


def _appointments(start: datetime, end: datetime) -> Select:
    return (
        select(BdmAppointment, BdmOrganization.name, User)
        .join(BdmOrganization, BdmOrganization.id == BdmAppointment.organization_id)
        .join(User, User.id == BdmAppointment.bdm_user_id)
        .where(BdmAppointment.status.in_(OPEN_APPOINTMENT), BdmAppointment.starts_at >= start, BdmAppointment.starts_at < end, User.active.is_(True))
    )


def day_before(appt: BdmAppointment, org_name: str) -> Reminder:
    url = f"/bdm/appointments/{appt.id}"
    confirmed = appt.status == "confirmed"  # R11
    parts = [f"Tomorrow at {_clock(appt.starts_at)}.", f"Organization: {clean(org_name)}.", f"Contact: {clean(appt.contact_name)}."]
    parts += [f"{label}: {clean(value, 200)}." for label, value in (("Purpose", appt.purpose), ("Location", appt.location)) if clean(value)]
    if not confirmed:
        parts.append("Please confirm your appointment.")
    actions = ([] if confirmed else [("Confirmed", "confirm")]) + [("Reschedule", "reschedule"), ("Cancel", "cancel")]
    links = [_link(label, f"{url}?action={action}") for label, action in actions]
    return Reminder("appointment_day_before", appt.id, appt.starts_at.astimezone(UTC).isoformat(), "Appointment reminder", " ".join(parts), url, links)


def hour_before(appt: BdmAppointment, org_name: str) -> Reminder:
    url = f"/bdm/appointments/{appt.id}"
    body = f"Your appointment with {clean(org_name)} is at {_clock(appt.starts_at)}."
    if clean(appt.location):
        body += f" Location: {clean(appt.location, 200)}."
    return Reminder("appointment_hour_before", appt.id, appt.starts_at.astimezone(UTC).isoformat(), "Appointment in 1 hour", body, url, [_link("View appointment", url)])


async def _appointment_reminders(db: AsyncSession, counts: dict, now: datetime, today: date, morning: bool) -> None:
    windows = [(now + timedelta(microseconds=1), now + timedelta(hours=1, microseconds=1), hour_before)]  # fire time <= now < start
    if morning:
        windows.append((_start_of(today + timedelta(days=1)), _start_of(today + timedelta(days=2)), day_before))
    for start, end, build in windows:
        async for rows in _chunks(db, _appointments(start, end), BdmAppointment.id):
            for appt, org_name, user in rows:
                await _remind(db, counts, build(appt, org_name), user)
            await db.commit()


# --- travel (§7) -------------------------------------------------------------------------------------------------------------------------


def trip_reminder(trip: BdmTrip, user: User, appointments: int) -> Reminder:
    url = f"/bdm/travel/{trip.id}"
    body = f"Tomorrow ({_day(trip.travel_date)}): travel to {clean(trip.to_place)}. BDM: {clean(user.full_name)}."
    if clean(trip.purpose):
        body += f" Purpose: {clean(trip.purpose, 200)}."
    body += f" Appointments: {appointments}."
    links = [_link("View Appointments", f"{url}#trip-appointments"), _link("View Expenses", f"{url}#trip-costs"), _link("Add Remarks", f"{url}#trip-remarks")]
    return Reminder("trip_day_before", trip.id, trip.travel_date.isoformat(), "Travel reminder", body, url, links)


async def _trip_reminders(db: AsyncSession, counts: dict, today: date) -> None:
    linked = select(func.count()).where(BdmAppointment.trip_id == BdmTrip.id, BdmAppointment.status != "cancelled").correlate(BdmTrip).scalar_subquery()
    query = (
        select(BdmTrip, User, linked)
        .join(User, User.id == BdmTrip.bdm_user_id)
        .where(BdmTrip.travel_date == today + timedelta(days=1), BdmTrip.approval_status == "approved", BdmTrip.travel_status == "planned", User.active.is_(True))
    )
    async for rows in _chunks(db, query, BdmTrip.id):
        for trip, user, appointments in rows:
            await _remind(db, counts, trip_reminder(trip, user, appointments), user)
        await db.commit()


# --- follow-ups and tasks (§4 Common) ----------------------------------------------------------------------------------------------------


def task_reminder(task: BdmTask, org_name: str | None) -> Reminder:
    follow_up = task.kind == "follow_up"
    body = f"{clean(task.title, 200)}."
    if org_name:
        body += f" Organization: {clean(org_name)}."
    body += f" Due {_day(task.due_on)}."
    url = f"/bdm/follow-ups?kind={task.kind}"
    title = "Follow-up due today" if follow_up else "Task due today"
    return Reminder("task_due", task.id, task.due_on.isoformat(), title, body, url, [_link("View follow-ups" if follow_up else "View tasks", url)])


async def _task_reminders(db: AsyncSession, counts: dict, today: date) -> None:
    query = (
        select(BdmTask, BdmOrganization.name, User)
        .outerjoin(BdmOrganization, BdmOrganization.id == BdmTask.organization_id)
        .join(User, User.id == BdmTask.assignee_user_id)
        .where(BdmTask.status == "open", BdmTask.due_on == today, User.active.is_(True))
    )
    async for rows in _chunks(db, query, BdmTask.id):
        for task, org_name, user in rows:
            await _remind(db, counts, task_reminder(task, org_name), user)
        await db.commit()


# --- MoU (§10, D19) ----------------------------------------------------------------------------------------------------------------------


def _mous(*where) -> Select:
    """The current MoU of a live organization, with its owner (the organization's assigned BDM) -- R5/R6."""
    return (
        select(BdmMou, BdmOrganization.name, User)
        .join(BdmOrganization, BdmOrganization.id == BdmMou.organization_id)
        .join(User, User.id == BdmOrganization.assigned_bdm_user_id)
        .where(BdmMou.is_current.is_(True), BdmOrganization.archived_at.is_(None), User.active.is_(True), *where)
    )


def mou_follow_up(mou: BdmMou, org_name: str, days: int) -> Reminder:
    url = f"/bdm/organizations/{mou.organization_id}#org-mou"
    body = f"{clean(org_name)}: {MOU_FOLLOW_UP[mou.status]} {days} days ago. Follow up with the contact person."
    key = f"{mou.status}:{mou.status_changed_at.astimezone(UTC).isoformat()}:{days}"
    return Reminder("mou_follow_up", mou.id, key, "MoU follow-up", body, url, [_link("View MoU", url)])


def mou_renewal(mou: BdmMou, org_name: str, valid_until: date) -> Reminder:
    url = f"/bdm/organizations/{mou.organization_id}#org-mou"
    body = f"{clean(org_name)}: the MoU is valid until {_day(valid_until)}. Plan the renewal with the contact person."
    return Reminder("mou_renewal", mou.id, valid_until.isoformat(), "MoU renewal due", body, url, [_link("View MoU", url)])


async def _mou_reminders(db: AsyncSession, counts: dict, today: date) -> None:
    waiting = _mous(BdmMou.status.in_(tuple(MOU_FOLLOW_UP)), BdmMou.status_changed_at < _start_of(today - timedelta(days=MOU_EVERY_DAYS - 1)))
    async for rows in _chunks(db, waiting, BdmMou.id):
        for mou, org_name, user in rows:
            days = (today - mou.status_changed_at.astimezone(INDIA).date()).days
            if days % MOU_EVERY_DAYS == 0:
                await _remind(db, counts, mou_follow_up(mou, org_name, days), user)
        await db.commit()
    valid_until = today + timedelta(days=RENEWAL_DAYS)
    async for rows in _chunks(db, _mous(BdmMou.status == "active", BdmMou.valid_until == valid_until), BdmMou.id):
        for mou, org_name, user in rows:
            await _remind(db, counts, mou_renewal(mou, org_name, valid_until), user)
        await db.commit()


async def send_bdm_reminders(db: AsyncSession, *, now: datetime) -> dict[str, int]:
    local = now.astimezone(INDIA)
    today, morning = local.date(), local.time() >= MORNING
    counts = {"created": 0, "duplicate": 0, "failed": 0}
    await _appointment_reminders(db, counts, now, today, morning)
    if morning:
        await _trip_reminders(db, counts, today)
        await _task_reminders(db, counts, today)
        await _mou_reminders(db, counts, today)
    logger.info("bdm012_reminders_done", extra={"extra_fields": {"day": today.isoformat(), **counts}})
    return counts


async def run_bdm_reminders() -> dict[str, int]:
    """The beat task's entry point: its own session, the current time."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await send_bdm_reminders(db, now=datetime.now(UTC))

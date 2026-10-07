"""tel-020 (DEC-SCOPE-111; EVID-019 §20, T14): the nine telecaller alerts, each one in-app notice plus one email (AL2), to the lead's telecaller
while that user is an active telecaller (AL5). No quiet hours (AL3).

- Event alerts (New Lead Assigned, Counselor Appointment Completed, Lead Returned) are added in the caller's transaction and never commit
  here: a rolled-back write leaves nothing, and the outbox publishes only after commit (AL7, AC3). The actor never alerts themselves.
- The beat (every 15 minutes) sends Follow-up Due, Missed Follow-up, Appointment Tomorrow, Appointment in 1 Hour, Lead Not Contacted and
  Hot Lead Pending. `notifications.dedupe_key` is the "sent" record (AL6, bdm-012's R1): the key names the kind, the record, the user and
  the event time, so a rerun or a late run is a no-op and a new time is a new alert (AC1, AC2). The team thresholds are read on every run
  (AC4).

Bodies carry the lead's name, its Lead ID and a time -- never a phone number, an email address or typed text. Logs carry counts and ids.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED
from app.models import (
    LEAD_APPOINTMENT_OPEN,
    TEL_SETTING_DEFAULTS,
    Appointment,
    Enquiry,
    LeadCall,
    LeadFollowUp,
    Notification,
    TelSetting,
    User,
)
from app.notifications.dispatch import queue_deliveries
from app.services.bdm_reminders import INDIA, _chunks, clean
from app.services.telecaller import TEAMS
from app.services.telecaller_metrics import FIRST_CALL

logger = logging.getLogger(__name__)

CHANNELS = ["email"]  # AL2: in-app + email, even for a user opted in to WhatsApp / SMS
DUE_AHEAD = timedelta(minutes=15)  # AL4: Follow-up Due in the quarter hour before
MISSED_AFTER = timedelta(hours=1)  # AL4: Missed when still open an hour after the due time
MISSED_LOOKBACK = timedelta(hours=24)  # AL10: the first run never alerts about follow-ups older than a day
HOUR_BEFORE = timedelta(hours=1)
EVENING = time(18, 0)  # AL4: Appointment Tomorrow from 18:00 IST the day before
FOLLOW_UPS_URL = "/telecaller/follow-ups"

TITLES = {
    "lead_assigned": "New lead assigned",
    "follow_up_due": "Follow-up due",
    "follow_up_missed": "Missed follow-up",
    "appointment_tomorrow": "Appointment tomorrow",
    "appointment_hour": "Appointment in 1 hour",
    "not_contacted": "Lead not contacted",
    "hot_pending": "Hot lead pending",
    "appointment_completed": "Counselor appointment completed",
    "lead_returned": "Lead returned for follow-up",
}


@dataclass(frozen=True)
class Alert:
    kind: str
    entity_id: UUID
    body: str
    url: str
    fire_key: str = ""

    @property
    def title(self) -> str:
        return TITLES[self.kind]

    def dedupe_key(self, user_id: UUID) -> str:
        return f"tel020:{self.kind}:{self.entity_id}:{user_id}:{self.fire_key}"

    def context(self) -> dict:
        label = "Open follow-ups" if self.url == FOLLOW_UPS_URL else "Open lead"
        return {"kind": "tel_alert", "links": [{"label": label, "path": self.url}]}


def _ref(lead: Enquiry) -> str:
    return f"{clean(lead.name)} ({lead.lead_code})"


def _when(value: datetime) -> str:
    local = value.astimezone(INDIA)
    return f"{local:%I:%M %p} IST on {local:%d %b %Y}"


def _lead_url(lead: Enquiry) -> str:
    return f"/telecaller/leads/{lead.id}"


def _key_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


async def thresholds(db: AsyncSession) -> dict[str, dict[str, int]]:
    """Each team's hours; a team without a row (a database older than 0099's seed) uses the defaults."""
    rows = {row.team: row for row in await db.scalars(select(TelSetting))}
    return {team: {k: getattr(rows[team], k) if team in rows else v for k, v in TEL_SETTING_DEFAULTS.items()} for team in TEAMS}


# --- event alerts (AL7) -----------------------------------------------------------------------------------------------------------


async def _recipient(db: AsyncSession, user_id: UUID | None, actor: User | None) -> User | None:
    if user_id is None or (actor is not None and actor.id == user_id):
        return None
    user = await db.get(User, user_id)
    return user if user is not None and user.active and user.role == "telecaller" else None


async def _event(db: AsyncSession, lead: Enquiry, actor: User | None, alert: Alert) -> None:
    user = await _recipient(db, lead.telecaller_user_id, actor)
    if user is None:
        return
    note = Notification(user_id=user.id, title=alert.title, body=alert.body, read=False, action_url=alert.url)
    db.add(note)
    await queue_deliveries(db, note, user, context=alert.context(), channels=CHANNELS)


async def notify_assigned(db: AsyncSession, lead: Enquiry, actor: User | None) -> None:
    await _event(db, lead, actor, Alert("lead_assigned", lead.id, f"{_ref(lead)} is now assigned to you.", _lead_url(lead)))


async def notify_appointment_completed(db: AsyncSession, appt: Appointment, lead: Enquiry, actor: User) -> None:
    body = f"The counselling appointment for {_ref(lead)} on {_when(appt.scheduled_at)} was completed."
    await _event(db, lead, actor, Alert("appointment_completed", appt.id, body, _lead_url(lead)))


async def notify_returned(db: AsyncSession, lead: Enquiry, actor: User) -> None:
    await _event(db, lead, actor, Alert("lead_returned", lead.id, f"{_ref(lead)} was returned to you for follow-up.", _lead_url(lead)))


# --- the beat ---------------------------------------------------------------------------------------------------------------------


async def _remind(db: AsyncSession, counts: dict, alert: Alert, user: User) -> None:
    """One alert in a savepoint, claimed by the partial unique index: a second insert of the same key is a no-op, never a read-then-write
    race. A failure is counted and logged with ids only, never raised, so one bad row never stops the run."""
    try:
        async with db.begin_nested():
            new_id = await db.scalar(
                pg_insert(Notification)
                .values(id=uuid4(), user_id=user.id, title=alert.title, body=alert.body, read=False, action_url=alert.url, dedupe_key=alert.dedupe_key(user.id))
                .on_conflict_do_nothing(index_elements=["dedupe_key"], index_where=Notification.dedupe_key.isnot(None))
                .returning(Notification.id)
            )
            if new_id is not None:
                await queue_deliveries(db, await db.get_one(Notification, new_id), user, context=alert.context(), channels=CHANNELS)
        counts["created" if new_id is not None else "duplicate"] += 1
    except Exception:
        counts["failed"] += 1
        logger.exception("tel020_alert_failed", extra={"extra_fields": {"kind": alert.kind, "entity_id": str(alert.entity_id), "user_id": str(user.id)}})


def _with_telecaller(query: Select) -> Select:
    """The lead's telecaller, read at fire time, only while an active telecaller (AL5)."""
    return query.join(User, User.id == Enquiry.telecaller_user_id).where(User.active.is_(True), User.role == "telecaller")


async def _each(db: AsyncSession, counts: dict, query: Select, id_column, build) -> None:
    async for rows in _chunks(db, query, id_column):
        for row in rows:
            alert, user = build(*row)
            await _remind(db, counts, alert, user)
        await db.commit()


def _follow_ups(start: datetime, end: datetime) -> Select:
    return _with_telecaller(
        select(LeadFollowUp, Enquiry).join(Enquiry, Enquiry.id == LeadFollowUp.lead_id).add_columns(User)
        .where(LeadFollowUp.status == "open", LeadFollowUp.due_at > start, LeadFollowUp.due_at <= end)
    )


def follow_up_due(fu: LeadFollowUp, lead: Enquiry, user: User) -> tuple[Alert, User]:
    body = f"Your follow-up with {_ref(lead)} is due at {_when(fu.due_at)}."
    return Alert("follow_up_due", fu.id, body, FOLLOW_UPS_URL, _key_time(fu.due_at)), user


def follow_up_missed(fu: LeadFollowUp, lead: Enquiry, user: User) -> tuple[Alert, User]:
    body = f"Your follow-up with {_ref(lead)} due at {_when(fu.due_at)} is still open."
    return Alert("follow_up_missed", fu.id, body, FOLLOW_UPS_URL, _key_time(fu.due_at)), user


def _appointments(start: datetime, end: datetime) -> Select:
    return _with_telecaller(
        select(Appointment, Enquiry).join(Enquiry, Enquiry.id == Appointment.lead_id).add_columns(User)
        .where(Appointment.status.in_(LEAD_APPOINTMENT_OPEN), Appointment.scheduled_at > start, Appointment.scheduled_at <= end)
    )


def appointment_hour(appt: Appointment, lead: Enquiry, user: User) -> tuple[Alert, User]:
    body = f"The counselling appointment for {_ref(lead)} starts at {_when(appt.scheduled_at)}."
    return Alert("appointment_hour", appt.id, body, _lead_url(lead), _key_time(appt.scheduled_at)), user


def appointment_tomorrow(appt: Appointment, lead: Enquiry, user: User) -> tuple[Alert, User]:
    body = f"{_ref(lead)} has a counselling appointment tomorrow at {_when(appt.scheduled_at)}."
    return Alert("appointment_tomorrow", appt.id, body, _lead_url(lead), _key_time(appt.scheduled_at)), user


def _own_open(team: str) -> list:
    """The telecaller's own open lead of `team`, not handed over (a counselor owns it then, T19)."""
    return [Enquiry.division == team, Enquiry.owner_id.is_(None), Enquiry.status.not_in(CLOSED)]


async def send_telecaller_alerts(db: AsyncSession, *, now: datetime) -> dict[str, int]:
    counts = {"created": 0, "duplicate": 0, "failed": 0}
    await _each(db, counts, _follow_ups(now - MISSED_AFTER, now + DUE_AHEAD), LeadFollowUp.id, follow_up_due)
    await _each(db, counts, _follow_ups(now - MISSED_AFTER - MISSED_LOOKBACK, now - MISSED_AFTER), LeadFollowUp.id, follow_up_missed)
    await _each(db, counts, _appointments(now, now + HOUR_BEFORE), Appointment.id, appointment_hour)
    local = now.astimezone(INDIA)
    if local.time() >= EVENING:
        tomorrow = datetime.combine(local.date() + timedelta(days=1), time(0), INDIA)
        await _each(db, counts, _appointments(tomorrow - timedelta(microseconds=1), tomorrow + timedelta(days=1) - timedelta(microseconds=1)),
                    Appointment.id, appointment_tomorrow)
    for team, hours in (await thresholds(db)).items():
        await _not_contacted(db, counts, team, hours["not_contacted_hours"], now)
        await _hot_pending(db, counts, team, hours["hot_pending_hours"], now)
    logger.info("tel020_alerts_done", extra={"extra_fields": {"at": now.isoformat(), **counts}})
    return counts


async def _not_contacted(db: AsyncSession, counts: dict, team: str, hours: int, now: datetime) -> None:
    """AL8: still in Assigned / First Call Pending (never connected) for the team's hours; a new stage time re-arms it."""
    query = _with_telecaller(select(Enquiry, User).where(*_own_open(team), Enquiry.status.in_(FIRST_CALL),
                                                          Enquiry.stage_changed_at <= now - timedelta(hours=hours)))

    def build(lead: Enquiry, user: User) -> tuple[Alert, User]:
        body = f"{_ref(lead)} has not been contacted for over {hours} hours."
        return Alert("not_contacted", lead.id, body, _lead_url(lead), _key_time(lead.stage_changed_at)), user

    await _each(db, counts, query, Enquiry.id, build)


async def _hot_pending(db: AsyncSession, counts: dict, team: str, hours: int, now: datetime) -> None:
    """AL9: a hot lead with no call for the team's hours, counted from its latest call (else its creation); a new call re-arms it."""
    last_call = select(func.max(LeadCall.occurred_at)).where(LeadCall.lead_id == Enquiry.id).correlate(Enquiry).scalar_subquery()
    since = func.coalesce(last_call, Enquiry.created_at)
    query = _with_telecaller(select(Enquiry, User, since).where(*_own_open(team), Enquiry.priority == "hot", since <= now - timedelta(hours=hours)))

    def build(lead: Enquiry, user: User, reference: datetime) -> tuple[Alert, User]:
        body = f"Hot lead {_ref(lead)} has had no call for over {hours} hours."
        return Alert("hot_pending", lead.id, body, _lead_url(lead), _key_time(reference)), user

    await _each(db, counts, query, Enquiry.id, build)


async def run_telecaller_alerts() -> dict[str, int]:
    """The beat task's entry point: its own session, the current time."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await send_telecaller_alerts(db, now=datetime.now(UTC))

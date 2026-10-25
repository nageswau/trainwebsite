"""ccrm-038 (DEC-SCOPE-271 CA4-CA6): the overseas counselor's read-only iCal feed.

The URL token is 256 random bits; only its SHA-256 is stored, so the full link exists only in the create/regenerate answer. Neither
the token nor its hash goes to the audit row or a log. The feed is served without a session: the token is the credential, and every
refusal (unknown token, inactive user, no longer an overseas counselor) is the same 404."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.models import Appointment, AuditLog, CalendarFeed, Enquiry, OverseasApplication, OverseasStudentCounselor, University, User, VisaCase
from app.services import appointment_invites, calendar_ics

FEED_PATH = "/api/v1/calendar/feeds/{token}.ics"
LOOKBACK = timedelta(days=90)  # CA5
MAX_EVENTS = 500
CALENDAR_NAME = "EduSphere appointments"


def is_overseas_counselor(user: User) -> bool:
    return user.role == "counselor" and user.division == "overseas" and bool(user.active)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def url(token: str) -> str:
    return settings.frontend_url.rstrip("/") + FEED_PATH.format(token=token)


def out(feed: CalendarFeed | None, token: str | None = None) -> dict:
    return {"active": feed is not None, "created_at": feed.created_at if feed else None, "url": url(token) if token else None}


def _audit(db: AsyncSession, user: User, action: str) -> None:
    db.add(AuditLog(user_id=user.id, action=f"calendar_feed.{action}", entity_type="calendar_feed", entity_id=str(user.id), metadata_json={}))


async def current(db: AsyncSession, user: User) -> CalendarFeed | None:
    return await db.get(CalendarFeed, user.id)


async def issue(db: AsyncSession, user: User) -> dict:
    """Create the feed, or regenerate it: the new token replaces the old one at once (the old link 404s)."""
    token = secrets.token_urlsafe(32)
    feed = await db.get(CalendarFeed, user.id, with_for_update=True)
    action = "regenerate" if feed else "create"
    if feed:
        feed.token_hash, feed.created_at = _hash(token), datetime.now(UTC)
    else:
        feed = CalendarFeed(user_id=user.id, token_hash=_hash(token), created_at=datetime.now(UTC))
        db.add(feed)
    _audit(db, user, action)
    await db.commit()
    return out(feed, token)


async def revoke(db: AsyncSession, user: User) -> None:
    if (await db.execute(delete(CalendarFeed).where(CalendarFeed.user_id == user.id))).rowcount:
        _audit(db, user, "revoke")
    await db.commit()


async def owner(db: AsyncSession, token: str) -> User | None:
    user = await db.scalar(select(User).join(CalendarFeed, CalendarFeed.user_id == User.id).where(CalendarFeed.token_hash == _hash(token)))
    return user if user is not None and is_overseas_counselor(user) else None


_Student = aliased(User)


async def _appointment_events(db: AsyncSession, counselor: User, since: datetime) -> list[list[str]]:
    rows = (await db.execute(
        select(Appointment, _Student.full_name, Enquiry.name)
        .outerjoin(_Student, _Student.id == Appointment.student_id)
        .outerjoin(Enquiry, Enquiry.id == Appointment.lead_id)
        .where(Appointment.staff_id == counselor.id, Appointment.division == "overseas", Appointment.scheduled_at >= since,
               func.lower(Appointment.status).notin_(appointment_invites.CANCELLED))
        .order_by(Appointment.scheduled_at).limit(MAX_EVENTS)
    )).all()
    events = []
    for appt, student_name, lead_name in rows:
        who = student_name or lead_name or "Student"
        code = f" ({appt.appointment_code})" if appt.appointment_code else ""
        events.append(calendar_ics.event(
            uid=appointment_invites.uid(appt), sequence=appt.calendar_sequence or 0, start=appt.scheduled_at,
            end=appt.scheduled_at + timedelta(minutes=appt.duration_minutes or 60), summary=f"Counselling: {who}{code}",
            location=appointment_invites.where(appt), description=f"{appt.appointment_type} · {appt.mode}",
        ))
    return events


async def _visa_events(db: AsyncSession, counselor: User, since: datetime, limit: int) -> list[list[str]]:
    """The applications this counselor counsels: the application's counselor, else a direct student's csc-001 counselor (ccrm-030 RM4)."""
    counselor_id = func.coalesce(OverseasApplication.counselor_id, case((OverseasApplication.agent_student_id.is_(None), OverseasStudentCounselor.counselor_user_id)))
    rows = (await db.execute(
        select(VisaCase, University.name, _Student.full_name)
        .join(OverseasApplication, OverseasApplication.id == VisaCase.application_id)
        .join(University, University.id == OverseasApplication.university_id)
        .outerjoin(OverseasStudentCounselor, OverseasStudentCounselor.student_user_id == OverseasApplication.student_id)
        .outerjoin(_Student, _Student.id == OverseasApplication.student_id)
        .where(and_(counselor_id == counselor.id, OverseasApplication.status != "withdrawn", VisaCase.appointment_date.is_not(None),
                    VisaCase.appointment_date >= since.date()))
        .order_by(VisaCase.appointment_date).limit(limit)
    )).all()
    return [
        calendar_ics.all_day_event(uid=f"visa-{visa.id}@edusphere", day=visa.appointment_date, summary=f"Visa appointment: {student_name or 'Student'}",
                                   location=visa.appointment_place, description=university_name)
        for visa, university_name, student_name in rows
    ]


async def body(db: AsyncSession, counselor: User) -> str:
    since = datetime.now(UTC) - LOOKBACK
    events = await _appointment_events(db, counselor, since)
    events += await _visa_events(db, counselor, since, MAX_EVENTS - len(events))
    return calendar_ics.calendar(events, name=CALENDAR_NAME)

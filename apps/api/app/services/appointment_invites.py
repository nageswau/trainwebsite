"""ccrm-038 (DEC-SCOPE-272 CA1-CA3): the calendar invite of an overseas appointment.

`queue` runs inside the caller's transaction: one in-app notification per attendee plus an email delivery whose context carries the
`.ics` built now, so a later change can never alter an email already queued. The attendees are the student (a student appointment) and
the assigned counselor; a lead is not a user and is never emailed here (lead email waits for ccrm-040 consent). The invite carries no
purpose, remarks or outcome notes."""

from datetime import timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Appointment, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.services import calendar_ics

INDIA = ZoneInfo("Asia/Kolkata")  # the time in the notification text, as the telecaller alerts show it
KIND = "appointment_invite"
Change = Literal["booked", "rescheduled", "cancelled"]
TITLES = {"booked": "Counselling appointment booked", "rescheduled": "Counselling appointment rescheduled",
          "cancelled": "Counselling appointment cancelled"}
URLS = {"overseas_student": "/overseas/student/appointments", "counselor": "/overseas/counselor/appointments"}
CANCELLED = frozenset({"cancelled", "canceled"})  # the student flow's free-text status (AP12)


def when(appt: Appointment) -> str:
    local = appt.scheduled_at.astimezone(INDIA)
    return f"{local:%d %b %Y}, {local:%I:%M %p} IST"


def uid(appt: Appointment) -> str:
    return f"appointment-{appt.id}@edusphere"


def summary(appt: Appointment) -> str:
    code = f" ({appt.appointment_code})" if appt.appointment_code else ""
    return f"Counselling appointment{code} — EduSphere"


def where(appt: Appointment) -> str:
    return appt.meeting_link or appt.location or appt.mode


def ics(appt: Appointment, change: Change) -> str:
    end = appt.scheduled_at + timedelta(minutes=appt.duration_minutes or 60)
    vevent = calendar_ics.event(uid=uid(appt), sequence=appt.calendar_sequence or 0, start=appt.scheduled_at, end=end, summary=summary(appt),
                                location=where(appt), status="CANCELLED" if change == "cancelled" else "CONFIRMED",
                                organizer=settings.smtp_from_email or None)
    return calendar_ics.calendar([vevent], method="CANCEL" if change == "cancelled" else "REQUEST")


async def queue(db: AsyncSession, appt: Appointment, change: Change) -> None:
    """A re-time or a cancellation first moves the SEQUENCE on, so calendars replace the earlier invite. Only overseas appointments."""
    if appt.division != "overseas":
        return
    if change != "booked":
        appt.calendar_sequence = (appt.calendar_sequence or 0) + 1
    text = ics(appt, change)
    method = "CANCEL" if change == "cancelled" else "REQUEST"
    body = f"{'Cancelled: ' if change == 'cancelled' else ''}{when(appt)} ({appt.mode}). The calendar invite is attached to the email."
    for user_id in dict.fromkeys(i for i in (appt.student_id, appt.staff_id) if i):
        recipient = await db.get(User, user_id)
        if recipient is None or not recipient.active:
            continue
        note = Notification(user_id=recipient.id, title=TITLES[change], body=body, read=False, action_url=URLS.get(recipient.role))
        db.add(note)
        await queue_deliveries(db, note, recipient, channels=["email"], context={"kind": KIND, "ics": text, "method": method})

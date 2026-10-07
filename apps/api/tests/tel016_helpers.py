"""tel-016 test builders. Every value is unique per call: the test database is shared and never truncated."""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import Appointment, Enquiry, User
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user

__all__ = ["as_user", "body", "book", "book_url", "action_url", "at", "make_counselor", "setup", "student_appointment", "OPTIONS", "COUNSELOR_LIST"]

COUNSELOR_LIST = "/api/v1/counselor/appointments"


def book_url(lead_id) -> str:
    return f"/api/v1/telecaller/leads/{lead_id}/appointments"


OPTIONS = "/api/v1/telecaller/leads/{}/appointment-options"


def action_url(appt_id, action: str) -> str:
    return f"/api/v1/lead-appointments/{appt_id}/{action}"


def at(hours: float = 0, *, days: int = 1) -> str:
    """A whole-minute UTC instant `days` + `hours` from now (unique per test via a random minute offset is not needed: each test makes
    its own counselor, so clashes only happen where a test builds them)."""
    base = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(days=days, hours=hours)
    return base.isoformat()


async def make_counselor(db, division: str = "it", *, active: bool = True) -> User:
    return await make_user(db, "counselor", division, active=active)


async def setup(db, division: str = "it", *, status: str = "follow_up", **lead_over):
    manager = await make_tl_manager(db)
    tel = await make_telecaller(db, manager, team=division)
    counselor = await make_counselor(db, division)
    row = Enquiry(**({"division": division, "name": f"Lead {uuid.uuid4().hex[:6]}", "email": f"{uuid.uuid4().hex[:8]}@example.local",
                      "phone": "9876543210", "subject": "Course", "message": "", "source": "website", "telecaller_user_id": tel.id,
                      "status": status} | lead_over))
    db.add(row)
    await db.commit()
    return manager, tel, counselor, row


def body(counselor: User, *, when: str | None = None, appointment_type: str | None = None, **over) -> dict:
    kind = appointment_type or ("it_course_counselling" if counselor.division == "it" else "overseas_counselling")
    return {"appointment_type": kind, "counselor_id": str(counselor.id), "scheduled_at": when or at(), "mode": "Online",
            "meeting_link": "https://meet.example.com/abc", "purpose": "Course fit", **over}


async def book(client, tel: User, lead: Enquiry, counselor: User, **kwargs):
    await as_user(client, tel)
    return await client.post(book_url(lead.id), json=body(counselor, **kwargs))


async def student_appointment(db, counselor: User, when: str) -> Appointment:
    student = await make_user(db, "overseas_student" if counselor.division == "overseas" else "it_student", counselor.division)
    row = Appointment(division=counselor.division, student_id=student.id, staff_id=counselor.id, scheduled_at=datetime.fromisoformat(when),
                      appointment_type="Career Counseling", mode="Online", status="scheduled")
    db.add(row)
    await db.commit()
    return row

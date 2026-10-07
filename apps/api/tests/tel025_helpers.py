"""tel-025 test builders. Rows are inserted directly (a closed lead, a handed-over lead, a logged call are states the API can't create in
one call). Unique values per call: the test database is shared and never truncated."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Appointment, AuditLog, Enquiry, LeadCall, LeadFollowUp, TelDistributionRule, User
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import lead, make_telecaller, make_tl_manager, make_user

__all__ = ["TELECALLERS", "MANAGERS", "add", "as_user", "audit_rows", "call", "follow_up", "fresh", "lead", "lead_appt", "make_telecaller",
           "make_tl_manager", "make_user", "post", "rule_for", "team"]

TELECALLERS = "/api/v1/admin/telecallers"
MANAGERS = "/api/v1/admin/telecaller-managers"


async def add(db, row):
    db.add(row)
    await db.commit()
    return row


async def fresh(db, model, row_id):
    """Re-read a row the API changed (the test session's identity map holds the old copy)."""
    return await db.get(model, row_id, populate_existing=True)


async def audit_rows(db, action: str, entity_id) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(entity_id)))).all())


async def team(db, division: str = "it"):
    """A manager with two telecallers A (leaving) and B (taking over), all on `division`."""
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager, team=division), await make_telecaller(db, manager, team=division)


async def follow_up(db, lead_row: Enquiry, author: User, *, status: str = "open") -> LeadFollowUp:
    return await add(db, LeadFollowUp(
        lead_id=lead_row.id, due_at=datetime.now(UTC) + timedelta(days=1), reason="course_details", status=status, created_by_user_id=author.id,
        completed_at=datetime.now(UTC) if status == "done" else None, completed_by_user_id=author.id if status == "done" else None,
        cancelled_at=datetime.now(UTC) if status == "cancelled" else None, cancel_reason="Seeded" if status == "cancelled" else None,
    ))


async def lead_appt(db, lead_row: Enquiry, booked_by: User, counselor: User, *, status: str = "scheduled") -> Appointment:
    return await add(db, Appointment(
        division=lead_row.division, staff_id=counselor.id, scheduled_at=datetime.now(UTC) + timedelta(days=2), appointment_type="career_counselling",
        status=status, lead_id=lead_row.id, appointment_code=f"CAP-T{uuid.uuid4().hex[:8]}", booked_by_user_id=booked_by.id,
    ))


async def call(db, lead_row: Enquiry, caller: User) -> LeadCall:
    return await add(db, LeadCall(lead_id=lead_row.id, caller_user_id=caller.id, call_type="outgoing", outcome="interested",
                                  duration_seconds=60, occurred_at=datetime.now(UTC)))


async def rule_for(db, telecaller: User, team_name: str = "it") -> TelDistributionRule:
    return await add(db, TelDistributionRule(team=team_name, kind="city", city=f"City {uuid.uuid4().hex[:8]}", telecaller_user_id=telecaller.id))


async def post(client, url: str, body: dict | None = None):
    return await client.post(url, json=body if body is not None else {})

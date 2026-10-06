"""bdm-025 test builders. Rows are inserted directly (a past appointment, a done task, an in-progress trip are states the API
can't create in one call). Unique values per call: the test database is shared and never truncated."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.models import AuditLog, BdmAppointment, BdmAssignmentHistory, BdmOrganization, BdmTask, BdmTrip, User
from app.services.bdm_travel import india_today
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import make_bdm

BDMS = "/api/v1/admin/bdms"
MANAGERS = "/api/v1/admin/bdm-managers"


def tag() -> str:
    return uuid.uuid4().hex[:8]


async def add(db, row):
    db.add(row)
    await db.commit()
    return row


async def org(db, owner: User, *, archived: bool = False, bdm_type: str = "college") -> BdmOrganization:
    t = tag()
    return await add(db, BdmOrganization(
        code=f"ORG-T{t}", org_type="college" if bdm_type == "college" else "school" if bdm_type == "school" else "agent",
        bdm_type=bdm_type, name=f"Org {t}", name_key=f"org {t}", city="Kochi", city_key="kochi", assigned_bdm_user_id=owner.id,
        created_by_user_id=owner.id, archived_at=datetime.now(UTC) if archived else None,
    ))


async def appt(db, owner: User, organization: BdmOrganization, *, hours: float = 48, status: str = "scheduled") -> BdmAppointment:
    return await add(db, BdmAppointment(
        code=f"APT-T{tag()}", bdm_user_id=owner.id, organization_id=organization.id, contact_name="Dr Rao",
        starts_at=datetime.now(UTC) + timedelta(hours=hours), appointment_type="college_meeting", status=status,
        outcome="interested" if status == "completed" else None,
    ))


async def task(db, owner: User, *, status: str = "open", organization: BdmOrganization | None = None) -> BdmTask:
    return await add(db, BdmTask(
        kind="task", title="Call back", due_on=india_today(), organization_id=organization.id if organization else None, source="manual",
        assignee_user_id=owner.id, status=status, completed_at=func.now() if status == "done" else None,
        cancelled_at=func.now() if status == "cancelled" else None, cancel_reason="Seeded" if status == "cancelled" else None,
    ))


async def trip(db, owner: User, *, approval: str = "draft", travel: str = "planned") -> BdmTrip:
    today = india_today()
    return await add(db, BdmTrip(
        code=f"TRV-T{tag()}", bdm_user_id=owner.id, travel_date=today + timedelta(days=3), return_date=today + timedelta(days=4),
        from_place="Hyderabad", to_place="Vijayawada", purpose="Visits", mode="train", estimated_cost=Decimal("100.00"),
        approval_status=approval, travel_status=travel, submitted_at=func.now() if approval != "draft" else None,
    ))


async def team(db, bdm_type: str = "college"):
    """A manager with two active BDMs of `bdm_type` (A leaves, B takes over)."""
    manager = await make_manager(db)
    return manager, await make_bdm(db, manager, bdm_type), await make_bdm(db, manager, bdm_type)


async def as_super(client, db) -> User:
    client.cookies.clear()
    admin = await make_user(db, "super_admin", "global")
    await login(client, admin)
    return admin


async def deactivate(client, bdm_id, body: dict):
    return await client.post(f"{BDMS}/{bdm_id}/deactivate", json=body)


async def history(db, entity_id) -> list[BdmAssignmentHistory]:
    return list((await db.scalars(select(BdmAssignmentHistory).where(BdmAssignmentHistory.entity_id == entity_id))).all())


async def audit_rows(db, action: str, entity_id) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(entity_id)))).all())


async def fresh(db, model, row_id):
    """Re-read a row the API changed (the test session's identity map holds the old copy)."""
    return await db.get(model, row_id, populate_existing=True)

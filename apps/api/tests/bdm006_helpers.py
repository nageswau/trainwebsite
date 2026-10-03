"""bdm-006 test builders. Unique per call: the shared test database is never truncated. Each test uses fresh BDMs, so overlap only
happens where a test books the same BDM twice on purpose (vary `hours` otherwise)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.models import AuditLog, BdmAppointment
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm

APPTS = "/api/v1/bdm/appointments"


def future(hours: float = 48) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).replace(second=0, microsecond=0).isoformat()


def appt_payload(org: dict, **over) -> dict:
    payload = {"organization_id": org["id"], "contact_id": org["contacts"][0]["id"], "starts_at": future(), "appointment_type": "college_meeting"}
    payload.update(over)
    return payload


async def create_appt(client, org: dict, **over) -> dict:
    response = await client.post(APPTS, json=appt_payload(org, **over))
    assert response.status_code == 201, response.text
    return response.json()["appointment"]


async def bdm_with_org(client, db, bdm_type: str = "college", manager=None):
    """A logged-in BDM of `bdm_type` with one organization assigned to them."""
    manager = manager or await make_manager(db)
    bdm = await make_bdm(db, manager, bdm_type)
    await login(client, bdm)
    return manager, bdm, await create_org(client)


async def move_to_past(db, appt_id, minutes: int = 30) -> None:
    """The only way to test "after the start time": the API never accepts a past time (A7)."""
    await db.execute(update(BdmAppointment).where(BdmAppointment.id == appt_id).values(starts_at=func.now() - timedelta(minutes=minutes)))
    await db.commit()


async def audits(db, appt_id) -> list[str]:
    rows = await db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(appt_id)).order_by(AuditLog.created_at, AuditLog.id))
    return list(rows.all())

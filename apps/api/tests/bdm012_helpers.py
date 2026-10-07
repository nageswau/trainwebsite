"""bdm-012 test builders. Rows are inserted directly with dates in 2033, so other tests' rows (the database is shared and never
truncated) stay out of the reminder windows; every assertion is about this test's own BDMs."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models import BdmAppointment, BdmMou, BdmTask, BdmTrip, Notification, NotificationDelivery, User
from app.services import bdm_reminders
from tests.bdm001_helpers import make_manager
from tests.bdm002_helpers import make_bdm
from tests.bdm025_helpers import add, org, tag

IST = ZoneInfo("Asia/Kolkata")
D = date(2033, 5, 10)


def ist(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), IST).astimezone(UTC)


NINE = ist(D, 9)  # 09:00 IST on D


async def world(db, bdm_type: str = "college"):
    manager = await make_manager(db)
    bdm = await make_bdm(db, manager, bdm_type)
    return bdm, await org(db, bdm, bdm_type=bdm_type)


async def appointment(db, owner: User, organization, starts_at: datetime, *, status: str = "scheduled", **over) -> BdmAppointment:
    fields = dict(contact_name="Mr. XYZ", contact_phone="9876543210", contact_email="xyz@abc.example", location="Vijayawada",
                  purpose="Edusphere Course Promotion", appointment_type="college_meeting", outcome="interested" if status == "completed" else None)
    return await add(db, BdmAppointment(code=f"APT-T{tag()}", bdm_user_id=owner.id, organization_id=organization.id, starts_at=starts_at,
                                        status=status, **{**fields, **over}))


async def trip(db, owner: User, travel_date: date, *, approval: str = "approved", travel: str = "planned") -> BdmTrip:
    return await add(db, BdmTrip(
        code=f"TRV-T{tag()}", bdm_user_id=owner.id, travel_date=travel_date, return_date=travel_date + timedelta(days=1), from_place="Hyderabad",
        to_place="Vijayawada", purpose="College visits", mode="train", estimated_cost=Decimal("100.00"), approval_status=approval,
        travel_status=travel, submitted_at=datetime.now(UTC) if approval != "draft" else None,
        decided_at=datetime.now(UTC) if approval in ("approved", "rejected") else None,
    ))


async def task(db, owner: User, due_on: date, *, kind: str = "follow_up", status: str = "open", organization=None, title: str = "Call the principal") -> BdmTask:
    now = datetime.now(UTC)
    return await add(db, BdmTask(
        kind=kind, title=title, due_on=due_on, organization_id=organization.id if organization else None, source="manual", assignee_user_id=owner.id,
        status=status, completed_at=now if status == "done" else None, cancelled_at=now if status == "cancelled" else None,
        cancel_reason="Seeded" if status == "cancelled" else None,
    ))


async def mou(db, organization, *, status: str, changed: datetime, valid_until: date | None = None, current: bool = True) -> BdmMou:
    signed = status in ("signed", "active")
    return await add(db, BdmMou(
        organization_id=organization.id, created_by_user_id=organization.assigned_bdm_user_id, status=status, status_changed_at=changed,
        signed_on=D - timedelta(days=300) if signed else None, valid_from=D - timedelta(days=300) if status == "active" else None,
        valid_until=valid_until, is_current=current,
    ))


async def run(db, now: datetime) -> dict:
    return await bdm_reminders.send_bdm_reminders(db, now=now)


async def reminders(db, user: User) -> list[Notification]:
    rows = await db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.dedupe_key.like("bdm012:%")).order_by(Notification.created_at))
    return list(rows)


async def deliveries(db, note: Notification) -> list[NotificationDelivery]:
    return list(await db.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id == note.id)))

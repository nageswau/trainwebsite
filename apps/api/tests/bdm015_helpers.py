"""bdm-015 test builders. Rows are written straight to the tables so each instant can sit exactly inside or outside an IST day.
Unique values per call: the test database is shared and never truncated."""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.models import (
    BdmActivity,
    BdmAppointment,
    BdmAppointmentEvent,
    BdmMou,
    BdmMouEvent,
    BdmOrganization,
    BdmTask,
    BdmTrip,
    Enquiry,
)
from app.services.bdm_activities import day_range
from app.services.bdm_travel import india_today

REPORTS = "/api/v1/bdm/daily-reports"
TEAM_REPORTS = "/api/v1/bdm/manager/daily-reports"


def report_url(day: date) -> str:
    return f"{REPORTS}/{day}"


def submit_url(day: date) -> str:
    return f"{REPORTS}/{day}/submit"


def team_report_url(bdm_id, day: date) -> str:
    return f"{TEAM_REPORTS}/{bdm_id}/{day}"


def a_past_day(days_back: int = 2) -> date:
    return india_today() - timedelta(days=days_back)


def inside(day: date, hours: float = 10) -> datetime:
    return day_range(day)[0] + timedelta(hours=hours)


def before(day: date) -> datetime:
    """The last instant of the previous IST day -- outside `day`."""
    return day_range(day)[0] - timedelta(seconds=1)


def after(day: date) -> datetime:
    """The first instant of the next IST day -- outside `day`."""
    return day_range(day)[1]


def by_key(items: list[dict]) -> dict:
    return {i["key"]: (i["count"] if i["tracked"] else "not tracked") for i in items}


async def org_row(db, owner_id, org_type: str = "college", bdm_type: str = "college", *, created_at: datetime | None = None, school_id=None) -> BdmOrganization:
    name = f"Org {uuid.uuid4().hex[:10]}"
    org = BdmOrganization(
        code=f"T{uuid.uuid4().hex[:12]}",
        org_type=org_type,
        bdm_type=bdm_type,
        name=name,
        name_key=name.lower(),
        city="Kochi",
        city_key="kochi",
        assigned_bdm_user_id=owner_id,
        created_by_user_id=owner_id,
        school_id=school_id,
    )
    if created_at is not None:
        org.created_at = created_at
    db.add(org)
    await db.commit()
    return org


async def activity(db, bdm_id, org_id, at: datetime, channel: str = "call", direction: str | None = "outbound") -> None:
    db.add(BdmActivity(bdm_user_id=bdm_id, organization_id=uuid.UUID(str(org_id)), channel=channel, direction=direction, occurred_at=at))
    await db.commit()


async def appointment(
    db, bdm_id, org_id, starts_at: datetime, *, status: str = "completed", appointment_type: str = "college_meeting", created_at: datetime | None = None, cancelled_at: datetime | None = None
) -> BdmAppointment:
    appt = BdmAppointment(
        code=f"T{uuid.uuid4().hex[:12]}",
        bdm_user_id=bdm_id,
        organization_id=org_id,
        contact_name="Dr Rao",
        starts_at=starts_at,
        appointment_type=appointment_type,
        status=status,
        outcome="interested" if status == "completed" else None,
    )
    if created_at is not None:
        appt.created_at = created_at
    db.add(appt)
    await db.flush()
    if cancelled_at is not None:
        db.add(BdmAppointmentEvent(appointment_id=appt.id, actor_user_id=bdm_id, from_status="scheduled", to_status="cancelled", created_at=cancelled_at))
    await db.commit()
    return appt


async def trip(db, bdm_id, completed_at: datetime | None, travel_status: str = "completed") -> None:
    day = completed_at.date() if completed_at else india_today()
    db.add(
        BdmTrip(
            code=f"T{uuid.uuid4().hex[:12]}",
            bdm_user_id=bdm_id,
            travel_date=day,
            return_date=day,
            from_place="Kochi",
            to_place="Chennai",
            purpose="Visits",
            mode="train",
            estimated_cost=Decimal("100"),
            approval_status="approved",
            travel_status=travel_status,
            completed_at=completed_at,
        )
    )
    await db.commit()


async def mou_event(db, actor_id, org_id, to_status: str, at: datetime, from_status: str | None = "discussion_started") -> None:
    mou = BdmMou(organization_id=org_id, created_by_user_id=actor_id, status="prospect", is_current=False)
    db.add(mou)
    await db.flush()
    db.add(BdmMouEvent(mou_id=mou.id, actor_user_id=actor_id, kind="status", from_status=from_status, to_status=to_status, created_at=at))
    await db.commit()


async def follow_up(db, bdm_id, at: datetime, *, kind: str = "follow_up", status: str = "done") -> None:
    """A task finished at `at`: done (completed_at) or cancelled (cancelled_at)."""
    db.add(
        BdmTask(
            kind=kind,
            title="Call back",
            due_on=india_today(),
            source="manual",
            assignee_user_id=bdm_id,
            status=status,
            completed_at=at if status == "done" else None,
            cancelled_at=at if status == "cancelled" else None,
        )
    )
    await db.commit()


async def lead(db, bdm_id, org_id, at: datetime) -> None:
    db.add(
        Enquiry(
            division="it",
            name="Asha",
            email=f"lead-{uuid.uuid4().hex[:10]}@example.local",
            subject="BDM lead",
            message="-",
            source="bdm",
            bdm_user_id=bdm_id,
            bdm_organization_id=org_id,
            created_at=at,
        )
    )
    await db.commit()

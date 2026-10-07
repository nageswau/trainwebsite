"""bdm-023 (DEC-SCOPE-104, spec §3-§5): the management dashboard -- the 8 overview tiles and the alert list of Appendix B.4 for a
manager's team; super_admin reads all teams, or one manager's with `manager_user_id` (R2). Read-only: no write, no audit, no log line.

A fixed number of statements whatever the team size: the database clock, one SELECT of scalar subqueries (every tile and every alert
count), then one query per alert list. Each count is taken over the same statement as its list, so the two can't disagree."""

from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Select, case, distinct, exists, func, literal, null, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import (
    BDM_APPOINTMENT_OPEN,
    BDM_MOU_STATUS_LABELS,
    BdmAppointment,
    BdmAppointmentEvent,
    BdmDailyReport,
    BdmMou,
    BdmOrganization,
    BdmProfile,
    BdmTask,
    BdmTrip,
    User,
)
from app.schemas import BdmManagerDashboardOut
from app.services.bdm import require_manager, team_filter
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import db_now, pending_filter, today_ist
from app.services.bdm_metrics import DAILY_METRICS, month_range

router = APIRouter(prefix="/bdm/manager/dashboard", tags=["bdm-dashboard"])
ITEM_LIMIT = 10  # R8
MOU_IN_PROGRESS = ("discussion_started", "proposal_sent", "under_negotiation", "draft_shared")  # T-M07
MOU_PENDING = ("proposal_sent", "draft_shared")  # AL-4
MOU_PENDING_DAYS = 5  # D19
SEP = " · "
Owner = aliased(User)

TILES = (
    ("T-M01", "Total BDMs", "Active BDMs."),
    ("T-M02", "Today's Appointments", "Appointments starting today, except cancelled ones."),
    ("T-M03", "Upcoming Appointments", "Scheduled, confirmed or rescheduled appointments after today."),
    ("T-M04", "BDMs Travelling", "BDMs on an approved trip that covers today."),
    ("T-M05", "Trips This Month", "Trips starting this month, except cancelled or rejected ones."),
    ("T-M06", "Meetings Completed", "Appointments this month that are completed."),
    ("T-M07", "MoUs in Progress", "Current MoUs from Discussion Started to Draft Shared."),
    ("T-M08", "MoUs Signed", "MoUs moved to Signed this month."),
)
# key -> (label, tone, record), in Appendix B.4 order
ALERTS = {
    "AL-1": ("Appointment not confirmed", "warning", "appointment"),
    "AL-2": ("Travel approval pending", "warning", "trip"),
    "AL-3": ("Follow-up overdue", "danger", "task"),
    "AL-4": ("MoU pending", "warning", "mou"),
    "AL-5": ("Appointment completed", "success", "appointment"),
    "AL-6": ("Outcome missing", "danger", "appointment"),
    "AL-7": ("Daily report not submitted", "warning", "daily_report"),
}


async def _scope(db: AsyncSession, user: User, manager_user_id: UUID | None) -> tuple[Select, User | None]:
    """The team's BDM ids as a sub-select (R1-R3), and the chosen manager when super_admin picked one."""
    require_manager(user)
    if manager_user_id is None:
        return select(BdmProfile.user_id).where(*team_filter(user)), None
    if user.role != "super_admin":
        raise HTTPException(422, "Only a super admin can choose a manager")
    manager = await db.scalar(select(User).where(User.id == manager_user_id, User.role == "bdm_manager"))
    if manager is None:
        raise HTTPException(404, "Manager not found")
    return select(BdmProfile.user_id).where(BdmProfile.reporting_manager_user_id == manager.id), manager


def _count(model, *where):
    return select(func.count()).select_from(model).where(*where).scalar_subquery()


def _tiles(team: Select, today: date) -> dict:
    day_start, day_end = day_range(today)
    month_start, month_end = month_range(today.replace(day=1))
    appts = BdmAppointment.bdm_user_id.in_(team)
    trips = BdmTrip.bdm_user_id.in_(team)
    return {
        "T-M01": select(func.count()).select_from(BdmProfile).join(User, User.id == BdmProfile.user_id)
        .where(BdmProfile.user_id.in_(team), User.active.is_(True)).scalar_subquery(),
        "T-M02": _count(BdmAppointment, appts, BdmAppointment.status != "cancelled", BdmAppointment.starts_at >= day_start,
                        BdmAppointment.starts_at < day_end),
        "T-M03": _count(BdmAppointment, appts, BdmAppointment.status.in_(BDM_APPOINTMENT_OPEN), BdmAppointment.starts_at >= day_end),
        "T-M04": select(func.count(distinct(BdmTrip.bdm_user_id))).where(
            trips, BdmTrip.approval_status == "approved", BdmTrip.travel_status.in_(("planned", "in_progress")),
            BdmTrip.travel_date <= today, BdmTrip.return_date >= today).scalar_subquery(),
        "T-M05": _count(BdmTrip, trips, BdmTrip.travel_status != "cancelled", BdmTrip.approval_status != "rejected",
                        BdmTrip.travel_date >= month_start.date(), BdmTrip.travel_date < month_end.date()),
        "T-M06": DAILY_METRICS["meetings_completed"][1](team, month_start, month_end),  # M-06 over the month
        "T-M07": select(func.count()).select_from(BdmMou).join(BdmOrganization, BdmOrganization.id == BdmMou.organization_id).where(
            BdmMou.is_current, BdmMou.status.in_(MOU_IN_PROGRESS), BdmOrganization.assigned_bdm_user_id.in_(team),
            BdmOrganization.archived_at.is_(None)).scalar_subquery(),
        "T-M08": DAILY_METRICS["mous_signed"][1](team, month_start, month_end),  # M-11 over the month
    }


def _row(id_, title, bdm_id, bdm_name, at, organization_id) -> Select:
    """Every alert list's columns, labelled so a list and its count subquery read the same shape."""
    return select(id_.label("id"), title.label("title"), bdm_id.label("bdm_id"), bdm_name.label("bdm_name"), at.label("at"),
                  organization_id.label("organization_id"))


def _appointments(team: Select, *where, at=BdmAppointment.starts_at) -> Select:
    return (_row(BdmAppointment.id, func.concat(BdmAppointment.code, SEP, BdmOrganization.name), Owner.id, Owner.full_name, at,
                 BdmAppointment.organization_id)
            .join(BdmOrganization, BdmOrganization.id == BdmAppointment.organization_id).join(Owner, Owner.id == BdmAppointment.bdm_user_id)
            .where(BdmAppointment.bdm_user_id.in_(team), *where))


def _alerts(team: Select, now: datetime, today: date) -> dict[str, tuple[Select, tuple]]:
    """key -> (rows: id, title, bdm id, bdm name, at, organization id; ordering). The order puts the most urgent first."""
    day_start, day_end = day_range(today)
    yesterday = today - timedelta(days=1)
    completed = BdmAppointmentEvent.created_at
    status_label = case(BDM_MOU_STATUS_LABELS, value=BdmMou.status)
    submitted = select(BdmDailyReport.id).where(BdmDailyReport.bdm_user_id == User.id, BdmDailyReport.report_date == yesterday)
    return {
        "AL-1": (_appointments(team, BdmAppointment.status.in_(("scheduled", "rescheduled")), BdmAppointment.starts_at > now,
                               BdmAppointment.starts_at <= now + timedelta(hours=24)), (BdmAppointment.starts_at, BdmAppointment.id)),
        "AL-2": (_row(BdmTrip.id, func.concat(BdmTrip.code, SEP, BdmTrip.from_place, " → ", BdmTrip.to_place), Owner.id, Owner.full_name,
                      BdmTrip.travel_date, null())
                 .join(Owner, Owner.id == BdmTrip.bdm_user_id)
                 .where(BdmTrip.bdm_user_id.in_(team), BdmTrip.approval_status == "submitted", BdmTrip.travel_status == "planned"),
                 (BdmTrip.travel_date, BdmTrip.code)),
        "AL-3": (_row(BdmTask.id, func.concat_ws(SEP, BdmTask.title, BdmOrganization.name), Owner.id, Owner.full_name, BdmTask.due_on,
                      BdmTask.organization_id)
                 .outerjoin(BdmOrganization, BdmOrganization.id == BdmTask.organization_id).join(Owner, Owner.id == BdmTask.assignee_user_id)
                 .where(BdmTask.assignee_user_id.in_(team), BdmTask.kind == "follow_up", BdmTask.status == "open", BdmTask.due_on < today),
                 (BdmTask.due_on, BdmTask.id)),
        "AL-4": (_row(BdmMou.id, func.concat(BdmOrganization.name, SEP, status_label), Owner.id, Owner.full_name, BdmMou.status_changed_at,
                      BdmMou.organization_id)
                 .join(BdmOrganization, BdmOrganization.id == BdmMou.organization_id).join(Owner, Owner.id == BdmOrganization.assigned_bdm_user_id)
                 .where(BdmOrganization.assigned_bdm_user_id.in_(team), BdmOrganization.archived_at.is_(None), BdmMou.is_current,
                        BdmMou.status.in_(MOU_PENDING), BdmMou.status_changed_at <= now - timedelta(days=MOU_PENDING_DAYS)),
                 (BdmMou.status_changed_at, BdmMou.id)),
        "AL-5": (_appointments(team, BdmAppointment.status == "completed", completed >= day_start, completed < day_end, at=completed)
                 .join(BdmAppointmentEvent, (BdmAppointmentEvent.appointment_id == BdmAppointment.id)
                       & (BdmAppointmentEvent.to_status == "completed")),
                 (completed.desc(), BdmAppointment.id)),
        "AL-6": (_appointments(team, pending_filter(True)), (BdmAppointment.starts_at, BdmAppointment.id)),
        "AL-7": (_row(User.id, User.full_name, User.id, User.full_name, literal(yesterday), null())
                 .join(BdmProfile, BdmProfile.user_id == User.id)
                 .where(User.id.in_(team), User.active.is_(True), BdmProfile.created_at < day_start, ~exists(submitted)),
                 (User.full_name, User.id)),
    }


@router.get("", response_model=BdmManagerDashboardOut)
async def manager_dashboard(manager_user_id: UUID | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    team, manager = await _scope(db, user, manager_user_id)
    now = await db_now(db)
    today = today_ist(now)
    tiles = _tiles(team, today)
    alerts = _alerts(team, now, today)
    counts = {key: select(func.count()).select_from(rows.subquery()).scalar_subquery() for key, (rows, _) in alerts.items()}
    values = dict(zip([*tiles, *counts], (await db.execute(select(*tiles.values(), *counts.values()))).one(), strict=True))

    out = []
    for key, (rows, order) in alerts.items():
        found = (await db.execute(rows.order_by(*order).limit(ITEM_LIMIT))).all()
        label, tone, record = ALERTS[key]
        out.append({
            "key": key, "label": label, "tone": tone, "record": record, "count": values[key],
            "items": [{"id": id_, "title": title, "bdm": {"id": bdm_id, "full_name": bdm_name}, "at": at, "organization_id": org_id}
                      for id_, title, bdm_id, bdm_name, at, org_id in found],
        })
    return {
        "today": today, "month": today.replace(day=1),
        "manager": {"id": manager.id, "full_name": manager.full_name} if manager else None,
        "tiles": [{"key": key, "label": label, "definition": definition, "value": values[key]} for key, label, definition in TILES],
        "alerts": out,
    }

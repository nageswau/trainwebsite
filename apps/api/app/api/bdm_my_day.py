"""bdm-014 (DEC-SCOPE-096, spec §3-§5): the BDM's My Day -- today's appointments, upcoming travel, follow-ups due, and the BDM type's
"Today's overview" tiles (Appendix B.2). Own records only, from the session. Read-only: no write, no audit, no log line.

A fixed number of statements whatever the data volume (AC4, K12): every count is a scalar subquery of one SELECT, plus one query each
for today's appointments, the upcoming trips (their appointment counts correlated) and the follow-up groups."""

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BDM_ORG_TYPES, BdmActivity, BdmAppointment, BdmMou, BdmOrganization, BdmTask, BdmTrip, Enquiry, User
from app.schemas import BdmMyDayOut
from app.services.bdm import bdm_context
from app.services.bdm_appointments import IST, db_now, today_ist

router = APIRouter(prefix="/bdm/my-day", tags=["bdm-my-day"])
APPOINTMENT_LIMIT = 50  # K8: far above a real day
TRIP_LIMIT = 5
PENDING_AGREEMENT = ("proposal_sent", "under_negotiation", "draft_shared")  # T-A5
MOU_PENDING = ("discussion_started", "proposal_sent", "under_negotiation", "draft_shared")  # T-S7
SCHOOL_ACTIVITIES = (  # T-S8 (D30), plus the common seminar_workshop (K4)
    "seminar", "workshop", "seminar_workshop", "parent_orientation", "teacher_orientation", "career_guidance_presentation",
    "psychometric_presentation", "profile_building_presentation",
)
COLLEGE_SEMINARS = ("student_seminar", "workshop", "seminar_workshop")  # T-K5 (K4)
# (key, label, note when not tracked) per BDM type, in the source's order (AC2). A note means "not tracked" (AC3, K5, K6).
TILES = {
    "agent": (
        ("T-A1", "Today's appointments", None), ("T-A2", "Today's agent meetings", None), ("T-A3", "Agents to follow up", None),
        ("T-A4", "New agent leads", None), ("T-A5", "Pending agreements", None),
        ("T-A6", "Agents awaiting onboarding", "Agent onboarding requests are not recorded in EduSphere yet."),
        ("T-A7", "Agent-related tasks", None), ("T-A8", "Travel for today/tomorrow", None),
    ),
    "school": (
        ("T-S1", "School appointments", None), ("T-S2", "Principal meetings", None), ("T-S3", "Management meetings", None),
        ("T-S4", "Follow-ups", None), ("T-S5", "School visits", None), ("T-S6", "Proposals", None), ("T-S7", "MoUs pending", None),
        ("T-S8", "School activities", None),
    ),
    "college": (
        ("T-K1", "College meetings", None), ("T-K2", "Placement-cell meetings", None), ("T-K3", "Principal/HOD meetings", None),
        ("T-K4", "Course promotion activities", None), ("T-K5", "Seminars", None), ("T-K6", "Internship discussions", None),
        ("T-K7", "MoU follow-ups", "MoU follow-ups are not created in EduSphere yet."), ("T-K8", "Student leads", None),
    ),
}
ORG_OF_APPT = BdmOrganization.id == BdmAppointment.organization_id
ORG_OF_TASK = BdmOrganization.id == BdmTask.organization_id


def _counts(user: User, today) -> dict:
    """Every count My Day can show, as scalar subqueries keyed by tile ID (plus the section totals)."""
    start = datetime.combine(today, time(), IST)
    end = start + timedelta(days=1)

    def appts(*where, org_type: str | None = None):
        stmt = select(func.count()).select_from(BdmAppointment)
        if org_type:
            stmt = stmt.join(BdmOrganization, ORG_OF_APPT).where(BdmOrganization.org_type == org_type)
        return stmt.where(BdmAppointment.bdm_user_id == user.id, BdmAppointment.status != "cancelled",
                          BdmAppointment.starts_at >= start, BdmAppointment.starts_at < end, *where).scalar_subquery()

    def of_type(*types):
        return BdmAppointment.appointment_type.in_(types)

    def open_due(kind: str):
        return (BdmTask.assignee_user_id == user.id, BdmTask.kind == kind, BdmTask.status == "open", BdmTask.due_on <= today)

    def tasks_at(kind: str, org_type: str, counted=None):
        return (select(func.count(counted if counted is not None else BdmTask.id)).select_from(BdmTask).join(BdmOrganization, ORG_OF_TASK)
                .where(*open_due(kind), BdmOrganization.org_type == org_type).scalar_subquery())

    def orgs_with_mou(org_type: str, statuses):
        return (select(func.count()).select_from(BdmOrganization)
                .join(BdmMou, (BdmMou.organization_id == BdmOrganization.id) & BdmMou.is_current)
                .where(BdmOrganization.assigned_bdm_user_id == user.id, BdmOrganization.org_type == org_type,
                       BdmOrganization.archived_at.is_(None), BdmMou.status.in_(statuses)).scalar_subquery())

    live_trip = (BdmTrip.bdm_user_id == user.id, BdmTrip.travel_status != "cancelled", BdmTrip.approval_status != "rejected")
    return {
        "appointments": appts(),
        "trips": select(func.count()).select_from(BdmTrip).where(*live_trip, BdmTrip.travel_date > today).scalar_subquery(),
        "T-A2": appts(of_type("agent_meeting", "agent_visit")),
        "T-A3": tasks_at("follow_up", "agent", distinct(BdmTask.organization_id)),
        "T-A4": select(func.count()).select_from(BdmOrganization).where(
            BdmOrganization.assigned_bdm_user_id == user.id, BdmOrganization.org_type == "agent",
            BdmOrganization.created_at >= start, BdmOrganization.created_at < end).scalar_subquery(),
        "T-A5": orgs_with_mou("agent", PENDING_AGREEMENT),
        "T-A7": tasks_at("task", "agent"),
        "T-A8": select(func.count()).select_from(BdmTrip).where(
            *live_trip, BdmTrip.travel_date <= today + timedelta(days=1), BdmTrip.return_date >= today).scalar_subquery(),
        "T-S1": appts(org_type="school"),
        "T-S2": appts(of_type("principal_meeting")),
        "T-S3": appts(of_type("management_meeting")),
        "T-S4": select(func.count()).select_from(BdmTask).where(*open_due("follow_up")).scalar_subquery(),
        "T-S5": select(func.count()).select_from(BdmActivity).where(
            BdmActivity.bdm_user_id == user.id, BdmActivity.channel == "visit",
            BdmActivity.occurred_at >= start, BdmActivity.occurred_at < end).scalar_subquery(),
        "T-S6": orgs_with_mou("school", ("proposal_sent",)),
        "T-S7": orgs_with_mou("school", MOU_PENDING),
        "T-S8": appts(of_type(*SCHOOL_ACTIVITIES)),
        "T-K1": appts(org_type="college"),
        "T-K2": appts(of_type("placement_cell_meeting")),
        "T-K3": appts(of_type("principal_meeting", "hod_meeting")),
        "T-K4": appts(of_type("course_promotion")),
        "T-K5": appts(of_type(*COLLEGE_SEMINARS)),
        "T-K6": appts(of_type("internship_discussion")),
        "T-K8": select(func.count()).select_from(Enquiry).where(
            Enquiry.bdm_user_id == user.id, Enquiry.created_at >= start, Enquiry.created_at < end).scalar_subquery(),
    }


@router.get("", response_model=BdmMyDayOut)
async def my_day(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await bdm_context(db, user)
    today = today_ist(await db_now(db))
    start = datetime.combine(today, time(), IST)
    tiles = TILES[profile.bdm_type]

    wanted = ["appointments", "trips", *(key for key, _, note in tiles if note is None and key != "T-A1")]
    available = _counts(user, today)
    row = (await db.execute(select(*(available[k] for k in wanted)))).one()
    counts: dict[str, int] = dict(zip(wanted, row.tuple(), strict=True))
    counts["T-A1"] = counts["appointments"]  # T-A1 = T-C01

    appts = (await db.execute(
        select(BdmAppointment, BdmOrganization).join(BdmOrganization, ORG_OF_APPT)
        .where(BdmAppointment.bdm_user_id == user.id, BdmAppointment.status != "cancelled",
               BdmAppointment.starts_at >= start, BdmAppointment.starts_at < start + timedelta(days=1))
        .order_by(BdmAppointment.starts_at, BdmAppointment.id).limit(APPOINTMENT_LIMIT)
    )).all()

    linked = (select(func.count()).select_from(BdmAppointment)
              .where(BdmAppointment.trip_id == BdmTrip.id, BdmAppointment.status != "cancelled").correlate(BdmTrip).scalar_subquery())
    trips = (await db.execute(
        select(BdmTrip, linked)
        .where(BdmTrip.bdm_user_id == user.id, BdmTrip.travel_status != "cancelled", BdmTrip.approval_status != "rejected",
               BdmTrip.travel_date > today)
        .order_by(BdmTrip.travel_date, BdmTrip.code).limit(TRIP_LIMIT)
    ))

    group = case((BdmTask.source == "mou", "mou"), else_=func.coalesce(BdmOrganization.org_type, "none"))
    found: dict[str, int] = dict((await db.execute(
        select(group, func.count()).select_from(BdmTask).outerjoin(BdmOrganization, ORG_OF_TASK)
        .where(BdmTask.assignee_user_id == user.id, BdmTask.kind == "follow_up", BdmTask.status == "open", BdmTask.due_on <= today)
        .group_by(group)
    )).all())
    groups = [{"key": key, "count": found[key]} for key in (*BDM_ORG_TYPES, "none", "mou") if found.get(key)]

    return {
        "today": today, "bdm_type": profile.bdm_type,
        "appointments": {
            "count": counts["appointments"], "truncated": counts["appointments"] > len(appts),
            "items": [{
                "id": a.id, "code": a.code, "starts_at": a.starts_at, "duration_minutes": a.duration_minutes,
                "appointment_type": a.appointment_type, "status": a.status,
                "organization": {"id": o.id, "code": o.code, "name": o.name, "org_type": o.org_type, "archived": o.archived_at is not None},
            } for a, o in appts],
        },
        "trips": {
            "total": counts["trips"],
            "items": [{
                "id": t.id, "code": t.code, "travel_date": t.travel_date, "return_date": t.return_date, "from_place": t.from_place,
                "to_place": t.to_place, "approval_status": t.approval_status, "travel_status": t.travel_status, "appointment_count": n,
            } for t, n in trips.tuples()],
        },
        "follow_ups": {"total": sum(g["count"] for g in groups), "groups": groups},
        "tiles": [{"key": key, "label": label, "tracked": note is None, "value": counts[key] if note is None else None, "note": note}
                  for key, label, note in tiles],
    }

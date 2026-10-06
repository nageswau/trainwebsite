"""bdm-013 (DEC-SCOPE-079, spec §5): the read-only BDM calendar -- appointments, trips, follow-ups and tasks in one date range.

Whose calendar comes from the session (a BDM) or a validated `bdm_user_id` (a manager's team, super_admin any BDM); out of scope is
the same 404 as a missing BDM. Three indexed range queries, each joined to its organization; no write, no audit, no log line."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmAppointment, BdmOrganization, BdmProfile, BdmTask, BdmTrip, User
from app.schemas import BdmCalendarOut
from app.services.bdm import bdm_context, person_ref
from app.services.bdm_appointments import IST, db_now, ist_bounds, today_ist
from app.services.bdm_tasks import is_overdue

router = APIRouter(prefix="/bdm/calendar", tags=["bdm-calendar"])
MAX_DAYS = 31  # K2
MAX_ROWS = 500  # K9: per source; far above real use
SEMINAR_TYPES = frozenset({"seminar_workshop", "seminar", "workshop", "student_seminar"})  # K5
NOT_FOUND = "BDM not found"


async def _whose(db: AsyncSession, user: User, bdm_user_id: UUID | None) -> User:
    """K3: a BDM reads their own; a manager names a BDM who reports to them; super_admin names any BDM; anyone else 403."""
    if user.role == "bdm":
        await bdm_context(db, user)
        if bdm_user_id is not None:
            raise HTTPException(422, "bdm_user_id is only for managers")
        return user
    if user.role not in ("bdm_manager", "super_admin"):
        raise HTTPException(403, "BDM role required")
    if bdm_user_id is None:
        raise HTTPException(422, "Choose a BDM")
    stmt = select(User).join(BdmProfile, BdmProfile.user_id == User.id).where(User.id == bdm_user_id)
    if user.role == "bdm_manager":
        stmt = stmt.where(BdmProfile.reporting_manager_user_id == user.id)
    bdm = await db.scalar(stmt)
    if bdm is None:
        raise HTTPException(404, NOT_FOUND)
    return bdm


def _org(org: BdmOrganization | None) -> dict | None:
    return None if org is None else {"id": org.id, "code": org.code, "name": org.name, "archived": org.archived_at is not None}


@router.get("", response_model=BdmCalendarOut)
async def calendar(
    date_from: date,
    date_to: date,
    bdm_user_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bdm = await _whose(db, user, bdm_user_id)
    if date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise HTTPException(422, f"The calendar shows at most {MAX_DAYS} days")
    today = today_ist(await db_now(db))

    appts = (await db.execute(
        select(BdmAppointment, BdmOrganization).join(BdmOrganization, BdmOrganization.id == BdmAppointment.organization_id)
        .where(BdmAppointment.bdm_user_id == bdm.id, BdmAppointment.status != "cancelled", *ist_bounds(date_from, date_to))
        .order_by(BdmAppointment.starts_at, BdmAppointment.id).limit(MAX_ROWS + 1)
    )).all()
    trips = (await db.scalars(
        select(BdmTrip)
        .where(BdmTrip.bdm_user_id == bdm.id, BdmTrip.travel_date <= date_to, BdmTrip.return_date >= date_from,
               BdmTrip.travel_status != "cancelled", BdmTrip.approval_status != "rejected")
        .order_by(BdmTrip.travel_date, BdmTrip.code).limit(MAX_ROWS + 1)
    )).all()
    tasks = (await db.execute(
        select(BdmTask, BdmOrganization).outerjoin(BdmOrganization, BdmOrganization.id == BdmTask.organization_id)
        .where(BdmTask.assignee_user_id == bdm.id, BdmTask.status != "cancelled", BdmTask.due_on >= date_from, BdmTask.due_on <= date_to)
        .order_by(BdmTask.due_on, BdmTask.created_at, BdmTask.id).limit(MAX_ROWS + 1)
    )).all()

    return {
        "bdm": person_ref(bdm), "date_from": date_from, "date_to": date_to, "today": today,
        "truncated": any(len(rows) > MAX_ROWS for rows in (appts, trips, tasks)),
        "appointments": [{
            "id": a.id, "code": a.code, "day": a.starts_at.astimezone(IST).date(), "starts_at": a.starts_at,
            "duration_minutes": a.duration_minutes, "appointment_type": a.appointment_type, "status": a.status,
            "seminar": a.appointment_type in SEMINAR_TYPES, "organization": _org(o),
        } for a, o in appts[:MAX_ROWS]],
        "trips": [{
            "id": t.id, "code": t.code, "travel_date": t.travel_date, "return_date": t.return_date, "from_place": t.from_place,
            "to_place": t.to_place, "mode": t.mode, "approval_status": t.approval_status, "travel_status": t.travel_status,
        } for t in trips[:MAX_ROWS]],
        "tasks": [{
            "id": t.id, "kind": t.kind, "title": t.title, "due_on": t.due_on, "status": t.status,
            "overdue": is_overdue(t.status, t.due_on, today), "organization": _org(o),
        } for t, o in tasks[:MAX_ROWS]],
    }

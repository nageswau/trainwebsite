"""upc-011 (DEC-SCOPE-150, spec CL8-CL10, §3): the read-only §9 calendar -- university meetings, university visits and partnership
events over at most 31 days, whose calendar it is, and the overlap warning per employee. No write, no audit, no log line (bdm-013)."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import CalendarEmployeesOut, PartnershipCalendarOut
from app.services import partnership_calendar as svc
from app.services.bdm_travel import india_today
from app.services.telecaller import person_ref

router = APIRouter(prefix="/partnership/calendar", tags=["partnership-calendar"])


@router.get("", response_model=PartnershipCalendarOut)
async def read_calendar(
    date_from: date,
    date_to: date,
    user_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    people, employee = await svc.scope(db, user, user_id)
    svc.check_range(date_from, date_to)
    items, truncated = await svc.calendar(db, date_from, date_to, people)
    return {
        "date_from": date_from, "date_to": date_to, "today": india_today(), "employee": person_ref(employee) if employee else None,
        "truncated": truncated, "items": items,
    }  # fmt: skip


@router.get("/employees", response_model=CalendarEmployeesOut)
async def calendar_employees(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CL9: whose calendar this caller may open."""
    return {"items": [person_ref(u) for u in await svc.employees(db, user)]}

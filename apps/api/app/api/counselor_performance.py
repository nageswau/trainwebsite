"""ccrm-036 (DEC-SCOPE-269, P1-P9): the overseas counselor's own performance report. Their own figures only -- the request names no
counselor, so there is nothing to tamper with. Read-only and not audited (P9).

ccrm-053 (DEC-SCOPE-325, PF2-PF6): the intake and lead-division filters on both reports, and the Overseas Admin's routes -- every overseas
counselor (`admin_router`), its CSV / xlsx (audited, committed before the file is returned) and one counselor's report. The counselor's
own route still names nobody: any `counselor_id` it is sent is ignored (PF4)."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE, export_response
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, User
from app.schemas import INTAKE_MESSAGE, CounselorPerformanceOut, CounselorPerformanceTeamOut, is_intake
from app.services import counselor_performance
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.bdm_performance import period

router = APIRouter(prefix="/counselor/performance", tags=["counselor-performance"])
admin_router = APIRouter(prefix="/overseas-admin/counselor-performance", tags=["counselor-performance"])

FORBIDDEN = "Only an overseas counselor has a performance report"
ADMIN_ONLY = "Overseas Administrator role required"
NOT_FOUND = "Counselor not found"
BAD_DIVISION = "Choose the Overseas or IT lead division"
ADMIN_ROLES = ("overseas_admin", "super_admin")  # PF6


@dataclass(frozen=True)
class Filters:
    start: date
    end: date
    intake: str | None
    division: str | None


async def _filters(from_: date | None = Query(None, alias="from"), to: date | None = None, intake: str | None = None, division: str | None = None, db: AsyncSession = Depends(get_db)) -> Filters:
    """P2: `from`..`to` inclusive IST dates, default this month. PF2 / PF3: an empty filter is no filter; any other bad value is 422."""
    intake, division = intake or None, division or None
    if intake is not None and not is_intake(intake):
        raise HTTPException(422, INTAKE_MESSAGE)
    if division is not None and division not in counselor_performance.LEAD_DIVISIONS:
        raise HTTPException(422, BAD_DIVISION)
    return Filters(*period(from_, to, india_date(await db_now(db))), intake, division)


def _admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, ADMIN_ONLY)
    return user


def _counselor(user: User = Depends(get_current_user)) -> User:
    """P1: the overseas counselor only -- checked before the filters, so everyone else is 403 whatever they send."""
    if user.role != "counselor" or user.division != "overseas":
        raise HTTPException(403, FORBIDDEN)
    return user


@router.get("", response_model=CounselorPerformanceOut)
async def my_performance(user: User = Depends(_counselor), f: Filters = Depends(_filters), db: AsyncSession = Depends(get_db)):
    return await counselor_performance.report(db, user, f.start, f.end, await db_now(db), f.intake, f.division)


async def _team(user: User = Depends(_admin), f: Filters = Depends(_filters), db: AsyncSession = Depends(get_db)) -> tuple[User, Filters, dict]:
    return user, f, await counselor_performance.team(db, f.start, f.end, await db_now(db), f.intake, f.division)


# Registered before `/{counselor_id}`, as the reports routers do.
@admin_router.get(".csv")
async def team_csv(read: tuple[User, Filters, dict] = Depends(_team), db: AsyncSession = Depends(get_db)):
    """AC6: the screen's columns, rows and Total row. One audit row, committed before the file is returned (fail closed)."""
    return await _export(db, *read, "csv")


@admin_router.get(".xlsx")
async def team_xlsx(read: tuple[User, Filters, dict] = Depends(_team), db: AsyncSession = Depends(get_db)):
    """nehn-004 (DEC-SCOPE-282 X3): the CSV's twin."""
    return await _export(db, *read, "xlsx")


async def _export(db: AsyncSession, user: User, f: Filters, payload: dict, fmt: str) -> Response:
    response = export_response(payload, fmt, f"counselor-performance-{f.start}-to-{f.end}", "Counselor performance")
    db.add(AuditLog(user_id=user.id, action="counselor_performance.export", entity_type="counselor_performance", entity_id="team", metadata_json={
        "from": f.start.isoformat(), "to": f.end.isoformat(), "intake": f.intake, "division": f.division, "rows": len(payload["items"]), "format": fmt,
    }))  # fmt: skip
    await db.commit()
    return response


@admin_router.get("", response_model=CounselorPerformanceTeamOut)
async def team(response: Response, read: tuple[User, Filters, dict] = Depends(_team)):
    """PF7-PF9: one row per overseas counselor over the period, with a Total row."""
    response.headers.update(NO_STORE)
    return read[2]


@admin_router.get("/{counselor_id}", response_model=CounselorPerformanceOut)
async def counselor_report(counselor_id: UUID, _: User = Depends(_admin), f: Filters = Depends(_filters), db: AsyncSession = Depends(get_db)):
    """The counselor's own report (ccrm-036), read by the Overseas Admin; an id that is not an overseas counselor is 404 (PF6)."""
    counselor = await counselor_performance.overseas_counselor(db, counselor_id)
    if counselor is None:
        raise HTTPException(404, NOT_FOUND)
    body = await counselor_performance.report(db, counselor, f.start, f.end, await db_now(db), f.intake, f.division)
    return {**body, "counselor": {"id": counselor.id, "full_name": counselor.full_name, "active": counselor.active}}

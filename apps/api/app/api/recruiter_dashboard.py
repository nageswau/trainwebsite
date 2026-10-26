"""rec-032 (DEC-SCOPE-180, API §12CU): the recruiter dashboard -- the fourteen §1 tiles, every figure computed by
`services/recruiter_metrics.py`. Read-only and never cached; one request for the page that shows it.

Scope (DB1-DB3): a recruiter reads their own figures (another recruiter id → 403); a placement manager their team + the unassigned
queue, or one direct report; super_admin everything, or any one recruiter (an id out of scope → 404). Every other role → 403.

rec-033 (DEC-SCOPE-182, API §12CW): the §24 performance dashboard -- P1-P15 per recruiter over a period, for the placement manager (their
team + Unassigned), super_admin and it_admin (everyone); `.csv` is the same table, audited.

rec-034 (DEC-SCOPE-183, API §12CX): §25 per recruiter -- B1-B12 credited to the actor of each event; a recruiter reads their own row, a
placement manager their team, super_admin everyone.

rec-035 (DEC-SCOPE-184, API §12CY): the §26 management dashboard -- M1-M9 for the same readers and scope as rec-033."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE, export_response
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, User
from app.services import recruiter_metrics as metrics
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/recruiter", tags=["recruiter-dashboard"])


@router.get("/dashboard")
async def dashboard(response: Response, recruiter: UUID | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§1: D1-D14 (Appendix B) for the caller's scope, optionally narrowed to one recruiter."""
    response.headers.update(NO_STORE)
    return await metrics.dashboard(db, user, recruiter, await db_now(db))


async def _performance(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    recruiter: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, dict]:
    return user, await metrics.performance(db, user, recruiter, date_from, date_to, await db_now(db))


@router.get("/performance.csv")
async def performance_csv(read: tuple[User, dict] = Depends(_performance), db: AsyncSession = Depends(get_db)):
    """PF9: CSV = the table (same columns and rows, Total last). One audit row, committed before the file is returned (fail closed)."""
    return await _export_performance(db, *read, "csv")


@router.get("/performance.xlsx")
async def performance_xlsx(read: tuple[User, dict] = Depends(_performance), db: AsyncSession = Depends(get_db)):
    """nehn-004 (DEC-SCOPE-280 X3): the CSV's twin."""
    return await _export_performance(db, *read, "xlsx")


async def _export_performance(db: AsyncSession, user: User, payload: dict, fmt: str) -> Response:
    response = export_response(payload, fmt, f"recruiter-performance-{payload['date_from']}-to-{payload['date_to']}", "Recruiter performance")
    recruiter = payload["recruiter"]
    db.add(AuditLog(user_id=user.id, action="recruiter_performance.export", entity_type="recruiter_performance", entity_id="performance", metadata_json={
        "date_from": payload["date_from"].isoformat(), "date_to": payload["date_to"].isoformat(),
        "recruiter": str(recruiter["id"]) if recruiter else None, "rows": len(payload["items"]), "format": fmt,
    }))
    await db.commit()
    return response


@router.get("/performance")
async def performance(response: Response, read: tuple[User, dict] = Depends(_performance)):
    """§24: P1-P15 (Appendix B) per recruiter in scope over the period, with a Total that is the sum of the rows."""
    response.headers.update(NO_STORE)
    return read[1]


@router.get("/performance/by-recruiter")
async def performance_by_recruiter(
    response: Response,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    recruiter: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """§25: B1-B12 (Appendix B) per recruiter over the period, credited to the actor of each event; a recruiter reads their own row."""
    response.headers.update(NO_STORE)
    return await metrics.by_recruiter(db, user, recruiter, date_from, date_to, await db_now(db))
@router.get("/management")
async def management(
    response: Response,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """§26: M1-M9 (Appendix B) -- the seven totals, the top companies by hires and the top job categories for the caller's scope."""
    response.headers.update(NO_STORE)
    return await metrics.management(db, user, date_from, date_to, await db_now(db))

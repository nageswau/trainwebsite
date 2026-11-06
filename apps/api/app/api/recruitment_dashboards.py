"""hrc-033 (DEC-SCOPE-413, API §12LG): the five operational recruitment dashboards -- a board's figures, the records behind one figure, and the
board as a file. `reports.recruitment` opens the route; `services/recruitment_dashboards.py` decides the records in the caller's scope."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE, export_response
from app.api.deps import require_permission
from app.core.database import get_db
from app.models import AuditLog, User
from app.services import recruitment_dashboards as svc
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/recruitment-dashboards", tags=["recruitment-dashboards"])

BoardKey = Literal["funnel", "vacancy", "recruiter", "officer", "interview"]
_READ = require_permission("reports.recruitment", "view", "Your role has no recruitment dashboards")
_DOWNLOAD = require_permission("reports.recruitment", "download", "You cannot download recruitment dashboards")


def _filters(
    date_from: date | None = Query(None, alias="from"), to: date | None = None, owner: UUID | None = None, employer: UUID | None = None, job: UUID | None = None,
) -> tuple[date | None, date | None, UUID | None, UUID | None, UUID | None]:  # fmt: skip
    return date_from, to, owner, employer, job


Filters = Annotated[tuple[date | None, date | None, UUID | None, UUID | None, UUID | None], Depends(_filters)]


async def _export(db: AsyncSession, user: User, board: BoardKey, filters: Filters, fmt: str) -> Response:
    payload = await svc.export_payload(db, user, board, *filters, await db_now(db))
    first, last = payload["date_from"], payload["date_to"]
    stem = f"recruitment-{board}-{first}-to-{last}" if first else f"recruitment-{board}"
    response = export_response(payload, fmt, stem, svc.BOARDS[board].label)
    db.add(AuditLog(user_id=user.id, action="recruitment_dashboard.export", entity_type="recruitment_dashboard", entity_id=board, metadata_json={
        "board": board, "date_from": first.isoformat() if first else None, "date_to": last.isoformat() if last else None, "format": fmt,
        "owner": str(filters[2]) if filters[2] else None, "employer": str(filters[3]) if filters[3] else None, "job": str(filters[4]) if filters[4] else None,
    }))  # fmt: skip
    await db.commit()
    return response


# Registered before `/{board}`, whose path parameter would otherwise also match "funnel.csv".
@router.get("/{board}.csv")
async def board_csv(board: BoardKey, filters: Filters, user: User = Depends(_DOWNLOAD), db: AsyncSession = Depends(get_db)):
    """The board's figures with their definitions. One audit row, committed before the file is returned (fail closed)."""
    return await _export(db, user, board, filters, "csv")


@router.get("/{board}.xlsx")
async def board_xlsx(board: BoardKey, filters: Filters, user: User = Depends(_DOWNLOAD), db: AsyncSession = Depends(get_db)):
    return await _export(db, user, board, filters, "xlsx")


@router.get("/{board}")
async def board_figures(response: Response, board: BoardKey, filters: Filters, user: User = Depends(_READ), db: AsyncSession = Depends(get_db)):
    response.headers.update(NO_STORE)
    return await svc.dashboard(db, user, board, *filters, await db_now(db))


@router.get("/{board}/drill/{figure}")
async def figure_records(
    response: Response, board: BoardKey, figure: str, filters: Filters, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
    user: User = Depends(_READ), db: AsyncSession = Depends(get_db),
):  # fmt: skip
    """The records one figure counted. Built from the figure's own predicate, so `total` equals the figure."""
    response.headers.update(NO_STORE)
    return await svc.drill(db, user, board, figure, *filters, await db_now(db), limit=limit, offset=offset)

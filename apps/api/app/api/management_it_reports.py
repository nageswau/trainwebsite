"""itc-032 (DEC-SCOPE-369) -- the management IT reports. Operational reports (funnel, conversions, activity, training, placement): the
operational management tier (partner, super_admin) and the IT Admin. Revenue: a partner, or an itc-017 accounts reader (an IT or
all-division `payments.view` holder: the IT Admin, the accountant, super_admin). Anyone else 403. Read-only; each CSV export is audited.
API_CONTRACT.md §12JO; RBAC_MATRIX.md §2.269."""

import csv
import io
import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.fee_accounts import _in_it
from app.api.it_accounts import _cell
from app.core.database import get_db
from app.models import AuditLog, User
from app.services import fee_accounts, it_accounts, management_access, permissions
from app.services import management_it_reports as reports

router = APIRouter(prefix="/management/it/reports", tags=["management-it-reports"])
logger = logging.getLogger("app.management_it_reports")

NO_ACCESS = "You do not have access to this IT report"
NO_REPORT = "Report not found"
EXPORT_ACTION = "management.it_reports.export"


async def _may_read(db: AsyncSession, user: User, report: str) -> bool:
    if report == "revenue":
        return user.role == "partner" or (_in_it(user) and await permissions.user_has_grant(db, user, "payments", "view"))
    return management_access.can_view_operational(user) or (user.role == "it_admin" and user.division == "it")


async def _reader(report: str, user: User, db: AsyncSession) -> User:
    if report not in reports.KEYS:
        raise HTTPException(404, NO_REPORT)
    if not await _may_read(db, user, report):
        raise HTTPException(403, NO_ACCESS)
    return user


def _filters(
    program_id: UUID | None = None,
    batch_id: UUID | None = None,
    owner_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = Query(None, max_length=40),
) -> reports.Filters:
    return reports.Filters(program_id, batch_id, owner_id, date_from, date_to, status)


@router.get("")
async def list_reports(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """R4: the reports the caller may open, in tab order; none at all is 403 (the page shows the access card)."""
    mine = [{"key": key, "label": label} for key, label in reports.REPORTS if await _may_read(db, user, key)]
    if not mine:
        raise HTTPException(403, NO_ACCESS)
    return {"reports": mine}


@router.get("/{report}")
async def read_report(
    report: str,
    f: reports.Filters = Depends(_filters),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _reader(report, user, db)
    f = await reports.resolve(db, report, f)
    body = await reports.RUN[report](db, f)
    rows = body.pop("rows")
    return {
        "report": report, **body, "items": rows[offset : offset + limit], "total": len(rows), "limit": limit, "offset": offset, "filters": f.echo(),
        "definitions": reports.definitions(report), "options": await reports.options(db, report),
    }  # fmt: skip


@router.get("/{report}/export")
async def export_report(report: str, f: reports.Filters = Depends(_filters), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _reader(report, user, db)
    f = await reports.resolve(db, report, f)
    rows = (await reports.RUN[report](db, f))["rows"]
    if len(rows) > reports.EXPORT_CAP:
        raise HTTPException(422, it_accounts.TOO_MANY)
    columns = reports.COLUMNS[report]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([header for header, _ in columns])
    for row in rows:
        writer.writerow([_cell("Yes" if row[key] is True else "No" if row[key] is False else row[key]) for _, key in columns])
    # R5: who exported which report with which filters -- never a figure or a name
    db.add(AuditLog(user_id=user.id, action=EXPORT_ACTION, entity_type="management_it_reports", entity_id=report, metadata_json={"report": report, "filters": f.echo(), "rows": len(rows)}))
    await db.commit()
    logger.info("management_it_reports_export", extra={"extra_fields": {"actor_id": str(user.id), "report": report, "rows": len(rows)}})
    filename = f"it-{report}-{fee_accounts.india_today().isoformat()}.csv"
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

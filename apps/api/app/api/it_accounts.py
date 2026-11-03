"""itc-017 (DEC-SCOPE-368) -- the IT accounts workspace's reports: read by a `payments.view` holder in IT or every division (the IT Admin,
the accountant, super_admin); anyone else 403. Read-only; each CSV export is audited. API_CONTRACT.md §12JN; RBAC_MATRIX.md §2.268."""

import csv
import io
import logging
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.fee_accounts import _in_it
from app.api.school_bulk import _safe_cell
from app.core.database import get_db
from app.models import AuditLog, User
from app.services import fee_accounts, it_accounts, permissions

router = APIRouter(prefix="/it/accounts", tags=["it-accounts"])
logger = logging.getLogger("app.it_accounts")

NO_ACCESS = "You do not have access to IT accounts"
NO_REPORT = "Report not found"
EXPORT_ACTION = "it.accounts.export"

Mode = Literal["cash", "upi", "card", "bank_transfer", "cheque", "razorpay"]  # fee_accounts.MODE_LABELS
Kind = Literal["credit_note", "write_off", "refund", "reversal"]  # models.FEE_ADJUSTMENT_KINDS
State = Literal["enrolled_pending_payment", "partially_paid", "overdue"]  # it_accounts.STATES


async def accounts_reader(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
    """F3: IT scope first (no grant lookup for an Overseas caller), then the `payments.view` grant (a user's own deny wins, nehn-007)."""
    if not _in_it(user) or not await permissions.user_has_grant(db, user, "payments", "view"):
        raise HTTPException(403, NO_ACCESS)
    return user


def _filters(
    program_id: UUID | None = None,
    batch_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    group: Literal["day", "month", "course"] = "day",
    mode: Mode | None = None,
    kind: Kind | None = None,
    state: State | None = None,
) -> it_accounts.Filters:
    return it_accounts.Filters(program_id, batch_id, date_from, date_to, group, mode, kind, state)


def _report(report: str) -> str:
    if report not in it_accounts.REPORTS:
        raise HTTPException(404, NO_REPORT)
    return report


@router.get("/reports/{report}")
async def read_report(
    report: str = Depends(_report),
    f: it_accounts.Filters = Depends(_filters),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(accounts_reader),
    db: AsyncSession = Depends(get_db),
):
    f = await it_accounts.resolve(db, f)
    body = await it_accounts.RUN[report](db, f, limit, offset)
    return {"report": report, **body, "limit": limit, "offset": offset, "filters": f.echo(), **await it_accounts.choices(db)}


def _cell(value) -> str:
    """Text through `_safe_cell` (a name or reference typed by a person must not run as a formula, AC4); numbers and dates as written."""
    if value is None:
        return ""
    return _safe_cell(value) if isinstance(value, str) else str(value)


@router.get("/reports/{report}/export")
async def export_report(
    report: str = Depends(_report),
    f: it_accounts.Filters = Depends(_filters),
    user: User = Depends(accounts_reader),
    db: AsyncSession = Depends(get_db),
):
    f = await it_accounts.resolve(db, f)
    items = (await it_accounts.RUN[report](db, f, it_accounts.EXPORT_CAP + 1, 0))["items"]
    if len(items) > it_accounts.EXPORT_CAP:
        raise HTTPException(422, it_accounts.TOO_MANY)
    columns = it_accounts.COLUMNS[report]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([header for header, _ in columns])
    for item in items:
        writer.writerow([_cell(item[key]) for _, key in columns])
    # F7: who exported which report with which filters -- never an amount or a name
    db.add(AuditLog(user_id=user.id, action=EXPORT_ACTION, entity_type="it_accounts", entity_id=report, metadata_json={"report": report, "filters": f.echo(), "rows": len(items)}))
    await db.commit()
    logger.info("it_accounts_export", extra={"extra_fields": {"actor_id": str(user.id), "report": report, "rows": len(items)}})
    filename = f"it-{report}-{fee_accounts.india_today().isoformat()}.csv"
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

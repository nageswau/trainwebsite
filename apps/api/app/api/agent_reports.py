"""AGN-020 -- the agency reports and their CSV export (DEC-SCOPE-063; docs/superpowers/specs/2026-10-03-agn-020-agency-reports-design.md §5).

AGN-004's gate (agency members of an active agency; super admin refused), then the AGN-003 Reports toggle, then the Master-only
kind, then the kind, then the inputs -- in that order, so a refused caller never learns which kinds exist or sees a 422 (§5.1).
Every query parameter is a plain string, validated in the handler after authorization (the AGN-014 precedent). Reads write nothing
and are not audited (DEC-SCOPE-051 R7); only a CSV export is (R3)."""

import csv
import io
import logging
import math
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate
from app.api.deps import get_current_user
from app.api.school_bulk import _safe_cell
from app.core.database import get_db
from app.core.rbac import REPORTS_REFUSED, agent_may, is_agent_staff
from app.models import AgentOrgMember, AuditLog, User
from app.schemas import AgentReportOut
from app.services import agent_reports as reports

logger = logging.getLogger("app.agent_reports")

router = APIRouter(prefix="/workflows/overseas/agent/crm/reports", tags=["agent-reports"])

STAFF_REPORT_REFUSED = "Only an agency Master can view staff performance"
NOT_FOUND = "Report not found"
NO_STORE = {"Cache-Control": "private, no-store"}
EXPORT_ACTION = "agent_report.export"
# R10: 30 exports per user per 10 minutes, counted from the caller's own audit rows (the AGN-008/009/011 no-new-table pattern).
# `agent_orgs.retry_after` is fixed to its 24-hour window, so the wait is worked out here.
EXPORT_LIMIT = 30
EXPORT_WINDOW = timedelta(minutes=10)
EXPORT_THROTTLED = "You've downloaded a lot of reports in a short time. Try again in a few minutes."


async def _export_wait(db: AsyncSession, user: User) -> int:
    """Seconds until the oldest of the caller's last EXPORT_LIMIT exports leaves the window; 0 while under the budget. Runs under
    the caller's membership lock."""
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.user_id == user.id, AuditLog.action == EXPORT_ACTION, AuditLog.created_at > now - EXPORT_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(EXPORT_LIMIT)
        )
    ).all()
    if len(recent) < EXPORT_LIMIT:
        return 0
    return max(1, math.ceil((recent[-1] + EXPORT_WINDOW - now).total_seconds()))


def _authorize(user: User, kind: str) -> AgentOrgMember:
    """Spec §5.1 steps 1-4."""
    membership = _gate(user)
    if not agent_may(user, "can_view_reports"):
        raise HTTPException(403, REPORTS_REFUSED)
    spec = reports.REPORT_KINDS.get(kind)
    if spec is not None and spec.master_only and is_agent_staff(user):
        raise HTTPException(403, STAFF_REPORT_REFUSED)
    if spec is None:
        raise HTTPException(404, NOT_FOUND)
    return membership


def _invalid(error: reports.ReportInputError) -> HTTPException:
    """FastAPI's own 422 list shape, so the panel (and `detailMessage`) find the field by `loc`."""
    return HTTPException(422, [{"loc": ["query", error.param], "msg": error.message, "type": "value_error"}])


def _log(event: str, membership: AgentOrgMember, user: User, kind: str, filters: reports.Filters, rows: int, started: float, level: int = logging.INFO, **extra) -> None:
    """Ids, the kind, which filters were set (never their values), counts and timing -- no names (spec §5.1)."""
    logger.log(level, event, extra={"extra_fields": {
        "org_id": str(membership.org_id), "actor_id": str(user.id), "kind": kind, "scope": "own" if is_agent_staff(user) else "agency",
        "filters": sorted(filters.echo), "rows": rows, "duration_ms": round((time.perf_counter() - started) * 1000), **extra,
    }})


def _cell(value: str | int | None) -> str:
    """Text through `_safe_cell` (formula-looking cells neutralised; it rejects None, so None becomes ""); integers as written."""
    if isinstance(value, int):
        return str(value)
    return _safe_cell("" if value is None else str(value))


def to_csv(payload: dict) -> str:
    """Spec §5.4: UTF-8 with a BOM (Excel shows non-ASCII names), the on-screen labels as the header, a summary's Total row last."""
    columns = payload["columns"]
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer)
    writer.writerow([column["label"] for column in columns])
    for item in [*payload["items"], *([payload["totals"]] if payload["totals"] else [])]:
        writer.writerow([_cell(item[column["key"]]) for column in columns])
    return buffer.getvalue()


def _raw(date_from, date_to, member, country, university, intake, status) -> dict[str, str | None]:
    return {"date_from": date_from, "date_to": date_to, "member": member, "country": country, "university": university, "intake": intake, "status": status}


# Registered before `/{kind}`, whose path parameter would otherwise also match "students.csv".
@router.get("/{kind}.csv")
async def export_report(
    kind: str, date_from: str | None = None, date_to: str | None = None, member: str | None = None, country: str | None = None,
    university: str | None = None, intake: str | None = None, status: str | None = None,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Spec §5.5, one transaction: checks, then the caller's own membership row locked (parallel downloads by one user queue, so
    the throttle count cannot be raced; other users are not blocked), the throttle, the rows, the audit row, and the commit before
    the file is returned -- an audit write that fails means no file (fail closed). A refused export writes nothing."""
    membership = _authorize(user, kind)
    started = time.perf_counter()
    try:
        filters = await reports.parse_filters(db, user, kind, _raw(date_from, date_to, member, country, university, intake, status))
    except reports.ReportInputError as error:
        raise _invalid(error) from None
    await db.execute(select(AgentOrgMember.id).where(AgentOrgMember.id == membership.id).with_for_update())
    wait = await _export_wait(db, user)
    if wait:
        _log("agent_report.export_throttled", membership, user, kind, filters, 0, started, level=logging.WARNING, wait_seconds=wait)
        raise HTTPException(429, EXPORT_THROTTLED, headers={"Retry-After": str(wait)})
    cap = reports.CSV_ROW_CAP
    payload = await reports.report(db, user, kind, filters, limit=cap + 1, offset=0)  # one row past the cap: no count/fetch race
    rows = len(payload["items"])
    if rows > cap:
        _log("agent_report.export_too_large", membership, user, kind, filters, rows, started, level=logging.WARNING)
        raise HTTPException(422, f"This report has more than {cap:,} rows; narrow the filters")
    body = to_csv(payload)
    scope = "own" if is_agent_staff(user) else "agency"
    db.add(AuditLog(user_id=user.id, action=EXPORT_ACTION, entity_type="agent_report", entity_id=kind, metadata_json={"scope": scope, "filters": filters.echo, "rows": rows}))
    await db.commit()
    _log("agent_report.export", membership, user, kind, filters, rows, started)
    start, end = filters.start, filters.end
    filename = f"agency-{kind}-{start.isoformat() if start else 'all'}-to-{end.isoformat() if end else 'all'}.csv"
    return Response(content=body, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"', **NO_STORE})


@router.get("/{kind}", response_model=AgentReportOut)
async def read_report(
    kind: str, response: Response, date_from: str | None = None, date_to: str | None = None, member: str | None = None,
    country: str | None = None, university: str | None = None, intake: str | None = None, status: str | None = None,
    limit: str | None = None, offset: str | None = None,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    membership = _authorize(user, kind)
    started = time.perf_counter()
    try:
        filters = await reports.parse_filters(db, user, kind, _raw(date_from, date_to, member, country, university, intake, status))
        page_limit, page_offset = reports.parse_page(limit, offset)
    except reports.ReportInputError as error:
        raise _invalid(error) from None
    payload = await reports.report(db, user, kind, filters, limit=page_limit, offset=page_offset)
    response.headers.update(NO_STORE)
    _log("agent_report.read", membership, user, kind, filters, len(payload["items"]), started)
    return payload

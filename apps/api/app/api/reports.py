"""nehn-009 (DEC-SCOPE-303, API §12HA, RBAC §2.214): the report library -- every registered report (services/reports) served one way.

`GET /reports` lists the reports whose `<resource>.view` the caller holds. `GET /reports/{id}` is the paged JSON read; `.csv`/`.xlsx`
are every matching row. Checks run report (unknown → 404), grant (403: view for the read, download for a file), then inputs (422, a
sentence naming the field), so input errors never reach a refused caller. The columns pass through the nehn-008 field policy before
the JSON and the files alike, so they can never differ. Reads are not audited; a download is, and its audit row (with the filters)
commits before the file is returned (fail closed). Downloads are throttled per user and refused over the row cap, never cut short."""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import EXPORT_THROTTLED, NO_STORE, _export_wait, export_response
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, User
from app.services import field_policy
from app.services.bdm_appointments import db_now, today_ist
from app.services.permissions import user_has_grant
from app.services.reports import registry
from app.services.reports.registry import Filters, Report

logger = logging.getLogger("app.reports")

router = APIRouter(prefix="/reports", tags=["reports"])

NOT_FOUND = "Report not found"
VIEW_REFUSED = "You don't have permission to view this report"
DOWNLOAD_REFUSED = "You don't have permission to download this report"
EXPORT_ACTION = "report.export"


async def _authorized(db: AsyncSession, user: User, report_id: str, action: str, refused: str) -> Report:
    report = registry.REPORTS.get(report_id)
    if report is None:
        raise HTTPException(404, NOT_FOUND)
    if not await user_has_grant(db, user, report.resource, action):
        raise HTTPException(403, refused)
    return report


def _parse(report: Report, request: Request) -> tuple[Filters, int, int]:
    try:
        return registry.parse(report, request.query_params.multi_items())
    except registry.ReportInputError as error:
        raise HTTPException(422, str(error)) from None


async def _rows(db: AsyncSession, user: User, report: Report, filters: Filters, offset: int, limit: int | None, cap: int | None = None) -> dict:
    """The `{columns, items, totals}` payload for one window of the sorted rows, with `total` (capped by `latest`) and the field policy
    applied. `cap` refuses (422) a result larger than it before any row is read."""
    stmt = report.query(user, filters)
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    if filters.latest is not None:
        total = min(total, filters.latest)
    if cap is not None and total > cap:
        raise HTTPException(422, f"This report has more than {cap:,} rows; narrow the filters")
    window = max(0, total - offset) if limit is None else max(0, min(limit, total - offset))
    rows = (await db.execute(stmt.offset(offset).limit(window))).mappings().all() if window else []
    payload = {
        "id": report.id, "title": report.title, "description": report.description,
        "columns": [{"key": c.key, "label": c.label} for c in report.columns],
        # Raw values: FastAPI renders days as ISO text, `to_csv` writes them the same, and `to_xlsx` types them as dates.
        "items": [{c.key: row[c.key] for c in report.columns} for row in rows],
        "totals": None, "total": total,
    }
    return await field_policy.strip(db, user, payload, report.classes)


def _log(event: str, user: User, report: Report, filters: Filters, rows: int, started: float, **extra) -> None:
    """Ids, the report and which filters were set -- never their values."""
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "report": report.id, "filters": sorted(filters.given),
                                               "rows": rows, "duration_ms": round((time.perf_counter() - started) * 1000), **extra}})


@router.get("")
async def catalogue(response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = []
    for report in registry.REPORTS.values():
        if await user_has_grant(db, user, report.resource, "view"):
            items.append({"id": report.id, "title": report.title, "description": report.description, "filters": list(report.filters),
                          "can_download": await user_has_grant(db, user, report.resource, "download")})
    response.headers.update(NO_STORE)
    return {"items": items}


# Registered before `/{report_id}`, whose path parameter would otherwise also match "enrollments.csv".
@router.get("/{report_id}.csv")
async def export_csv(report_id: str, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _export(db, user, report_id, request, "csv")


@router.get("/{report_id}.xlsx")
async def export_xlsx(report_id: str, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _export(db, user, report_id, request, "xlsx")


async def _export(db: AsyncSession, user: User, report_id: str, request: Request, fmt: str) -> Response:
    """One transaction: the caller's user row locked (one user's parallel downloads queue, so the throttle count cannot be raced), the
    throttle, the cap, the rows, the file, the audit row, and the commit before the file is returned. A refused download writes nothing."""
    started = time.perf_counter()
    report = await _authorized(db, user, report_id, "download", DOWNLOAD_REFUSED)
    filters, _, _ = _parse(report, request)
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    if wait := await _export_wait(db, user, EXPORT_ACTION):
        raise HTTPException(429, EXPORT_THROTTLED, headers={"Retry-After": str(wait)})
    payload = await _rows(db, user, report, filters, 0, None, cap=registry.EXPORT_CAP)
    rows = len(payload["items"])
    response = export_response(payload, fmt, f"{report.id}-{today_ist(await db_now(db)).isoformat()}", report.title)
    db.add(AuditLog(user_id=user.id, action=EXPORT_ACTION, entity_type="report", entity_id=report.id,
                    metadata_json={"filters": filters.given, "rows": rows, "format": fmt}))
    await db.commit()
    _log("report.export", user, report, filters, rows, started, format=fmt)
    return response


@router.get("/{report_id}")
async def read_report(report_id: str, request: Request, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    started = time.perf_counter()
    report = await _authorized(db, user, report_id, "view", VIEW_REFUSED)
    filters, page, size = _parse(report, request)
    payload = await _rows(db, user, report, filters, (page - 1) * size, size)
    response.headers.update(NO_STORE)
    _log("report.read", user, report, filters, len(payload["items"]), started)
    return payload | {"page": page, "page_size": size, "filters": list(report.filters), "applied": filters.given, "options": await report.options(db, user)}

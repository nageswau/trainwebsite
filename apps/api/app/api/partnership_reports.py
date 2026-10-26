"""upc-031 (DEC-SCOPE-173, spec §3): the §32 partnership reports and their CSV export.

Checks run role (403; a manager without a profile too) → kind (404) → inputs (422, a sentence naming the form's field), so a refused caller
never learns which kinds exist (RP4, the tel-024 order). Query parameters are plain strings validated after authorization. Reads are not
audited; an export is, and the audit row commits before the file is returned (fail closed, RP14). The screen shows the first
`SCREEN_ROWS`; an export over `CSV_ROWS` is refused, never cut short (RP11)."""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE, export_response
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, User
from app.services import partnership_reports as reports

logger = logging.getLogger("app.partnership_reports")

router = APIRouter(prefix="/partnership/reports", tags=["partnership-reports"])

NOT_FOUND = "Report not found"
EXPORT_ACTION = "partnership_report.export"
FROM = Query(None, alias="from")
TO = Query(None, alias="to")


async def _report(db: AsyncSession, user: User, kind: str, raw: dict[str, str | None]) -> dict:
    await reports.require_reader(db, user)
    if kind not in reports.TITLES:
        raise HTTPException(404, NOT_FOUND)
    try:
        return await reports.build(db, user, kind, raw)
    except reports.ReportInputError as error:
        raise HTTPException(422, str(error)) from None


def _log(event: str, user: User, kind: str, raw: dict, rows: int, started: float, level: int = logging.INFO) -> None:
    """Ids, the kind and which filters were set -- never their values, never a name."""
    logger.log(level, event, extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "kind": kind, "filters": reports.given(kind, raw),
                                                     "rows": rows, "duration_ms": round((time.perf_counter() - started) * 1000)}})  # fmt: skip


def _raw(window: str | None = None, first: str | None = FROM, last: str | None = TO, month: str | None = None) -> dict[str, str | None]:
    """The filters as plain strings -- one dependency for the read, CSV and xlsx routes, so they cannot drift."""
    return {"window": window, "from": first, "to": last, "month": month}


# Registered before `/{kind}`, whose path parameter would otherwise also match "pipeline.csv".
@router.get("/{kind}.csv")
async def export_report(kind: str, raw: dict = Depends(_raw), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _export(db, user, kind, raw, "csv")


@router.get("/{kind}.xlsx")
async def export_report_xlsx(kind: str, raw: dict = Depends(_raw), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-004 (DEC-SCOPE-280 X3): the CSV export's twin -- the same checks, cap and audit."""
    return await _export(db, user, kind, raw, "xlsx")


async def _export(db: AsyncSession, user: User, kind: str, raw: dict[str, str | None], fmt: str) -> Response:
    started = time.perf_counter()
    payload = await _report(db, user, kind, raw)
    rows = len(payload["items"])
    if rows > reports.CSV_ROWS:
        _log("partnership_report.export_too_large", user, kind, raw, rows, started, logging.WARNING)
        raise HTTPException(422, f"This report has more than {reports.CSV_ROWS:,} rows; narrow the filters")
    response = export_response(payload, fmt, f"partnership-{kind}-{payload['as_of']}", payload["title"])
    db.add(AuditLog(user_id=user.id, action=EXPORT_ACTION, entity_type="partnership_report", entity_id=kind,
                    metadata_json={"filters": reports.given(kind, raw), "rows": rows, "format": fmt}))  # fmt: skip
    await db.commit()
    _log("partnership_report.export", user, kind, raw, rows, started)
    return response


@router.get("/{kind}")
async def read_report(kind: str, response: Response, raw: dict = Depends(_raw), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    started = time.perf_counter()
    payload = await _report(db, user, kind, raw)
    response.headers.update(NO_STORE)
    _log("partnership_report.read", user, kind, raw, payload["total"], started)
    return payload | {"items": payload["items"][: reports.SCREEN_ROWS], "truncated": payload["total"] > reports.SCREEN_ROWS}

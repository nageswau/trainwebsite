"""tel-024 (DEC-SCOPE-108, API §12AB, RBAC §2.34): the five Telecaller CRM management reports and their CSV export.

Checks run in the AGN-020 order -- role (a telecaller and every other role → 403, EVID-019 §22), then the kind (unknown → 404), then
the inputs (422, a sentence naming the form's field, as the other telecaller routes) -- so a refused caller never learns which kinds exist. Query parameters are plain strings validated
after authorization. Reads are not audited; an export is, and the audit row commits before the file is returned (fail closed)."""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE, to_csv
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, User
from app.services import telecaller_reports as reports
from app.services.bdm_appointments import db_now, today_ist

logger = logging.getLogger("app.telecaller_reports")

router = APIRouter(prefix="/telecaller/reports", tags=["telecaller-reports"])

ROLE_REQUIRED = "Telecaller reports are for managers and administrators"
NOT_FOUND = "Report not found"
EXPORT_ACTION = "telecaller_report.export"


async def _report(db: AsyncSession, user: User, kind: str, raw: dict[str, str | None]) -> tuple[dict, reports.Filters]:
    if user.role not in reports.REPORT_ROLES:
        raise HTTPException(403, ROLE_REQUIRED)
    if kind not in reports.REPORTS:
        raise HTTPException(404, NOT_FOUND)
    try:
        filters = reports.parse_filters(raw, today_ist(await db_now(db)))
    except reports.ReportInputError as error:
        raise HTTPException(422, str(error)) from None
    return await reports.report(db, user, kind, filters), filters


def _log(event: str, user: User, kind: str, filters: reports.Filters, rows: int, started: float) -> None:
    """Ids, the kind and which filters were set -- never their values."""
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "kind": kind, "filters": list(filters.given),
                                               "rows": rows, "duration_ms": round((time.perf_counter() - started) * 1000)}})


# Registered before `/{kind}`, whose path parameter would otherwise also match "source.csv".
@router.get("/{kind}.csv")
async def export_report(
    kind: str, date_from: str | None = None, date_to: str | None = None, team: str | None = None, product_id: str | None = None,
    campaign_id: str | None = None, source: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    started = time.perf_counter()
    payload, filters = await _report(db, user, kind, {"date_from": date_from, "date_to": date_to, "team": team, "product_id": product_id,
                                                      "campaign_id": campaign_id, "source": source})
    rows = len(payload["items"])
    db.add(AuditLog(user_id=user.id, action=EXPORT_ACTION, entity_type="telecaller_report", entity_id=kind,
                    metadata_json={"filters": list(filters.given), "rows": rows}))
    await db.commit()
    _log("telecaller_report.export", user, kind, filters, rows, started)
    filename = f"telecaller-{kind}-{filters.date_from.isoformat()}-to-{filters.date_to.isoformat()}.csv"
    return Response(content=to_csv(payload), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', **NO_STORE})


@router.get("/{kind}")
async def read_report(
    kind: str, response: Response, date_from: str | None = None, date_to: str | None = None, team: str | None = None,
    product_id: str | None = None, campaign_id: str | None = None, source: str | None = None,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    started = time.perf_counter()
    payload, filters = await _report(db, user, kind, {"date_from": date_from, "date_to": date_to, "team": team, "product_id": product_id,
                                                      "campaign_id": campaign_id, "source": source})
    response.headers.update(NO_STORE)
    _log("telecaller_report.read", user, kind, filters, len(payload["items"]), started)
    return payload

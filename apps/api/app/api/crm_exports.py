"""ccrm-035 (DEC-SCOPE-268, E1-E9; §13 export, §16 "restrict bulk exports to authorized roles and log exports", AC 11): CSV and xlsx
export of the management CRM reports (the route is beside ccrm-034's in `api/management.py`) and of the overseas counselor's own
application and lead lists (here).

`export` is the one export step: the caller's user row locked (one user's parallel downloads queue, so the throttle cannot be raced),
the throttle (AGN-020 R10, counted from the caller's own `crm.export` audit rows), the rows, the cap, the audit row, and the commit before
the file is returned -- an audit write that fails means no file. A refused export writes nothing. Only allowlisted columns leave (E4):
never contact details, identity or internal reasons."""

import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import EXPORT_THROTTLED, NO_STORE, _export_wait, to_csv
from app.api.deps import get_current_user
from app.application_outcome import label as outcome_label
from app.application_sub_status import label as sub_status_label
from app.core.database import get_db
from app.lead_stages import STAGE_LABELS
from app.models import AuditLog, OverseasApplication, University, User
from app.services import application_filters, bdm_leads, lead_handover
from app.services.agent_applications import owned, stage_label, with_owner
from app.services.bdm_appointments import db_now, today_ist
from app.services.tabular import XLSX_TYPE, to_xlsx
from app.services.telecaller_reports import SOURCE_LABELS

logger = logging.getLogger("app.crm_exports")

router = APIRouter(prefix="/counselor/exports", tags=["crm-exports"])

Format = Literal["csv", "xlsx"]
EXPORT_ACTION = "crm.export"
ROW_CAP = 5000  # E7: the counselor's lists; the management reports are grouped and far smaller
COUNSELOR_REQUIRED = "Exports of your lists are for overseas counselors"
TOO_LARGE = "This list has more than {cap:,} rows; narrow the filters"

APPLICATION_COLUMNS = (
    ("application_code", "EduSphere ID"), ("student", "Student"), ("university", "University"), ("agency", "Agency"), ("intake", "Intake"),
    ("status", "Status"), ("sub_status", "Sub-status"), ("outcome", "Outcome"), ("next_action", "Next action"), ("updated", "Last updated"),
)  # fmt: skip
LEAD_COLUMNS = (
    ("lead_code", "Lead ID"), ("name", "Name"), ("subject", "Interest"), ("stage", "Stage"), ("priority", "Priority"), ("source", "Source"),
    ("telecaller", "Telecaller"), ("created", "Lead date"),
)  # fmt: skip


def render(table: dict, fmt: str, sheet_name: str) -> str | bytes:
    return to_csv(table) if fmt == "csv" else to_xlsx(table, sheet_name)


async def export(db: AsyncSession, user: User, *, entity_type: str, key: str, fmt: str, filters: dict[str, str], filename: str, sheet_name: str, build: Callable[[], Awaitable[dict]]) -> Response:
    """E5-E7. `filters` are the set filters and their values (ids, dates, intakes, stage keys -- no personal data)."""
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    wait = await _export_wait(db, user, EXPORT_ACTION)
    if wait:
        _log(logging.WARNING, "crm.export_throttled", user, entity_type, key, fmt, filters, 0, wait_seconds=wait)
        raise HTTPException(429, EXPORT_THROTTLED, headers={"Retry-After": str(wait)})
    table = await build()
    rows = len(table["items"])
    if rows > ROW_CAP:
        _log(logging.WARNING, "crm.export_too_large", user, entity_type, key, fmt, filters, rows)
        raise HTTPException(422, TOO_LARGE.format(cap=ROW_CAP))
    body = render(table, fmt, sheet_name)
    db.add(AuditLog(user_id=user.id, action=EXPORT_ACTION, entity_type=entity_type, entity_id=key, metadata_json={"format": fmt, "filters": filters, "rows": rows}))
    await db.commit()
    _log(logging.INFO, "crm.export", user, entity_type, key, fmt, filters, rows)
    media_type = "text/csv; charset=utf-8" if fmt == "csv" else XLSX_TYPE
    return Response(content=body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}.{fmt}"', **NO_STORE})


def _log(level: int, event: str, user: User, entity_type: str, key: str, fmt: str, filters: dict, rows: int, **extra) -> None:
    """Ids, the key, the format, which filters were set (never their values) and the row count."""
    logger.log(
        level, event, extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "entity_type": entity_type, "key": key, "format": fmt, "filters": sorted(filters), "rows": rows, **extra}}
    )


def _overseas_counselor(user: User) -> None:
    """E3: the overseas counselor only -- an IT counselor and every other role 403, before any input is read."""
    if user.role != "counselor" or user.division != "overseas":
        raise HTTPException(403, COUNSELOR_REQUIRED)


def _given(**values: str | None) -> dict[str, str]:
    return {key: value for key, value in values.items() if value is not None}


def _table(columns: tuple[tuple[str, str], ...], items: list[dict]) -> dict:
    return {"columns": [{"key": k, "label": label} for k, label in columns], "items": items, "totals": None}


@router.get("/applications")
async def export_applications(
    request: Request,
    format: Format = "csv",
    country: str | None = None,
    university: str | None = None,  # noqa: A002 -- the query name
    intake: str | None = None,
    stage: str | None = None,
    sub_status: str | None = None,
    created_from: str | None = Query(None, alias="from"),
    created_to: str | None = Query(None, alias="to"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The counselor's Students / Applications list (ccrm-012 QS6 filters, the same parser and 422s), newest change first."""
    _overseas_counselor(user)
    given = _given(country=country, university=university, intake=intake, stage=stage, sub_status=sub_status, **{"from": created_from, "to": created_to})
    repeated = frozenset(key for key in application_filters.FILTER_KEYS if len(request.query_params.getlist(key)) > 1)
    # `agency` and `counselor` are the Admin's filters (the parser refuses a counselor's), so they are never read here.
    filters = await application_filters.parse(db, user, "applications", request.query_params.get("agency"), request.query_params.get("counselor"), repeated,
                                              country=country, university=university, intake=intake, stage=stage, sub_status=sub_status,
                                              created_from=created_from, created_to=created_to)  # fmt: skip

    async def build() -> dict:
        stmt = with_owner(select(OverseasApplication, University).join(University, University.id == OverseasApplication.university_id))
        stmt = application_filters.apply(stmt.where(OverseasApplication.counselor_id == user.id), filters)
        rows = owned((await db.execute(stmt.order_by(OverseasApplication.updated_at.desc(), OverseasApplication.id).limit(ROW_CAP + 1))).all())
        agencies, _ = await application_filters.row_labels(db, [a for a, _, _ in rows])
        return _table(APPLICATION_COLUMNS, [
            {"application_code": a.application_code, "student": s.full_name, "university": u.name, "agency": agencies.get(a.agent_id), "intake": a.intake,
             "status": stage_label(a.status), "sub_status": sub_status_label(a.sub_status), "outcome": outcome_label(a.outcome),
             "next_action": a.next_action, "updated": today_ist(a.updated_at).isoformat()}
            for a, u, s in rows
        ])  # fmt: skip

    today = today_ist(await db_now(db))
    return await export(db, user, entity_type="counselor_list", key="applications", fmt=format, filters=given, filename=f"my-applications-{today}", sheet_name="My applications", build=build)


@router.get("/leads")
async def export_leads(
    format: Format = "csv",
    stage: str | None = None,
    priority: str | None = None,  # noqa: A002 -- the query name
    created_from: str | None = Query(None, alias="from"),
    created_to: str | None = Query(None, alias="to"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The counselor's own leads (ccrm-012 QS7 filters), newest first -- never phone, email or any other contact detail."""
    _overseas_counselor(user)
    where = [*lead_handover.counselor_scope(user), *lead_handover.list_filters(stage, priority, created_from, created_to)]

    async def build() -> dict:
        rows = (await db.execute(bdm_leads.admin_rows().where(*where).order_by(*bdm_leads.NEWEST).limit(ROW_CAP + 1))).all()
        leads = [bdm_leads.admin_out(row) for row in rows]
        return _table(LEAD_COLUMNS, [
            {"lead_code": x["lead_code"], "name": x["name"], "subject": x["subject"], "stage": STAGE_LABELS.get(x["status"], x["status"]),
             "priority": (x["priority"] or "").capitalize(), "source": SOURCE_LABELS.get(x["source"], x["source"]),
             "telecaller": (x["telecaller"] or {}).get("full_name"), "created": today_ist(x["created_at"]).isoformat()}
            for x in leads
        ])  # fmt: skip

    today = today_ist(await db_now(db))
    return await export(
        db,
        user,
        entity_type="counselor_list",
        key="leads",
        fmt=format,
        filters=_given(stage=stage, priority=priority, **{"from": created_from, "to": created_to}),
        filename=f"my-leads-{today}",
        sheet_name="My leads",
        build=build,
    )

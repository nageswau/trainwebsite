"""pob-029 (DEC-SCOPE-438, API §12ME): placement outcome reports and their CSV / xlsx export. Read-only and never cached; the export is
the on-screen group table, one audit row (filters and row count, no names) committed before the file is returned (fail closed)."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE, export_response
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, User
from app.services import placement_outcomes as svc

router = APIRouter(prefix="/reports/placement-outcomes", tags=["placement-outcomes"])
Group = Literal["company", "vendor", "role", "source", "recruiter", "po"]


async def _read(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    group_by: Group = "company",
    company: UUID | None = None,
    vendor: UUID | None = None,
    recruiter: UUID | None = None,
    po: UUID | None = None,
    source: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, dict]:
    filters = {"company": company, "vendor": vendor, "recruiter": recruiter, "po": po, "source": source}
    return user, await svc.report(db, user, date_from, date_to, group_by, filters)


@router.get("")
async def outcomes(response: Response, read: tuple[User, dict] = Depends(_read)):
    response.headers.update(NO_STORE)
    return read[1]


@router.get(".csv")
async def outcomes_csv(read: tuple[User, dict] = Depends(_read), db: AsyncSession = Depends(get_db)):
    return await _export(db, *read, "csv")


@router.get(".xlsx")
async def outcomes_xlsx(read: tuple[User, dict] = Depends(_read), db: AsyncSession = Depends(get_db)):
    return await _export(db, *read, "xlsx")


async def _export(db: AsyncSession, user: User, data: dict, fmt: str) -> Response:
    stem = f"placement-outcomes-by-{data['group_by']}-{data['date_from']}-to-{data['date_to']}"
    response = export_response(svc.export_payload(data), fmt, stem, "Placement outcomes")
    db.add(AuditLog(user_id=user.id, action="placement_outcomes.export", entity_type="placement_outcomes", entity_id="report", metadata_json={
        "date_from": data["date_from"].isoformat(), "date_to": data["date_to"].isoformat(), "group_by": data["group_by"],
        "filters": {key: str(value) for key, value in data["filters"].items()}, "rows": len(data["items"]), "format": fmt,
    }))  # fmt: skip
    await db.commit()
    return response

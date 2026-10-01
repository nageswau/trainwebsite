"""ENH-029 -- bulk school partner onboarding (docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md,
DEC-SCOPE-044).

Each accepted CSV row creates exactly what `POST /overseas-admin/schools` creates, through the same `admin._provision_school`.
One request = one transaction with a savepoint per row, on ENH-028's batch/row tables (`target_type = 'school_onboarding'`);
welcome links go out after the commit. Its own router so `admin.py` does not grow; imports from `admin`/`school_bulk` only.
"""

import asyncio
import csv
import hashlib
import io
import time

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import _provision_school, _valid_email
from app.api.deps import get_current_user
from app.api.school_bulk import LOCK_TIMEOUT, _claim, _read_csv, _read_upload
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, School, SchoolBulkUploadBatch, SchoolBulkUploadRow, User
from app.schemas import SchoolCreate, validation_message
from app.services.provisioning import IssuedWelcome, deliver_welcome_link

logger = get_logger(__name__)
router = APIRouter(prefix="/overseas-admin", tags=["school-onboarding-bulk"])

TARGET_TYPE = "school_onboarding"
ADMIN_ROLES = {"overseas_admin", "super_admin"}
COLUMNS = tuple(SchoolCreate.model_fields)  # D1: the template is exactly the single create's fields, in order
REQUIRED = ("name", "coordinator_full_name", "coordinator_email")
MAX_ROWS = 100
SEND_CONCURRENCY = 5  # D3: welcome emails in flight at once, after the commit
ROW_CONFLICT = "This row conflicts with a record created at the same time; upload it again"

Created = tuple[int, User, IssuedWelcome]  # (file line, coordinator, welcome token) of an accepted row


def _require_admin(user: User) -> None:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Overseas Admin role required")


async def _flush_row(db: AsyncSession) -> None:
    """A plain flush for the row's savepoint (never provisioning.flush_unique_email, whose rollback would discard the batch)."""
    await db.flush()


def _norm(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


class _Seen:
    """Rules 2-5 (spec §6): what the database already holds plus what earlier rows of this file claimed."""

    def __init__(self, emails: set[str], schools: set[tuple[str, str]]):
        self.emails, self.schools = emails, schools
        self.file_emails: dict[str, int] = {}
        self.file_schools: dict[tuple[str, str], int] = {}

    def error(self, line: int, payload: SchoolCreate) -> str | None:
        try:
            email = _valid_email(payload.coordinator_email)
        except HTTPException as exc:
            return exc.detail
        if email in self.file_emails:
            return f"same coordinator_email as row {self.file_emails[email]}"
        self.file_emails[email] = line
        if email in self.emails:
            return "Email already exists"
        school = (_norm(payload.name), _norm(payload.city))
        if school in self.schools:
            return "a school with this name and city already exists"
        if school in self.file_schools:
            return f"same school name and city as row {self.file_schools[school]}"
        self.file_schools[school] = line
        return None


async def _seen(db: AsyncSession, filled: list[tuple[int, dict[str, str]]]) -> _Seen:
    wanted = {cells.get("coordinator_email", "").strip().lower() for _, cells in filled} - {""}
    emails = set((await db.scalars(select(func.lower(User.email)).where(func.lower(User.email).in_(wanted)))).all()) if wanted else set()
    schools = {(_norm(name), _norm(city)) for name, city in (await db.execute(select(School.name, School.city))).all()}
    return _Seen(emails, schools)


async def _process(db: AsyncSession, user: User, batch: SchoolBulkUploadBatch, filled: list[tuple[int, dict[str, str]]]) -> tuple[list[SchoolBulkUploadRow], list[Created]]:
    seen = await _seen(db, filled)
    rows: list[SchoolBulkUploadRow] = []
    created: list[Created] = []
    for line, cells in filled:
        error, school, coordinator = None, None, None
        try:
            payload = SchoolCreate.model_validate({name: value for name, value in cells.items() if value})
        except ValidationError as exc:
            error = validation_message(exc)
        else:
            error = seen.error(line, payload)
            if error is None:
                try:
                    async with db.begin_nested():  # the row's own savepoint: a failure undoes this row only
                        school, coordinator, issued = await _provision_school(db, payload, user, flush_coordinator=_flush_row)
                    created.append((line, coordinator, issued))
                except HTTPException as exc:
                    error, school, coordinator = exc.detail, None, None
                except IntegrityError:
                    error, school, coordinator = ROW_CONFLICT, None, None
                    logger.warning("bulk_upload_row_conflict", extra={"extra_fields": {"batch_id": str(batch.id), "target_type": TARGET_TYPE, "row_number": line}})
        row = SchoolBulkUploadRow(
            batch_id=batch.id,
            row_number=line,
            status="rejected" if error else "accepted",
            error_message=error,
            created_record_id=school.id if school else None,
            created_user_id=coordinator.id if coordinator else None,
        )
        db.add(row)
        rows.append(row)
    return rows, created


async def _deliver(created: list[Created], actor: User) -> dict[int, dict]:
    """After the commit: each accepted row's welcome link, at most SEND_CONCURRENCY at once, keyed by file line. deliver_welcome_link
    never raises and audits in its own session, so a failed send leaves the school and account in place (pending_setup, re-sendable
    from the Users page)."""
    gate = asyncio.Semaphore(SEND_CONCURRENCY)

    async def one(coordinator: User, issued: IssuedWelcome) -> dict:
        async with gate:
            return await deliver_welcome_link(user=coordinator, issued=issued, issued_by=actor)

    results = await asyncio.gather(*(one(coordinator, issued) for _, coordinator, issued in created))
    return {line: result for (line, _, _), result in zip(created, results, strict=True)}


async def _report(db: AsyncSession, batch: SchoolBulkUploadBatch, rows: list[SchoolBulkUploadRow], deliveries: dict[int, dict] | None = None) -> dict:
    """One fixed row shape for the first response and every replay: names, codes and emails are read back by the stored ids."""
    school_ids = [r.created_record_id for r in rows if r.created_record_id]
    user_ids = [r.created_user_id for r in rows if r.created_user_id]
    schools = {sid: (code, name) for sid, code, name in (await db.execute(select(School.id, School.school_code, School.name).where(School.id.in_(school_ids)))).all()} if school_ids else {}
    emails = dict((await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))).all()) if user_ids else {}
    out = []
    for r in rows:
        code, name = schools.get(r.created_record_id, (None, None))
        delivery = (deliveries or {}).get(r.row_number, {})
        item = {
            "row_number": r.row_number,
            "status": r.status,
            "error_message": r.error_message,
            "created_record_id": r.created_record_id,
            "school_code": code,
            "school_name": name,
            "coordinator_id": r.created_user_id,
            "coordinator_email": emails.get(r.created_user_id),
            "email_status": delivery.get("email_status"),
        }
        if "development_welcome_token" in delivery:
            item["development_welcome_token"] = delivery["development_welcome_token"]
        out.append(item)
    return {
        "id": batch.id,
        "target_type": batch.target_type,
        "status": "completed",
        "total_rows": batch.total_rows,
        "accepted_count": batch.accepted_count,
        "rejected_count": batch.rejected_count,
        "rows": out,
    }


@router.get("/schools/bulk-template")
async def bulk_onboarding_template(user: User = Depends(get_current_user)):
    _require_admin(user)
    buffer = io.StringIO()
    csv.writer(buffer).writerow(COLUMNS)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=school-onboarding-bulk-template.csv", "Cache-Control": "private, no-store"},
    )


@router.post("/schools/bulk-upload", status_code=201)
async def bulk_onboard_schools(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    started = time.monotonic()
    _require_admin(user)
    raw = await _read_upload(file, idempotency_key, TARGET_TYPE, user)
    filled = _read_csv(raw, target_type=TARGET_TYPE, user=user, required=REQUIRED, columns=COLUMNS, max_rows=MAX_ROWS, known=COLUMNS)

    # `set_config(..., true)` is SET LOCAL with a bound parameter: it bounds the key wait (and, below, the onboarding lock).
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": LOCK_TIMEOUT})
    claimed = await _claim(db, TARGET_TYPE, user, idempotency_key, hashlib.sha256(raw).hexdigest())
    if isinstance(claimed, tuple):
        return await _report(db, *claimed)
    batch = claimed

    rows, created = await _process(db, user, batch, filled)
    batch.total_rows = len(rows)
    batch.accepted_count = len(created)
    batch.rejected_count = batch.total_rows - batch.accepted_count
    db.add(
        AuditLog(
            user_id=user.id,
            action="school.bulk_upload",
            entity_type="school_bulk_upload_batch",
            entity_id=str(batch.id),
            metadata_json={"target_type": TARGET_TYPE, "total": batch.total_rows, "accepted": batch.accepted_count, "rejected": batch.rejected_count, "file_sha256": batch.file_sha256},
        )
    )
    await db.commit()
    deliveries = await _deliver(created, user)
    report = await _report(db, batch, rows, deliveries)
    logger.info(
        "bulk_upload_completed",
        extra={
            "extra_fields": {
                "batch_id": str(batch.id),
                "target_type": TARGET_TYPE,
                "actor_id": str(user.id),
                "total": batch.total_rows,
                "accepted": batch.accepted_count,
                "rejected": batch.rejected_count,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
        },
    )
    return report

"""ENH-020 -- financial support / loan assistance cases (docs/superpowers/specs/2026-10-01-enh-020-funding-support-tracking-design.md).

A Career Counsellor tracks a school student's education loan, financial assistance, scholarship or funding guidance case through
School CRM.md §21's stages (DEC-SCOPE-043). Its own router, like ENH-030's, so `schools.py` does not grow; the scope, tier,
notification and name helpers are reused from there. Case contents (provider, amount, notes, closure reason) are sensitive: they are
never written to audit rows, logs or notifications.
"""

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import (
    FUNDING_SERVICE_KEYS,
    OUTSIDE_PORTFOLIO,
    _master_fields_or_422,
    _notify_student_parents,
    _portfolio_school_ids,
    _today_ist,
    _user_names,
    require_school_entitlement,
)
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, SchoolFundingRecord, SchoolStudent, User
from app.schemas import FUNDING_SUPPORT_TYPE_LABEL, FundingRecordCreate

router = APIRouter(prefix="/school", tags=["school-funding"])
logger = get_logger("app.school.funding")

COUNSELOR_REQUIRED = "Career Counselor role required"
CREATE_ACTION = "school.funding_record_create"
DENIED_ACTION = "school.funding_record_denied"
ENTITY = "school_funding_record"
OPEN_CASE_INDEX = "uq_funding_record_open_student_type"
RECORD_KEYS = ("id", "school_student_id", "support_type", "status", "status_changed_on", "provider_name", "amount_text", "notes", "closure_reason", "created_at", "updated_at")


async def _records_out(db: AsyncSession, rows) -> list[dict]:
    """The one response shape for every endpoint (spec §4): no `school_id`, no student master data."""
    names = await _user_names(db, [i for r in rows for i in (r.career_counselor_user_id, r.updated_by_user_id)])
    return [{**{key: getattr(r, key) for key in RECORD_KEYS}, "counselor_name": names.get(r.career_counselor_user_id), "updated_by_name": names.get(r.updated_by_user_id)} for r in rows]


async def _deny(db: AsyncSession, user: User, reason: str, entity_type: str, entity_id: UUID | None, message: str) -> NoReturn:
    """D13: a role or scope refusal is audited before the 403 (as ENH-030's). Nothing else may be pending in the session. The refusal
    stands even when its audit row cannot be written."""
    fields = {"actor_id": str(user.id), "role": user.role, "reason": reason, "entity_type": entity_type, "entity_id": str(entity_id) if entity_id else None}
    db.add(AuditLog(user_id=user.id, action=DENIED_ACTION, entity_type=entity_type, entity_id=str(entity_id) if entity_id else None, outcome="denied", metadata_json={"role": user.role, "reason": reason}))
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("funding_record_denied_audit_failed", extra={"extra_fields": fields})
    logger.warning("funding_record_denied", extra={"extra_fields": fields})
    raise HTTPException(403, message)


async def _locked_student(db: AsyncSession, student_id: UUID) -> SchoolStudent | None:
    """The row transfer approval locks, so the student's school cannot change under us until this transaction ends."""
    return await db.scalar(select(SchoolStudent).where(SchoolStudent.id == student_id).with_for_update().execution_options(populate_existing=True))


async def _notify_parents(db: AsyncSession, student: SchoolStudent, *, title: str, body: str, ids: dict) -> None:
    """After the case's own commit: a failure here is logged and rolled back, never undoes the saved case (spec §4.1 step 8)."""
    try:
        await _notify_student_parents(db, student, title=title, body=body, action_url=f"/school/parent/children/{student.id}")
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("funding_record_notify_failed", extra={"extra_fields": ids})


@router.post("/funding-records", status_code=201)
async def create_funding_record(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Spec §4.1: one transaction up to the commit (student row locked, tier gate before any write); parents notified after it."""
    if user.role != "career_counselor":
        await _deny(db, user, "role", ENTITY, None, COUNSELOR_REQUIRED)
    fields = _master_fields_or_422(FundingRecordCreate, payload)
    student = await _locked_student(db, fields.school_student_id)
    if student is None:
        raise HTTPException(404, "Student not found")
    if student.school_id not in await _portfolio_school_ids(db, user):
        await _deny(db, user, "outside_portfolio", "school_student", student.id, OUTSIDE_PORTFOLIO)
    await require_school_entitlement(db, user, student.school_id, FUNDING_SERVICE_KEYS[fields.support_type])
    name, type_label = student.full_name, FUNDING_SUPPORT_TYPE_LABEL[fields.support_type]
    record = SchoolFundingRecord(
        school_student_id=student.id, school_id=student.school_id, support_type=fields.support_type, status="required", status_changed_on=_today_ist(),
        provider_name=fields.provider_name, amount_text=fields.amount_text, notes=fields.notes, career_counselor_user_id=user.id,
    )
    db.add(record)
    ids = {"actor_id": str(user.id), "student_id": str(student.id), "support_type": fields.support_type}
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if OPEN_CASE_INDEX not in str(exc.orig):
            raise
        logger.info("funding_record_duplicate_open", extra={"extra_fields": ids})
        raise HTTPException(409, f"{name} already has an open {type_label.lower()} case. Open it from the list to update it.") from None
    sent = sorted(fields.model_fields_set - {"school_student_id", "support_type"})
    db.add(AuditLog(user_id=user.id, action=CREATE_ACTION, entity_type=ENTITY, entity_id=str(record.id), metadata_json={"support_type": fields.support_type, "fields": sent}))
    await db.commit()
    await db.refresh(record)
    out = (await _records_out(db, [record]))[0]
    ids["record_id"] = str(record.id)
    logger.info("funding_record_create", extra={"extra_fields": ids})
    await _notify_parents(db, student, title=f"Funding support update for {name}", body=f"{type_label} support is now being tracked (Required).", ids=ids)
    return out

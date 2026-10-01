"""ENH-020 -- financial support / loan assistance cases (docs/superpowers/specs/2026-10-01-enh-020-funding-support-tracking-design.md).

A Career Counsellor tracks a school student's education loan, financial assistance, scholarship or funding guidance case through
School CRM.md §21's stages (DEC-SCOPE-045). Its own router, like ENH-030's, so `schools.py` does not grow; the scope, tier,
notification and name helpers are reused from there. Case contents (provider, amount, notes, closure reason) are sensitive: they are
never written to audit rows, logs or notifications.
"""

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import (
    FUNDING_SERVICE_KEYS,
    OUTSIDE_PORTFOLIO,
    _load_student_for_reader,
    _notify_student_parents,
    _portfolio_school_ids,
    _today_ist,
    _user_names,
    require_school_entitlement,
)
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, SchoolFundingRecord, SchoolStudent, User
from app.schemas import FUNDING_FINAL_STATUSES, FUNDING_STATUS_LABEL, FUNDING_SUPPORT_TYPE_LABEL, FundingRecordCreate, FundingRecordUpdate, funding_transition_allowed, validation_message

router = APIRouter(prefix="/school", tags=["school-funding"])
logger = get_logger("app.school.funding")

COUNSELOR_REQUIRED = "Career Counselor role required"
TEACHERS_DENIED = "Funding support cases are not visible to teachers."
READERS_REQUIRED = "School Coordinator, Principal, Parent or Career Counselor role required"
READER_ROLES = frozenset({"career_counselor", "school_coordinator", "school_principal", "school_parent"})  # D5; teachers excluded
PREVIOUS_SCHOOL = "This case belongs to the student's previous school and can no longer be changed."
CLOSURE_REASON_REQUIRED = "Give a reason for closing this case."
CLOSURE_REASON_ONLY_WHEN_CLOSING = "A closure reason can only be given when closing the case."
CREATE_ACTION = "school.funding_record_create"
UPDATE_ACTION = "school.funding_record_update"
DENIED_ACTION = "school.funding_record_denied"
ENTITY = "school_funding_record"
OPEN_CASE_INDEX = "uq_funding_record_open_student_type"
RECORD_KEYS = ("id", "school_student_id", "support_type", "status", "status_changed_on", "provider_name", "amount_text", "notes", "closure_reason", "created_at", "updated_at")
TRACKED_FIELDS = ("status", "provider_name", "amount_text", "notes", "closure_reason")  # what a PATCH may change, in audit order
# QA-01: a 422 is shown to the counsellor as-is, so it names the form's label, not the API field (ENH-026 QA-03's rule).
FIELD_LABELS = {
    "school_student_id": "Student", "support_type": "Support type", "status": "Stage", "expected_status": "Expected stage",
    "provider_name": "Provider or institution", "amount_text": "Amount", "notes": "Notes", "closure_reason": "Reason for closing",
}
OPEN_FIRST = (case((SchoolFundingRecord.status.in_(FUNDING_FINAL_STATUSES), 1), else_=0), SchoolFundingRecord.updated_at.desc())  # list order


def _fields_or_422[M: BaseModel](model: type[M], payload: dict) -> M:
    """The house string-422 (`validation_message`) with the field named by its form label. An unknown key keeps naming itself: only
    an API caller sends one, and that message is the API contract."""
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        message, error = validation_message(exc), exc.errors()[0]
        field = str(error["loc"][0]) if error["loc"] else ""
        if error["type"] != "extra_forbidden" and field in FIELD_LABELS:
            message = FIELD_LABELS[field] + message[len(field):]
        raise HTTPException(422, message) from None


async def _records_out(db: AsyncSession, rows) -> list[dict]:
    """The one response shape for every endpoint (spec §4): no `school_id`, no student master data."""
    names = await _user_names(db, [i for r in rows for i in (r.career_counselor_user_id, r.updated_by_user_id)])
    return [{**{key: getattr(r, key) for key in RECORD_KEYS}, "counselor_name": names.get(r.career_counselor_user_id), "updated_by_name": names.get(r.updated_by_user_id)} for r in rows]


async def _deny(db: AsyncSession, user: User, reason: str, entity_type: str, entity_id: UUID | None, message: str) -> NoReturn:
    """D13: a role or scope refusal is audited before the 403 (as ENH-030's). Nothing else may be pending in the session. The refusal
    stands even when its audit row cannot be written."""
    target = str(entity_id) if entity_id else None
    fields = {"actor_id": str(user.id), "role": user.role, "reason": reason, "entity_type": entity_type, "entity_id": target}
    db.add(AuditLog(user_id=user.id, action=DENIED_ACTION, entity_type=entity_type, entity_id=target, outcome="denied", metadata_json={"role": user.role, "reason": reason}))
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


@router.get("/career-counselor/funding-records")
async def list_counselor_funding_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """E3: every case opened at a school in the counsellor's portfolio whose student is still there (D12), open cases first. Not
    paginated -- bounded by the portfolio, like `GET /school/career-counselor/records` (spec §4). Not tier-gated: history stays readable."""
    if user.role != "career_counselor":
        await _deny(db, user, "role", ENTITY, None, COUNSELOR_REQUIRED)
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    rows = (
        await db.scalars(
            select(SchoolFundingRecord)
            .join(SchoolStudent, SchoolStudent.id == SchoolFundingRecord.school_student_id)
            .where(SchoolFundingRecord.school_id.in_(portfolio), SchoolStudent.school_id == SchoolFundingRecord.school_id)
            .order_by(*OPEN_FIRST)
        )
    ).all()
    return await _records_out(db, rows)


@router.get("/students/{student_id}/funding-records")
async def list_student_funding_records(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """E4: one student's cases, read-only. Teachers are refused before the shared loader (which would admit an assigned teacher).
    Staff see only cases opened at the student's current school (D12); a linked parent sees all of their child's cases."""
    if user.role == "school_teacher":
        await _deny(db, user, "teacher", "school_student", student_id, TEACHERS_DENIED)
    if user.role not in READER_ROLES:
        await _deny(db, user, "role", "school_student", student_id, READERS_REQUIRED)
    try:
        student = await _load_student_for_reader(db, user, student_id)
    except HTTPException as exc:
        if exc.status_code == 403:
            await _deny(db, user, "scope", "school_student", student_id, str(exc.detail))
        raise
    stmt = select(SchoolFundingRecord).where(SchoolFundingRecord.school_student_id == student.id)
    if user.role != "school_parent":
        stmt = stmt.where(SchoolFundingRecord.school_id == student.school_id)
    return await _records_out(db, (await db.scalars(stmt.order_by(*OPEN_FIRST))).all())


@router.post("/funding-records", status_code=201)
async def create_funding_record(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Spec §4.1: one transaction up to the commit (student row locked, tier gate before any write); parents notified after it."""
    if user.role != "career_counselor":
        await _deny(db, user, "role", ENTITY, None, COUNSELOR_REQUIRED)
    fields = _fields_or_422(FundingRecordCreate, payload)
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


def _rule_error(record: SchoolFundingRecord, sent: set[str]) -> str | None:
    """Spec §4.2 step 8 on the case as it would be saved: a closed case needs its reason, and only a closing PATCH may send one."""
    if record.status == "closed" and not record.closure_reason:
        return CLOSURE_REASON_REQUIRED
    if "closure_reason" in sent and record.status != "closed":
        return CLOSURE_REASON_ONLY_WHEN_CLOSING
    return None


@router.patch("/funding-records/{record_id}")
async def update_funding_record(record_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Spec §4.2 (the ENH-026 update shape). One transaction up to the commit: lock the case, then its student (the lock transfer
    approval takes; same order as ENH-026, so the two never deadlock), re-check scope under it, tier gate, precondition, transition,
    rules, audit. Parents are notified only after the commit, so no row lock is held across delivery."""
    if user.role != "career_counselor":
        await _deny(db, user, "role", ENTITY, record_id, COUNSELOR_REQUIRED)
    record = await db.scalar(select(SchoolFundingRecord).where(SchoolFundingRecord.id == record_id).with_for_update().execution_options(populate_existing=True))
    if record is None:
        raise HTTPException(404, "Funding support case not found")
    student = await _locked_student(db, record.school_student_id)
    if student is None or student.school_id not in await _portfolio_school_ids(db, user):
        await _deny(db, user, "outside_portfolio", ENTITY, record.id, OUTSIDE_PORTFOLIO)
    if record.school_id != student.school_id:  # D12: the student has moved; the previous school's case is history now
        await _deny(db, user, "previous_school", ENTITY, record.id, PREVIOUS_SCHOOL)
    await require_school_entitlement(db, user, student.school_id, FUNDING_SERVICE_KEYS[record.support_type], grandfathered_since=record.created_at)
    fields = _fields_or_422(FundingRecordUpdate, payload)
    sent = set(fields.model_fields_set)
    if "expected_status" in sent and fields.expected_status != record.status:
        raise HTTPException(409, f"This case was changed by someone else (now {FUNDING_STATUS_LABEL[record.status]}). Reload to see the latest.")
    sent.discard("expected_status")
    if record.status in FUNDING_FINAL_STATUSES:
        raise HTTPException(422, f"This case is {FUNDING_STATUS_LABEL[record.status]} and can no longer be changed.")
    if "status" in sent and (fields.status is None or not funding_transition_allowed(record.status, fields.status)):
        requested = FUNDING_STATUS_LABEL.get(fields.status or "", "no status")
        raise HTTPException(422, f"Cannot change status from {FUNDING_STATUS_LABEL[record.status]} to {requested}")

    before = {key: getattr(record, key) for key in TRACKED_FIELDS}
    for key in sent:
        setattr(record, key, getattr(fields, key))
    error = _rule_error(record, sent)
    if error:
        raise HTTPException(422, error)
    changed = [key for key in TRACKED_FIELDS if getattr(record, key) != before[key]]
    if not changed:
        return (await _records_out(db, [record]))[0]  # a repeat PATCH writes nothing (safe to retry)
    old_status, new_status = before["status"], record.status
    status_changed = new_status != old_status
    if status_changed:
        record.status_changed_on = _today_ist()
    record.updated_by_user_id = user.id
    metadata: dict = {"changed_fields": changed}  # field names only, never contents (AC19)
    if status_changed:
        metadata["status"] = {"old": old_status, "new": new_status}
    db.add(AuditLog(user_id=user.id, action=UPDATE_ACTION, entity_type=ENTITY, entity_id=str(record.id), metadata_json=metadata))
    await db.commit()
    await db.refresh(record)
    # Everything the response and logs need is read now: a notification failure below rolls back and expires these objects.
    out = (await _records_out(db, [record]))[0]
    ids = {"actor_id": str(user.id), "record_id": str(record.id), "student_id": str(student.id)}
    logger.info("funding_record_update", extra={"extra_fields": {**ids, "status": new_status, "changed": len(changed)}})
    if status_changed:
        title = f"Funding support update for {student.full_name}"
        body = f"{FUNDING_SUPPORT_TYPE_LABEL[record.support_type]} support is now at {FUNDING_STATUS_LABEL[new_status]}."
        await _notify_parents(db, student, title=title, body=body, ids=ids)
    return out

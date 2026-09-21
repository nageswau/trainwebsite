"""ENH-005 -- student school transfer: a coordinator requests, an admin approves
(docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md).

Two routers live here so `schools.py` (coordinator, `/school`) and `admin.py` (`/overseas-admin`) do not grow. Filing is
in this section; the request list/cancel/history and the admin approve/reject follow. Every route depends on
`get_current_user`; the caller's school always comes from their server-owned profile, never from a request body."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schools import _own_school_id, _require_coordinator_user
from app.core.database import get_db
from app.core.logging import get_logger, request_id_ctx
from app.models import AuditLog, School, SchoolStudent, SchoolStudentTransferRequest, User
from app.schemas import AcceptedOut, IncomingTransferCreate, TransferRequestCreate, TransferRequestOut

coordinator_router = APIRouter(prefix="/school", tags=["school-transfers"])
admin_router = APIRouter(prefix="/overseas-admin", tags=["school-transfers"])
logger = get_logger("app.school.transfers")

# Module constants, read at call time so a test can shorten them; none is ever request input.
MAX_OPEN_TRANSFER_REQUESTS_PER_SCHOOL = 50  # D7
TRANSFER_FILINGS_PER_HOUR = 30  # D8, per coordinator

# The `detail` strings are a contract (spec §5.3a): a client may match on them.
NOT_AT_INSTITUTION = "This student is not at your institution"
ALREADY_PENDING = "A transfer request is already pending for this student"
TOO_MANY_OPEN = "Too many open transfer requests; wait for a decision or cancel one"

ACTION_FILED = "school.transfer_request_filed"
ACTION_DENIED = "school.transfer_request_denied"
FILING_ACTIONS = (ACTION_FILED, ACTION_DENIED)


def _audit(db: AsyncSession, actor_id: UUID, action: str, entity_id, *, outcome: str = "recorded", **metadata) -> None:
    """One `AuditLog` row, added to the caller's transaction (so a failed audit write aborts the change). Metadata is IDs and
    reason tokens only -- never a student code, a reason, a note or a name (security review S8) -- plus the request ID so the
    row correlates with its log lines."""
    db.add(
        AuditLog(
            user_id=actor_id, action=action, entity_type="school_student_transfer_request", entity_id=str(entity_id) if entity_id else None,
            outcome=outcome, metadata_json={**metadata, "request_id": request_id_ctx.get()},
        )
    )


async def _filing_guard(db: AsyncSession, actor_id: UUID, school_id: UUID) -> None:
    """The hourly throttle (D8) and the open-request cap (D7), both checked BEFORE any student lookup so neither answer can
    depend on which student a code names. The throttle counts the audit rows every filing attempt already writes, so it holds
    across several server instances (an in-process limiter would not)."""
    now = datetime.now(UTC)
    window = (AuditLog.user_id == actor_id, AuditLog.action.in_(FILING_ACTIONS), AuditLog.created_at > now - timedelta(hours=1))
    if await db.scalar(select(func.count()).select_from(AuditLog).where(*window)) >= TRANSFER_FILINGS_PER_HOUR:
        oldest = await db.scalar(select(func.min(AuditLog.created_at)).where(*window))
        wait = max(1, int((oldest + timedelta(hours=1) - now).total_seconds()))
        logger.warning("transfer_filing_throttled", extra={"extra_fields": {"actor_id": str(actor_id), "school_id": str(school_id), "wait_seconds": wait}})
        raise HTTPException(429, f"Too many transfer requests; try again in {wait} seconds", headers={"Retry-After": str(wait)})
    open_count = await db.scalar(
        select(func.count()).select_from(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.filed_by_school_id == school_id, SchoolStudentTransferRequest.status == "pending")
    )
    if open_count >= MAX_OPEN_TRANSFER_REQUESTS_PER_SCHOOL:
        logger.warning("transfer_open_cap_reached", extra={"extra_fields": {"actor_id": str(actor_id), "school_id": str(school_id), "open": open_count}})
        raise HTTPException(409, TOO_MANY_OPEN)


def _request_out(row: SchoolStudentTransferRequest, student: SchoolStudent, from_school: School, to_school: School) -> TransferRequestOut:
    return TransferRequestOut(
        id=row.id, direction="outgoing" if row.filed_by_school_id == row.from_school_id else "incoming", status=row.status, student_id=student.id,
        student_code=student.student_code, student_name=student.full_name, from_school={"id": from_school.id, "name": from_school.name},
        to_school={"id": to_school.id, "name": to_school.name}, reason=row.reason, decision_note=row.decision_note, created_at=row.created_at, decided_at=row.decided_at,
    )


@coordinator_router.post("/students/{student_id}/transfer-requests", status_code=201, response_model=TransferRequestOut)
async def file_outgoing_request(student_id: UUID, payload: TransferRequestCreate, user: User = Depends(_require_coordinator_user), db: AsyncSession = Depends(get_db)):
    """Ask for one of this school's students to move to another school. An unknown student ID and another school's student give
    the same 403 (ENH-004's "same absence" rule), and the refusal is audited. Business-rule 422s (same or unknown destination)
    are user mistakes, not attempts: nothing is written for them."""
    actor_id, school_id = user.id, _own_school_id(user)
    await _filing_guard(db, actor_id, school_id)
    student = await db.get(SchoolStudent, student_id)
    if student is None or student.school_id != school_id:
        _audit(db, actor_id, ACTION_DENIED, None, outcome="denied", reason_token="not_at_institution", school_id=str(school_id))
        await db.commit()
        raise HTTPException(403, NOT_AT_INSTITUTION)
    if payload.to_school_id == school_id:
        raise HTTPException(422, "Choose a different school")
    to_school = await db.get(School, payload.to_school_id)
    if to_school is None:
        raise HTTPException(422, "Unknown destination school")
    from_school = await db.get(School, school_id)
    row = SchoolStudentTransferRequest(
        school_student_id=student.id, from_school_id=school_id, to_school_id=to_school.id, requested_by_user_id=actor_id, filed_by_school_id=school_id,
        status="pending", reason=payload.reason,
    )
    db.add(row)
    try:
        await db.flush()  # the partial unique index is the atomic claim: two simultaneous filings cannot both win
    except IntegrityError as exc:
        await db.rollback()
        _audit(db, actor_id, ACTION_DENIED, None, outcome="denied", reason_token="duplicate", school_id=str(school_id))
        await db.commit()
        raise HTTPException(409, ALREADY_PENDING) from exc
    _audit(db, actor_id, ACTION_FILED, row.id, school_id=str(school_id), from_school_id=str(school_id), to_school_id=str(to_school.id), direction="outgoing")
    await db.commit()
    logger.info("transfer_request_filed", extra={"extra_fields": {"actor_id": str(actor_id), "request_id_row": str(row.id), "direction": "outgoing", "school_id": str(school_id)}})
    return _request_out(row, student, from_school, to_school)


@coordinator_router.post("/transfer-requests/incoming", status_code=202, response_model=AcceptedOut)
async def file_incoming_request(payload: IncomingTransferCreate, user: User = Depends(_require_coordinator_user), db: AsyncSession = Depends(get_db)):
    """Ask for a student who is at ANOTHER school, by Student ID. Every well-formed code gets the identical `202 {"accepted": true}`
    (the same shape as `POST /auth/forgot-password`), so the response is not an existence oracle. A row is created only for a
    real student at a different school with no pending request; every attempt is audited with a reason token, never the code."""
    actor_id, school_id = user.id, _own_school_id(user)
    await _filing_guard(db, actor_id, school_id)
    student = await db.scalar(select(SchoolStudent).where(SchoolStudent.student_code == payload.student_code))
    token = None
    row = None
    if student is None:
        token = "unknown_code"
    elif student.school_id == school_id:
        token = "own_school"
    else:
        row = SchoolStudentTransferRequest(
            school_student_id=student.id, from_school_id=student.school_id, to_school_id=school_id, requested_by_user_id=actor_id, filed_by_school_id=school_id,
            status="pending", reason=payload.reason,
        )
        db.add(row)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            row, token = None, "duplicate"
    if row is not None:
        _audit(db, actor_id, ACTION_FILED, row.id, school_id=str(school_id), from_school_id=str(row.from_school_id), to_school_id=str(school_id), direction="incoming")
    else:
        _audit(db, actor_id, ACTION_DENIED, None, outcome="denied", reason_token=token, school_id=str(school_id))
    await db.commit()
    logger.info("transfer_incoming_attempt", extra={"extra_fields": {"actor_id": str(actor_id), "school_id": str(school_id), "created": row is not None}})
    return {"accepted": True}

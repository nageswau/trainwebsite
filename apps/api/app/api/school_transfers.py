"""ENH-005 -- student school transfer: a coordinator requests, an admin approves
(docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md).

Two routers live here so `schools.py` (coordinator, `/school`) and `admin.py` (`/overseas-admin`) do not grow. Filing is
in this section; the request list/cancel/history and the admin approve/reject follow. Every route depends on
`get_current_user`; the caller's school always comes from their server-owned profile, never from a request body."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_current_user
from app.api.schools import _load_readable_student, _own_school_id, _require_coordinator_user
from app.core.database import get_db
from app.core.logging import get_logger, request_id_ctx
from app.models import AuditLog, School, SchoolStudent, SchoolStudentTransferRequest, User
from app.schemas import (
    AcceptedOut,
    IncomingTransferCreate,
    SchoolRef,
    TransferHistoryResponse,
    TransferRequestCreate,
    TransferRequestOut,
    TransferRequestPage,
    TransferStatusFilter,
)

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
NOT_PERMITTED = "Not permitted for this transfer request"
ALREADY_DECIDED = "This transfer request has already been decided"

ACTION_FILED = "school.transfer_request_filed"
ACTION_DENIED = "school.transfer_request_denied"
ACTION_CANCELLED = "school.transfer_request_cancelled"
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
    """The coordinator's view of a request. A request the GAINING school filed is redacted until it is approved: the student's ID,
    name and current school stay null, so the gaining coordinator knows only the Student ID they typed (spec §5.2). One schema
    either way -- nothing appears or disappears by condition."""
    direction = "outgoing" if row.filed_by_school_id == row.from_school_id else "incoming"
    redacted = direction == "incoming" and row.status != "approved"
    return TransferRequestOut(
        id=row.id, direction=direction, status=row.status, student_id=None if redacted else student.id, student_code=student.student_code,
        student_name=None if redacted else student.full_name, from_school=None if redacted else {"id": from_school.id, "name": from_school.name},
        to_school={"id": to_school.id, "name": to_school.name}, reason=row.reason, decision_note=row.decision_note, created_at=row.created_at, decided_at=row.decided_at,
    )


@coordinator_router.get("/transfer-destinations", response_model=list[SchoolRef])
async def transfer_destinations(user: User = Depends(_require_coordinator_user), db: AsyncSession = Depends(get_db)):
    """Every other school, as id and name only -- the source of the destination picker."""
    school_id = _own_school_id(user)
    schools = (await db.scalars(select(School).where(School.id != school_id).order_by(School.name))).all()
    return [{"id": s.id, "name": s.name} for s in schools]


@coordinator_router.get("/transfer-requests", response_model=TransferRequestPage)
async def list_my_transfer_requests(
    status: TransferStatusFilter = "pending", limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
    user: User = Depends(_require_coordinator_user), db: AsyncSession = Depends(get_db),
):
    """The requests THIS school filed (either direction), newest first. Scoped in the query, not filtered afterwards; the other
    school in a request is not told of it until an admin decides (decision D5)."""
    school_id = _own_school_id(user)
    conditions = [SchoolStudentTransferRequest.filed_by_school_id == school_id]
    if status != "all":
        conditions.append(SchoolStudentTransferRequest.status == status)
    total = await db.scalar(select(func.count()).select_from(SchoolStudentTransferRequest).where(*conditions))
    from_school, to_school = aliased(School), aliased(School)
    rows = (
        await db.execute(
            select(SchoolStudentTransferRequest, SchoolStudent, from_school, to_school)
            .join(SchoolStudent, SchoolStudent.id == SchoolStudentTransferRequest.school_student_id)
            .join(from_school, from_school.id == SchoolStudentTransferRequest.from_school_id)
            .join(to_school, to_school.id == SchoolStudentTransferRequest.to_school_id)
            .where(*conditions)
            .order_by(SchoolStudentTransferRequest.created_at.desc(), SchoolStudentTransferRequest.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {"items": [_request_out(r, s, f, t) for r, s, f, t in rows], "total": total, "limit": limit, "offset": offset}


@coordinator_router.post("/transfer-requests/{request_id}/cancel", response_model=TransferRequestOut)
async def cancel_transfer_request(request_id: UUID, user: User = Depends(_require_coordinator_user), db: AsyncSession = Depends(get_db)):
    """Withdraw a pending request THIS school filed. The school filter is part of the locking query, so another school's request
    is never locked or read, and an unknown ID and another school's ID are the same absence (one identical 403, audited). The row
    lock also serialises this with a concurrent admin decision: whichever commits second sees a decided request and gets 409."""
    actor_id, school_id = user.id, _own_school_id(user)
    row = await db.scalar(
        select(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.id == request_id, SchoolStudentTransferRequest.filed_by_school_id == school_id).with_for_update()
    )
    if row is None:
        _audit(db, actor_id, ACTION_DENIED, None, outcome="denied", reason_token="cancel_not_permitted", school_id=str(school_id))
        await db.commit()
        raise HTTPException(403, NOT_PERMITTED)
    if row.status != "pending":
        raise HTTPException(409, ALREADY_DECIDED)
    row.status, row.decided_by_user_id, row.decided_at = "cancelled", actor_id, datetime.now(UTC)
    _audit(db, actor_id, ACTION_CANCELLED, row.id, school_id=str(school_id))
    await db.commit()
    logger.info("transfer_request_cancelled", extra={"extra_fields": {"actor_id": str(actor_id), "request_id_row": str(row.id), "school_id": str(school_id)}})
    student = await db.get(SchoolStudent, row.school_student_id)
    return _request_out(row, student, await db.get(School, row.from_school_id), await db.get(School, row.to_school_id))


@coordinator_router.get("/students/{student_id}/transfer-history", response_model=TransferHistoryResponse)
async def student_transfer_history(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A student's APPROVED transfers, newest first, through the same own-scope loader as the overview and timeline (own institution;
    assigned-only Teacher; linked-only Parent). No reason and no staff IDs: a coordinator's free text is for the admin, and a Parent
    must never receive a staff user ID. Bounded by the transfers one student can have, so it is not paginated."""
    student = await _load_readable_student(db, user, student_id)
    from_school, to_school = aliased(School), aliased(School)
    rows = (
        await db.execute(
            select(SchoolStudentTransferRequest, from_school, to_school)
            .join(from_school, from_school.id == SchoolStudentTransferRequest.from_school_id)
            .join(to_school, to_school.id == SchoolStudentTransferRequest.to_school_id)
            .where(SchoolStudentTransferRequest.school_student_id == student.id, SchoolStudentTransferRequest.status == "approved")
            .order_by(SchoolStudentTransferRequest.decided_at.desc(), SchoolStudentTransferRequest.id.desc())
        )
    ).all()
    return {
        "student": {"id": student.id, "full_name": student.full_name},
        "history": [{"id": r.id, "decided_at": r.decided_at, "from_school": {"id": f.id, "name": f.name}, "to_school": {"id": t.id, "name": t.name}} for r, f, t in rows],
    }


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

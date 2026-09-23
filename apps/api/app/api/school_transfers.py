"""ENH-005 -- student school transfer: a coordinator requests, an admin approves
(docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md).

Two routers live here so `schools.py` (coordinator, `/school`) and `admin.py` (`/overseas-admin`) do not grow. Filing is
in this section; the request list/cancel/history and the admin approve/reject follow. Every route depends on
`get_current_user`; the caller's school always comes from their server-owned profile, never from a request body."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_current_user
from app.api.schools import _load_readable_student, _notify_student_parents, _own_school_id, _require_coordinator_user
from app.core.database import get_db
from app.core.logging import get_logger, request_id_ctx
from app.models import (
    AuditLog,
    Notification,
    School,
    SchoolAcademicResult,
    SchoolParentLink,
    SchoolResultStatusHistory,
    SchoolStaffAssignment,
    SchoolStudent,
    SchoolStudentTransferRequest,
    User,
)
from app.schemas import (
    AcceptedOut,
    AdminTransferHistoryResponse,
    AdminTransferPage,
    AdminTransferPreview,
    AdminTransferRequestOut,
    IncomingTransferCreate,
    SchoolRef,
    TransferDirection,
    TransferHistoryResponse,
    TransferRejectRequest,
    TransferRequestCreate,
    TransferRequestOut,
    TransferRequestPage,
    TransferStatus,
    TransferStatusFilter,
    UserRef,
)

coordinator_router = APIRouter(prefix="/school", tags=["school-transfers"])
admin_router = APIRouter(prefix="/overseas-admin", tags=["school-transfers"])
logger = get_logger("app.school.transfers")

# Module constants, read at call time so a test can shorten them; none is ever request input.
MAX_OPEN_TRANSFER_REQUESTS_PER_SCHOOL = 50  # D7
TRANSFER_FILINGS_PER_HOUR = 30  # D8, per coordinator
TRANSFER_LOCK_TIMEOUT = "5s"  # bounded wait for the row locks an approval takes (spec §5.4); passed as a bound parameter, never request input

# The `detail` strings are a contract (spec §5.3a): a client may match on them.
NOT_AT_INSTITUTION = "This student is not at your institution"
ALREADY_PENDING = "A transfer request is already pending for this student"
TOO_MANY_OPEN = "Too many open transfer requests; wait for a decision or cancel one"
NOT_PERMITTED = "Not permitted for this transfer request"
ALREADY_DECIDED = "This transfer request has already been decided"
STALE_REQUEST = "The student is no longer at the school this request was filed for; reject it and file a new one"
LOCK_BUSY = "Another change to this student is in progress; retry"

ACTION_FILED = "school.transfer_request_filed"
ACTION_DENIED = "school.transfer_request_denied"
ACTION_CANCELLED = "school.transfer_request_cancelled"
ACTION_REJECTED = "school.transfer_request_rejected"
ACTION_TRANSFER = "school.student_transfer"
FILING_ACTIONS = (ACTION_FILED, ACTION_DENIED)


def _audit(db: AsyncSession, actor_id: UUID, action: str, entity_id, *, outcome: str = "recorded", **metadata) -> None:
    """One `AuditLog` row, added to the caller's transaction (so a failed audit write aborts the change). Metadata is IDs and
    reason tokens only -- never a student code, a reason, a note or a name (security review S8) -- plus the request ID so the
    row correlates with its log lines."""
    db.add(
        AuditLog(
            user_id=actor_id,
            action=action,
            entity_type="school_student_transfer_request",
            entity_id=str(entity_id) if entity_id else None,
            outcome=outcome,
            metadata_json={**metadata, "request_id": request_id_ctx.get()},
        )
    )


async def _get_or_404[Row](db: AsyncSession, model: type[Row], pk: UUID, what: str) -> Row:
    """`db.get` for a row a foreign key guarantees exists (a request's student and schools, the caller's own school). It only narrows the type:
    schools and students are never deleted, so the 404 is a defensive answer where the alternative would be an AttributeError."""
    row = await db.get(model, pk)
    if row is None:
        raise HTTPException(404, f"{what} not found")
    return row


async def _filing_guard(db: AsyncSession, actor_id: UUID, school_id: UUID) -> None:
    """The hourly throttle (D8) and the open-request cap (D7), both checked BEFORE any student lookup so neither answer can
    depend on which student a code names. The throttle counts the audit rows every filing attempt already writes, so it holds
    across several server instances (an in-process limiter would not).

    Both limits are "count, then insert", so at READ COMMITTED simultaneous filings would all count before any committed and all pass
    (Codex review). The first statement therefore takes the school's row lock (`FOR NO KEY UPDATE`: it excludes another filing, but not a
    foreign-key insert that merely references the school), which queues every filing of a school -- and so of each of its coordinators --
    behind the one before it. The lock is released by the caller's commit, after the row and its audit row are visible to the next count.
    No other code locks a school row, so this cannot join a lock cycle with an approval's request -> student -> parent -> result order."""
    await db.scalar(select(School.id).where(School.id == school_id).with_for_update(key_share=True))
    now = datetime.now(UTC)
    window = (AuditLog.user_id == actor_id, AuditLog.action.in_(FILING_ACTIONS), AuditLog.created_at > now - timedelta(hours=1))
    if (await db.scalar(select(func.count()).select_from(AuditLog).where(*window)) or 0) >= TRANSFER_FILINGS_PER_HOUR:
        oldest = await db.scalar(select(func.min(AuditLog.created_at)).where(*window)) or now  # never None here: the count above found rows
        wait = max(1, int((oldest + timedelta(hours=1) - now).total_seconds()))
        logger.warning("transfer_filing_throttled", extra={"extra_fields": {"actor_id": str(actor_id), "school_id": str(school_id), "wait_seconds": wait}})
        raise HTTPException(429, f"Too many transfer requests; try again in {wait} seconds", headers={"Retry-After": str(wait)})
    open_count = (
        await db.scalar(
            select(func.count()).select_from(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.filed_by_school_id == school_id, SchoolStudentTransferRequest.status == "pending")
        )
        or 0
    )
    if open_count >= MAX_OPEN_TRANSFER_REQUESTS_PER_SCHOOL:
        logger.warning("transfer_open_cap_reached", extra={"extra_fields": {"actor_id": str(actor_id), "school_id": str(school_id), "open": open_count}})
        # AC-27: a refused attempt is still an attempt that passed validation, so it is audited (a token and the school, never the code typed) and
        # committed before the 409. Unlike the throttle's own 429 it is safe to count: it happens only while the school is at its cap.
        _audit(db, actor_id, ACTION_DENIED, None, outcome="denied", reason_token="cap_reached", school_id=str(school_id))
        await db.commit()
        raise HTTPException(409, TOO_MANY_OPEN)


def _ref(school: School) -> SchoolRef:
    return SchoolRef(id=school.id, name=school.name)


def _direction(row: SchoolStudentTransferRequest) -> TransferDirection:
    """Outgoing when the losing school filed it, incoming when the gaining school did. Derived, never stored."""
    return "outgoing" if row.filed_by_school_id == row.from_school_id else "incoming"


def _request_out(row: SchoolStudentTransferRequest, student: SchoolStudent, from_school: School, to_school: School) -> TransferRequestOut:
    """The coordinator's view of a request. A request the GAINING school filed is redacted until it is approved: the student's ID,
    name and current school stay null, so the gaining coordinator knows only the Student ID they typed (spec §5.2). One schema
    either way -- nothing appears or disappears by condition."""
    direction = _direction(row)
    redacted = direction == "incoming" and row.status != "approved"
    return TransferRequestOut(
        id=row.id,
        direction=direction,
        status=cast(TransferStatus, row.status),
        student_id=None if redacted else student.id,
        student_code=student.student_code,
        student_name=None if redacted else student.full_name,
        from_school=None if redacted else _ref(from_school),
        to_school=_ref(to_school),
        reason=row.reason,
        decision_note=row.decision_note,
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


@coordinator_router.get("/transfer-destinations", response_model=list[SchoolRef])
async def transfer_destinations(user: User = Depends(_require_coordinator_user), db: AsyncSession = Depends(get_db)):
    """Every other school, as id and name only -- the source of the destination picker."""
    school_id = _own_school_id(user)
    schools = (await db.scalars(select(School).where(School.id != school_id).order_by(School.name))).all()
    return [_ref(s) for s in schools]


@coordinator_router.get("/transfer-requests", response_model=TransferRequestPage)
async def list_my_transfer_requests(
    status: TransferStatusFilter = "pending",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(_require_coordinator_user),
    db: AsyncSession = Depends(get_db),
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
    row = await db.scalar(select(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.id == request_id, SchoolStudentTransferRequest.filed_by_school_id == school_id).with_for_update())
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
    student = await _get_or_404(db, SchoolStudent, row.school_student_id, "Student")
    return _request_out(row, student, await _get_or_404(db, School, row.from_school_id, "School"), await _get_or_404(db, School, row.to_school_id, "School"))


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
        "history": [{"id": r.id, "decided_at": r.decided_at, "from_school": _ref(f), "to_school": _ref(t)} for r, f, t in rows],
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
    from_school = await _get_or_404(db, School, school_id, "School")
    row = SchoolStudentTransferRequest(
        school_student_id=student.id,
        from_school_id=school_id,
        to_school_id=to_school.id,
        requested_by_user_id=actor_id,
        filed_by_school_id=school_id,
        status="pending",
        reason=payload.reason,
    )
    try:
        async with db.begin_nested():  # a savepoint: losing the race must not release the school lock before the denial is audited and committed
            db.add(row)
            await db.flush()  # the partial unique index is the atomic claim: two simultaneous filings cannot both win
    except IntegrityError as exc:
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
            school_student_id=student.id,
            from_school_id=student.school_id,
            to_school_id=school_id,
            requested_by_user_id=actor_id,
            filed_by_school_id=school_id,
            status="pending",
            reason=payload.reason,
        )
        try:
            async with db.begin_nested():  # a savepoint, for the same reason as in the outgoing route
                db.add(row)
                await db.flush()
        except IntegrityError:
            row, token = None, "duplicate"
    if row is not None:
        _audit(db, actor_id, ACTION_FILED, row.id, school_id=str(school_id), from_school_id=str(row.from_school_id), to_school_id=str(school_id), direction="incoming")
    else:
        _audit(db, actor_id, ACTION_DENIED, None, outcome="denied", reason_token=token, school_id=str(school_id))
    await db.commit()
    logger.info("transfer_incoming_attempt", extra={"extra_fields": {"actor_id": str(actor_id), "school_id": str(school_id), "created": row is not None}})
    return {"accepted": True}


# ---------------------------------------------------------------------------------------------- admin: approve (spec §5.4)


async def _require_transfer_admin(user: User = Depends(get_current_user)) -> User:
    """Approve and reject are admin-only, and a coordinator can never reach them (filers and approvers are disjoint roles).
    Checked as a dependency so a wrong role gets 403 before any 404/422/409 can hint at a request's existence."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    return user


def _raise_if_conflict(exc: DBAPIError, actor_id: UUID, request_id: UUID) -> None:
    """A concurrent conflict (IntegrityError) or a lock wait past the bound (`55P03`, lock_not_available) becomes a clean 409 with
    nothing written; anything else is a real error and is left to propagate."""
    if isinstance(exc, IntegrityError) or getattr(exc.orig, "sqlstate", None) == "55P03":
        logger.warning("transfer_decision_conflict", extra={"extra_fields": {"actor_id": str(actor_id), "request_id_row": str(request_id), "timeout": TRANSFER_LOCK_TIMEOUT}})
        raise HTTPException(409, LOCK_BUSY) from exc


def _admin_rows_stmt(*conditions):
    """Requests joined to everything the admin view names, in ONE statement (no per-row lookups)."""
    from_school, to_school, filed_by = aliased(School), aliased(School), aliased(School)
    requester, decider = aliased(User), aliased(User)
    stmt = (
        select(SchoolStudentTransferRequest, SchoolStudent, from_school, to_school, filed_by, requester, decider)
        .join(SchoolStudent, SchoolStudent.id == SchoolStudentTransferRequest.school_student_id)
        .join(from_school, from_school.id == SchoolStudentTransferRequest.from_school_id)
        .join(to_school, to_school.id == SchoolStudentTransferRequest.to_school_id)
        .join(filed_by, filed_by.id == SchoolStudentTransferRequest.filed_by_school_id)
        .join(requester, requester.id == SchoolStudentTransferRequest.requested_by_user_id)
        .join(decider, decider.id == SchoolStudentTransferRequest.decided_by_user_id, isouter=True)
    )
    return stmt.where(*conditions).order_by(SchoolStudentTransferRequest.created_at.desc(), SchoolStudentTransferRequest.id.desc())


def _admin_out(row, student, from_school, to_school, filed_by, requester, decider, preview=None) -> AdminTransferRequestOut:
    """The admin's view: always complete, no redaction."""
    return AdminTransferRequestOut(
        id=row.id,
        direction=_direction(row),
        status=cast(TransferStatus, row.status),
        student_id=student.id,
        student_code=student.student_code,
        student_name=student.full_name,
        from_school=_ref(from_school),
        to_school=_ref(to_school),
        filed_by_school=_ref(filed_by),
        requester=UserRef(id=requester.id, name=requester.full_name),
        reason=row.reason,
        decision_note=row.decision_note,
        decided_by=UserRef(id=decider.id, name=decider.full_name) if decider else None,
        outcome=row.outcome,
        preview=preview,
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


async def _approve(db: AsyncSession, request_id: UUID, admin_id: UUID):
    """The whole move, inside the caller's transaction. Lock order is fixed -- request, then student, then parent users by id, then
    in-flight results by id -- so it cannot deadlock with itself, with a promotion (which locks students) or with a result
    verify (which locks a result and only reads the student). The parent count runs AFTER the parent locks, so two siblings
    transferred at once serialise on their shared parent and both see the other's committed move."""
    request = await db.scalar(select(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.id == request_id).with_for_update())
    if request is None:
        raise HTTPException(404, "Transfer request not found")
    if request.status != "pending":
        raise HTTPException(409, ALREADY_DECIDED)
    student = await db.scalar(select(SchoolStudent).where(SchoolStudent.id == request.school_student_id).with_for_update())
    if student is None:
        raise HTTPException(404, "Student not found")
    if student.school_id != request.from_school_id:  # the student left by some other route since it was filed
        raise HTTPException(409, STALE_REQUEST)
    from_school, to_school = await _get_or_404(db, School, request.from_school_id, "School"), await _get_or_404(db, School, request.to_school_id, "School")
    from_id, to_id = str(from_school.id), str(to_school.id)

    # Parents (D1): the link is never touched. An account at the losing school whose only child there was this student follows the
    # child conceptually (this and every other place a Parent's data is scoped reads that from SchoolParentLink alone, per ENH-008) --
    # nothing is written to the parent's own account. The row lock below still matters: it's what makes two siblings transferred at
    # once serialise on their shared parent, so the moved/kept read below sees a consistent view (security review S2/S4).
    linked = select(SchoolParentLink.parent_user_id).where(SchoolParentLink.school_student_id == student.id)
    parents = (await db.scalars(select(User).where(User.id.in_(linked)).order_by(User.id).with_for_update())).all()
    moved_parent_ids: list[str] = []
    kept_parent_ids: list[str] = []
    for parent in parents:
        if parent.role != "school_parent":
            continue
        others_at_from = await db.scalar(
            select(func.count())
            .select_from(SchoolParentLink)
            .join(SchoolStudent, SchoolStudent.id == SchoolParentLink.school_student_id)
            .where(SchoolParentLink.parent_user_id == parent.id, SchoolStudent.school_id == request.from_school_id, SchoolStudent.id != student.id)
        )
        if others_at_from:
            kept_parent_ids.append(str(parent.id))
        else:
            moved_parent_ids.append(str(parent.id))
    moved, kept = len(moved_parent_ids), len(kept_parent_ids)

    # In-flight results (D3): kept, frozen, hidden. Published results stay with the student.
    in_flight = (
        await db.scalars(
            select(SchoolAcademicResult)
            .where(SchoolAcademicResult.school_student_id == student.id, SchoolAcademicResult.status.in_(("draft", "verified")))
            .order_by(SchoolAcademicResult.id)
            .with_for_update()
        )
    ).all()
    for result in in_flight:
        db.add(SchoolResultStatusHistory(result_id=result.id, from_status=result.status, to_status="withdrawn", changed_by_user_id=admin_id))
        result.status = "withdrawn"

    teacher_cleared, pending_email_cleared = student.assigned_teacher_user_id is not None, student.pending_parent_email is not None
    student.school_id, student.assigned_teacher_user_id, student.pending_parent_email = request.to_school_id, None, None
    # ENH-025 (DEC-SCOPE-029 item 7): section and roll number belong to the losing school, like the teacher.
    student.section, student.roll_number = None, None
    request.status, request.decided_by_user_id, request.decided_at = "approved", admin_id, datetime.now(UTC)
    request.outcome = {"parents_moved": moved, "parents_kept": kept, "results_withdrawn": len(in_flight), "teacher_cleared": teacher_cleared, "pending_parent_email_cleared": pending_email_cleared}
    _audit(db, admin_id, ACTION_TRANSFER, request.id, from_school_id=from_id, to_school_id=to_id, parents_moved_ids=moved_parent_ids, parents_kept_ids=kept_parent_ids, **request.outcome)
    return request, student, from_school, to_school


async def _notify_transfer_approved(db: AsyncSession, student: SchoolStudent, from_school: School, to_school: School) -> None:
    """After the commit (a rolled-back approval can never have told anyone). Both schools' coordinators are told in-app only; the
    parents get the existing SCH-007 notice (in-app plus the email channel). The student is named to all of them: it is now, or was,
    their student."""
    parents_told = await _notify_student_parents(
        db,
        student,
        title=f"{student.full_name} has moved to {to_school.name}",
        body=f"{student.full_name}'s school record has moved from {from_school.name} to {to_school.name}. You keep access to their profile and progress.",
        action_url=f"/school/parent/children/{student.id}",
    )
    coordinators = (await db.scalars(select(User).where(User.role == "school_coordinator", User.active.is_(True)))).all()
    for coordinator in coordinators:
        school = (coordinator.profile or {}).get("school_id")
        if school == str(from_school.id):
            db.add(
                Notification(
                    user_id=coordinator.id,
                    title=f"Transfer approved: {student.full_name} moved to {to_school.name}",
                    body=f"{student.full_name} has left {from_school.name} for {to_school.name}.",
                    read=False,
                    action_url="/school/coordinator/transfers",
                )
            )
        elif school == str(to_school.id):
            db.add(
                Notification(
                    user_id=coordinator.id,
                    title=f"{student.full_name} has joined {to_school.name}",
                    body=f"{student.full_name} has moved to your school from {from_school.name}.",
                    read=False,
                    action_url=f"/school/coordinator/students/{student.id}",
                )
            )
    await db.commit()
    logger.info("transfer_notifications_sent", extra={"extra_fields": {"student_id": str(student.id), "parents": parents_told}})


@admin_router.post("/school-transfer-requests/{request_id}/approve", response_model=AdminTransferRequestOut)
async def approve_transfer_request(request_id: UUID, admin: User = Depends(_require_transfer_admin), db: AsyncSession = Depends(get_db)):
    """Approve a pending request: the one action that moves the student. Everything below is one transaction; a lock wait longer than
    the bound, or a concurrent conflict, is a clean 409 with nothing written."""
    admin_id = admin.id
    # `set_config(..., true)` is SET LOCAL with a bound parameter, so no SQL is built from a string.
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": TRANSFER_LOCK_TIMEOUT})
    try:
        request, student, from_school, to_school = await _approve(db, request_id, admin_id)
        await db.commit()
    except DBAPIError as exc:
        await db.rollback()
        _raise_if_conflict(exc, admin_id, request_id)
        raise
    logger.info("student_transfer_approved", extra={"extra_fields": {"actor_id": str(admin_id), "request_id_row": str(request.id), **request.outcome}})
    # The response is built BEFORE the notification step: a failure there rolls the session back, which expires every loaded object.
    requester = await db.get(User, request.requested_by_user_id)
    filed_by = from_school if request.filed_by_school_id == from_school.id else to_school
    out = _admin_out(request, student, from_school, to_school, filed_by, requester, admin)
    request_row_id = str(request.id)
    try:
        await _notify_transfer_approved(db, student, from_school, to_school)
    except Exception:  # noqa: BLE001 -- the transfer has committed; a notification problem must never undo or fail it (SCH-007-AC04)
        await db.rollback()
        logger.warning("transfer_notification_failed", extra={"extra_fields": {"request_id_row": request_row_id}}, exc_info=True)
    return out


@admin_router.post("/school-transfer-requests/{request_id}/reject", response_model=AdminTransferRequestOut)
async def reject_transfer_request(request_id: UUID, payload: TransferRejectRequest | None = None, admin: User = Depends(_require_transfer_admin), db: AsyncSession = Depends(get_db)):
    """Refuse a pending request. Only the request row changes; no student, parent or result is touched. The optional note is shown
    to the filing coordinator and is never copied into the audit row or a log. The body is optional."""
    admin_id, note = admin.id, payload.note if payload else None
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": TRANSFER_LOCK_TIMEOUT})
    try:
        request = await db.scalar(select(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.id == request_id).with_for_update())
        if request is None:
            raise HTTPException(404, "Transfer request not found")
        if request.status != "pending":
            raise HTTPException(409, ALREADY_DECIDED)
        request.status, request.decided_by_user_id, request.decided_at, request.decision_note = "rejected", admin_id, datetime.now(UTC), note
        _audit(db, admin_id, ACTION_REJECTED, request.id, from_school_id=str(request.from_school_id), to_school_id=str(request.to_school_id))
        await db.commit()
    except DBAPIError as exc:
        await db.rollback()
        _raise_if_conflict(exc, admin_id, request_id)
        raise
    logger.info("transfer_request_rejected", extra={"extra_fields": {"actor_id": str(admin_id), "request_id_row": str(request.id)}})
    student = await _get_or_404(db, SchoolStudent, request.school_student_id, "Student")
    from_school, to_school = await _get_or_404(db, School, request.from_school_id, "School"), await _get_or_404(db, School, request.to_school_id, "School")
    requester = await _get_or_404(db, User, request.requested_by_user_id, "Requester")
    filed_by = from_school if request.filed_by_school_id == from_school.id else to_school
    out = _admin_out(request, student, from_school, to_school, filed_by, requester, admin)
    incoming = request.filed_by_school_id == request.to_school_id
    try:
        # In-app only. To a coordinator who filed an INCOMING request the notice carries the Student ID they typed and nothing else:
        # naming the student or their school would tell a school about a student it does not own (security review S3/S8).
        title = f"Transfer request for Student ID {student.student_code} was not approved" if incoming else f"Transfer of {student.full_name} to {to_school.name} was not approved"
        db.add(
            Notification(
                user_id=request.requested_by_user_id,
                title=title,
                body="An admin reviewed the request and did not approve it. Nothing has changed.",
                read=False,
                action_url="/school/coordinator/transfers",
            )
        )
        await db.commit()
    except Exception:  # noqa: BLE001 -- the decision has committed; a notification problem must never undo or fail it
        await db.rollback()
        logger.warning("transfer_notification_failed", extra={"extra_fields": {"request_id_row": str(request_id)}}, exc_info=True)
    return out


@admin_router.get("/school-transfer-requests", response_model=AdminTransferPage)
async def admin_list_transfer_requests(
    status: TransferStatusFilter = "pending",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(_require_transfer_admin),
    db: AsyncSession = Depends(get_db),
):
    """The admin's queue, newest first, unredacted. A pending row carries a preview of what approval would touch; the three counts are
    computed with ONE grouped query each over the page's IDs, never per row."""
    conditions = [] if status == "all" else [SchoolStudentTransferRequest.status == status]
    total = await db.scalar(select(func.count()).select_from(SchoolStudentTransferRequest).where(*conditions))
    rows = (await db.execute(_admin_rows_stmt(*conditions).limit(limit).offset(offset))).all()
    pending = [r for r in rows if r[0].status == "pending"]
    parents: dict[UUID, int] = {}
    in_flight: dict[UUID, int] = {}
    staffed: set[UUID] = set()
    if pending:
        student_ids, to_ids = [r[1].id for r in pending], {r[0].to_school_id for r in pending}
        parent_counts = await db.execute(
            select(SchoolParentLink.school_student_id, func.count()).where(SchoolParentLink.school_student_id.in_(student_ids)).group_by(SchoolParentLink.school_student_id)
        )
        parents = {student_id: n for student_id, n in parent_counts.all()}
        result_counts = await db.execute(
            select(SchoolAcademicResult.school_student_id, func.count())
            .where(SchoolAcademicResult.school_student_id.in_(student_ids), SchoolAcademicResult.status.in_(("draft", "verified")))
            .group_by(SchoolAcademicResult.school_student_id)
        )
        in_flight = {student_id: n for student_id, n in result_counts.all()}
        staffed = set((await db.scalars(select(SchoolStaffAssignment.school_id).where(SchoolStaffAssignment.school_id.in_(to_ids)).distinct())).all())
    items = [
        _admin_out(
            r,
            s,
            f,
            t,
            filed,
            requester,
            decider,
            AdminTransferPreview(
                linked_parents=parents.get(s.id, 0),
                in_flight_results=in_flight.get(s.id, 0),
                to_school_has_portfolio_staff=r.to_school_id in staffed,
                pending_parent_invite=s.pending_parent_email is not None,
            )
            if r.status == "pending"
            else None,
        )
        for r, s, f, t, filed, requester, decider in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@admin_router.get("/school-students/{student_id}/transfer-history", response_model=AdminTransferHistoryResponse)
async def admin_student_transfer_history(student_id: UUID, admin: User = Depends(_require_transfer_admin), db: AsyncSession = Depends(get_db)):
    """Every request for one student, all statuses, with staff names (admin-only, so names are allowed). Bounded per student."""
    student = await db.get(SchoolStudent, student_id)
    if student is None:
        raise HTTPException(404, "Student not found")
    rows = (await db.execute(_admin_rows_stmt(SchoolStudentTransferRequest.school_student_id == student.id))).all()
    return {"student": {"id": student.id, "full_name": student.full_name}, "history": [_admin_out(r, s, f, t, filed, requester, decider) for r, s, f, t, filed, requester, decider in rows]}

import secrets
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.identifiers import uuid_reference
from app.core.rbac import agent_is_approved
from app.models import (
    AgentCommission,
    AgentStudent,
    Agreement,
    ApplicationStatusHistory,
    Appointment,
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentQuestion,
    Assignment,
    Attendance,
    AttendanceCorrection,
    AuditLog,
    Batch,
    Certificate,
    Company,
    ConsentRecord,
    Country,
    CourseFeedback,
    Enrollment,
    Interview,
    Job,
    JobApplication,
    JobOffer,
    LearningResource,
    LiveSession,
    Message,
    Notification,
    NotificationDelivery,
    OverseasApplication,
    OverseasCourse,
    Payment,
    PlacementProfile,
    ProfileDocument,
    Program,
    QuestionReply,
    QuestionThread,
    Scholarship,
    ScholarshipApplication,
    StudentDocument,
    Submission,
    SupportTicket,
    University,
    User,
    VisaCase,
)
from app.schemas import (
    AgentStudentCreate,
    AppointmentCreate,
    AssessmentCreate,
    AssessmentGradeIn,
    AssessmentQuestionIn,
    AssessmentSubmitIn,
    AssessmentUpdate,
    AssignmentCreate,
    AssignmentSubmissionIn,
    AssignmentUpdate,
    AttendanceBulkIn,
    AttendanceCorrectionIn,
    CommissionAmountUpdate,
    CommissionCreate,
    CourseFeedbackCreate,
    EnrollmentCreate,
    EnrollmentProgressUpdate,
    LearningResourceCreate,
    OverseasApplicationCreate,
    OverseasApplicationAdvance,
    OverseasApplicationUpdate,
    ProfileDocumentCreate,
    QuestionReplyCreate,
    QuestionThreadCreate,
    StudentDocumentCreate,
    SubmissionGradeIn,
    SupportTicketCreate,
    SupportTicketUpdate,
    VisaCaseCreate,
)
from app.api.files import _allowed
from app.core.config import settings
from app.services.certificates import generate_certificate_pdf
from app.services.integrations import send_notification
from app.services.storage import storage

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _require(user: User, roles: set[str], division: str | None = None):
    if user.role == "super_admin":
        return
    if user.role not in roles:
        raise HTTPException(403, "This role cannot perform this operation")
    if division and user.division != division:
        raise HTTPException(403, "Wrong EduSphere division")
    # AGT-001-AC02: a Pending/Rejected Agent cannot refer students or view data, even
    # though `user.role == "agent"` already passed above -- this codebase's `_require`
    # checks the legacy `User.role` column, which has no approval concept of its own.
    if not agent_is_approved(user):
        raise HTTPException(403, "Agent registration is pending approval")


async def _audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id: UUID | str | None, metadata: dict | None = None):
    db.add(AuditLog(user_id=user.id, action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None, metadata_json=metadata or {}))


async def _notify_user(db: AsyncSession, recipient: User, title: str, body: str, action_url: str | None, channels: list[str] | None = None):
    item = Notification(user_id=recipient.id, title=title, body=body, read=False, action_url=action_url)
    db.add(item)
    await db.flush()
    for channel in channels or ["email"]:
        status, error = await send_notification(channel, {"to": recipient.email, "phone": recipient.phone, "title": title, "body": body, "action_url": action_url})
        db.add(NotificationDelivery(notification_id=item.id, channel=channel, status=status, error=error, sent_at=datetime.now(UTC) if status == "sent" else None))


def _grade(percentage: float) -> str:
    if percentage >= 90:
        return "A+"
    if percentage >= 80:
        return "A"
    if percentage >= 70:
        return "B"
    if percentage >= 60:
        return "C"
    if percentage >= 50:
        return "D"
    return "F"


async def _assigned_application(db: AsyncSession, user: User, application_id: UUID) -> OverseasApplication:
    item = await db.get(OverseasApplication, application_id)
    if not item:
        raise HTTPException(404, "Application not found")
    if user.role == "super_admin":
        return item
    if user.division != "overseas":
        raise HTTPException(403, "Wrong EduSphere division")
    allowed = (
        user.role == "overseas_admin"
        or user.role == "overseas_student"
        and item.student_id == user.id
        or user.role == "counselor"
        and item.counselor_id == user.id
        or user.role == "agent"
        and item.agent_id == user.id
        or user.role == "university_rep"
        and uuid_reference(user.profile.get("university_id"), "university reference", required=False) == item.university_id
    )
    if not allowed:
        raise HTTPException(403, "Application is outside your assigned scope")
    return item


# ------------------------------- IT LEARNING -------------------------------
@router.get("/it/trainer/context")
async def trainer_context(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    stmt = select(Batch).order_by(Batch.start_date.desc())
    if user.role == "trainer":
        stmt = stmt.where(Batch.trainer_id == user.id)
    batches = (await db.scalars(stmt)).all()
    batch_ids = [batch.id for batch in batches]
    enrollments = []
    if batch_ids:
        enrollments = (
            await db.execute(select(Enrollment, User).join(User, User.id == Enrollment.student_id).where(Enrollment.batch_id.in_(batch_ids), Enrollment.status == "active").order_by(User.full_name))
        ).all()
    enrolled_counts: dict[UUID, int] = {}
    for e, _ in enrollments:
        enrolled_counts[e.batch_id] = enrolled_counts.get(e.batch_id, 0) + 1
    return {
        # TRN-002: "roster (capped at 20 per DEC-WF-002) and schedule/status" -- start/end
        # dates, status, mode, and timezone were previously missing here (only used for the
        # batch-picker dropdowns elsewhere, which only needed id/name/schedule/capacity).
        "batches": [
            {
                "id": b.id,
                "name": b.name,
                "schedule": b.schedule,
                "timezone": b.timezone,
                "capacity": b.capacity,
                "enrolled_count": enrolled_counts.get(b.id, 0),
                "start_date": b.start_date,
                "end_date": b.end_date,
                "status": b.status,
                "mode": b.mode,
            }
            for b in batches
        ],
        "students": [{"id": s.id, "name": s.full_name, "email": s.email, "batch_id": e.batch_id} for e, s in enrollments],
        "enrollments": [
            {
                "id": e.id,
                "student_id": s.id,
                "student": s.full_name,
                "batch_id": e.batch_id,
                "batch": next((b.name for b in batches if b.id == e.batch_id), "Assigned batch"),
                "enrollment_code": e.enrollment_code,
                "progress_percent": e.progress_percent,
            }
            for e, s in enrollments
        ],
    }


@router.get("/it/student/learning")
async def student_learning(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    enrollments = (await db.execute(select(Enrollment, Batch).join(Batch, Enrollment.batch_id == Batch.id).where(Enrollment.student_id == user.id))).all()
    batch_ids = [e.batch_id for e, _ in enrollments]
    assignments = []
    resources = []
    assessments = []
    live_sessions = []
    certificates = []
    submissions = []
    if batch_ids:
        assignments = (await db.scalars(select(Assignment).where(Assignment.batch_id.in_(batch_ids)).order_by(Assignment.due_date))).all()
        resources = (await db.scalars(select(LearningResource).where(LearningResource.batch_id.in_(batch_ids)).order_by(LearningResource.created_at.desc()))).all()
        assessments = (await db.scalars(select(Assessment).where(Assessment.batch_id.in_(batch_ids)).order_by(Assessment.scheduled_at))).all()
        live_sessions = (await db.scalars(select(LiveSession).where(LiveSession.batch_id.in_(batch_ids)).order_by(LiveSession.starts_at))).all()
        submissions = (await db.scalars(select(Submission).where(Submission.student_id == user.id))).all()
    certificates = (await db.scalars(select(Certificate).where(Certificate.student_id == user.id).order_by(Certificate.issued_on.desc()))).all()
    return {
        "enrollments": [
            {
                "id": e.id,
                "enrollment_code": e.enrollment_code,
                "batch_id": b.id,
                "batch": b.name,
                "status": e.status,
                "progress": e.progress_percent,
                "schedule": b.schedule,
                "timezone": b.timezone,
                "mode": b.mode,
            }
            for e, b in enrollments
        ],
        "assignments": [
            {
                "id": a.id,
                "batch_id": a.batch_id,
                "title": a.title,
                "description": a.description,
                "due_date": a.due_date,
                "max_score": a.max_score,
                "assignment_type": a.assignment_type,
                "submission_type": a.submission_type,
            }
            for a in assignments
        ],
        "submissions": [{"id": s.id, "assignment_id": s.assignment_id, "score": s.score, "feedback": s.feedback, "status": s.status} for s in submissions],
        "assessments": [
            {
                "id": a.id,
                "batch_id": a.batch_id,
                "title": a.title,
                "scheduled_at": a.scheduled_at,
                "duration_minutes": a.duration_minutes,
                "max_score": a.max_score,
                "pass_percent": a.pass_percent,
                "status": a.status,
            }
            for a in assessments
        ],
        "live_sessions": [
            {
                "id": s.id,
                "batch_id": s.batch_id,
                "title": s.title,
                "starts_at": s.starts_at,
                "ends_at": s.ends_at,
                "provider": s.provider,
                "meeting_url": s.meeting_url,
                "recording_url": s.recording_url,
                "recording_status": s.recording_status,
                "status": s.status,
            }
            for s in live_sessions
        ],
        "certificates": [
            {"id": c.id, "certificate_no": c.certificate_no, "verification_code": c.verification_code, "issued_on": c.issued_on, "file_url": c.file_url, "status": c.status} for c in certificates
        ],
        "resources": [{"id": r.id, "batch_id": r.batch_id, "title": r.title, "type": r.resource_type, "url": r.url} for r in resources],
    }


@router.get("/it/batches/available")
async def available_batches(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student", "it_admin"}, "it")
    # Capacity is consumed the moment a slot is booked (DEC-WF-002: locked, non-transferable
    # for the course duration) -- a not-yet-consented enrolment still holds its seat, so this
    # counts "active" and "pending_consent" alike, not just "active".
    counts = dict((await db.execute(select(Enrollment.batch_id, func.count(Enrollment.id)).where(Enrollment.status.in_(("active", "pending_consent"))).group_by(Enrollment.batch_id))).all())
    # RAID.md I-25: this never excluded a batch whose own `end_date` had already passed --
    # confirmed directly (a batch scheduled 2026-01-01/2026-04-01 was still listed as
    # "available" well after that end date had passed), surfaced by a user screenshot of
    # the student's own slot picker showing stale cohorts alongside real ones. A batch
    # that has already ended has nothing left to enrol into, regardless of `status`.
    # RAID.md I-26: this also never excluded a batch the caller already has *any*
    # Enrollment row for -- `create_enrollment` already 409s on a repeat booking
    # (`Enrollment.student_id == student.id, Enrollment.batch_id == batch.id`, any
    # status), so "Book this slot" stayed clickable for a batch already booked,
    # producing a confusing 409 with no visible reason. Excluding it here matches that
    # same rule and means there's nothing left to click for it in the first place.
    already_enrolled_batch_ids = set(await db.scalars(select(Enrollment.batch_id).where(Enrollment.student_id == user.id)))
    rows = (
        await db.execute(
            select(Batch, Program).join(Program).where(Batch.enrollment_open.is_(True), Batch.status.in_(["upcoming", "active"]), Batch.end_date >= date.today()).order_by(Batch.start_date)
        )
    ).all()
    return [
        {
            "id": b.id,
            "name": b.name,
            "program_id": p.id,
            "program": p.title,
            "schedule": b.schedule,
            "timezone": b.timezone,
            "capacity": b.capacity,
            "available": max(0, b.capacity - counts.get(b.id, 0)),
            "start_date": b.start_date,
            "end_date": b.end_date,
            "mode": b.mode,
        }
        for b, p in rows
        if counts.get(b.id, 0) < b.capacity and b.id not in already_enrolled_batch_ids
    ]


@router.post("/it/enrollments", status_code=201)
async def create_enrollment(payload: EnrollmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student", "it_admin"}, "it")
    student_id = user.id if user.role == "it_student" else (payload.student_id or 0)
    student = await db.get(User, student_id)
    if not student or student.role != "it_student" or student.division != "it":
        raise HTTPException(422, "Valid IT student is required")
    batch = await db.scalar(select(Batch).where(Batch.id == payload.batch_id).with_for_update())
    if not batch:
        raise HTTPException(404, "Batch not found")
    if not batch.enrollment_open or batch.status not in {"upcoming", "active"}:
        raise HTTPException(409, "Enrollment is closed for this batch")
    existing = await db.scalar(select(Enrollment).where(Enrollment.student_id == student.id, Enrollment.batch_id == batch.id))
    if existing:
        raise HTTPException(409, "Student is already enrolled in this batch")
    count = await db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.batch_id == batch.id, Enrollment.status.in_(("active", "pending_consent")))) or 0
    if count >= batch.capacity:
        raise HTTPException(409, "This batch is full")
    code = f"EDU-{date.today():%Y%m%d}-{secrets.token_hex(3).upper()}"
    # DEC-WF-002: a booked slot is locked for the course duration -- this is never
    # client-controlled (the base codebase's own EnrollmentCreate.slot_locked field let
    # the caller set it; removed there, always True here).
    # STU-009-AC02 / DATA_MODEL.md §3.4: status cannot reach "active" without a matching
    # ConsentRecord -- the slot is locked immediately (counts toward capacity above), but
    # the enrolment itself starts "pending_consent" until the student accepts the agreement.
    item = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=code, enrolled_on=date.today(), slot_locked=True, status="pending_consent", progress_percent=0)
    db.add(item)
    await db.flush()
    await _audit(db, user, "enrollment.create", "enrollment", item.id, {"batch_id": batch.id, "student_id": student.id})
    # Enrolling never used to create anything a student actually owed -- `Program.fees`
    # was catalogue metadata only, and the "Fees" page is a plain read of the `Payment`
    # table, so nothing appeared there until an Admin separately remembered to call
    # `POST /admin/payments` by hand. Bill for the program's own listed fee at the
    # moment of enrolment instead, the same way `create_payment` already bills for
    # anything else -- skipped only if the program is genuinely free (`fees` is 0).
    program = await db.get(Program, batch.program_id)
    if program and float(program.fees) > 0:
        from app.api.payments import _ensure_invoice

        payment = Payment(
            user_id=student.id,
            division="it",
            reference_type="enrollment_fee",
            reference_id=item.id,
            amount=program.fees,
            currency="INR",
            provider="manual",
            status="pending",
            is_manual=True,
        )
        db.add(payment)
        await db.flush()
        await _ensure_invoice(db, payment, student)
        await _audit(db, user, "payment.create", "payment", payment.id, {"amount": float(payment.amount), "division": payment.division, "auto_created_from": "enrollment"})
    await _notify_user(db, student, "Enrollment confirmed", f"You are enrolled in {batch.name} ({batch.schedule}). Your enrollment number is {code}. Review and accept the enrolment agreement to activate it.", "/it/student/course")
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "enrollment_code": item.enrollment_code, "batch_id": item.batch_id, "status": item.status}


@router.get("/it/student/agreements/current")
async def current_agreement(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    agreement = await db.scalar(select(Agreement).where(Agreement.division == "it", Agreement.active.is_(True)).order_by(Agreement.created_at.desc()))
    if not agreement:
        raise HTTPException(404, "No active enrolment agreement is configured")
    consent = await db.scalar(select(ConsentRecord).where(ConsentRecord.user_id == user.id, ConsentRecord.agreement_id == agreement.id))
    pending = await db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.student_id == user.id, Enrollment.status == "pending_consent")) or 0
    return {
        "id": agreement.id,
        "version": agreement.version,
        "title": agreement.title,
        "body": agreement.body,
        "accepted": consent is not None,
        "accepted_at": consent.created_at if consent else None,
        "pending_enrollments": pending,
    }


@router.post("/it/student/agreements/{agreement_id}/accept", status_code=201)
async def accept_agreement(agreement_id: UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    agreement = await db.get(Agreement, agreement_id)
    if not agreement or not agreement.active:
        raise HTTPException(404, "Agreement not found")
    existing = await db.scalar(select(ConsentRecord).where(ConsentRecord.user_id == user.id, ConsentRecord.agreement_id == agreement.id))
    if not existing:
        db.add(ConsentRecord(user_id=user.id, agreement_id=agreement.id, version=agreement.version, ip_address=request.client.host if request.client else None))
        await _audit(db, user, "agreement.accept", "agreement", agreement.id, {"version": agreement.version})
    # STU-009-AC02: this is the one place Enrollment.status is allowed to reach "active".
    pending = (await db.scalars(select(Enrollment).where(Enrollment.student_id == user.id, Enrollment.status == "pending_consent"))).all()
    for enrollment in pending:
        enrollment.status = "active"
    await db.commit()
    return {"agreement_id": agreement.id, "accepted": True, "activated_enrollments": len(pending)}


@router.post("/it/assignments/{assignment_id}/submissions", status_code=201)
async def submit_assignment(assignment_id: UUID, payload: AssignmentSubmissionIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Assignment not found")
    enrolled = await db.scalar(select(Enrollment.id).where(Enrollment.student_id == user.id, Enrollment.batch_id == assignment.batch_id))
    if not enrolled:
        raise HTTPException(403, "You are not enrolled in this batch")
    if assignment.submission_type == "text" and not payload.answer:
        raise HTTPException(422, "A text answer is required")
    if assignment.submission_type == "file" and not payload.file_url:
        raise HTTPException(422, "A file is required")
    if not payload.answer and not payload.file_url:
        raise HTTPException(422, "Provide an answer or file")
    # STU-004-AC02: "Submission after due date flagged, not silently accepted unless
    # allowed." No global late-submission policy is confirmed anywhere in evidence, so
    # this never blocks a late submission -- it only ensures lateness is recorded and
    # visible, per DATA_MODEL.md §4.2, rather than silently indistinguishable from an
    # on-time one.
    is_late = datetime.now(UTC) > assignment.due_date
    existing = await db.scalar(select(Submission).where(Submission.assignment_id == assignment_id, Submission.student_id == user.id))
    if existing:
        existing.answer = payload.answer if payload.answer is not None else existing.answer
        existing.file_url = payload.file_url if payload.file_url is not None else existing.file_url
        existing.status = "resubmitted"
        existing.is_late = is_late
        submission = existing
    else:
        submission = Submission(assignment_id=assignment_id, student_id=user.id, answer=payload.answer, file_url=payload.file_url, status="submitted", is_late=is_late)
        db.add(submission)
    await _audit(db, user, "assignment.submit", "submission", getattr(submission, "id", None), {"assignment_id": assignment_id, "is_late": is_late})
    await db.commit()
    await db.refresh(submission)
    return {"id": submission.id, "status": submission.status, "is_late": submission.is_late}


@router.post("/it/trainer/attendance", status_code=201)
async def mark_attendance(payload: AttendanceBulkIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    batch_id = payload.batch_id
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Trainer is not assigned to this batch")
    enrolled_ids = set((await db.scalars(select(Enrollment.student_id).where(Enrollment.batch_id == batch_id, Enrollment.status == "active"))).all())
    requested_ids = [item.student_id for item in payload.records]
    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(422, "Duplicate student attendance records are not allowed")
    if not set(requested_ids).issubset(enrolled_ids):
        raise HTTPException(422, "Attendance can only be marked for active students in this batch")
    session_date = payload.session_date
    for item in payload.records:
        student_id = item.student_id
        current = await db.scalar(select(Attendance).where(Attendance.student_id == student_id, Attendance.batch_id == batch_id, Attendance.session_date == session_date))
        if current:
            current.status = item.status
            current.notes = item.notes
        else:
            db.add(Attendance(student_id=student_id, batch_id=batch_id, session_date=session_date, status=item.status, notes=item.notes))
    await _audit(db, user, "attendance.bulk_mark", "batch", batch_id, {"session_date": session_date.isoformat(), "records": len(payload.records)})
    await db.commit()
    return {"ok": True, "records": len(payload.records)}


@router.get("/it/student/attendance")
async def student_attendance(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    rows = (await db.execute(select(Attendance, Batch).join(Batch).where(Attendance.student_id == user.id).order_by(Attendance.session_date.desc()))).all()
    return [{"id": a.id, "batch": b.name, "session_date": a.session_date, "status": a.status, "notes": a.notes} for a, b in rows]


@router.post("/it/student/attendance-corrections", status_code=201)
async def request_attendance_correction(payload: AttendanceCorrectionIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    attendance = await db.get(Attendance, payload.attendance_id)
    if not attendance or attendance.student_id != user.id:
        raise HTTPException(404, "Attendance record not found")
    pending = await db.scalar(select(AttendanceCorrection).where(AttendanceCorrection.attendance_id == attendance.id, AttendanceCorrection.status == "pending"))
    if pending:
        raise HTTPException(409, "A correction request is already pending")
    item = AttendanceCorrection(attendance_id=attendance.id, student_id=user.id, reason=payload.reason, requested_status=payload.requested_status, status="pending")
    db.add(item)
    await db.flush()
    await _audit(db, user, "attendance.correction_request", "attendance_correction", item.id)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.patch("/it/attendance-corrections/{correction_id}")
async def review_attendance_correction(correction_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    item = await db.get(AttendanceCorrection, correction_id)
    if not item:
        raise HTTPException(404, "Correction request not found")
    attendance = await db.get(Attendance, item.attendance_id)
    batch = await db.get(Batch, attendance.batch_id) if attendance else None
    if user.role == "trainer" and (not batch or batch.trainer_id != user.id):
        raise HTTPException(403, "Correction is outside your assigned batch")
    decision = payload.get("status")
    if decision not in {"approved", "rejected"}:
        raise HTTPException(422, "Status must be approved or rejected")
    item.status = decision
    item.reviewed_by_id = user.id
    item.review_notes = payload.get("review_notes")
    if decision == "approved" and attendance:
        attendance.status = item.requested_status
    await _audit(db, user, "attendance.correction_review", "attendance_correction", item.id, {"status": decision})
    await db.commit()
    return {"id": item.id, "status": item.status}


@router.get("/it/trainer/attendance-corrections")
async def trainer_attendance_corrections(status: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    stmt = (
        select(AttendanceCorrection, Attendance, User, Batch)
        .join(Attendance, Attendance.id == AttendanceCorrection.attendance_id)
        .join(User, User.id == AttendanceCorrection.student_id)
        .join(Batch, Batch.id == Attendance.batch_id)
    )
    if user.role == "trainer":
        stmt = stmt.where(Batch.trainer_id == user.id)
    if status:
        stmt = stmt.where(AttendanceCorrection.status == status)
    rows = (await db.execute(stmt.order_by(AttendanceCorrection.created_at.desc()).limit(300))).all()
    return [
        {
            "id": c.id,
            "attendance_id": a.id,
            "student": student.full_name,
            "batch": batch.name,
            "session_date": a.session_date,
            "current_status": a.status,
            "requested_status": c.requested_status,
            "reason": c.reason,
            "status": c.status,
            "review_notes": c.review_notes,
        }
        for c, a, student, batch in rows
    ]


@router.post("/it/trainer/assignments", status_code=201)
async def create_assignment(payload: AssignmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    batch_id = payload.batch_id
    if user.role == "trainer":
        batch = await db.get(Batch, batch_id)
        if not batch or batch.trainer_id != user.id:
            raise HTTPException(403, "Trainer is not assigned to this batch")
    assignment = Assignment(
        batch_id=batch_id,
        title=payload.title,
        description=payload.description,
        due_date=payload.due_date,
        max_score=payload.max_score,
        assignment_type=payload.assignment_type,
        submission_type=payload.submission_type,
        published=payload.published,
    )
    db.add(assignment)
    await db.flush()
    await _audit(db, user, "assignment.create", "assignment", assignment.id, {"batch_id": batch_id})
    await db.commit()
    await db.refresh(assignment)
    return {"id": assignment.id, "title": assignment.title, "due_date": assignment.due_date}


@router.patch("/it/trainer/assignments/{assignment_id}")
async def update_assignment(assignment_id: UUID, payload: AssignmentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    row = (await db.execute(select(Assignment, Batch).join(Batch, Batch.id == Assignment.batch_id).where(Assignment.id == assignment_id))).first()
    if not row:
        raise HTTPException(404, "Assignment not found")
    assignment, batch = row
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Assignment is outside your assigned batch")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(assignment, key, value)
    # TRN-005-AC02: editing (e.g. extending a due date) never touches existing Submission
    # rows -- `Submission.is_late` is computed and stored once, at submission time
    # (STU-004), never recomputed from the assignment's current due_date on read, so
    # already-submitted work is never retroactively invalidated or re-flagged by an edit.
    await _audit(db, user, "assignment.update", "assignment", assignment.id, changes)
    await db.commit()
    return {"id": assignment.id, "title": assignment.title, "due_date": assignment.due_date, "published": assignment.published}


@router.get("/it/trainer/assignments")
async def trainer_assignments(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    stmt = select(Assignment, Batch).join(Batch, Batch.id == Assignment.batch_id)
    if user.role == "trainer":
        stmt = stmt.where(Batch.trainer_id == user.id)
    rows = (await db.execute(stmt.order_by(Assignment.due_date.desc()).limit(500))).all()
    return [
        {
            "id": a.id,
            "batch_id": a.batch_id,
            "batch": b.name,
            "title": a.title,
            "description": a.description,
            "due_date": a.due_date,
            "max_score": a.max_score,
            "assignment_type": a.assignment_type,
            "submission_type": a.submission_type,
            "published": a.published,
        }
        for a, b in rows
    ]


@router.post("/it/trainer/materials", status_code=201)
async def create_learning_resource(payload: LearningResourceCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    batch = await db.get(Batch, payload.batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Trainer is not assigned to this batch")
    item = LearningResource(batch_id=batch.id, title=payload.title, resource_type=payload.resource_type, url=payload.url, metadata_json=payload.metadata)
    db.add(item)
    await db.flush()
    await _audit(db, user, "learning_resource.create", "learning_resource", item.id, {"batch_id": batch.id})
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "title": item.title, "type": item.resource_type, "url": item.url}


@router.patch("/it/trainer/enrollments/{enrollment_id}/progress")
async def update_enrollment_progress(enrollment_id: UUID, payload: EnrollmentProgressUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    item = await db.get(Enrollment, enrollment_id)
    if not item:
        raise HTTPException(404, "Enrollment not found")
    batch = await db.get(Batch, item.batch_id)
    if user.role == "trainer" and (not batch or batch.trainer_id != user.id):
        raise HTTPException(403, "Enrollment is outside your assigned batches")
    item.progress_percent = payload.progress_percent
    await _audit(db, user, "enrollment.progress_update", "enrollment", item.id, {"progress_percent": item.progress_percent})
    await db.commit()
    return {"id": item.id, "progress_percent": item.progress_percent}


@router.get("/it/trainer/submissions")
async def trainer_submissions(batch_id: UUID | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    stmt = select(Submission, Assignment, User).join(Assignment, Assignment.id == Submission.assignment_id).join(User, User.id == Submission.student_id).join(Batch, Batch.id == Assignment.batch_id)
    if user.role == "trainer":
        stmt = stmt.where(Batch.trainer_id == user.id)
    if batch_id:
        stmt = stmt.where(Assignment.batch_id == batch_id)
    rows = (await db.execute(stmt.order_by(Submission.created_at.desc()).limit(500))).all()
    return [
        {
            "id": s.id,
            "assignment_id": a.id,
            "assignment": a.title,
            "student_id": student.id,
            "student": student.full_name,
            "answer": s.answer,
            "file_url": s.file_url,
            "score": s.score,
            "max_score": a.max_score,
            "feedback": s.feedback,
            "status": s.status,
        }
        for s, a, student in rows
    ]


@router.patch("/it/trainer/submissions/{submission_id}")
async def grade_submission(submission_id: UUID, payload: SubmissionGradeIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    row = (
        await db.execute(
            select(Submission, Assignment, Batch).join(Assignment, Assignment.id == Submission.assignment_id).join(Batch, Batch.id == Assignment.batch_id).where(Submission.id == submission_id)
        )
    ).first()
    if not row:
        raise HTTPException(404, "Submission not found")
    submission, assignment, batch = row
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Submission is outside your assigned batch")
    if payload.score > assignment.max_score:
        raise HTTPException(422, "Score cannot exceed the assignment maximum")
    submission.score = payload.score
    submission.feedback = payload.feedback
    submission.status = payload.status
    submission.graded_by_id = user.id
    submission.graded_at = datetime.now(UTC)
    student = await db.get(User, submission.student_id)
    await _audit(db, user, "assignment.grade", "submission", submission.id, {"score": payload.score})
    if student:
        await _notify_user(db, student, "Assignment reviewed", f"{assignment.title} has been reviewed. Score: {payload.score}/{assignment.max_score}.", "/it/student/assignments")
    await db.commit()
    return {"id": submission.id, "status": submission.status, "score": submission.score}


@router.post("/it/trainer/assessments", status_code=201)
async def create_assessment(payload: AssessmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    batch_id = payload.batch_id
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Trainer is not assigned to this batch")
    assessment = Assessment(
        batch_id=batch_id,
        title=payload.title,
        description=payload.description,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        max_score=payload.max_score,
        pass_percent=payload.pass_percent,
        attempts_allowed=payload.attempts_allowed,
        instructions=payload.instructions,
        publish_results=payload.publish_results,
        status=payload.status,
    )
    db.add(assessment)
    await db.flush()
    await _audit(db, user, "assessment.create", "assessment", assessment.id, {"batch_id": batch_id})
    await db.commit()
    await db.refresh(assessment)
    return {"id": assessment.id, "title": assessment.title, "scheduled_at": assessment.scheduled_at, "status": assessment.status}


@router.patch("/it/trainer/assessments/{assessment_id}")
async def update_assessment(assessment_id: UUID, payload: AssessmentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    row = (await db.execute(select(Assessment, Batch).join(Batch, Batch.id == Assessment.batch_id).where(Assessment.id == assessment_id))).first()
    if not row:
        raise HTTPException(404, "Assessment not found")
    assessment, batch = row
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Assessment is outside your assigned batch")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(assessment, key, value)
    # TRN-006: "authors in Draft; moves to Scheduled to publish" -- this same partial
    # update carries that status transition; no separate publish endpoint is needed
    # since publishing an assessment is just one more field, the same way TRN-005's
    # Assignment.published is a plain PATCH-able boolean rather than its own endpoint.
    await _audit(db, user, "assessment.update", "assessment", assessment.id, changes)
    await db.commit()
    return {"id": assessment.id, "title": assessment.title, "status": assessment.status}


@router.get("/it/trainer/assessments")
async def trainer_assessments(batch_id: UUID | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    stmt = select(Assessment, Batch).join(Batch)
    if user.role == "trainer":
        stmt = stmt.where(Batch.trainer_id == user.id)
    if batch_id:
        stmt = stmt.where(Assessment.batch_id == batch_id)
    rows = (await db.execute(stmt.order_by(Assessment.scheduled_at.desc()).limit(300))).all()
    # RAID.md I-18 sub-item 3: a trainer needs to see, before picking an assessment in
    # "Add question", whether it already has attempt data -- adding a question to a
    # skipped-when-attempted the reference implementation once tried would be unfair to
    # whoever already started. Real count, not a guess -- backs the frontend's own lock.
    assessment_ids = [a.id for a, _ in rows]
    attempt_counts: dict[UUID, int] = {}
    if assessment_ids:
        count_rows = (
            await db.execute(
                select(AssessmentAttempt.assessment_id, func.count())
                .where(AssessmentAttempt.assessment_id.in_(assessment_ids))
                .group_by(AssessmentAttempt.assessment_id)
            )
        ).all()
        attempt_counts = dict(count_rows)
    return [
        {
            "id": a.id,
            "batch_id": b.id,
            "batch": b.name,
            "title": a.title,
            "scheduled_at": a.scheduled_at,
            "duration_minutes": a.duration_minutes,
            "max_score": a.max_score,
            "pass_percent": a.pass_percent,
            "attempts_allowed": a.attempts_allowed,
            "status": a.status,
            "description": a.description,
            "instructions": a.instructions,
            "publish_results": a.publish_results,
            "attempt_count": attempt_counts.get(a.id, 0),
        }
        for a, b in rows
    ]


async def _trainer_assessment(db: AsyncSession, user: User, assessment_id: UUID) -> tuple[Assessment, Batch]:
    row = (await db.execute(select(Assessment, Batch).join(Batch).where(Assessment.id == assessment_id))).first()
    if not row:
        raise HTTPException(404, "Assessment not found")
    assessment, batch = row
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Assessment is outside your assigned batch")
    return assessment, batch


async def _assert_no_attempts_yet(db: AsyncSession, assessment_id: UUID) -> None:
    # RAID.md I-18 sub-item 3: a question could previously be added to an assessment
    # after a student had already started (or finished) an attempt against it -- unfair
    # to whoever already took it, since they never saw the new question. Once any attempt
    # exists (in_progress, submitted, or graded), the question set is locked.
    existing = await db.scalar(select(func.count()).select_from(AssessmentAttempt).where(AssessmentAttempt.assessment_id == assessment_id))
    if existing:
        raise HTTPException(409, "Questions are locked -- a student has already started an attempt on this assessment")


@router.post("/it/trainer/assessments/{assessment_id}/questions", status_code=201)
async def add_assessment_question(assessment_id: UUID, payload: AssessmentQuestionIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    assessment, _ = await _trainer_assessment(db, user, assessment_id)
    await _assert_no_attempts_yet(db, assessment.id)
    if payload.question_type.startswith("mcq") and len(payload.options) < 2:
        raise HTTPException(422, "MCQ questions require at least two options")
    if payload.question_type.startswith("mcq") and not payload.correct_answers:
        raise HTTPException(422, "MCQ questions require a correct answer")
    if not set(payload.correct_answers).issubset(set(payload.options)):
        raise HTTPException(422, "Correct answers must exist in options")
    item = AssessmentQuestion(assessment_id=assessment.id, **payload.model_dump())
    db.add(item)
    await db.flush()
    await _audit(db, user, "assessment.question_create", "assessment_question", item.id, {"assessment_id": assessment.id})
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "position": item.position}


@router.post("/it/trainer/assessments/{assessment_id}/questions/bulk", status_code=201)
async def add_assessment_questions_bulk(assessment_id: UUID, payload: list[AssessmentQuestionIn], user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    if not payload or len(payload) > 500:
        raise HTTPException(422, "Provide between 1 and 500 questions")
    assessment, _ = await _trainer_assessment(db, user, assessment_id)
    await _assert_no_attempts_yet(db, assessment.id)
    items = []
    for question in payload:
        if question.question_type.startswith("mcq") and (len(question.options) < 2 or not question.correct_answers):
            raise HTTPException(422, "Every MCQ requires options and a correct answer")
        if not set(question.correct_answers).issubset(set(question.options)):
            raise HTTPException(422, "Correct answers must exist in options")
        item = AssessmentQuestion(assessment_id=assessment.id, **question.model_dump())
        db.add(item)
        items.append(item)
    await db.flush()
    await _audit(db, user, "assessment.questions_bulk_create", "assessment", assessment.id, {"count": len(items)})
    await db.commit()
    return {"created": len(items), "ids": [item.id for item in items]}


@router.get("/it/trainer/assessments/{assessment_id}/questions")
async def trainer_assessment_questions(assessment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    await _trainer_assessment(db, user, assessment_id)
    rows = (await db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == assessment_id).order_by(AssessmentQuestion.position, AssessmentQuestion.id))).all()
    return [
        {
            "id": q.id,
            "question_type": q.question_type,
            "prompt": q.prompt,
            "options": q.options,
            "correct_answers": q.correct_answers,
            "max_score": q.max_score,
            "position": q.position,
            "required": q.required,
        }
        for q in rows
    ]


@router.post("/it/assessments/{assessment_id}/attempts", status_code=201)
async def start_assessment(assessment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    assessment = await db.get(Assessment, assessment_id)
    if not assessment or assessment.status not in {"scheduled", "open", "published"}:
        raise HTTPException(404, "Available assessment not found")
    enrolled = await db.scalar(select(Enrollment.id).where(Enrollment.student_id == user.id, Enrollment.batch_id == assessment.batch_id, Enrollment.status == "active"))
    if not enrolled:
        raise HTTPException(403, "You are not enrolled in this assessment batch")
    attempts = await db.scalar(select(func.count()).select_from(AssessmentAttempt).where(AssessmentAttempt.assessment_id == assessment.id, AssessmentAttempt.student_id == user.id)) or 0
    if attempts >= assessment.attempts_allowed:
        raise HTTPException(409, "No assessment attempts remain")
    item = AssessmentAttempt(assessment_id=assessment.id, student_id=user.id, attempt_no=attempts + 1, status="in_progress")
    db.add(item)
    await db.flush()
    await _audit(db, user, "assessment.attempt_start", "assessment_attempt", item.id, {"assessment_id": assessment.id})
    questions = (await db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == assessment.id).order_by(AssessmentQuestion.position, AssessmentQuestion.id))).all()
    await db.commit()
    await db.refresh(item)
    return {
        "id": item.id,
        "assessment_id": assessment.id,
        "title": assessment.title,
        "duration_minutes": assessment.duration_minutes,
        "instructions": assessment.instructions,
        "questions": [{"id": q.id, "question_type": q.question_type, "prompt": q.prompt, "options": q.options, "max_score": q.max_score, "required": q.required} for q in questions],
    }


@router.post("/it/assessment-attempts/{attempt_id}/submit")
async def submit_assessment(attempt_id: UUID, payload: AssessmentSubmitIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    attempt = await db.get(AssessmentAttempt, attempt_id)
    if not attempt or attempt.student_id != user.id:
        raise HTTPException(404, "Assessment attempt not found")
    if attempt.status != "in_progress":
        raise HTTPException(409, "Assessment attempt is already submitted")
    questions = (await db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == attempt.assessment_id))).all()
    qmap = {q.id: q for q in questions}
    provided = {answer.question_id: answer for answer in payload.answers}
    missing = [q.id for q in questions if q.required and q.id not in provided]
    if missing:
        raise HTTPException(422, f"Required questions are unanswered: {missing}")
    score = 0.0
    manual = False
    for question_id, answer_in in provided.items():
        question = qmap.get(question_id)
        if not question:
            raise HTTPException(422, f"Question {question_id} is not part of this assessment")
        raw = answer_in.value
        answer_score = None
        if question.question_type == "mcq_single":
            answer_score = float(question.max_score if str(raw) in {str(x) for x in question.correct_answers} else 0)
            score += answer_score
        elif question.question_type == "mcq_multiple":
            selected = {str(x) for x in (raw if isinstance(raw, list) else [raw])}
            correct = {str(x) for x in question.correct_answers}
            answer_score = float(question.max_score if selected == correct else 0)
            score += answer_score
        else:
            manual = True
        db.add(AssessmentAnswer(attempt_id=attempt.id, question_id=question.id, answer={"value": raw}, score=answer_score))
    possible = float(sum(q.max_score for q in questions) or 1)
    percentage = round(score * 100 / possible, 2)
    attempt.submitted_at = datetime.now(UTC)
    attempt.score = score
    attempt.percentage = percentage
    attempt.grade = _grade(percentage)
    attempt.status = "submitted" if manual else "graded"
    attempt.graded_at = None if manual else datetime.now(UTC)
    await _audit(db, user, "assessment.attempt_submit", "assessment_attempt", attempt.id, {"auto_graded": not manual})
    await db.commit()
    return {"id": attempt.id, "status": attempt.status, "score": float(attempt.score), "percentage": float(attempt.percentage), "grade": attempt.grade}


@router.get("/it/trainer/assessment-attempts")
async def assessment_attempts(assessment_id: UUID | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    stmt = (
        select(AssessmentAttempt, Assessment, User, Batch)
        .join(Assessment, Assessment.id == AssessmentAttempt.assessment_id)
        .join(User, User.id == AssessmentAttempt.student_id)
        .join(Batch, Batch.id == Assessment.batch_id)
    )
    if user.role == "trainer":
        stmt = stmt.where(Batch.trainer_id == user.id)
    if assessment_id:
        stmt = stmt.where(AssessmentAttempt.assessment_id == assessment_id)
    rows = (await db.execute(stmt.order_by(AssessmentAttempt.created_at.desc()).limit(500))).all()
    return [
        {
            "id": a.id,
            "assessment_id": assessment.id,
            "assessment": assessment.title,
            "student": student.full_name,
            "attempt_no": a.attempt_no,
            "status": a.status,
            "score": float(a.score) if a.score is not None else None,
            "max_score": assessment.max_score,
            "percentage": float(a.percentage) if a.percentage is not None else None,
            "grade": a.grade,
        }
        for a, assessment, student, _ in rows
    ]


@router.get("/it/trainer/assessment-attempts/{attempt_id}")
async def assessment_attempt_detail(attempt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # RAID.md I: blind grading -- trainers previously graded a written/file attempt with no
    # view of what the student actually answered. This surfaces each question's real
    # submitted value (and any existing per-question score) so grading isn't blind.
    _require(user, {"trainer", "it_admin"}, "it")
    row = (
        await db.execute(
            select(AssessmentAttempt, Assessment, User, Batch)
            .join(Assessment, Assessment.id == AssessmentAttempt.assessment_id)
            .join(User, User.id == AssessmentAttempt.student_id)
            .join(Batch, Batch.id == Assessment.batch_id)
            .where(AssessmentAttempt.id == attempt_id)
        )
    ).first()
    if not row:
        raise HTTPException(404, "Assessment attempt not found")
    attempt, assessment, student, batch = row
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Attempt is outside your assigned batch")
    answers = (await db.scalars(select(AssessmentAnswer).where(AssessmentAnswer.attempt_id == attempt.id))).all()
    qids = [a.question_id for a in answers]
    questions = (await db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.id.in_(qids)))).all() if qids else []
    qmap = {q.id: q for q in questions}
    auto_types = {"mcq_single", "mcq_multiple"}
    answers_sorted = sorted(answers, key=lambda a: qmap[a.question_id].position if a.question_id in qmap else 0)
    return {
        "id": attempt.id,
        "assessment": assessment.title,
        "student": student.full_name,
        "status": attempt.status,
        "score": float(attempt.score) if attempt.score is not None else None,
        "max_score": assessment.max_score,
        "percentage": float(attempt.percentage) if attempt.percentage is not None else None,
        "feedback": attempt.feedback,
        "answers": [
            {
                "id": answer.id,
                "question_id": answer.question_id,
                "prompt": qmap[answer.question_id].prompt if answer.question_id in qmap else "(question removed)",
                "question_type": qmap[answer.question_id].question_type if answer.question_id in qmap else "text",
                "max_score": qmap[answer.question_id].max_score if answer.question_id in qmap else 0,
                "value": answer.answer.get("value") if isinstance(answer.answer, dict) else None,
                "auto_graded": (qmap[answer.question_id].question_type if answer.question_id in qmap else "") in auto_types,
                "score": float(answer.score) if answer.score is not None else None,
            }
            for answer in answers_sorted
        ],
    }


@router.patch("/it/trainer/assessment-attempts/{attempt_id}")
async def grade_assessment_attempt(attempt_id: UUID, payload: AssessmentGradeIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    row = (
        await db.execute(
            select(AssessmentAttempt, Assessment, Batch)
            .join(Assessment, Assessment.id == AssessmentAttempt.assessment_id)
            .join(Batch, Batch.id == Assessment.batch_id)
            .where(AssessmentAttempt.id == attempt_id)
        )
    ).first()
    if not row:
        raise HTTPException(404, "Assessment attempt not found")
    attempt, assessment, batch = row
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Attempt is outside your assigned batch")
    answers = (await db.scalars(select(AssessmentAnswer).where(AssessmentAnswer.attempt_id == attempt.id))).all()
    qids = [a.question_id for a in answers]
    questions = (await db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.id.in_(qids)))).all() if qids else []
    qmap = {q.id: q for q in questions}
    possible = float(sum(q.max_score for q in questions) or assessment.max_score or 1)
    if payload.score is not None:
        if payload.score > possible:
            raise HTTPException(422, f"Score must be between 0 and {possible:g}")
        total = float(payload.score)
    else:
        total = 0.0
        for answer in answers:
            supplied = payload.answer_scores.get(str(answer.id))
            if supplied is not None:
                maximum = qmap[answer.question_id].max_score
                if supplied < 0 or supplied > maximum:
                    raise HTTPException(422, f"Answer score must be between 0 and {maximum}")
                answer.score = supplied
            total += float(answer.score or 0)
    percentage = round(total * 100 / possible, 2)
    attempt.score = total
    attempt.percentage = percentage
    attempt.grade = _grade(percentage)
    attempt.feedback = payload.feedback
    attempt.status = "graded"
    attempt.graded_at = datetime.now(UTC)
    student = await db.get(User, attempt.student_id)
    await _audit(db, user, "assessment.attempt_grade", "assessment_attempt", attempt.id, {"score": total})
    if student:
        await _notify_user(db, student, "Assessment result published", f"Your result for {assessment.title} is {percentage}% ({attempt.grade}).", "/it/student/examinations")
    await db.commit()
    return {"id": attempt.id, "status": attempt.status, "score": total, "percentage": percentage, "grade": attempt.grade}


async def _certificate_eligibility(db: AsyncSession, enrollment: Enrollment) -> dict:
    batch = await db.get(Batch, enrollment.batch_id)
    attendance_total = await db.scalar(select(func.count()).select_from(Attendance).where(Attendance.student_id == enrollment.student_id, Attendance.batch_id == enrollment.batch_id)) or 0
    attendance_present = (
        await db.scalar(
            select(func.count())
            .select_from(Attendance)
            .where(Attendance.student_id == enrollment.student_id, Attendance.batch_id == enrollment.batch_id, Attendance.status.in_(["present", "late", "excused"]))
        )
        or 0
    )
    attendance_percent = round(attendance_present * 100 / attendance_total, 2) if attendance_total else 0
    assignment_total = await db.scalar(select(func.count()).select_from(Assignment).where(Assignment.batch_id == enrollment.batch_id, Assignment.published.is_(True))) or 0
    assignment_graded = (
        await db.scalar(
            select(func.count())
            .select_from(Submission)
            .join(Assignment)
            .where(Submission.student_id == enrollment.student_id, Assignment.batch_id == enrollment.batch_id, Submission.status == "graded")
        )
        or 0
    )
    assessments = (await db.scalars(select(Assessment).where(Assessment.batch_id == enrollment.batch_id, Assessment.status.in_(["scheduled", "open", "closed", "published"])))).all()
    passed = 0
    for assessment in assessments:
        best = await db.scalar(
            select(func.max(AssessmentAttempt.percentage)).where(
                AssessmentAttempt.assessment_id == assessment.id, AssessmentAttempt.student_id == enrollment.student_id, AssessmentAttempt.status == "graded"
            )
        )
        if best is not None and float(best) >= assessment.pass_percent:
            passed += 1
    pending_fee = (
        await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.user_id == enrollment.student_id, Payment.division == "it", Payment.status.in_(["pending", "overdue"]))) or 0
    )
    criteria = {
        "progress_percent": enrollment.progress_percent,
        "attendance_percent": attendance_percent,
        "assignments_graded": assignment_graded,
        "assignments_total": assignment_total,
        "assessments_passed": passed,
        "assessments_total": len(assessments),
        "pending_fee": float(pending_fee),
    }
    criteria["eligible"] = bool(enrollment.progress_percent >= 100 and attendance_percent >= 75 and assignment_graded >= assignment_total and passed >= len(assessments) and float(pending_fee) == 0)
    criteria["batch_id"] = batch.id if batch else enrollment.batch_id
    return criteria


@router.get("/it/certificates/eligibility/{enrollment_id}")
async def certificate_eligibility(enrollment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    enrollment = await db.get(Enrollment, enrollment_id)
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")
    if user.role == "it_student" and enrollment.student_id != user.id:
        raise HTTPException(403, "Enrollment belongs to another student")
    if user.role == "trainer":
        batch = await db.get(Batch, enrollment.batch_id)
        if not batch or batch.trainer_id != user.id:
            raise HTTPException(403, "Enrollment is outside your assigned batch")
    elif user.role not in {"it_student", "it_admin", "super_admin"}:
        raise HTTPException(403, "Certificate access denied")
    return await _certificate_eligibility(db, enrollment)


@router.post("/it/certificates/{enrollment_id}/issue", status_code=201)
async def issue_certificate(enrollment_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    enrollment = await db.get(Enrollment, enrollment_id)
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")
    batch = await db.get(Batch, enrollment.batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Enrollment is outside your assigned batch")
    existing = await db.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id))
    if existing:
        return {"id": existing.id, "certificate_no": existing.certificate_no, "file_url": existing.file_url, "status": existing.status}
    criteria = await _certificate_eligibility(db, enrollment)
    override = bool(payload.get("override", False))
    override_reason = payload.get("override_reason")
    if not criteria["eligible"]:
        if not override:
            # A real, pre-existing bug found while testing this path directly (never
            # exercised before -- every prior caller always passed override=True):
            # `HTTPException.detail` is serialized by Starlette's plain `json.dumps`,
            # not FastAPI's `jsonable_encoder`, so the raw `UUID` in `criteria["batch_id"]`
            # crashed this response with a 500 instead of ever returning the intended 409.
            raise HTTPException(409, {"message": "Completion criteria are not met", "criteria": {**criteria, "batch_id": str(criteria["batch_id"])}})
        # ADM-006-AC02: an override is never silent -- a written justification is
        # required in the same request, not just a boolean flag, and it's captured
        # durably below (both the certificate's own snapshot and the audit trail).
        if not override_reason or not str(override_reason).strip():
            raise HTTPException(422, "override_reason is required to issue a certificate before completion criteria are met")
    program = await db.get(Program, batch.program_id)
    student = await db.get(User, enrollment.student_id)
    if not program or not student:
        raise HTTPException(422, "Certificate data is incomplete")
    certificate_no = f"EDU-CERT-{date.today():%Y}-{secrets.token_hex(4).upper()}"
    verification_code = secrets.token_urlsafe(12)
    file_url = generate_certificate_pdf(certificate_no=certificate_no, student_name=student.full_name, program_title=program.title, issued_on=date.today(), verification_code=verification_code)
    item = Certificate(
        student_id=student.id,
        program_id=program.id,
        enrollment_id=enrollment.id,
        certificate_no=certificate_no,
        verification_code=verification_code,
        issued_on=date.today(),
        file_url=file_url,
        approved_by_id=user.id,
        criteria_snapshot={**criteria, "override_reason": override_reason} if not criteria["eligible"] else criteria,
        status="issued",
    )
    db.add(item)
    await db.flush()
    await _notify_user(db, student, "Certificate issued", f"Your {program.title} certificate is ready.", "/it/student/certificates", ["email"])
    item.emailed_at = datetime.now(UTC)
    await _audit(db, user, "certificate.issue", "certificate", item.id, {"enrollment_id": enrollment.id, "override": override, "override_reason": override_reason if override else None})
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "certificate_no": item.certificate_no, "verification_code": item.verification_code, "file_url": item.file_url, "status": item.status}


@router.get("/it/certificates/{certificate_id}/download")
async def download_certificate(certificate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # STU-007-AC01/AC03: the PDF itself is stored under a certificate-number-derived key,
    # never handed out as a raw, guessable, permanently-public object link -- only the
    # owning student (or an admin) can exchange a certificate id for a real, short-lived
    # download URL, verified here rather than left to the frontend to hide.
    certificate = await db.get(Certificate, certificate_id)
    if not certificate:
        raise HTTPException(404, "Certificate not found")
    if user.role == "it_student" and certificate.student_id != user.id:
        raise HTTPException(403, "Certificate belongs to another student")
    elif user.role not in {"it_student", "it_admin", "super_admin"}:
        raise HTTPException(403, "Certificate access denied")
    key = f"certificates/{certificate.certificate_no}.pdf"
    return {"url": storage.presign_download(key), "expires_in": 900 if storage.bucket else None}


@router.post("/it/student/feedback", status_code=201)
async def submit_feedback(payload: CourseFeedbackCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # STU-008-AC03: 422, not a silent drop or a 403, when there is no matching Enrollment
    # for the target batch -- an anonymous-submission option is an explicitly unconfirmed
    # PRD open item (PRD-STU-009), so this only ever records identified feedback.
    _require(user, {"it_student"}, "it")
    enrolled = await db.scalar(select(Enrollment).where(Enrollment.student_id == user.id, Enrollment.batch_id == payload.batch_id))
    if not enrolled:
        raise HTTPException(422, "You are not enrolled in this batch")
    item = CourseFeedback(student_id=user.id, batch_id=payload.batch_id, rating=payload.rating, comments=payload.comments)
    db.add(item)
    await db.flush()
    await _audit(db, user, "feedback.submit", "course_feedback", item.id, {"batch_id": str(payload.batch_id), "rating": payload.rating})
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "batch_id": item.batch_id, "rating": item.rating, "comments": item.comments}


@router.get("/it/student/profile/documents")
async def list_profile_documents(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    rows = (await db.scalars(select(ProfileDocument).where(ProfileDocument.user_id == user.id).order_by(ProfileDocument.created_at.desc()))).all()
    return [{"id": d.id, "document_type": d.document_type, "file_url": d.file_url, "original_filename": d.original_filename, "uploaded_at": d.created_at} for d in rows]


@router.get("/it/student/profile/documents/{document_id}/download")
async def download_profile_document(document_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # RAID.md I-16: the student's own uploaded documents (STU-011) rendered as inert
    # plain text -- no download action existed anywhere, same class of gap already fixed
    # for STU-007's certificates and OVS-005's documents. STU-011-AC03 confirms Self-only
    # (no admin/staff secondary actor named), narrower than those two siblings.
    _require(user, {"it_student"}, "it")
    item = await db.get(ProfileDocument, document_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "Document not found")
    key = item.file_url[len("/local-files/"):] if item.file_url.startswith("/local-files/") else item.file_url.lstrip("/")
    return {"url": storage.presign_download(key), "expires_in": 900 if storage.bucket else None}


@router.post("/it/student/profile/documents", status_code=201)
async def upload_profile_document(payload: ProfileDocumentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # STU-011-AC02: the same upload-validation contract used at `/files/presign` --
    # re-checked here, at the record-creation step, so an invalid type/size is rejected
    # with a clear error regardless of how `file_url` was obtained, never silently stored.
    _require(user, {"it_student"}, "it")
    if not _allowed(payload.content_type):
        raise HTTPException(415, "This file type is not allowed")
    if payload.file_size > settings.max_upload_bytes:
        raise HTTPException(413, f"File size must not exceed {settings.max_upload_bytes} bytes")
    item = ProfileDocument(
        user_id=user.id,
        document_type=payload.document_type,
        file_url=payload.file_url,
        original_filename=payload.original_filename,
        content_type=payload.content_type,
        file_size=payload.file_size,
    )
    db.add(item)
    await db.flush()
    await _audit(db, user, "profile.document_upload", "profile_document", item.id, {"document_type": payload.document_type})
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "document_type": item.document_type, "file_url": item.file_url}


def _reply_payload(reply: QuestionReply) -> dict:
    return {"id": reply.id, "author_id": reply.author_id, "body": reply.body, "created_at": reply.created_at}


@router.post("/it/student/questions", status_code=201)
async def raise_question(payload: QuestionThreadCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # TRN-009: a question can only be raised against a batch the student actually holds
    # an Enrollment for -- same "422, not a silent drop" pattern as STU-008's feedback.
    _require(user, {"it_student"}, "it")
    enrolled = await db.scalar(select(Enrollment).where(Enrollment.student_id == user.id, Enrollment.batch_id == payload.batch_id))
    if not enrolled:
        raise HTTPException(422, "You are not enrolled in this batch")
    item = QuestionThread(student_id=user.id, batch_id=payload.batch_id, subject=payload.subject, body=payload.body)
    db.add(item)
    await db.flush()
    await _audit(db, user, "question.raise", "question_thread", item.id, {"batch_id": str(payload.batch_id)})
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "subject": item.subject, "body": item.body}


@router.get("/it/student/questions")
async def list_student_questions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    threads = (await db.scalars(select(QuestionThread).where(QuestionThread.student_id == user.id).order_by(QuestionThread.created_at.desc()))).all()
    thread_ids = [t.id for t in threads]
    replies_by_thread: dict[UUID, list[QuestionReply]] = {t.id: [] for t in threads}
    if thread_ids:
        replies = (await db.scalars(select(QuestionReply).where(QuestionReply.thread_id.in_(thread_ids)).order_by(QuestionReply.created_at))).all()
        for reply in replies:
            replies_by_thread[reply.thread_id].append(reply)
    return [{"id": t.id, "batch_id": t.batch_id, "subject": t.subject, "body": t.body, "replies": [_reply_payload(r) for r in replies_by_thread[t.id]]} for t in threads]


@router.get("/it/trainer/questions")
async def list_trainer_questions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    stmt = select(QuestionThread, User, Batch).join(User, User.id == QuestionThread.student_id).join(Batch, Batch.id == QuestionThread.batch_id)
    if user.role == "trainer":
        stmt = stmt.where(Batch.trainer_id == user.id)
    threads = (await db.execute(stmt.order_by(QuestionThread.created_at.desc()))).all()
    thread_ids = [t.id for t, _, _ in threads]
    replies_by_thread: dict[UUID, list[QuestionReply]] = {t.id: [] for t, _, _ in threads}
    if thread_ids:
        replies = (await db.scalars(select(QuestionReply).where(QuestionReply.thread_id.in_(thread_ids)).order_by(QuestionReply.created_at))).all()
        for reply in replies:
            replies_by_thread[reply.thread_id].append(reply)
    return [
        {"id": t.id, "student": s.full_name, "batch": b.name, "subject": t.subject, "body": t.body, "replies": [_reply_payload(r) for r in replies_by_thread[t.id]]}
        for t, s, b in threads
    ]


@router.post("/it/trainer/questions/{thread_id}/replies", status_code=201)
async def reply_to_question(thread_id: UUID, payload: QuestionReplyCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # TRN-009-AC02: only the Trainer assigned to the thread's own batch may reply,
    # checked server-side against `Batch.trainer_id` -- never left to the UI to hide.
    _require(user, {"trainer", "it_admin"}, "it")
    thread = await db.get(QuestionThread, thread_id)
    if not thread:
        raise HTTPException(404, "Question thread not found")
    batch = await db.get(Batch, thread.batch_id)
    if user.role == "trainer" and (not batch or batch.trainer_id != user.id):
        raise HTTPException(403, "Question is outside your assigned batch")
    reply = QuestionReply(thread_id=thread.id, author_id=user.id, body=payload.body)
    db.add(reply)
    await db.flush()
    await _audit(db, user, "question.reply", "question_reply", reply.id, {"thread_id": str(thread.id)})
    student = await db.get(User, thread.student_id)
    await _notify_user(db, student, "Your question has a new reply", f'"{thread.subject}" was answered.', "/it/student/questions", ["email"])
    await db.commit()
    await db.refresh(reply)
    return _reply_payload(reply)


# ----------------------------- PLACEMENT / HR ------------------------------
@router.get("/it/jobs/open")
async def open_jobs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student", "placement_team", "hr_team", "it_admin"}, "it")
    # EMP-002-AC02: a posting past its own closing date is not shown as open, even if
    # the Employer never explicitly closed it -- `status` alone was previously trusted.
    rows = (
        await db.execute(
            select(Job, Company).join(Company).where(Job.status == "open", or_(Job.closes_on.is_(None), Job.closes_on >= date.today())).order_by(Job.created_at.desc())
        )
    ).all()
    return [
        {"id": job.id, "company": company.name, "title": job.title, "location": job.location, "description": job.description, "skills": job.skills, "closes_on": job.closes_on} for job, company in rows
    ]


@router.get("/it/jobs")
async def all_jobs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # ADM-008: HR Team's own "manages hiring requirements and shortlists" needs to pick
    # a requirement (any status, not just currently-open ones) to review its shortlist.
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    rows = (await db.execute(select(Job, Company).join(Company).order_by(Job.created_at.desc()))).all()
    return [{"id": job.id, "company": company.name, "title": job.title, "status": job.status} for job, company in rows]


@router.get("/it/jobs/{job_id}/shortlist")
async def job_shortlist(job_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # ADM-008-AC02: a requirement with no matching/shortlisted candidates returns a
    # clean empty list, never an error -- the outer join below never raises just
    # because zero `JobApplication` rows exist for this job.
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job requirement not found")
    rows = (
        await db.execute(
            select(JobApplication, User).join(User, User.id == JobApplication.student_id).where(JobApplication.job_id == job_id).order_by(JobApplication.created_at.desc())
        )
    ).all()
    return [{"id": a.id, "student": s.full_name, "email": s.email, "status": a.status, "resume_url": a.resume_url} for a, s in rows]


@router.get("/it/placement/candidates")
async def placement_candidates(q: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    stmt = select(User).where(User.division == "it", User.role == "it_student", User.active.is_(True))
    if q:
        stmt = stmt.where(User.full_name.ilike(f"%{q}%"))
    students = (await db.scalars(stmt.limit(250))).all()
    return [
        {
            "id": s.id,
            "name": s.full_name,
            "email": s.email,
            "skills": s.profile.get("skills", []),
            "placement_status": s.profile.get("placement_status", "Available"),
            "resume_url": s.profile.get("resume_url"),
        }
        for s in students
    ]


@router.post("/it/jobs", status_code=201)
async def create_job(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    company_id = payload.get("company_id")
    if not company_id and payload.get("company_name"):
        company = await db.scalar(select(Company).where(Company.name == payload["company_name"]))
        if not company:
            company = Company(name=payload["company_name"], website=payload.get("company_website"), partner_type="recruiter")
            db.add(company)
            await db.flush()
        company_id = company.id
    if not company_id:
        raise HTTPException(422, "A company reference or company name is required")
    job = Job(
        company_id=uuid_reference(company_id, "company reference"),
        title=payload["title"],
        location=payload.get("location", "Remote"),
        description=payload.get("description", ""),
        skills=payload.get("skills", []),
        status="open",
        closes_on=date.fromisoformat(payload["closes_on"]) if payload.get("closes_on") else None,
    )
    db.add(job)
    await db.flush()
    await _audit(db, user, "job.create", "job", job.id)
    await db.commit()
    await db.refresh(job)
    return {"id": job.id, "status": job.status}


@router.post("/it/jobs/{job_id}/apply", status_code=201)
async def apply_job(job_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    job = await db.get(Job, job_id)
    # EMP-002-AC02: a posting past its own closing date is not open, even if the
    # Employer never explicitly closed it -- applies here too, not just to the listing.
    if not job or job.status != "open" or (job.closes_on and job.closes_on < date.today()):
        raise HTTPException(404, "Open job not found")
    existing = await db.scalar(select(JobApplication).where(JobApplication.job_id == job_id, JobApplication.student_id == user.id))
    if existing:
        raise HTTPException(409, "Already applied")
    item = JobApplication(job_id=job_id, student_id=user.id, status="applied", resume_url=payload.get("resume_url") or user.profile.get("resume_url"))
    db.add(item)
    await db.flush()
    await _audit(db, user, "job.apply", "job_application", item.id, {"job_id": job_id})
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.patch("/it/jobs/{job_id}")
async def update_job(job_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    for key in {"title", "location", "description", "skills", "status"}:
        if key in payload:
            setattr(job, key, payload[key])
    if "closes_on" in payload:
        job.closes_on = date.fromisoformat(payload["closes_on"]) if payload["closes_on"] else None
    await _audit(db, user, "job.update", "job", job.id, payload)
    await db.commit()
    return {"id": job.id, "status": job.status}


@router.patch("/it/job-applications/{application_id}")
async def update_job_application(application_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    item = await db.get(JobApplication, application_id)
    if not item:
        raise HTTPException(404, "Job application not found")
    status = payload.get("status")
    if status not in {"applied", "screening", "shortlisted", "interview_scheduled", "rejected", "offer_received", "hired", "withdrawn"}:
        raise HTTPException(422, "Invalid application status")
    item.status = status
    student = await db.get(User, item.student_id)
    if student:
        await _notify_user(db, student, "Job application updated", f"Your application status is now {status.replace('_', ' ')}.", "/it/student/job-applications")
    await _audit(db, user, "job_application.update", "job_application", item.id, {"status": status})
    await db.commit()
    return {"id": item.id, "status": item.status}


@router.post("/it/interviews", status_code=201)
async def schedule_interview(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    application = await db.get(JobApplication, uuid_reference(payload.get("application_id"), "job application reference"))
    if not application:
        raise HTTPException(404, "Application not found")
    item = Interview(application_id=application.id, scheduled_at=datetime.fromisoformat(payload["scheduled_at"]), mode=payload.get("mode", "Online"), meeting_url=payload.get("meeting_url"))
    application.status = "interview_scheduled"
    db.add(item)
    await db.flush()
    await _audit(db, user, "interview.schedule", "interview", item.id)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "scheduled_at": item.scheduled_at}


@router.patch("/it/interviews/{interview_id}")
async def update_interview(interview_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    item = await db.get(Interview, interview_id)
    if not item:
        raise HTTPException(404, "Interview not found")
    for key in {"mode", "meeting_url", "result"}:
        if key in payload:
            setattr(item, key, payload[key])
    if payload.get("scheduled_at"):
        item.scheduled_at = datetime.fromisoformat(payload["scheduled_at"])
    application = await db.get(JobApplication, item.application_id)
    if application and item.result in {"selected", "rejected"}:
        application.status = "shortlisted" if item.result == "selected" else "rejected"
    await _audit(db, user, "interview.update", "interview", item.id, payload)
    await db.commit()
    return {"id": item.id, "result": item.result}


@router.get("/it/placement/profiles")
async def placement_profiles(include_withdrawn: bool = False, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    stmt = select(User, PlacementProfile).outerjoin(PlacementProfile, PlacementProfile.student_id == User.id).where(User.division == "it", User.role == "it_student", User.active.is_(True))
    # ADM-007-AC02: withdrawn candidates are excluded from the active pool by default --
    # this is "active matching" -- but never truly hidden; `include_withdrawn=true`
    # still surfaces them (their own JobApplication/Interview/JobOffer history was
    # never touched by withdrawal in the first place, since none of those reference
    # this table).
    if not include_withdrawn:
        stmt = stmt.where(or_(PlacementProfile.id.is_(None), PlacementProfile.withdrawn.is_(False)))
    rows = (await db.execute(stmt.order_by(User.full_name))).all()
    return [
        {
            "student_id": student.id,
            "student": student.full_name,
            "email": student.email,
            "skills": student.profile.get("skills", []),
            "readiness_status": profile.readiness_status if profile else "preparation",
            "resume_status": profile.resume_status if profile else "pending",
            "mock_interview_status": profile.mock_interview_status if profile else "pending",
            "aptitude_status": profile.aptitude_status if profile else "pending",
            "available": profile.available if profile else False,
            "withdrawn": profile.withdrawn if profile else False,
            "notes": profile.notes if profile else None,
        }
        for student, profile in rows
    ]


@router.put("/it/placement/profiles/{student_id}")
async def update_placement_profile(student_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "it_admin"}, "it")
    student = await db.get(User, student_id)
    if not student or student.role != "it_student" or student.division != "it":
        raise HTTPException(404, "IT student not found")
    item = await db.scalar(select(PlacementProfile).where(PlacementProfile.student_id == student_id))
    if not item:
        item = PlacementProfile(student_id=student_id)
        db.add(item)
    allowed = {"readiness_status", "resume_status", "mock_interview_status", "aptitude_status", "available", "notes", "withdrawn"}
    for key, value in payload.items():
        if key in allowed:
            setattr(item, key, value)
    await db.flush()
    await _audit(db, user, "placement.profile_update", "placement_profile", item.id, {"student_id": student_id, "withdrawn": item.withdrawn})
    await _notify_user(db, student, "Placement status updated", f"Your placement readiness status is {item.readiness_status}.", "/it/student/placement-status")
    await db.commit()
    return {"id": item.id, "readiness_status": item.readiness_status, "available": item.available, "withdrawn": item.withdrawn}


@router.post("/it/offers", status_code=201)
async def create_job_offer(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    application = await db.get(JobApplication, uuid_reference(payload.get("application_id"), "job application reference"))
    if not application:
        raise HTTPException(404, "Job application not found")
    existing = await db.scalar(select(JobOffer).where(JobOffer.application_id == application.id))
    if existing:
        raise HTTPException(409, "An offer already exists for this application")
    joining = date.fromisoformat(payload["joining_date"]) if payload.get("joining_date") else None
    item = JobOffer(
        application_id=application.id,
        compensation=payload.get("compensation"),
        currency=payload.get("currency", "INR"),
        status=payload.get("status", "offered"),
        joining_date=joining,
        letter_url=payload.get("letter_url"),
    )
    application.status = "offer_received"
    db.add(item)
    await db.flush()
    student = await db.get(User, application.student_id)
    if student:
        await _notify_user(db, student, "Job offer received", "A job offer has been recorded in your placement portal.", "/it/student/placement-status")
    await _audit(db, user, "placement.offer_create", "job_offer", item.id)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.patch("/it/offers/{offer_id}")
async def update_job_offer(offer_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    item = await db.get(JobOffer, offer_id)
    if not item:
        raise HTTPException(404, "Offer not found")
    for key in {"compensation", "currency", "status", "letter_url"}:
        if key in payload:
            setattr(item, key, payload[key])
    if "joining_date" in payload:
        item.joining_date = date.fromisoformat(payload["joining_date"]) if payload["joining_date"] else None
    application = await db.get(JobApplication, item.application_id)
    if application and item.status in {"accepted", "joined"}:
        application.status = "hired"
    await _audit(db, user, "placement.offer_update", "job_offer", item.id, payload)
    await db.commit()
    return {"id": item.id, "status": item.status}


# --------------------------- OVERSEAS EDUCATION ----------------------------
# DATA_MODEL.md #6.2: the confirmed base sequence (DEC-WF-001), fixed by this contract.
# Exception-path values (rejected/waitlisted/deferred) are deliberately NOT included --
# DEC-WF-001 leaves those open (PRD_OPEN_ITEMS.md), so a status outside this list is
# rejected rather than guessed (OVS-003-AC02).
OVERSEAS_APPLICATION_STAGES = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"]


async def _maybe_trigger_agent_commission(db: AsyncSession, application: OverseasApplication, old_status: str, changed_by: User) -> None:
    """AGT-003 / `DATA_MODEL.md` #6.3 (`ADR-012`): the automatic commission-accrual
    trigger fires when an `ApplicationStatusHistory` row is written with
    `to_status='enrolled'` for an application that has an assigned `agent_id` --
    verified through this audit-trail write, not a raw status-field edit, per the
    resolved trigger mapping. No fixed commission rate is confirmed (`DEC-SCOPE-005`),
    so the amount starts at 0 in `estimated` status until an Overseas Admin sets it
    (`AGT-003-AC02`, the `PATCH .../commissions/{id}` endpoint below). Called from both
    write sites that can reach `enrolled` (`update_overseas_application`,
    `advance_overseas_application`) -- the trigger is about the status transition
    itself, not which endpoint performed it.
    """

    if application.status != "enrolled" or old_status == "enrolled" or not application.agent_id:
        return
    existing = await db.scalar(select(AgentCommission.id).where(AgentCommission.application_id == application.id))
    if existing:
        return
    item = AgentCommission(agent_id=application.agent_id, application_id=application.id, amount=0, currency="INR", status="estimated", created_by="system_trigger")
    db.add(item)
    await db.flush()
    agent = await db.get(User, application.agent_id)
    if agent:
        await _notify_user(db, agent, "Commission estimated", "A referred student has enrolled -- a commission is now estimated and awaiting an amount from Overseas Admin.", "/overseas/agent/commissions")
    await _audit(db, changed_by, "agent.commission_auto_create", "agent_commission", item.id, {"application_id": str(application.id), "trigger": "enrolled"})


@router.post("/overseas/applications", status_code=201)
async def create_overseas_application(payload: OverseasApplicationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"overseas_student", "counselor", "overseas_admin", "agent"}, "overseas")
    student_id = user.id if user.role == "overseas_student" else payload.student_id
    student = await db.get(User, student_id)
    if not student or student.role != "overseas_student" or student.division != "overseas":
        raise HTTPException(422, "Valid overseas student is required")
    if user.role == "agent":
        linked = await db.scalar(select(AgentStudent.id).where(AgentStudent.agent_id == user.id, AgentStudent.student_id == student_id, AgentStudent.status == "active"))
        if not linked:
            raise HTTPException(403, "Student is not assigned to this agent")
    university = await db.get(University, payload.university_id)
    if not university:
        raise HTTPException(404, "University not found")
    course_id = payload.course_id
    if course_id:
        course = await db.get(OverseasCourse, course_id)
        if not course or course.university_id != university.id:
            raise HTTPException(422, "Course does not belong to selected university")
    # OVS-002-AC02 / DATA_MODEL.md #6.2: submitting interest twice for the same
    # (student, university, course) must not create a duplicate row -- a withdrawn
    # application is explicitly excluded from this check (re-application is allowed),
    # though nothing sets status="withdrawn" yet since no feature owns that action.
    duplicate = await db.scalar(
        select(OverseasApplication.id).where(
            OverseasApplication.student_id == student_id,
            OverseasApplication.university_id == university.id,
            OverseasApplication.course_id == course_id,
            OverseasApplication.status != "withdrawn",
        )
    )
    if duplicate:
        raise HTTPException(409, "An application for this university/course already exists")
    counselor_id = payload.counselor_id or (user.id if user.role == "counselor" else None)
    agent_id = user.id if user.role == "agent" else payload.agent_id
    item = OverseasApplication(
        student_id=student_id,
        university_id=university.id,
        course_id=course_id,
        counselor_id=counselor_id,
        agent_id=agent_id,
        intake=payload.intake,
        # DATA_MODEL.md #6.2: contract-fixed enum sequence starts at "enquiry" -- the
        # base codebase's own free-text "profile_evaluation" predates this contract.
        status="enquiry",
        application_reference=payload.application_reference,
        next_action=payload.next_action or "Complete profile and required document checklist",
    )
    db.add(item)
    await db.flush()
    db.add(ApplicationStatusHistory(application_id=item.id, from_status=None, to_status=item.status, next_action=item.next_action, changed_by_id=user.id))
    await _audit(db, user, "overseas.application.create", "overseas_application", item.id)
    await _notify_user(db, student, "Application created", f"Your application to {university.name} has been created.", "/overseas/student/applications")
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.post("/overseas/student/counselor-chat", status_code=201)
async def send_counselor_message(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # RAID.md I-19: `ROLE_ACTION_MATRIX.md`'s own confirmed base action for this role is
    # "counselor-chat (direct messaging with their assigned counselor)" -- the Student
    # side only ever had a read-only history view, never a way to actually send. The
    # counselor is resolved here, server-side, from the student's own application(s)
    # rather than trusting a client-supplied recipient id (same "no manual reference
    # typing" precedent as every other feature in this file).
    _require(user, {"overseas_student"}, "overseas")
    body = str(payload.get("body") or "").strip()
    if not body:
        raise HTTPException(422, "Message body is required")
    counselor_id = await db.scalar(
        select(OverseasApplication.counselor_id)
        .where(OverseasApplication.student_id == user.id, OverseasApplication.counselor_id.is_not(None))
        .order_by(OverseasApplication.updated_at.desc())
    )
    if not counselor_id:
        raise HTTPException(409, "No counselor is assigned to your case yet")
    counselor = await db.get(User, counselor_id)
    item = Message(division="overseas", sender_id=user.id, recipient_id=counselor_id, context_type="counselor_chat", body=body)
    db.add(item)
    await db.flush()
    await _audit(db, user, "message.send", "message", item.id, {"recipient_id": counselor_id})
    if counselor:
        await _notify_user(db, counselor, f"Message from {user.full_name}", body[:240], "/overseas/counselor/counselor-chat")
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "created_at": item.created_at}


@router.get("/overseas/applications")
async def list_overseas_applications(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"overseas_student", "counselor", "overseas_admin", "university_rep", "agent"}, "overseas")
    stmt = select(OverseasApplication, University, User).join(University).join(User, User.id == OverseasApplication.student_id)
    if user.role == "overseas_student":
        stmt = stmt.where(OverseasApplication.student_id == user.id)
    elif user.role == "counselor":
        stmt = stmt.where(OverseasApplication.counselor_id == user.id)
    elif user.role == "agent":
        stmt = stmt.where(OverseasApplication.agent_id == user.id)
    elif user.role == "university_rep":
        stmt = stmt.where(OverseasApplication.university_id == uuid_reference(user.profile.get("university_id"), "university reference", required=False))
    rows = (await db.execute(stmt.order_by(OverseasApplication.updated_at.desc()).limit(500))).all()
    return [
        {
            "id": a.id,
            "student_id": student.id,
            "student": student.full_name,
            "university_id": u.id,
            "university": u.name,
            "course_id": a.course_id,
            "intake": a.intake,
            "status": a.status,
            "next_action": a.next_action,
            "application_reference": a.application_reference,
            "offer_letter_url": a.offer_letter_url,
            "counselor_id": a.counselor_id,
            "agent_id": a.agent_id,
        }
        for a, u, student in rows
    ]


@router.patch("/overseas/applications/{application_id}")
async def update_overseas_application(application_id: UUID, payload: OverseasApplicationUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"counselor", "university_rep", "overseas_admin"}, "overseas")
    item = await _assigned_application(db, user, application_id)
    changes = payload.model_dump(exclude_unset=True)
    channels = changes.pop("notify_channels", ["email"])
    notes = changes.pop("notes", None)
    if user.role == "university_rep":
        allowed = {"status", "application_reference", "offer_letter_url", "next_action"}
        if set(changes) - allowed:
            raise HTTPException(403, "University representatives cannot change assignments or intake ownership")
    # OVS-003-AC02: exception-path values (rejected/waitlisted/deferred) are an open
    # item, not silently accepted through this generic path either -- the dedicated,
    # forward-only `/advance` endpoint below is the confirmed way to change stage.
    if "status" in changes and changes["status"] not in OVERSEAS_APPLICATION_STAGES:
        raise HTTPException(422, f"'{changes['status']}' is not a supported application stage yet -- rejection/waitlist/deferral outcomes are an open item (see docs/product/PRD_OPEN_ITEMS.md), not a status this endpoint can set.")
    old_status = item.status
    old_next_action = item.next_action
    allowed = {"counselor_id", "intake", "status", "application_reference", "offer_letter_url"}
    allowed.add("next_action")
    for k, v in changes.items():
        if k in allowed:
            setattr(item, k, v)
    if item.status != old_status or item.next_action != old_next_action:
        db.add(ApplicationStatusHistory(application_id=item.id, from_status=old_status, to_status=item.status, next_action=item.next_action, notes=notes, changed_by_id=user.id))
    if item.status != old_status:
        await _maybe_trigger_agent_commission(db, item, old_status, user)
    student = await db.get(User, item.student_id)
    safe_channels = [channel for channel in channels if channel in {"email", "sms", "whatsapp"}]
    if student and (item.status != old_status or "next_action" in changes):
        await _notify_user(
            db, student, "Application status updated", f"Status: {item.status}. Next action: {item.next_action or 'No action required'}.", "/overseas/student/applications", safe_channels or ["email"]
        )
    await _audit(db, user, "overseas.application.update", "overseas_application", item.id, changes)
    await db.commit()
    return {"id": item.id, "status": item.status, "next_action": item.next_action}


@router.post("/overseas/university-rep/applications/{application_id}/updates", status_code=201)
async def post_university_rep_update(application_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # UNI-001: net-new -- `API_CONTRACT.md` §9 names this endpoint explicitly ("Posts an
    # admission update, visible to the assigned Counselor and Student") but it never
    # existed anywhere in the codebase; the generic PATCH above only lets a Rep edit the
    # application's own fields, with no distinct communication action. Scoped via the
    # same `_assigned_application` own-institution check already used everywhere else for
    # this role -- a Rep cannot message about an application outside their institution
    # even via a direct application ID (UNI-001-AC02).
    _require(user, {"university_rep"}, "overseas")
    item = await _assigned_application(db, user, application_id)
    message = str(payload.get("message", "")).strip()
    if not message:
        raise HTTPException(422, "message is required")
    university = await db.get(University, item.university_id)
    student = await db.get(User, item.student_id)
    recipients = [student] + ([await db.get(User, item.counselor_id)] if item.counselor_id else [])
    for recipient in recipients:
        if recipient:
            await _notify_user(db, recipient, f"Update from {university.name if university else 'the university'}", message, "/overseas/student/applications" if recipient.id == item.student_id else "/overseas/counselor/applications")
    await _audit(db, user, "university_rep.application_update", "overseas_application", item.id, {"message": message[:200]})
    await db.commit()
    return {"application_id": item.id, "notified": len([r for r in recipients if r])}


@router.post("/overseas/applications/{application_id}/advance")
async def advance_overseas_application(application_id: UUID, payload: OverseasApplicationAdvance, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # OVS-003: Counselor reviews and advances the application stage -- RBAC/resource
    # scope is "Counselor (assigned students)" specifically, not Admin/University Rep
    # (they retain the generic PATCH above for their own broader corrections).
    _require(user, {"counselor"}, "overseas")
    item = await _assigned_application(db, user, application_id)
    if payload.to_status not in OVERSEAS_APPLICATION_STAGES:
        raise HTTPException(422, f"'{payload.to_status}' is not a supported application stage yet -- rejection/waitlist/deferral outcomes are an open item (see docs/product/PRD_OPEN_ITEMS.md), not a status this endpoint can set.")
    current_index = OVERSEAS_APPLICATION_STAGES.index(item.status) if item.status in OVERSEAS_APPLICATION_STAGES else -1
    target_index = OVERSEAS_APPLICATION_STAGES.index(payload.to_status)
    if target_index <= current_index:
        raise HTTPException(422, f"Cannot advance from '{item.status}' to '{payload.to_status}' -- must move forward along the confirmed sequence.")
    old_status = item.status
    item.status = payload.to_status
    if payload.next_action is not None:
        item.next_action = payload.next_action
    db.add(ApplicationStatusHistory(application_id=item.id, from_status=old_status, to_status=item.status, next_action=item.next_action, notes=payload.notes, changed_by_id=user.id))
    await _maybe_trigger_agent_commission(db, item, old_status, user)
    student = await db.get(User, item.student_id)
    safe_channels = [channel for channel in payload.notify_channels if channel in {"email", "sms", "whatsapp"}]
    if student:
        # OVS-004-AC02 (this feature's own concern, not OVS-003's): a notification
        # send failure must never block or roll back this status-history write --
        # `_notify_user` already persists its own outcome independently below.
        await _notify_user(
            db, student, "Application status updated", f"Status: {item.status}. Next action: {item.next_action or 'No action required'}.", "/overseas/student/applications", safe_channels or ["email"]
        )
    await _audit(db, user, "overseas.application.advance", "overseas_application", item.id, {"from_status": old_status, "to_status": item.status})
    await db.commit()
    return {"id": item.id, "status": item.status, "next_action": item.next_action}


@router.get("/overseas/applications/{application_id}/status")
async def get_application_status(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # OVS-004: "Stage change triggers a notification and updates the Student's tracking
    # view." The notification side is already wired into every status-changing endpoint
    # above (`advance_overseas_application`, `update_overseas_application`); this is the
    # dedicated tracking-view read `API_CONTRACT.md` #7 names, distinct from the
    # checklist/status-summary endpoints VISA-001/003 already added -- a real history
    # timeline, not just the current status a student could already see in their
    # applications list.
    _require(user, {"overseas_student", "counselor", "overseas_admin"}, "overseas")
    application = await _assigned_application(db, user, application_id)
    history = (await db.scalars(select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == application_id).order_by(ApplicationStatusHistory.created_at))).all()
    return {
        "status": application.status,
        "next_action": application.next_action,
        "history": [{"from_status": h.from_status, "to_status": h.to_status, "next_action": h.next_action, "changed_at": h.created_at} for h in history],
    }


@router.post("/overseas/documents", status_code=201)
async def add_document(payload: StudentDocumentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"overseas_student", "counselor", "overseas_admin", "agent"}, "overseas")
    student_id = user.id if user.role == "overseas_student" else payload.student_id
    student = await db.get(User, student_id)
    if not student or student.role != "overseas_student":
        raise HTTPException(422, "Valid overseas student is required")
    if payload.application_id:
        application = await _assigned_application(db, user, payload.application_id)
        if application.student_id != student_id:
            raise HTTPException(422, "Document student does not match the application")
    elif user.role in {"counselor", "agent"}:
        if user.role == "counselor":
            linked = await db.scalar(select(OverseasApplication.id).where(OverseasApplication.student_id == student_id, OverseasApplication.counselor_id == user.id))
        else:
            linked = await db.scalar(select(AgentStudent.id).where(AgentStudent.student_id == student_id, AgentStudent.agent_id == user.id))
        if not linked:
            raise HTTPException(403, "Student is outside your assigned scope")
    item = StudentDocument(
        student_id=student_id,
        application_id=payload.application_id,
        document_type=payload.document_type,
        file_url=payload.file_url,
        verification_status="pending",
        original_filename=payload.original_filename,
        content_type=payload.content_type,
        file_size=payload.file_size,
    )
    db.add(item)
    await db.flush()
    await _audit(db, user, "document.upload", "student_document", item.id)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "verification_status": item.verification_status}


@router.patch("/overseas/documents/{document_id}/verify")
async def verify_document(document_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    item = await db.get(StudentDocument, document_id)
    if not item:
        raise HTTPException(404, "Document not found")
    if item.application_id:
        await _assigned_application(db, user, item.application_id)
    elif user.role == "counselor":
        assigned = await db.scalar(select(OverseasApplication.id).where(OverseasApplication.student_id == item.student_id, OverseasApplication.counselor_id == user.id))
        if not assigned:
            raise HTTPException(403, "Document is outside your assigned scope")
    item.verification_status = payload.get("verification_status", "verified")
    item.verified_by_id = user.id
    item.reviewer_notes = payload.get("notes")
    student = await db.get(User, item.student_id)
    if student:
        await _notify_user(db, student, "Document reviewed", f"{item.document_type}: {item.verification_status}.", "/overseas/student/documents")
    await _audit(db, user, "document.verify", "student_document", item.id, payload)
    await db.commit()
    return {"id": item.id, "verification_status": item.verification_status}


@router.get("/overseas/documents/{document_id}/download")
async def download_student_document(document_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # OVS-005 security note (OVS-DOC-02): passports/financial evidence require
    # least-privilege access -- a raw, permanently-public object link was exposed
    # directly through the student's own generic table (same class of gap already
    # fixed for STU-007's certificates). Only the owning student, an assigned
    # Counselor/Agent, or Admin can exchange a document id for a real download URL --
    # verified here, never left to the frontend to hide.
    _require(user, {"overseas_student", "counselor", "overseas_admin", "agent"}, "overseas")
    item = await db.get(StudentDocument, document_id)
    if not item:
        raise HTTPException(404, "Document not found")
    if user.role == "overseas_student" and item.student_id != user.id:
        raise HTTPException(403, "Document belongs to another student")
    elif user.role == "counselor":
        if item.application_id:
            await _assigned_application(db, user, item.application_id)
        else:
            assigned = await db.scalar(select(OverseasApplication.id).where(OverseasApplication.student_id == item.student_id, OverseasApplication.counselor_id == user.id))
            if not assigned:
                raise HTTPException(403, "Document is outside your assigned scope")
    elif user.role == "agent":
        assigned = await db.scalar(select(AgentStudent.id).where(AgentStudent.student_id == item.student_id, AgentStudent.agent_id == user.id))
        if not assigned:
            raise HTTPException(403, "Document is outside your assigned scope")
    # `file_url` is stored in two shapes depending on which upload path a client used
    # (local-upload returns an already browser-servable "/local-files/..." path; the
    # S3 presign path returns a bare object key) -- normalize to a bare key so this
    # always calls `presign_download` uniformly, never trusting either shape blindly.
    key = item.file_url[len("/local-files/"):] if item.file_url.startswith("/local-files/") else item.file_url.lstrip("/")
    return {"url": storage.presign_download(key), "expires_in": 900 if storage.bucket else None}


# DATA_MODEL.md #6.5, DEC-SCOPE-006: the four confirmed category names plus a terminal
# `decision` state. Exact decision outcomes (approved/refused) are not modeled as
# separate values -- no source confirms them.
VISA_CASE_STAGES = ["checklist", "documentation", "interview_prep", "tracking", "decision"]


async def _checklist_verification(db: AsyncSession, application_id: UUID, checklist: list[str]) -> dict[str, str]:
    docs = (await db.scalars(select(StudentDocument).where(StudentDocument.application_id == application_id))).all()
    latest_by_type = {d.document_type: d.verification_status for d in docs}
    return {item: latest_by_type.get(item, "not_uploaded") for item in checklist}


@router.get("/overseas/applications/{application_id}/visa-checklist")
async def get_visa_checklist(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # VISA-001-AC02: viewing the checklist is never blocked by an unverified document --
    # only *advancing* past the "checklist" stage is (enforced in `update_visa` below).
    _require(user, {"overseas_student", "counselor", "overseas_admin"}, "overseas")
    application = await _assigned_application(db, user, application_id)
    case = await db.scalar(select(VisaCase).where(VisaCase.application_id == application.id))
    if not case:
        # No visa case has been started yet -- an honest empty state, not an error or a
        # fabricated one (the case is created by a Counselor once the application is far
        # enough along; not every application has reached that point).
        return {"exists": False, "status": None, "checklist": [], "appointment_date": None, "tracking_reference": None}
    return {
        "exists": True,
        "id": case.id,
        "status": case.status,
        "appointment_date": case.appointment_date,
        "tracking_reference": case.tracking_reference,
        "checklist": [{"item": item, "verification_status": status} for item, status in (await _checklist_verification(db, application.id, case.checklist)).items()],
    }


@router.get("/overseas/visa/interview-prep")
async def get_interview_prep(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # VISA-002: Self only (no Counselor scope, unlike its visa-checklist/visa-status
    # siblings -- API_CONTRACT.md #7 names this endpoint distinctly). Not scoped to one
    # application id -- returns one entry per the student's own visa cases. The actual
    # prep content is a confirmed open item (DEC-DATA-001/DEC-SCOPE-006), so a country
    # with none yet returns an explicit fallback (`available: false`), never a 500
    # (VISA-002-AC02), and a student with no visa case at all gets an honest empty list.
    _require(user, {"overseas_student"}, "overseas")
    rows = (
        await db.execute(
            select(VisaCase, OverseasApplication, University, Country)
            .join(OverseasApplication, OverseasApplication.id == VisaCase.application_id)
            .join(University, University.id == OverseasApplication.university_id)
            .join(Country, Country.id == University.country_id)
            .where(OverseasApplication.student_id == user.id)
        )
    ).all()
    return [
        {
            "application_id": application.id,
            "university": university.name,
            "country": country.name,
            "available": bool(country.interview_prep),
            "content": country.interview_prep,
        }
        for case, application, university, country in rows
    ]


# VISA-003-AC02: a fixed compliance sentence, sourced from the reference
# implementation's own compliance language (DATA_MODEL.md #6.5) -- never invented, and
# never varied per case, so no response can ever imply EduSphere decides visa outcomes.
VISA_DECISION_DISCLAIMER = "Visa decisions are made by the relevant government or immigration authority. EduSphere does not decide visa outcomes."


@router.get("/overseas/applications/{application_id}/visa-status")
async def get_visa_status(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # VISA-003: "Status updates as the case progresses (checklist -> ... -> decision)."
    # Self(Student)/Counselor(assigned) scoped, same as the checklist endpoint above.
    _require(user, {"overseas_student", "counselor", "overseas_admin"}, "overseas")
    application = await _assigned_application(db, user, application_id)
    case = await db.scalar(select(VisaCase).where(VisaCase.application_id == application.id))
    if not case:
        return {"exists": False, "status": None, "appointment_date": None, "tracking_reference": None, "disclaimer": VISA_DECISION_DISCLAIMER}
    return {
        "exists": True,
        "status": case.status,
        "appointment_date": case.appointment_date,
        "tracking_reference": case.tracking_reference,
        "disclaimer": VISA_DECISION_DISCLAIMER,
    }


@router.patch("/overseas/visa/{visa_id}")
async def update_visa(visa_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    item = await db.get(VisaCase, visa_id)
    if not item:
        raise HTTPException(404, "Visa case not found")
    await _assigned_application(db, user, item.application_id)
    if "status" in payload:
        if payload["status"] not in VISA_CASE_STAGES:
            raise HTTPException(422, f"'{payload['status']}' is not a supported visa case stage -- must be one of {VISA_CASE_STAGES}.")
        # VISA-001-AC02: an unverified document never blocks *viewing* the checklist,
        # but does block *advancing past* the "checklist" stage that requires it.
        if item.status == "checklist" and payload["status"] != "checklist":
            verification = await _checklist_verification(db, item.application_id, item.checklist)
            unverified = [doc_type for doc_type, status in verification.items() if status != "verified"]
            if unverified:
                raise HTTPException(422, f"Cannot advance past the checklist stage -- not yet verified: {', '.join(unverified)}.")
    for k in ("status", "tracking_reference", "checklist"):
        if k in payload:
            setattr(item, k, payload[k])
    if payload.get("appointment_date"):
        item.appointment_date = date.fromisoformat(payload["appointment_date"])
    await _audit(db, user, "visa.update", "visa_case", item.id, payload)
    await db.commit()
    return {"id": item.id, "status": item.status}


@router.post("/overseas/visa", status_code=201)
async def create_visa_case(payload: VisaCaseCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    if payload.status not in VISA_CASE_STAGES:
        raise HTTPException(422, f"'{payload.status}' is not a supported visa case stage -- must be one of {VISA_CASE_STAGES}.")
    application = await _assigned_application(db, user, payload.application_id)
    existing = await db.scalar(select(VisaCase).where(VisaCase.application_id == application.id))
    if existing:
        raise HTTPException(409, "A visa case already exists for this application")
    item = VisaCase(application_id=application.id, status=payload.status, appointment_date=payload.appointment_date, checklist=payload.checklist, tracking_reference=payload.tracking_reference)
    db.add(item)
    await db.flush()
    await _audit(db, user, "visa.create", "visa_case", item.id)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.post("/overseas/appointments", status_code=201)
async def create_appointment(payload: AppointmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"overseas_student", "counselor", "overseas_admin"}, "overseas")
    student_id = user.id if user.role == "overseas_student" else payload.student_id
    student = await db.get(User, student_id)
    if not student or student.role != "overseas_student":
        raise HTTPException(422, "Valid overseas student is required")
    # CNS-001-AC02: a Counselor cannot act on a student who is not assigned to them,
    # even via a direct record ID -- the same assignment check `add_document` (OVS-005)
    # already has, previously missing here.
    if user.role == "counselor":
        assigned = await db.scalar(select(OverseasApplication.id).where(OverseasApplication.student_id == student_id, OverseasApplication.counselor_id == user.id))
        if not assigned:
            raise HTTPException(403, "Student is outside your assigned scope")
    staff_id = payload.staff_id or (user.id if user.role == "counselor" else None)
    if staff_id:
        staff = await db.get(User, staff_id)
        if not staff or staff.role not in {"counselor", "overseas_admin"} or staff.division != "overseas":
            raise HTTPException(422, "Valid overseas staff member is required")
    item = Appointment(
        division="overseas", student_id=student_id, staff_id=staff_id, scheduled_at=payload.scheduled_at, appointment_type=payload.appointment_type, mode=payload.mode, status="scheduled"
    )
    db.add(item)
    await db.flush()
    await _audit(db, user, "appointment.create", "appointment", item.id)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "scheduled_at": item.scheduled_at, "status": item.status}


@router.patch("/overseas/appointments/{appointment_id}")
async def update_appointment(appointment_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    item = await db.get(Appointment, appointment_id)
    if not item or item.division != "overseas":
        raise HTTPException(404, "Appointment not found")
    if user.role == "counselor" and item.staff_id != user.id:
        raise HTTPException(403, "Appointment is outside your assigned scope")
    for key in {"appointment_type", "mode", "status"}:
        if key in payload:
            setattr(item, key, payload[key])
    if payload.get("scheduled_at"):
        item.scheduled_at = datetime.fromisoformat(payload["scheduled_at"])
    await _audit(db, user, "appointment.update", "appointment", item.id, payload)
    await db.commit()
    return {"id": item.id, "status": item.status}


@router.post("/overseas/scholarships/{scholarship_id}/apply", status_code=201)
async def apply_scholarship(scholarship_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"overseas_student"}, "overseas")
    scholarship = await db.get(Scholarship, scholarship_id)
    if not scholarship or not scholarship.active:
        raise HTTPException(404, "Active scholarship not found")
    existing = await db.scalar(select(ScholarshipApplication).where(ScholarshipApplication.scholarship_id == scholarship_id, ScholarshipApplication.student_id == user.id))
    if existing:
        raise HTTPException(409, "Already applied")
    item = ScholarshipApplication(scholarship_id=scholarship_id, student_id=user.id, status="submitted")
    db.add(item)
    await db.flush()
    await _audit(db, user, "scholarship.apply", "scholarship_application", item.id)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


# ------------------------------- AGENT PORTAL ------------------------------
@router.get("/overseas/agent/students")
async def agent_students(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"agent"}, "overseas")
    rows = (await db.execute(select(AgentStudent, User).join(User, User.id == AgentStudent.student_id).where(AgentStudent.agent_id == user.id).order_by(User.full_name))).all()
    return [{"link_id": link.id, "student_id": student.id, "student": student.full_name, "email": student.email, "phone": student.phone, "status": link.status} for link, student in rows]


@router.post("/overseas/agent/students", status_code=201)
async def add_agent_student(payload: AgentStudentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"agent"}, "overseas")
    student = await db.get(User, payload.student_id)
    if not student or student.role != "overseas_student" or student.division != "overseas":
        raise HTTPException(404, "Overseas student not found")
    existing = await db.scalar(select(AgentStudent).where(AgentStudent.agent_id == user.id, AgentStudent.student_id == student.id))
    if existing:
        raise HTTPException(409, "Student is already linked to this agent")
    item = AgentStudent(agent_id=user.id, student_id=student.id, status="active")
    db.add(item)
    await db.flush()
    await _audit(db, user, "agent.student_link", "agent_student", item.id, {"student_id": student.id})
    await db.commit()
    return {"id": item.id, "status": item.status}


@router.get("/overseas/agent/commissions")
async def agent_commissions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"agent"}, "overseas")
    rows = (
        await db.execute(
            select(AgentCommission, OverseasApplication, University, User)
            .join(OverseasApplication)
            .join(University)
            .join(User, User.id == OverseasApplication.student_id)
            .where(AgentCommission.agent_id == user.id)
            .order_by(AgentCommission.created_at.desc())
        )
    ).all()
    return [
        {
            "id": commission.id,
            "application_id": application.id,
            "student": student.full_name,
            "university": university.name,
            "amount": float(commission.amount),
            "currency": commission.currency,
            "status": commission.status,
            "claim_reference": commission.claim_reference,
            "claimed_at": commission.claimed_at,
            "paid_at": commission.paid_at,
        }
        for commission, application, university, student in rows
    ]


@router.post("/overseas/agent/commissions/{commission_id}/claim")
async def claim_commission(commission_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"agent"}, "overseas")
    item = await db.get(AgentCommission, commission_id)
    if not item or item.agent_id != user.id:
        raise HTTPException(404, "Commission not found")
    if item.status not in {"eligible", "estimated"}:
        raise HTTPException(409, "Commission cannot be claimed in its current status")
    item.status = "claimed"
    item.claimed_at = datetime.now(UTC)
    item.claim_reference = f"CLM-{date.today():%Y%m%d}-{secrets.token_hex(3).upper()}"
    await _audit(db, user, "agent.commission_claim", "agent_commission", item.id)
    await db.commit()
    return {"id": item.id, "status": item.status, "claim_reference": item.claim_reference}


@router.post("/overseas/agent/commissions", status_code=201)
async def create_commission(payload: CommissionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"overseas_admin"}, "overseas")
    agent = await db.get(User, payload.agent_id)
    application = await db.get(OverseasApplication, payload.application_id)
    if not agent or agent.role != "agent" or not application or application.agent_id != agent.id:
        raise HTTPException(422, "Agent and application assignment do not match")
    # AGT-003-AC03: "no commission creatable before the trigger condition" governs this
    # base-codebase manual path too, not just the new automatic trigger -- otherwise an
    # Admin could freely create a commission for an application still at "enquiry",
    # bypassing the entire enrolled-stage gate this feature exists to establish.
    if application.status != "enrolled":
        raise HTTPException(409, "A commission cannot be created until the application has reached the 'enrolled' stage")
    existing = await db.scalar(select(AgentCommission).where(AgentCommission.application_id == application.id))
    if existing:
        raise HTTPException(409, "Commission already exists for this application")
    item = AgentCommission(agent_id=agent.id, application_id=application.id, amount=payload.amount, currency=payload.currency, status="eligible", created_by="admin_manual")
    db.add(item)
    await db.flush()
    await _notify_user(db, agent, "Commission eligible", f"A {payload.currency} {payload.amount:,.2f} commission is available to claim.", "/overseas/agent/commissions")
    await _audit(db, user, "agent.commission_create", "agent_commission", item.id)
    await db.commit()
    return {"id": item.id, "status": item.status}


@router.patch("/overseas/agent/commissions/{commission_id}")
async def update_commission_amount(commission_id: UUID, payload: CommissionAmountUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # AGT-003-AC02: Overseas Admin sets/adjusts the amount on a commission (typically a
    # system-triggered "estimated" row with amount=0, since no fixed rate is confirmed --
    # `DEC-SCOPE-005`) without breaking the main workflow's data integrity once an Agent
    # has already acted on it, so this is only permitted before a claim exists.
    _require(user, {"overseas_admin"}, "overseas")
    item = await db.get(AgentCommission, commission_id)
    if not item:
        raise HTTPException(404, "Commission not found")
    if item.status not in {"estimated", "eligible"}:
        raise HTTPException(409, "Commission amount can no longer be adjusted once claimed")
    item.amount = payload.amount
    if payload.currency:
        item.currency = payload.currency
    if item.status == "estimated":
        item.status = "eligible"
    await _audit(db, user, "agent.commission_amount_update", "agent_commission", item.id, {"amount": payload.amount, "currency": item.currency})
    await db.commit()
    return {"id": item.id, "status": item.status, "amount": float(item.amount), "currency": item.currency}


# -------------------------- NOTIFICATIONS / SUPPORT ------------------------
@router.get("/notifications")
async def notifications(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(100))).all()
    return [{"id": x.id, "title": x.title, "body": x.body, "read": x.read, "action_url": x.action_url, "created_at": x.created_at} for x in rows]


@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(Notification, notification_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    item.read = True
    await db.commit()
    return {"ok": True}


SUPPORT_STAFF_ROLES = {"trainer", "super_admin", "it_admin", "overseas_admin"}


@router.get("/support")
async def support_tickets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(SupportTicket)
    if user.role in SUPPORT_STAFF_ROLES:
        # STU-005-AC02: staff see every ticket in their division, including unassigned
        # ones -- an unassigned ticket must stay visible, never hidden from the queue.
        if user.role != "super_admin":
            stmt = stmt.where(SupportTicket.division == user.division)
    else:
        stmt = stmt.where(SupportTicket.user_id == user.id)
    rows = (await db.scalars(stmt.order_by(SupportTicket.created_at.desc()).limit(200))).all()
    return [
        {
            "id": x.id,
            "subject": x.subject,
            "description": x.description,
            "priority": x.priority,
            "status": x.status,
            "division": x.division,
            "assigned_to_user_id": x.assigned_to_user_id,
            "resolution_note": x.resolution_note,
            "created_at": x.created_at,
        }
        for x in rows
    ]


@router.post("/support", status_code=201)
async def create_support_ticket(payload: SupportTicketCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = SupportTicket(
        user_id=user.id, division=user.division if user.division != "global" else "it", subject=payload.subject, description=payload.description, priority=payload.priority, status="open"
    )
    db.add(item)
    await db.flush()
    await _audit(db, user, "support.create", "support_ticket", item.id)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.patch("/support/{ticket_id}")
async def update_support_ticket(ticket_id: UUID, payload: SupportTicketUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in SUPPORT_STAFF_ROLES:
        raise HTTPException(403, "Only staff can act on a support ticket")
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Support ticket not found")
    if user.role != "super_admin" and ticket.division != user.division:
        raise HTTPException(403, "Ticket is outside your division")
    # Auto-claim on first staff action -- never a client-supplied assignee (STU-005-AC02's
    # own "not silently lost" only means *visible*, not that anyone can reassign anyone).
    if ticket.assigned_to_user_id is None:
        ticket.assigned_to_user_id = user.id
    if payload.status is not None:
        ticket.status = payload.status
    if payload.resolution_note is not None:
        ticket.resolution_note = payload.resolution_note
    await _audit(db, user, "support.update", "support_ticket", ticket.id, {"status": ticket.status})
    student = await db.get(User, ticket.user_id)
    if student and payload.status == "resolved":
        await _notify_user(db, student, "Support ticket resolved", f'"{ticket.subject}" has been resolved.', "/it/student/support")
    await db.commit()
    await db.refresh(ticket)
    return {"id": ticket.id, "status": ticket.status, "assigned_to_user_id": ticket.assigned_to_user_id, "resolution_note": ticket.resolution_note}

import contextlib
import csv
import io
import logging
import re
import secrets
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app import application_fields
from app.api.deps import get_current_user, require_paid_feature, require_permission
from app.api.files import _allowed, serve_stored_file
from app.api.school_bulk import _safe_cell
from app.application_outcome import label as outcome_label
from app.application_sub_status import label as sub_status_label
from app.core.config import settings
from app.core.database import get_db
from app.core.identifiers import uuid_reference
from app.core.rbac import REVIEW_MASTER_ONLY, REVIEW_REASON_REQUIRED, VERIFY_REFUSED, agent_denial_reason, agent_may, is_agent_staff
from app.document_checklists import STATUS_LABELS as DOCUMENT_STATUS_LABELS
from app.document_checklists import review_refusal
from app.models import (
    JOB_OPEN_STATUSES,
    AgentCommission,
    AgentOrgMember,
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
    CertificateRequest,
    CertificateRule,
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
    SchoolStudent,
    StoredFile,
    StudentAccessRule,
    StudentDocument,
    Submission,
    SubmissionFile,
    SupportTicket,
    University,
    User,
    VisaCase,
)
from app.notifications.dispatch import queue_deliveries
from app.schemas import (
    AgentDocumentReview,
    AgentStudentCreate,
    ApplicationDetailsUpdate,
    ApplicationOutcomeReopen,
    ApplicationOutcomeSet,
    ApplicationSubStatusChange,
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
    AttendanceCorrectionReviewIn,
    CertificateBulkIssueIn,
    CertificateIssueIn,
    CertificateRecommendIn,
    CertificateRulesIn,
    CommissionAmountUpdate,
    CommissionCreate,
    CommissionReportOut,
    CounselorAgencyVisaUpdate,
    CourseFeedbackCreate,
    DocumentReview,
    EnrollmentCreate,
    EnrollmentProgressUpdate,
    LearningResourceCreate,
    LearningResourceUpdate,
    NotificationUnreadCount,
    OverseasApplicationAdvance,
    OverseasApplicationCounselorAssign,
    OverseasApplicationCreate,
    OverseasApplicationUpdate,
    ProfileDocumentCreate,
    QuestionReplyCreate,
    QuestionThreadCreate,
    StudentAccessRulesIn,
    StudentDocumentCreate,
    SubmissionGradeIn,
    SupportTicketCreate,
    SupportTicketUpdate,
    VisaCaseCreate,
    VisaLifecycleUpdate,
)
from app.services import agent_documents as document_files
from app.services import agent_notifications as agency_notices
from app.services import (
    application_checklists,
    applications,
    appointment_invites,
    counselor_students,
    course_skills,
    document_access,
    interviews,
    offers,
    permissions,
    student_access,
    student_archive,
    student_document_requests,
    visa_lifecycle,
)
from app.services import application_outcomes as outcomes
from app.services import application_sub_status as sub_statuses
from app.services import document_checklists as checklist_templates
from app.services import recruiter_requirements as requirements
from app.services.agent_applications import (
    ARCHIVED,
    COUNSELLOR_ASSIGNED,
    COUNSELLOR_CHANGED,
    DEFAULT_NEXT_ACTION,
    OFFER_STAGES_ON,
    OVERSEAS_APPLICATION_STAGES,
    open_clause,
    owned,
    stage_label,
    status_history,
    with_owner,
)
from app.services.agent_documents import add_event, in_scope
from app.services.agent_orgs import lock_org, notification_recipients, org_member_ids
from app.services.agent_students import application_scope, student_scope
from app.services.agent_visa import VISA_CASE_STAGES, VISA_DECIDED, VISA_DECISION_DISCLAIMER, VISA_ENROLLED, VISA_OFFER_NEEDED, ChecklistGateRefused, sync_from_stage, update_case
from app.services.bdm_appointments import db_now
from app.services.certificates import active_signatories, generate_certificate_pdf, require_signatories, signatory_snapshot
from app.services.storage import storage
from app.services.tabular import XLSX_TYPE, to_xlsx
from app.visa_status import DECISIONS as VISA_DECISIONS
from app.visa_status import FIRST_OF_STAGE as VISA_FIRST_OF_STAGE
from app.visa_status import label as visa_status_label

router = APIRouter(prefix="/workflows", tags=["workflows"])
# nehn-018 (DEC-SCOPE-304): an IT student below the feature's payment state gets 403 `payment_required`.
PAID_ASSESSMENTS = require_paid_feature("assessments")
PAID_ASSIGNMENTS = require_paid_feature("assignments")
PAID_ATTENDANCE = require_paid_feature("attendance")
PAID_FEEDBACK = require_paid_feature("feedback")
PAID_QUESTIONS = require_paid_feature("questions")
logger = logging.getLogger("app.workflows")
INDIA = ZoneInfo("Asia/Kolkata")  # ccrm-021 S2: a passport expiry is compared with the India date
DOCUMENT_REPLACED = "A newer version replaced this document -- open the current one"
COUNSELOR_REFUSED_ON_UPDATE = "Use Assign counselor to change the counselor"  # AGN-023 (DEC-SCOPE-090 H10)
APPLICATION_CLOSED = "This application is closed"
CHOOSE_ACTIVE_COUNSELOR = "Choose an active overseas counselor"
MASTER_ENROLLS = "Only the agency's Master confirms enrollment"  # AGN-023 (DEC-SCOPE-090 H4), DEC-SCOPE-054 E1
# ccrm-027 (DEC-SCOPE-262, E3): `enrolled` is reached only through a confirmation (PUT …/enrollment, or the agency's AGN-013 route).
CONFIRM_ENROLLMENT = "Enrolment is confirmed with the enrolment confirmation document, not by a stage change"


def _refuse_unconfirmed_enrollment(item: OverseasApplication, target: str | None) -> None:
    if target == "enrolled" and item.status != "enrolled":
        raise HTTPException(422, CONFIRM_ENROLLMENT)

AGENCY_VISA_STARTS_AT_CHECKLIST = "A visa case starts at the checklist stage"
AGENCY_RECORDS_VISA_DECISION = "The visa decision is recorded by the agency"
AGENCY_USE_ADVANCE = "Use Advance stage to move an agency application"  # AGN-023 (DEC-SCOPE-090 H4): the generic PATCH has no agency rules
OUTSIDE_SCOPE = "Application is outside your assigned scope"


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
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)


def _require_agent_master(user: User) -> None:
    """AGN-002 (DEC-SCOPE-040 S1): commissions are Master-only; an agency's staff are refused."""
    if is_agent_staff(user):
        raise HTTPException(403, "Only an agency Master can view commissions")


async def _audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id: UUID | str | None, metadata: dict | None = None, *, outcome: str = "recorded"):
    db.add(AuditLog(user_id=user.id, action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None, outcome=outcome, metadata_json=metadata or {}))


async def _notify_user(db: AsyncSession, recipient: User, title: str, body: str, action_url: str | None, channels: list[str] | None = None):
    """ENH-014: in-app row plus queued deliveries (email + the recipient's opted-in channels), sent after commit.
    `channels` can only narrow that set (admin sends); it never adds a channel the recipient did not opt in to."""
    item = Notification(user_id=recipient.id, title=title, body=body, read=False, action_url=action_url)
    db.add(item)
    await db.flush()
    await queue_deliveries(db, item, recipient, channels=channels)


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


async def _require_overseas_counselor(db: AsyncSession, counselor_id: UUID) -> None:
    """tel-017 (DEC-SCOPE-076): a counselor can be IT now, and an application's counselor receives the student's counselor-chat and
    the update notices -- so the one set on an overseas application must be an overseas counselor."""
    counselor = await db.get(User, counselor_id)
    if counselor is None or counselor.role != "counselor" or counselor.division != "overseas":
        raise HTTPException(422, "Choose an overseas counselor")


async def _assigned_application(db: AsyncSession, user: User, application_id: UUID) -> OverseasApplication:
    item = await db.get(OverseasApplication, application_id)
    if not item:
        raise HTTPException(404, "Application not found")
    if user.role == "super_admin":
        return item
    if user.division != "overseas":
        raise HTTPException(403, "Wrong EduSphere division")
    # AGN-001 (D1): an agent may act on any application referred by a member of its own organisation.
    # AGN-004 (G4): a staff member only their assigned students' applications.
    agent_in_scope = user.role == "agent" and bool(await db.scalar(select(OverseasApplication.id).where(OverseasApplication.id == item.id, *application_scope(user))))
    allowed = (
        user.role == "overseas_admin"
        or user.role == "overseas_student"
        and item.student_id == user.id
        or user.role == "counselor"
        and item.counselor_id == user.id
        or agent_in_scope
        or user.role == "university_rep"
        and uuid_reference(user.profile.get("university_id"), "university reference", required=False) == item.university_id
    )
    if not allowed:
        raise HTTPException(403, "Application is outside your assigned scope")
    return item


async def _require_bridged_visa_entitlement(db: AsyncSession, user: User, application: OverseasApplication, *, grandfathered_since: datetime | None = None) -> None:
    """ENH-022 (D9): a visa case on a School-bridged application consumes the school's Platinum `visa_support`. An ordinary
    Overseas application (no `school_student_id`) is untouched. Call after `_assigned_application`, before any write.
    ENH-023 D8: updating an existing visa case passes its `created_at`; opening a new case never does."""
    if application.school_student_id is None:
        return
    from app.api.schools import require_school_entitlement  # noqa: PLC0415 -- lazy, like admin.py's bridge import
    from app.models import SchoolStudent  # noqa: PLC0415

    student = await db.get(SchoolStudent, application.school_student_id)  # FK: always present for a bridged application
    await require_school_entitlement(db, user, student.school_id, "visa_support", grandfathered_since=grandfathered_since)


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
    # nehn-018 (DEC-SCOPE-304): a locked feature's list stays empty; the enrolments (course information) never are.
    access = await student_access.summary(db, user)
    locked = student_access.locked_features(access)
    if batch_ids:
        if "assignments" not in locked:
            assignments = (await db.scalars(select(Assignment).where(Assignment.batch_id.in_(batch_ids)).order_by(Assignment.due_date))).all()
            submissions = (await db.scalars(select(Submission).where(Submission.student_id == user.id))).all()
        if "resources" not in locked:
            resources = (await db.scalars(select(LearningResource).where(LearningResource.batch_id.in_(batch_ids), LearningResource.deleted_at.is_(None)).order_by(LearningResource.sort_order, LearningResource.created_at.desc()))).all()
        if "assessments" not in locked:
            assessments = (await db.scalars(select(Assessment).where(Assessment.batch_id.in_(batch_ids)).order_by(Assessment.scheduled_at))).all()
        if "live_classes" not in locked:
            live_sessions = (await db.scalars(select(LiveSession).where(LiveSession.batch_id.in_(batch_ids)).order_by(LiveSession.starts_at))).all()
    if "certificates" not in locked:
        certificates = (await db.scalars(select(Certificate).where(Certificate.student_id == user.id).order_by(Certificate.issued_on.desc()))).all()
    return {
        "access": access,
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
                "cancel_reason": s.cancel_reason,
            }
            for s in live_sessions
        ],
        "certificates": [
            {"id": c.id, "certificate_no": c.certificate_no, "verification_code": c.verification_code, "issued_on": c.issued_on, "file_url": c.file_url, "status": c.status} for c in certificates
        ],
        "resources": [{"id": r.id, "batch_id": r.batch_id, "title": r.title, "type": r.resource_type, "url": r.href} for r in resources],
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
async def submit_assignment(assignment_id: UUID, payload: AssignmentSubmissionIn, user: User = Depends(PAID_ASSIGNMENTS), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Assignment not found")
    enrolled = await db.scalar(select(Enrollment.id).where(Enrollment.student_id == user.id, Enrollment.batch_id == assignment.batch_id))
    if not enrolled:
        raise HTTPException(403, "You are not enrolled in this batch")
    if assignment.submission_type == "text" and not payload.answer:
        raise HTTPException(422, "A text answer is required")
    has_file = bool(payload.file_url or payload.file_ids)
    if assignment.submission_type == "file" and not has_file:
        raise HTTPException(422, "A file is required")
    if not payload.answer and not has_file:
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
    await db.flush()
    metadata = {"assignment_id": assignment_id, "is_late": is_late}
    if payload.file_ids is not None:
        file_ids = list(dict.fromkeys(payload.file_ids))  # a repeated id is attached once
        await _attach_submission_files(db, user, submission, file_ids)
        metadata["file_count"] = len(file_ids)
    await _audit(db, user, "assignment.submit", "submission", submission.id, metadata)
    try:
        await db.commit()
    except IntegrityError:  # a concurrent submit took the same row or file first
        await db.rollback()
        raise HTTPException(409, "This submission changed while saving. Please try again.") from None
    await db.refresh(submission)
    return {"id": submission.id, "status": submission.status, "is_late": submission.is_late}


async def _attach_submission_files(db: AsyncSession, user: User, submission: Submission, file_ids: list[UUID]) -> None:
    """nehn-024 (DEC-SCOPE-292 F4/F6): replace the submission's files. Each must be the caller's own `assignment_submission` upload, not
    attached to another submission -- one 422 for every failure, so nothing about other users' files is confirmed."""
    if file_ids:
        usable = await db.scalar(
            select(func.count(StoredFile.id))
            .outerjoin(SubmissionFile, SubmissionFile.stored_file_id == StoredFile.id)
            .where(
                StoredFile.id.in_(file_ids),
                StoredFile.owner_id == user.id,
                StoredFile.purpose == "assignment_submission",
                or_(SubmissionFile.id.is_(None), SubmissionFile.submission_id == submission.id),
            )
        )
        if usable != len(file_ids):
            raise HTTPException(422, "One or more files cannot be attached to this submission")
    await db.execute(delete(SubmissionFile).where(SubmissionFile.submission_id == submission.id))
    db.add_all(SubmissionFile(submission_id=submission.id, stored_file_id=file_id) for file_id in file_ids)


@router.get("/it/submissions/{submission_id}/files/{file_id}")
async def submission_file(submission_id: UUID, file_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-024 (DEC-SCOPE-292 F8): the submitting student, the batch's trainer, it_admin and super_admin download an attached file."""
    row = (
        await db.execute(
            select(Submission, Batch, StoredFile)
            .join(Assignment, Assignment.id == Submission.assignment_id)
            .join(Batch, Batch.id == Assignment.batch_id)
            .join(SubmissionFile, SubmissionFile.submission_id == Submission.id)
            .join(StoredFile, StoredFile.id == SubmissionFile.stored_file_id)
            .where(Submission.id == submission_id, StoredFile.id == file_id)
        )
    ).first()
    if not row:
        raise HTTPException(404, "File not found")
    submission, batch, stored = row
    if user.id != submission.student_id:
        _require(user, {"trainer", "it_admin"}, "it")
        if user.role == "trainer" and batch.trainer_id != user.id:
            raise HTTPException(403, "Submission is outside your assigned batch")
    await student_access.require(db, user, "assignments")  # nehn-018: after ownership, so another student's file is refused as before
    return serve_stored_file(stored)


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
    # nehn-029: a date whose live classes were all cancelled takes no attendance; a date with no live session is unaffected.
    zone = ZoneInfo(batch.timezone or "Asia/Kolkata")
    day_starts = datetime.combine(session_date, time.min, zone)
    day_statuses = set((await db.scalars(select(LiveSession.status).where(LiveSession.batch_id == batch_id, LiveSession.starts_at >= day_starts, LiveSession.starts_at < day_starts + timedelta(days=1)))).all())
    if day_statuses == {"cancelled"}:
        raise HTTPException(409, "The live class on this date was cancelled; attendance cannot be marked for it")
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
async def student_attendance(user: User = Depends(PAID_ATTENDANCE), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_student"}, "it")
    rows = (await db.execute(select(Attendance, Batch).join(Batch).where(Attendance.student_id == user.id).order_by(Attendance.session_date.desc()))).all()
    # nehn-023: the row says whether a request is already pending, so the UI offers "Request correction" only where it can succeed.
    pending = set((await db.scalars(select(AttendanceCorrection.attendance_id).where(AttendanceCorrection.student_id == user.id, AttendanceCorrection.status == "pending"))).all())
    return [{"id": a.id, "batch": b.name, "session_date": a.session_date, "status": a.status, "notes": a.notes, "correction_pending": a.id in pending} for a, b in rows]


@router.post("/it/student/attendance-corrections", status_code=201)
async def request_attendance_correction(payload: AttendanceCorrectionIn, user: User = Depends(PAID_ATTENDANCE), db: AsyncSession = Depends(get_db)):
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
    # nehn-023 (DEC-SCOPE-284 D1/D2): in-app + email to the batch's trainer; a batch without an active trainer goes to the IT Admins,
    # whose action is to assign one (they have no attendance page).
    batch = await db.get(Batch, attendance.batch_id)
    trainer = await db.get(User, batch.trainer_id) if batch.trainer_id else None
    change = f"{user.full_name} asked to change {batch.name} on {attendance.session_date:%d %b %Y} from {attendance.status} to {item.requested_status}."
    if trainer and trainer.active:
        await _notify_user(db, trainer, "Attendance correction requested", change, "/it/trainer/attendance", channels=["email"])
    else:
        body = f"{change} The batch has no trainer to review it; assign one so the request can be decided."
        for admin in (await db.scalars(select(User).where(User.role == "it_admin", User.active.is_(True)))).all():
            await _notify_user(db, admin, "Attendance correction needs a trainer", body, "/it/admin/batches", channels=["email"])
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.patch("/it/attendance-corrections/{correction_id}")
async def review_attendance_correction(correction_id: UUID, payload: AttendanceCorrectionReviewIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"trainer", "it_admin"}, "it")
    item = await db.get(AttendanceCorrection, correction_id, with_for_update=True)  # nehn-023: two reviewers at once -> the second gets 409
    if not item:
        raise HTTPException(404, "Correction request not found")
    attendance = await db.get(Attendance, item.attendance_id)
    batch = await db.get(Batch, attendance.batch_id) if attendance else None
    if user.role == "trainer" and (not batch or batch.trainer_id != user.id):
        raise HTTPException(403, "Correction is outside your assigned batch")
    # nehn-023 (D5): decide once -- a repeat would flip the attendance again and notify the student twice.
    if item.status != "pending":
        raise HTTPException(409, "This correction request has already been reviewed")
    decision = payload.status
    item.status = decision
    item.reviewed_by_id = user.id
    item.review_notes = payload.review_notes
    if decision == "approved" and attendance:
        attendance.status = item.requested_status
    await _audit(db, user, "attendance.correction_review", "attendance_correction", item.id, {"status": decision})
    student = await db.get(User, item.student_id)
    if student and student.active and attendance and batch:
        body = f"Your request to change {batch.name} on {attendance.session_date:%d %b %Y} to {item.requested_status} was {decision}."
        if item.review_notes:
            body += f" Comment: {item.review_notes}"
        await _notify_user(db, student, f"Attendance correction {decision}", body, "/it/student/attendance", channels=["email"])
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
    if payload.file_id:
        _check_material_type(payload.resource_type)
        usable = await db.scalar(
            select(StoredFile.id)
            .outerjoin(LearningResource, LearningResource.stored_file_id == StoredFile.id)
            .where(StoredFile.id == payload.file_id, StoredFile.owner_id == user.id, StoredFile.purpose == "learning_material", LearningResource.id.is_(None))
        )
        if not usable:  # one message for every reason, so nothing about another user's file is confirmed (M2)
            raise HTTPException(422, "This file cannot be attached to a material")
    item = LearningResource(batch_id=batch.id, title=payload.title, resource_type=payload.resource_type, url=payload.url, stored_file_id=payload.file_id, metadata_json=payload.metadata)
    db.add(item)
    await db.flush()
    await _audit(db, user, "learning_resource.create", "learning_resource", item.id, {"batch_id": batch.id, "kind": "file" if payload.file_id else "link"})
    try:
        await db.commit()
    except IntegrityError:  # a concurrent create attached the same file first
        await db.rollback()
        raise HTTPException(422, "This file cannot be attached to a material") from None
    await db.refresh(item)
    return {"id": item.id, "title": item.title, "type": item.resource_type, "url": item.href}


def _check_material_type(resource_type: str) -> None:
    """nehn-027 M3: videos and provider recordings stay links (NEEDS_CONFIRMATION); no video hosting is approved."""
    if resource_type in {"video", "recording"}:
        raise HTTPException(422, "Upload videos to YouTube or Google Drive and add the link")


def _material_row(item: LearningResource, batch: Batch, stored: StoredFile | None) -> dict:
    return {
        "id": item.id,
        "batch_id": batch.id,
        "batch": batch.name,
        "title": item.title,
        "resource_type": item.resource_type,
        "url": item.href,
        "sort_order": item.sort_order,
        "file": {"filename": stored.original_filename, "content_type": stored.content_type, "size": stored.size_bytes} if stored else None,
        "created_at": item.created_at,
    }


@router.get("/it/trainer/materials")
async def list_learning_resources(batch_id: UUID | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-027 M4: live materials, the trainer's own batches only (it_admin: every batch), in `sort_order` then newest first."""
    _require(user, {"trainer", "it_admin"}, "it")
    stmt = (
        select(LearningResource, Batch, StoredFile)
        .join(Batch, Batch.id == LearningResource.batch_id)
        .outerjoin(StoredFile, StoredFile.id == LearningResource.stored_file_id)
        .where(LearningResource.deleted_at.is_(None))
    )
    if user.role == "trainer":
        stmt = stmt.where(Batch.trainer_id == user.id)
    if batch_id:
        stmt = stmt.where(Batch.id == batch_id)
    rows = (await db.execute(stmt.order_by(LearningResource.sort_order, LearningResource.created_at.desc()).limit(500))).all()
    return [_material_row(item, batch, stored) for item, batch, stored in rows]


async def _managed_material(db: AsyncSession, user: User, resource_id: UUID) -> tuple[LearningResource, Batch]:
    _require(user, {"trainer", "it_admin"}, "it")
    row = (
        await db.execute(select(LearningResource, Batch).join(Batch, Batch.id == LearningResource.batch_id).where(LearningResource.id == resource_id, LearningResource.deleted_at.is_(None)))
    ).first()
    if not row:
        raise HTTPException(404, "Material not found")
    if user.role == "trainer" and row[1].trainer_id != user.id:
        raise HTTPException(403, "Trainer is not assigned to this batch")
    return row[0], row[1]


@router.patch("/it/trainer/materials/{resource_id}")
async def update_learning_resource(resource_id: UUID, payload: LearningResourceUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-027 M5: edit the title, type or link, or move it (`sort_order`)."""
    item, batch = await _managed_material(db, user, resource_id)
    changes = payload.model_dump(exclude_unset=True)
    if item.stored_file_id:
        if "url" in changes:
            raise HTTPException(422, "An uploaded file has no link to edit")
        if "resource_type" in changes:
            _check_material_type(changes["resource_type"])
    for field, value in changes.items():
        if value is not None:
            setattr(item, field, value)
    await _audit(db, user, "learning_resource.update", "learning_resource", item.id, {"batch_id": batch.id, "fields": sorted(changes)})
    await db.commit()
    await db.refresh(item)
    stored = await db.get(StoredFile, item.stored_file_id) if item.stored_file_id else None
    return _material_row(item, batch, stored)


@router.delete("/it/trainer/materials/{resource_id}", status_code=204)
async def delete_learning_resource(resource_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-027 M6: a soft delete -- hidden from every list and download; the stored file stays with its owner."""
    item, batch = await _managed_material(db, user, resource_id)
    item.deleted_at = datetime.now(UTC)
    await _audit(db, user, "learning_resource.delete", "learning_resource", item.id, {"batch_id": batch.id})
    await db.commit()


@router.get("/it/materials/{resource_id}/file")
async def learning_resource_file(resource_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-027 M7: a learner enrolled in the batch, the batch's trainer, it_admin and super_admin download the file. Everyone else --
    and a deleted, link-only or unknown material -- gets the same 404, so another batch's materials are not confirmed to exist."""
    row = (
        await db.execute(
            select(LearningResource, Batch, StoredFile)
            .join(Batch, Batch.id == LearningResource.batch_id)
            .join(StoredFile, StoredFile.id == LearningResource.stored_file_id)
            .where(LearningResource.id == resource_id, LearningResource.deleted_at.is_(None))
        )
    ).first()
    if not row:
        raise HTTPException(404, "Material not found")
    _, batch, stored = row
    allowed = user.role == "super_admin" or (user.role == "it_admin" and user.division == "it") or (user.role == "trainer" and batch.trainer_id == user.id)
    if not allowed and user.role == "it_student":
        allowed = bool(await db.scalar(select(Enrollment.id).where(Enrollment.batch_id == batch.id, Enrollment.student_id == user.id).limit(1)))
    if not allowed:
        raise HTTPException(404, "Material not found")
    await student_access.require(db, user, "resources")  # nehn-018: after the enrolment check, so another batch's material stays a 404
    return serve_stored_file(stored)


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
    # nehn-024 (DEC-SCOPE-292 F7): each row lists its attached files with the authorised download route.
    files: dict[UUID, list[dict]] = {s.id: [] for s, _, _ in rows}
    if files:
        attached = await db.execute(
            select(SubmissionFile.submission_id, StoredFile)
            .join(StoredFile, StoredFile.id == SubmissionFile.stored_file_id)
            .where(SubmissionFile.submission_id.in_(files))
            .order_by(SubmissionFile.created_at, StoredFile.original_filename)
        )
        for submission_id, stored in attached:
            files[submission_id].append(
                {"id": stored.id, "filename": stored.original_filename, "content_type": stored.content_type, "size": stored.size_bytes, "url": f"/api/v1/workflows/it/submissions/{submission_id}/files/{stored.id}"}
            )
    return [
        {
            "id": s.id,
            "assignment_id": a.id,
            "assignment": a.title,
            "student_id": student.id,
            "student": student.full_name,
            "answer": s.answer,
            "file_url": s.file_url,
            "files": files[s.id],
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
async def start_assessment(assessment_id: UUID, user: User = Depends(PAID_ASSESSMENTS), db: AsyncSession = Depends(get_db)):
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
async def submit_assessment(attempt_id: UUID, payload: AssessmentSubmitIn, user: User = Depends(PAID_ASSESSMENTS), db: AsyncSession = Depends(get_db)):
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


CAN_ISSUE_CERTIFICATES = require_permission("certificates", "issue", "You do not have permission to issue certificates")  # nehn-031 W3
CAN_CONFIGURE_CERTIFICATES = require_permission("certificates", "configure", "You do not have permission to change certificate rules")
DEFAULT_CERTIFICATE_RULES = {"min_progress_percent": 100, "min_attendance_percent": 75}  # nehn-031 W1: the thresholds before 0204
CERTIFICATE_QUEUE_EXCLUDED = ("pending_consent", "rejected", "withdrawn", "dropped")  # never seated, or left the course


async def _certificate_rules(db: AsyncSession) -> dict:
    """nehn-031 (DEC-SCOPE-297 W1): the global thresholds, read on every evaluation so an admin's change applies to the next one."""
    rule = await db.get(CertificateRule, "it")
    if not rule:
        return dict(DEFAULT_CERTIFICATE_RULES)
    return {"min_progress_percent": rule.min_progress_percent, "min_attendance_percent": rule.min_attendance_percent}


async def _certificate_eligibility(db: AsyncSession, enrollment: Enrollment, rules: dict | None = None) -> dict:
    rules = rules or await _certificate_rules(db)
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
    criteria: dict[str, object] = {
        "progress_percent": enrollment.progress_percent,
        "attendance_percent": attendance_percent,
        "assignments_graded": assignment_graded,
        "assignments_total": assignment_total,
        "assessments_passed": passed,
        "assessments_total": len(assessments),
        "pending_fee": float(pending_fee),
        "rules": rules,
    }
    criteria["eligible"] = bool(
        enrollment.progress_percent >= rules["min_progress_percent"]
        and attendance_percent >= rules["min_attendance_percent"]
        and assignment_graded >= assignment_total
        and passed >= len(assessments)
        and float(pending_fee) == 0
    )
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
    elif user.role not in {"it_student", "it_admin", "super_admin", "coordinator"}:  # nehn-031: the coordinator checks before issuing
        raise HTTPException(403, "Certificate access denied")
    issued = await db.scalar(select(Certificate.id).where(Certificate.enrollment_id == enrollment.id))
    return {**await _certificate_eligibility(db, enrollment), "certificate_issued": issued is not None}  # nehn-031 QA31-04


@router.get("/it/certificates/rules")
async def read_certificate_rules(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"it_admin", "coordinator", "trainer"}, "it")
    return await _certificate_rules(db)


@router.put("/it/certificates/rules")
async def update_certificate_rules(
    payload: CertificateRulesIn,
    user: User = Depends(CAN_CONFIGURE_CERTIFICATES),
    db: AsyncSession = Depends(get_db),
):
    """nehn-031 (DEC-SCOPE-297 W2): the thresholds; audited with before and after. Issued certificates keep their own snapshot."""
    rule = await db.get(CertificateRule, "it", with_for_update=True)
    before = await _certificate_rules(db)  # the locked row, from the identity map
    if not rule:
        rule = CertificateRule(division="it")
        db.add(rule)
    rule.min_progress_percent, rule.min_attendance_percent, rule.updated_by_id = payload.min_progress_percent, payload.min_attendance_percent, user.id
    after = payload.model_dump()
    await _audit(db, user, "certificate_rules.update", "certificate_rules", "it", {"before": before, "after": after})
    await db.commit()
    return after


CAN_CONFIGURE_STUDENT_ACCESS = require_permission("student_access", "configure", "You do not have permission to change student access rules")


@router.get("/it/student/access")
async def student_access_summary(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-018 (DEC-SCOPE-304): the student's payment state and which features it unlocks -- the portal's locks and nav badges."""
    _require(user, {"it_student"}, "it")
    return await student_access.summary(db, user)


def _student_access_rules(rules: dict[str, str]) -> dict:
    return {
        "rules": [{"feature": f, "label": student_access.FEATURE_LABELS[f], "min_state": rules[f]} for f in student_access.FEATURES],
        "states": [{"key": s, "label": student_access.STATE_LABELS[s]} for s in student_access.STATES],
    }


@router.get("/it/student-access/rules")
async def read_student_access_rules(user: User = Depends(CAN_CONFIGURE_STUDENT_ACCESS), db: AsyncSession = Depends(get_db)):
    return _student_access_rules(await student_access.policy(db))


@router.put("/it/student-access/rules")
async def update_student_access_rules(payload: StudentAccessRulesIn, user: User = Depends(CAN_CONFIGURE_STUDENT_ACCESS), db: AsyncSession = Depends(get_db)):
    """nehn-018 (DEC-SCOPE-304 AC4): replaces the policy; the next request of every student uses it. Audited with before and after."""
    rows = {r.feature: r for r in (await db.scalars(select(StudentAccessRule).with_for_update())).all()}
    before = await student_access.policy(db)
    for feature, state in payload.rules.items():
        rule = rows.get(feature) or StudentAccessRule(feature=feature)
        rule.min_state, rule.updated_by_id = state, user.id
        db.add(rule)
    after = {f: payload.rules[f] for f in student_access.FEATURES}
    await _audit(db, user, "student_access_rules.update", "student_access_rules", "it", {"before": before, "after": after})
    await db.commit()
    return _student_access_rules(after)


@router.post("/it/certificates/{enrollment_id}/recommend")
async def recommend_certificate(enrollment_id: UUID, payload: CertificateRecommendIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-031 (DEC-SCOPE-297 W6): the batch's trainer recommends a learner or flags them not ready; a later call replaces it."""
    _require(user, {"trainer"}, "it")
    enrollment = await db.get(Enrollment, enrollment_id)
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")
    batch = await db.get(Batch, enrollment.batch_id)
    if not batch or batch.trainer_id != user.id:
        raise HTTPException(403, "Enrollment is outside your assigned batch")
    if await db.scalar(select(Certificate.id).where(Certificate.enrollment_id == enrollment.id)):
        raise HTTPException(409, "A certificate has already been issued for this enrolment")
    values = {"status": payload.status, "comment": payload.comment, "recommended_by_id": user.id, "updated_at": func.now()}
    stmt = pg_insert(CertificateRequest).values(id=uuid4(), enrollment_id=enrollment.id, **values)
    await db.execute(stmt.on_conflict_do_update(index_elements=[CertificateRequest.enrollment_id], set_=values))
    await _audit(db, user, f"certificate.{payload.status}", "enrollment", enrollment.id, {"comment": payload.comment})
    await db.commit()
    return {"enrollment_id": enrollment.id, "status": payload.status, "comment": payload.comment}


@router.get("/it/certificates/queue")
async def certificate_queue(user: User = Depends(CAN_ISSUE_CERTIFICATES), db: AsyncSession = Depends(get_db)):
    """nehn-031 (DEC-SCOPE-297 W5): enrolments without a certificate that pass the progress threshold or carry a trainer's
    recommendation, recommended first. Full eligibility is evaluated per row (capped at 200)."""
    rules = await _certificate_rules(db)
    recommender = aliased(User)
    rows = (
        await db.execute(
            select(Enrollment, User.full_name, Batch.name, Program.title, CertificateRequest, recommender.full_name)
            .join(User, User.id == Enrollment.student_id)
            .join(Batch, Batch.id == Enrollment.batch_id)
            .join(Program, Program.id == Batch.program_id)
            .outerjoin(CertificateRequest, CertificateRequest.enrollment_id == Enrollment.id)
            .outerjoin(recommender, recommender.id == CertificateRequest.recommended_by_id)
            .where(
                Enrollment.status.not_in(CERTIFICATE_QUEUE_EXCLUDED),
                ~select(Certificate.id).where(Certificate.enrollment_id == Enrollment.id).exists(),
                or_(Enrollment.progress_percent >= rules["min_progress_percent"], CertificateRequest.status.in_(("recommended", "not_ready"))),
            )
            .order_by(CertificateRequest.status != "recommended", User.full_name)  # recommended, then not ready, then the rest (NULLS LAST)
            .limit(200)
        )
    ).all()
    items = []
    for enrollment, student, batch_name, program_title, request, recommended_by in rows:
        criteria = await _certificate_eligibility(db, enrollment, rules)
        recommendation = (
            {"status": request.status, "comment": request.comment, "by": recommended_by, "at": request.updated_at} if request and request.status != "issued" else None
        )
        items.append(
            {"enrollment_id": enrollment.id, "student": student, "batch": batch_name, "program": program_title, "eligible": criteria["eligible"], "criteria": criteria, "recommendation": recommendation}
        )
    return {"can_override": await permissions.has_grant(db, user.role, "certificates", "override"), "rules": rules, "items": items}


async def _issue_certificate(db: AsyncSession, user: User, enrollment_id: UUID, override: bool, override_reason: str | None) -> Certificate:
    """Issue one certificate (DEC-ROLE-003: a `certificates.issue` holder) and commit. Eligibility is re-evaluated now, not taken from
    the queue. The enrolment row is locked, so two concurrent issues cannot both create one (W7)."""
    enrollment = await db.scalar(select(Enrollment).where(Enrollment.id == enrollment_id).with_for_update())
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")
    batch = await db.get(Batch, enrollment.batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    if await db.scalar(select(Certificate.id).where(Certificate.enrollment_id == enrollment.id)):
        raise HTTPException(409, "A certificate has already been issued for this enrolment")
    criteria = await _certificate_eligibility(db, enrollment)
    override_reason = (override_reason or "").strip() or None
    if not criteria["eligible"]:
        if not override:
            # `HTTPException.detail` is serialized by Starlette's plain `json.dumps`, so the UUID in `batch_id` goes out as a string.
            raise HTTPException(409, {"message": "Completion criteria are not met", "criteria": {**criteria, "batch_id": str(criteria["batch_id"])}})
        # ADM-006-AC02: an override is never silent -- a written justification is required in the same request, captured on the
        # certificate's own snapshot and in the audit trail.
        if not override_reason:
            raise HTTPException(422, "override_reason is required to issue a certificate before completion criteria are met")
    program = await db.get(Program, batch.program_id)
    student = await db.get(User, enrollment.student_id)
    if not program or not student:
        raise HTTPException(422, "Certificate data is incomplete")
    # nehn-032 (DEC-SCOPE-302 S7): both signatures are drawn on the PDF and their versions snapshotted; without both, no certificate.
    signatories = await active_signatories(db)
    require_signatories(signatories)
    certificate_no = f"EDU-CERT-{date.today():%Y}-{secrets.token_hex(4).upper()}"
    verification_code = secrets.token_urlsafe(12)
    file_url = generate_certificate_pdf(
        certificate_no=certificate_no, student_name=student.full_name, program_title=program.title, issued_on=date.today(), verification_code=verification_code, signatories=signatories
    )
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
        signatory_snapshot=signatory_snapshot(signatories),
        status="issued",
    )
    db.add(item)
    await db.flush()
    await db.execute(update(CertificateRequest).where(CertificateRequest.enrollment_id == enrollment.id).values(status="issued", certificate_id=item.id, updated_at=func.now()))
    await course_skills.grant(db, user, student_id=student.id, program_id=program.id)  # rec-036 CI3: opted-in students only
    await _notify_user(db, student, "Certificate issued", f"Your {program.title} certificate is ready.", "/it/student/certificates")
    item.emailed_at = datetime.now(UTC)
    override_used = not criteria["eligible"]
    await _audit(db, user, "certificate.issue", "certificate", item.id, {"enrollment_id": enrollment.id, "override": override_used, "override_reason": override_reason if override_used else None})
    await db.commit()
    await db.refresh(item)
    return item


async def _check_override(db: AsyncSession, user: User, override: bool) -> None:
    if override and not await permissions.has_grant(db, user.role, "certificates", "override"):
        raise HTTPException(403, "You do not have permission to override certificate eligibility")


def _certificate_out(item: Certificate) -> dict:
    return {"id": item.id, "certificate_no": item.certificate_no, "verification_code": item.verification_code, "file_url": item.file_url, "status": item.status}


@router.post("/it/certificates/issue")
async def bulk_issue_certificates(
    payload: CertificateBulkIssueIn,
    user: User = Depends(CAN_ISSUE_CERTIFICATES),
    db: AsyncSession = Depends(get_db),
):
    """nehn-031 (DEC-SCOPE-297 W8): each enrolment is checked and issued on its own; the answer says which were issued and why the
    others were not."""
    await _check_override(db, user, payload.override)
    issued, failed = [], []
    for enrollment_id in dict.fromkeys(payload.enrollment_ids):
        try:
            item = await _issue_certificate(db, user, enrollment_id, payload.override, payload.override_reason)
        except HTTPException as error:
            await db.rollback()  # releases the row lock; it also expires `user`, which the next issue reads
            await db.refresh(user)
            detail = error.detail.get("message") if isinstance(error.detail, dict) else error.detail
            failed.append({"enrollment_id": str(enrollment_id), "status_code": error.status_code, "detail": detail})
            continue
        issued.append({"enrollment_id": str(enrollment_id), **_certificate_out(item)})
    logger.info("certificate.bulk_issue", extra={"extra_fields": {"actor_id": str(user.id), "issued": len(issued), "failed": len(failed)}})
    return {"issued": issued, "failed": failed}


@router.post("/it/certificates/{enrollment_id}/issue", status_code=201)
async def issue_certificate(
    enrollment_id: UUID,
    payload: CertificateIssueIn,
    user: User = Depends(CAN_ISSUE_CERTIFICATES),
    db: AsyncSession = Depends(get_db),
):
    # nehn-031 (DEC-ROLE-003): the cut-over -- trainers and IT admins no longer issue; a duplicate is now a 409 (W7).
    await _check_override(db, user, payload.override)
    return _certificate_out(await _issue_certificate(db, user, enrollment_id, payload.override, payload.override_reason))


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
    await student_access.require(db, user, "certificates")  # nehn-018: after ownership
    key = f"certificates/{certificate.certificate_no}.pdf"
    return {"url": storage.presign_download(key), "expires_in": 900 if storage.bucket else None}


@router.post("/it/student/feedback", status_code=201)
async def submit_feedback(payload: CourseFeedbackCreate, user: User = Depends(PAID_FEEDBACK), db: AsyncSession = Depends(get_db)):
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
async def raise_question(payload: QuestionThreadCreate, user: User = Depends(PAID_QUESTIONS), db: AsyncSession = Depends(get_db)):
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
async def list_student_questions(user: User = Depends(PAID_QUESTIONS), db: AsyncSession = Depends(get_db)):
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
    await _notify_user(db, student, "Your question has a new reply", f'"{thread.subject}" was answered.', "/it/student/questions")
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
            select(Job, Company).join(Company).where(Job.status.in_(JOB_OPEN_STATUSES), or_(Job.closes_on.is_(None), Job.closes_on >= date.today())).order_by(Job.created_at.desc())
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
    return [{"id": job.id, "company": company.name, "title": job.title, "status": job.status, "status_label": requirements.STATUS_LABELS[job.status]} for job, company in rows]


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
    return [{"id": a.id, "student": s.full_name, "email": s.email, "status": a.status, "status_label": applications.label(a.status), "resume_url": a.resume_url} for a, s in rows]


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
        skills=[],
        status="requirement_received",  # rec-007 J1: the legacy "open"; this staff route still publishes immediately
        closes_on=date.fromisoformat(payload["closes_on"]) if payload.get("closes_on") else None,
        requirement_date=requirements.ist_today(),
        created_by_user_id=user.id,
    )
    db.add(job)
    await db.flush()
    await requirements.set_legacy_skills(db, job, payload.get("skills") or [])
    await requirements.record_created(db, user, job)
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
    if not job or job.status not in JOB_OPEN_STATUSES or (job.closes_on and job.closes_on < date.today()):
        raise HTTPException(404, "Open job not found")
    # rec-017 (R6, A4): the application belongs to the student's candidate (created or linked here, outside the pool until rec-010's
    # opt-in); "applied" is now Sourced.
    candidate = await applications.candidate_for_student(db, user)
    if await db.scalar(select(JobApplication.id).where(JobApplication.job_id == job_id, JobApplication.candidate_id == candidate.id)):
        raise HTTPException(409, "Already applied")
    resume_url = payload.get("resume_url") or user.profile.get("resume_url")
    item = await applications.create(db, user, job, candidate, "sourced", "Applied from the student portal", resume_url=resume_url)
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
    for key in {"title", "location", "description"}:
        if key in payload:
            setattr(job, key, payload[key])
    if "skills" in payload:
        await requirements.set_legacy_skills(db, job, payload["skills"] or [])
    if payload.get("status"):
        # rec-007 (J3): a §6 status, or a legacy draft/open/closed word mapped onto one; the move is validated and kept in history.
        status = payload["status"]
        if status in requirements.LEGACY_WORDS:
            status = requirements.legacy_target(job.status, status)
        elif status not in requirements.STATUS_LABELS:
            raise HTTPException(422, "Unknown requirement status")
        if status:
            await requirements.change_status(db, user, job, status)
    if "closes_on" in payload:
        job.closes_on = date.fromisoformat(payload["closes_on"]) if payload["closes_on"] else None
    await _audit(db, user, "job.update", "job", job.id, payload)
    await db.commit()
    return {"id": job.id, "status": job.status}


@router.patch("/it/job-applications/{application_id}")
async def update_job_application(application_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    item = await db.scalar(select(JobApplication).where(JobApplication.id == application_id).with_for_update())
    if not item:
        raise HTTPException(404, "Job application not found")
    # rec-017 (A1/A2): a legacy word or a §12 key; the move is validated and kept in history. The same status stays a no-op 200.
    status = applications.from_legacy(payload.get("status") or "")
    if status is None:
        raise HTTPException(422, "Invalid application status")
    if status != item.status:
        await applications.change_status(db, user, item, status)
        await applications.notify_student(db, item)
    await _audit(db, user, "job_application.update", "job_application", item.id, {"status": status})
    await db.commit()
    return {"id": item.id, "status": item.status, "status_label": applications.label(item.status)}


@router.post("/it/interviews", status_code=201)
async def schedule_interview(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    application = await db.get(JobApplication, uuid_reference(payload.get("application_id"), "job application reference"))
    if not application:
        raise HTTPException(404, "Application not found")
    # rec-020 (IV11): the code, the first event and the per-candidate clash (409) come from the service; no other new rule here.
    item = await interviews.insert(db, user, application, datetime.fromisoformat(payload["scheduled_at"]), mode=payload.get("mode", "Online"), meeting_url=payload.get("meeting_url"))
    applications.follow(db, user, application, "interview", "Interview scheduled")
    await _audit(db, user, "interview.schedule", "interview", item.id)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "code": item.interview_code, "scheduled_at": item.scheduled_at}


@router.patch("/it/interviews/{interview_id}")
async def update_interview(interview_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"placement_team", "hr_team", "it_admin"}, "it")
    item = await db.scalar(select(Interview).where(Interview.id == interview_id).with_for_update())
    if not item:
        raise HTTPException(404, "Interview not found")
    for key in {"mode", "meeting_url", "result"}:
        if key in payload:
            setattr(item, key, payload[key])
    application = await db.get(JobApplication, item.application_id)
    # rec-020 (IV11): a changed time is recorded as a reschedule; a known result also sets the status when the move is allowed.
    scheduled_at = datetime.fromisoformat(payload["scheduled_at"]) if payload.get("scheduled_at") else None
    await interviews.legacy_update(db, user, item, application, scheduled_at, payload.get("result"), await db_now(db))
    if application and item.result in {"selected", "rejected"}:  # rec-017 A2: a selected result now means Selected
        applications.follow(db, user, application, item.result, f"Interview result: {item.result}")
    await _audit(db, user, "interview.update", "interview", item.id, payload)
    await db.commit()
    return {"id": item.id, "result": item.result, "status": item.status}


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
    # rec-022 OF9: through services/offers (the mapped status, the created history row, the 409 on a second offer, the student notice).
    status = offers.from_legacy(payload.get("status", "offered"))
    if status is None:
        raise HTTPException(422, offers.UNKNOWN_STATUS)
    joining = date.fromisoformat(payload["joining_date"]) if payload.get("joining_date") else None
    applications.follow(db, user, application, "selected", "Offer recorded")
    item = await offers.insert(
        db, user, application, status,
        compensation=payload.get("compensation"), currency=payload.get("currency", "INR"), joining_date=joining, letter_url=payload.get("letter_url"),
    )
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
    for key in {"compensation", "currency", "letter_url"}:
        if key in payload:
            setattr(item, key, payload[key])
    if "joining_date" in payload:
        item.joining_date = date.fromisoformat(payload["joining_date"]) if payload["joining_date"] else None
    if "status" in payload:  # rec-022 OF9 / AC3: mapped, with history; accepted/joined still joins the application
        application = await db.get(JobApplication, item.application_id)
        await offers.legacy_status(db, user, item, application, payload["status"])
    await _audit(db, user, "placement.offer_update", "job_offer", item.id, {k: v for k, v in payload.items() if k != "compensation"})
    await db.commit()
    return {"id": item.id, "status": item.status}


# --------------------------- OVERSEAS EDUCATION ----------------------------
# DATA_MODEL.md #6.2: the confirmed base sequence (DEC-WF-001), fixed by this contract.
# Exception-path values (rejected/waitlisted/deferred) are deliberately NOT included --
# DEC-WF-001 leaves those open (PRD_OPEN_ITEMS.md), so a status outside this list is
# rejected rather than guessed (OVS-003-AC02).


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
        for recipient in await notification_recipients(db, agent):  # AGN-001 (D12): every active Master
            await _notify_user(db, recipient, "Commission estimated", "A referred student has enrolled -- a commission is now estimated and awaiting an amount from Overseas Admin.", "/overseas/agent/commissions")
    await _audit(db, changed_by, "agent.commission_auto_create", "agent_commission", item.id, {"application_id": str(application.id), "trigger": "enrolled"})


@router.post("/overseas/applications", status_code=201)
async def create_overseas_application(payload: OverseasApplicationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"overseas_student", "counselor", "overseas_admin", "agent"}, "overseas")
    student_id = user.id if user.role == "overseas_student" else payload.student_id
    student = await db.get(User, student_id)
    if not student or student.role != "overseas_student" or student.division != "overseas":
        raise HTTPException(422, "Valid overseas student is required")
    await student_archive.refuse_new_application(db, student_id)  # ccrm-040 (DEC-SCOPE-276 AR6)
    if user.role == "agent":
        linked = await db.scalar(select(AgentStudent.id).where(*student_scope(user), AgentStudent.student_id == student_id, AgentStudent.status == "active"))
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
    # and so is a rejected / offer-declined / visa-refused one (ccrm-015 O3).
    duplicate = await db.scalar(
        select(OverseasApplication.id).where(
            OverseasApplication.student_id == student_id,
            OverseasApplication.university_id == university.id,
            OverseasApplication.course_id == course_id,
            open_clause(),
        )
    )
    if duplicate:
        raise HTTPException(409, "An application for this university/course already exists")
    if payload.counselor_id:
        await _require_overseas_counselor(db, payload.counselor_id)
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
        next_action=payload.next_action or DEFAULT_NEXT_ACTION,
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
    stmt = with_owner(select(OverseasApplication, University).join(University, University.id == OverseasApplication.university_id))
    if user.role == "overseas_student":
        stmt = stmt.where(OverseasApplication.student_id == user.id)
    elif user.role == "counselor":
        stmt = stmt.where(OverseasApplication.counselor_id == user.id)
    elif user.role == "agent":
        stmt = stmt.where(*application_scope(user))
    elif user.role == "university_rep":
        stmt = stmt.where(OverseasApplication.university_id == uuid_reference(user.profile.get("university_id"), "university reference", required=False))
    rows = owned((await db.execute(stmt.order_by(OverseasApplication.updated_at.desc()).limit(500))).all())
    return [
        {
            "id": a.id,
            "application_code": a.application_code,  # ccrm-011 (DEC-SCOPE-239)
            "student_id": student.id,
            "student": student.full_name,
            "university_id": u.id,
            "university": u.name,
            "course_id": a.course_id,
            "intake": a.intake,
            "status": a.status,
            "sub_status": a.sub_status,
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
    # AGN-008 (final review): re-read under the row lock so the guard below sees an agent's committed withdraw.
    await db.refresh(item, with_for_update=True)
    # AGN-023 (DEC-SCOPE-090 H4, final review C1): a counselor moves an agency application only through `/advance` (forward, never
    # `enrolled`); the generic PATCH has neither rule and could trigger the commission, so it refuses them before any field is applied.
    if user.role == "counselor" and item.agent_id is not None:
        raise HTTPException(403, AGENCY_USE_ADVANCE)
    _recheck_counselor_scope(user, item)  # a direct application's counselor swapped between the scope read and the lock
    changes = payload.model_dump(exclude_unset=True)
    # AGN-023 (DEC-SCOPE-090 H10): after creation only the Admin's assign route changes the counselor (audited, notified).
    if "counselor_id" in changes:
        raise HTTPException(422, COUNSELOR_REFUSED_ON_UPDATE)
    # AGN-008 (A1): `withdrawn` is terminal -- no generic status write revives it; ccrm-015 (O2): nor any terminal outcome, and on
    # hold pauses stage moves. Other fields stay editable, as on a withdrawn application before.
    if "status" in changes:
        outcomes.refuse_closed(item)
        outcomes.refuse_on_hold(item)
        _refuse_unconfirmed_enrollment(item, changes["status"])
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
    allowed = {"intake", "status", "application_reference", "offer_letter_url"}
    allowed.add("next_action")
    for k, v in changes.items():
        if k in allowed:
            setattr(item, k, v)
    if item.status != old_status or item.next_action != old_next_action:
        db.add(ApplicationStatusHistory(application_id=item.id, from_status=old_status, to_status=item.status, next_action=item.next_action, notes=notes, changed_by_id=user.id))
    if item.status != old_status:
        had_commission = await agency_notices.has_commission(db, item.id)
        await _maybe_trigger_agent_commission(db, item, old_status, user)
        await agency_notices.status_changed(db, item, old_status, user, had_commission=had_commission)  # AGN-017 (N3, AC3)
    # DEC-SCOPE-018: a bridged (School-origin) application has `student_id IS NULL` --
    # guarded the same way as `advance_overseas_application` below.
    student = await db.get(User, item.student_id) if item.student_id else None
    safe_channels = [channel for channel in channels if channel in {"email", "sms", "whatsapp"}]
    if student and (item.status != old_status or "next_action" in changes):
        await _notify_user(
            db, student, "Application status updated", f"Status: {item.status}. Next action: {item.next_action or 'No action required'}.", "/overseas/student/applications", safe_channels or ["email"]
        )
    await _audit(db, user, "overseas.application.update", "overseas_application", item.id, changes)
    await db.commit()
    return {"id": item.id, "status": item.status, "next_action": item.next_action}


async def _owner_name(db: AsyncSession, item: OverseasApplication) -> str:
    """The application's student for an internal counselor notice: the account, else the agency record, else the school record."""
    for model, key in ((User, item.student_id), (AgentStudent, item.agent_student_id), (SchoolStudent, item.school_student_id)):
        if key is not None:
            name = await db.scalar(select(model.full_name).where(model.id == key))
            if name:
                return name
    return "A student"


@router.put("/overseas/applications/{application_id}/counselor")
async def assign_overseas_counselor(
    application_id: UUID, payload: OverseasApplicationCounselorAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """AGN-023 (DEC-SCOPE-090 §3.1): the Overseas Admin assigns or swaps an application's EduSphere counselor (H2, H8). Not
    super_admin, which `_require` would wave through."""
    if user.role != "overseas_admin" or user.division != "overseas":
        raise HTTPException(403, "Only the Overseas Admin can assign a counselor")
    item = await db.get(OverseasApplication, application_id, with_for_update=True)
    if item is None:
        raise HTTPException(404, "Application not found")
    if item.status == "enrolled" or outcomes.is_closed(item):
        raise HTTPException(409, APPLICATION_CLOSED)
    counselor = await db.get(User, payload.counselor_id)
    if counselor is None or counselor.role != "counselor" or counselor.division != "overseas" or not counselor.active:
        raise HTTPException(422, CHOOSE_ACTIVE_COUNSELOR)
    result = {"id": item.id, "counselor_id": counselor.id, "counselor_name": counselor.full_name}
    if item.counselor_id == counselor.id:
        return {**result, "changed": False}
    previous_id = item.counselor_id
    reason = payload.reason
    counselor_students.require_reason(previous_id, reason)  # ccrm-033 (DEC-SCOPE-271 RR1): a swap needs a reason
    item.counselor_id = counselor.id
    note = COUNSELLOR_CHANGED if previous_id else COUNSELLOR_ASSIGNED
    db.add(ApplicationStatusHistory(application_id=item.id, from_status=item.status, to_status=item.status, next_action=item.next_action, notes=note, reason=reason, changed_by_id=user.id))
    await _audit(db, user, "overseas.application.counselor_assign", "overseas_application", item.id,
                 {"from_counselor_id": str(previous_id) if previous_id else None, "to_counselor_id": str(counselor.id), **counselor_students.reason_meta(reason)})  # fmt: skip
    university = await db.scalar(select(University.name).where(University.id == item.university_id))
    await _notify_user(db, counselor, "Application assigned to you", counselor_students.with_reason(f"{await _owner_name(db, item)} — {university}", reason), "/overseas/counselor/applications")
    previous = await db.get(User, previous_id) if previous_id else None
    if previous is not None and previous.active:
        await _notify_user(db, previous, "Application reassigned", counselor_students.with_reason("An application has moved to another counselor.", reason), "/overseas/counselor/applications")
    if item.agent_id is not None:
        await agency_notices.counselor_assigned(db, item, user, changed=previous_id is not None)
    await db.commit()
    return {**result, "changed": True}


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
    student = await db.get(User, item.student_id) if item.student_id else None
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
    await db.refresh(item, with_for_update=True)  # AGN-008 (final review): the guard must see a committed withdraw
    _recheck_counselor_scope(user, item)  # AGN-023 (final review I4): a swap committed after the scope read
    outcomes.refuse_closed(item)  # AGN-008 (A1): otherwise index -1 would let any target revive it; ccrm-015 terminal outcomes too
    outcomes.refuse_on_hold(item)
    if item.agent_id is not None and await _agency_record_archived(db, item):  # AGN-023 (final review I1): the agency's A15 rule
        raise HTTPException(409, ARCHIVED)
    if item.agent_id is not None and payload.to_status == "enrolled":
        raise HTTPException(403, MASTER_ENROLLS)
    _refuse_unconfirmed_enrollment(item, payload.to_status)
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
    had_commission = await agency_notices.has_commission(db, item.id)
    await _maybe_trigger_agent_commission(db, item, old_status, user)
    await agency_notices.status_changed(db, item, old_status, user, had_commission=had_commission)  # AGN-017 (N3, AC3)
    # DEC-SCOPE-018: a bridged (School-origin) application has `student_id IS NULL` --
    # `db.get(User, None)` triggers a SAWarning ("fully NULL primary key identity") and
    # is documented as a future error, so it's guarded here rather than relied on to
    # short-circuit. There is no User to notify for a bridged application.
    student = await db.get(User, item.student_id) if item.student_id else None
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


@router.post("/overseas/applications/{application_id}/sub-status")
async def change_application_sub_status(application_id: UUID, payload: ApplicationSubStatusChange, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-014 (DEC-SCOPE-240, SS4): the counselor (their applications, direct and agency) or the Overseas Admin sets a sub-status;
    one of a later stage advances the stage. `/advance`'s locks and agency rules apply; the agency enrols its own applications."""
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    item = await _assigned_application(db, user, application_id)
    await db.refresh(item, with_for_update=True)
    _recheck_counselor_scope(user, item)
    outcomes.refuse_closed(item)
    outcomes.refuse_on_hold(item)
    stage = sub_statuses.stage_of(payload.sub_status)
    if item.agent_id is not None and await _agency_record_archived(db, item):
        raise HTTPException(409, ARCHIVED)
    if item.agent_id is not None and stage == "enrolled" and user.role == "counselor":
        raise HTTPException(403, MASTER_ENROLLS)
    _refuse_unconfirmed_enrollment(item, stage)
    override =await application_checklists.ready_gate(db, user, item, payload.sub_status, payload.override_reason)  # ccrm-019
    before = sub_statuses.change(db, user, item, payload.sub_status, payload.notes, f"Override: {override}" if override else None)
    if before is not None:
        if before.status != item.status:
            had_commission = await agency_notices.has_commission(db, item.id)
            await _maybe_trigger_agent_commission(db, item, before.status, user)
            await agency_notices.status_changed(db, item, before.status, user, had_commission=had_commission)
        else:
            await agency_notices.sub_status_changed(db, item, user)  # CC5
        student = await db.get(User, item.student_id) if item.student_id else None
        if student:
            await _notify_user(db, student, "Application status updated", f"Status: {stage_label(item.status)} — {sub_status_label(item.sub_status)}.", "/overseas/student/applications")
        await _audit(
            db,
            user,
            "overseas.application.sub_status",
            "overseas_application",
            item.id,
            {"from_status": before.status, "to_status": item.status, "from_sub_status": before.sub_status, "to_sub_status": item.sub_status}
            | ({"checklist_override": override} if override else {}),
        )
        await db.commit()
    return {"id": item.id, "status": item.status, "sub_status": item.sub_status, "sub_status_label": sub_status_label(item.sub_status), "changed": before is not None}


def _details_view(item: OverseasApplication) -> dict:
    return {
        "id": item.id,
        "application_code": item.application_code,
        **{name: getattr(item, name) for name in application_fields.DETAIL_FIELDS},
        "scholarship_label": application_fields.scholarship_label(item.scholarship_status),
    }


@router.get("/overseas/applications/{application_id}/details")
async def get_application_details(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-013 (DEC-SCOPE-256): the university-side fields and the three dates -- the counselor of the application or the Admin."""
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    return _details_view(await _assigned_application(db, user, application_id))


@router.patch("/overseas/applications/{application_id}/details")
async def update_application_details(application_id: UUID, payload: ApplicationDetailsUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-013 (DEC-SCOPE-256, F2): the counselor (their applications, direct and agency: CC4) or the Overseas Admin edits the details.
    Not the generic PATCH, which keeps refusing a counselor on an agency application (no stage write here). CC5: last write wins, the
    audit keeps every change with its author, the agency is told."""
    item = await _outcome_entry(db, user, application_id)
    changes = payload.model_dump(exclude_unset=True)
    if "scholarship_amount" not in changes and changes.get("scholarship_status", item.scholarship_status) != "awarded":
        changes["scholarship_amount"] = None  # F3: leaving awarded clears the amount; one sent with another status is a 422 below
    merged = {name: getattr(item, name) for name in application_fields.DETAIL_FIELDS} | changes
    if problem := application_fields.problem(merged):
        raise HTTPException(422, problem)
    diff = {name: {"from": getattr(item, name), "to": value} for name, value in changes.items() if getattr(item, name) != value}
    if diff:
        old_scholarship = item.scholarship_status
        for name in diff:
            setattr(item, name, changes[name])
        await _audit(db, user, "overseas.application.details", "overseas_application", item.id, jsonable_encoder(diff))
        await agency_notices.details_changed(db, item, user)  # CC5
        student = await db.get(User, item.student_id) if item.student_id else None
        if student and item.scholarship_status != old_scholarship:  # F8: the student hears about the scholarship only
            university = await db.scalar(select(University.name).where(University.id == item.university_id))
            text = application_fields.scholarship_text(item.scholarship_status, item.scholarship_amount, item.currency) or "No scholarship recorded"
            await _notify_user(db, student, "Scholarship update", f"{university}: {text}.", "/overseas/student/applications")
        await db.commit()
    return {**_details_view(item), "changed": bool(diff)}


async def _outcome_entry(db: AsyncSession, user: User, application_id: UUID) -> OverseasApplication:
    """ccrm-015: the sub-status route's entry -- counselor (own applications, agency too: CC4) or Overseas Admin, scoped, row-locked."""
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    item = await _assigned_application(db, user, application_id)
    await db.refresh(item, with_for_update=True)
    _recheck_counselor_scope(user, item)
    if item.agent_id is not None and await _agency_record_archived(db, item):
        raise HTTPException(409, ARCHIVED)
    return item


async def _outcome_response(db: AsyncSession, item: OverseasApplication) -> dict:
    event = (await outcomes.latest(db, [item.id])).get(item.id)
    return {"id": item.id, "status": item.status, "sub_status": item.sub_status, "outcome": item.outcome, "detail": outcomes.view(item, event, staff=True)}


async def _tell_outcome(db: AsyncSession, user: User, item: OverseasApplication, text: str) -> None:
    """CC5: the student (when they have a login) and, on an agency application, the agency."""
    student = await db.get(User, item.student_id) if item.student_id else None
    if student:
        university = await db.scalar(select(University.name).where(University.id == item.university_id))
        await _notify_user(db, student, "Application update", f"{university}: {text}.", "/overseas/student/applications")
    await agency_notices.outcome_changed(db, item, user, text)


@router.post("/overseas/applications/{application_id}/outcome")
async def set_application_outcome(application_id: UUID, payload: ApplicationOutcomeSet, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-015 (DEC-SCOPE-244): record rejected / withdrawn / deferred / on hold / offer declined on ONE application (AC 9); the others
    of the student are untouched. Terminal outcomes close it until the Overseas Admin reopens it (O2)."""
    item = await _outcome_entry(db, user, application_id)
    before = item.status
    event = await outcomes.record(db, user, item, payload)
    await db.flush()
    await _tell_outcome(db, user, item, outcome_label(item.outcome))
    await _audit(db, user, "overseas.application.outcome", "overseas_application", item.id, {"outcome": item.outcome, "event_id": str(event.id), "from_status": before, "to_status": item.status})
    await db.commit()
    return await _outcome_response(db, item)


@router.post("/overseas/applications/{application_id}/outcome/reopen")
async def reopen_application_outcome(application_id: UUID, payload: ApplicationOutcomeReopen, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-015 (DEC-SCOPE-244): clear the outcome -- resume on hold / deferred (counselor or Admin) or reopen a terminal one (Overseas
    Admin only), with a reason. A withdrawn application returns to the stage it was withdrawn from."""
    item = await _outcome_entry(db, user, application_id)
    before = item.status
    cleared = await outcomes.reopen(db, user, item, payload.reason)
    await _tell_outcome(db, user, item, f"{outcome_label(cleared)} cleared -- the application continues")
    await _audit(db, user, "overseas.application.outcome_reopen", "overseas_application", item.id, {"cleared": cleared, "from_status": before, "to_status": item.status})
    await db.commit()
    return await _outcome_response(db, item)


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
    staff = user.role != "overseas_student"
    event = (await outcomes.latest(db, [application.id])).get(application.id) if application.outcome else None
    return {
        "status": application.status,
        "sub_status": application.sub_status,
        "outcome": outcomes.view(application, event, staff=staff),  # ccrm-015: the student's view is filtered
        "next_action": application.next_action,
        # ccrm-016 (DEC-SCOPE-247): author, notes and reason for staff only (H2); `changed_at` stays beside `created_at`
        "history": [{**h, "changed_at": h["created_at"]} for h in await status_history(db, application.id, staff=staff)],
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
            linked = await db.scalar(select(AgentStudent.id).where(AgentStudent.student_id == student_id, *student_scope(user)))
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
        uploaded_by_user_id=user.id,
        expiry_date=payload.expiry_date,
    )
    db.add(item)
    await db.flush()
    add_event(db, event="uploaded", actor=user, document=item, to_status="pending")  # AGN-009: additive history row
    await _audit(db, user, "document.upload", "student_document", item.id)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "verification_status": item.verification_status}


async def _agent_document_review(db: AsyncSession, user: User, document_id: UUID, payload: dict) -> dict:
    """AGN-003 (DEC-SCOPE-044 P3/P5/P6, spec §7): an agency member decides a PENDING document of their agency. Permission checks
    come before any read (a refused caller learns nothing about the document); the row lock makes a second agent decision see the
    first and get 409. Same notification and audit action as the counselor path, with validated metadata only."""
    if not agent_may(user, "can_verify_documents"):
        logger.warning("document_review_refused_no_permission", extra={"extra_fields": {"document_id": str(document_id), "actor_id": str(user.id)}})
        raise HTTPException(403, VERIFY_REFUSED)
    try:
        review = AgentDocumentReview.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError([{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)]) from exc
    if is_agent_staff(user) and review.verification_status != "verified":
        logger.warning(
            "document_review_refused_staff_outcome",
            extra={"extra_fields": {"document_id": str(document_id), "actor_id": str(user.id), "verification_status": review.verification_status}},
        )
        raise HTTPException(403, REVIEW_MASTER_ONLY)
    # AGN-009 (DEC-SCOPE-052 G1/G2): an agent rejecting or asking for changes says why -- after the role rule, so staff still get 403.
    notes = (review.notes or "").strip() or None
    if review.verification_status != "verified" and notes is None:
        raise HTTPException(422, REVIEW_REASON_REQUIRED)
    item = await db.scalar(select(StudentDocument).where(StudentDocument.id == document_id).with_for_update())
    if not item:
        raise HTTPException(404, "Document not found")
    if item.application_id:
        await _assigned_application(db, user, item.application_id)
    # AGN-004 G4 (adopted by AGN-003 on merging `main`): a staff member only their assigned students; a Master the agency's.
    # AGN-009: an unattached document follows its owner -- the agency record or the linked account (`document_scope`).
    elif not await in_scope(db, user, item.id):
        raise HTTPException(403, "Document is outside your assigned scope")
    if item.verification_status != "pending" or item.archived_at is not None:
        raise HTTPException(409, "This document has already been reviewed")
    item.verification_status = review.verification_status
    item.verified_by_id = user.id
    item.reviewer_notes = notes
    item.reviewed_at = datetime.now(UTC)  # ccrm-021 S5
    add_event(db, event=item.verification_status, actor=user, document=item, from_status="pending", to_status=item.verification_status, notes=notes)
    student = await db.get(User, item.student_id) if item.student_id else None  # AGN-009: an agency-only document has no account
    if student:
        await _notify_user(db, student, "Document reviewed", f"{item.document_type}: {DOCUMENT_STATUS_LABELS[item.verification_status].lower()}.", "/overseas/student/documents")
    await agency_notices.document_needs_attention(db, item, user)  # AGN-017 (DEC-SCOPE-059 N9): rejected / changes required only
    await student_document_requests.reopen_on_rejection(db, user, item)  # ccrm-020 R1: a direct student's request opens again
    await application_checklists.sync_for_documents(db, [item.id])  # ccrm-019 AC9
    member_role = user.agent_membership.role
    await _audit(db, user, "document.verify", "student_document", item.id, {**review.model_dump(), "member_role": member_role})
    await db.commit()
    logger.info(
        "agent_document_reviewed",
        extra={"extra_fields": {"document_id": str(item.id), "actor_id": str(user.id), "member_role": member_role, "verification_status": item.verification_status}},
    )
    return {"id": item.id, "verification_status": item.verification_status}


@router.patch("/overseas/documents/{document_id}/verify")
async def verify_document(document_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"counselor", "overseas_admin", "agent"}, "overseas")
    if user.role == "agent":  # AGN-003: the agent path is fully separate; the counselor/admin lines below are unchanged
        return await _agent_document_review(db, user, document_id, payload)
    try:
        review = DocumentReview.model_validate(payload)  # ccrm-021 (DEC-SCOPE-251): no longer any string
    except ValidationError as exc:
        raise RequestValidationError([{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)]) from exc
    item = await _staff_document(db, user, document_id)
    expiry = review.expiry_date or item.expiry_date
    refusal = review_refusal(item.document_type, review.verification_status, expiry, datetime.now(INDIA).date())
    if refusal:
        raise HTTPException(422, refusal)
    from_status = item.verification_status
    item.verification_status = review.verification_status
    item.verified_by_id = user.id
    item.reviewer_notes = review.notes
    item.reviewed_at = datetime.now(UTC)
    item.expiry_date = expiry
    add_event(db, event=item.verification_status, actor=user, document=item, from_status=from_status, to_status=item.verification_status, notes=item.reviewer_notes)
    student = await db.get(User, item.student_id) if item.student_id else None
    if student:
        await _notify_user(db, student, "Document reviewed", f"{item.document_type}: {DOCUMENT_STATUS_LABELS[item.verification_status].lower()}.", "/overseas/student/documents")
    await agency_notices.document_needs_attention(db, item, user)  # AGN-017 (DEC-SCOPE-059 N9): an agency document's assignee
    await student_document_requests.reopen_on_rejection(db, user, item)  # ccrm-020 R1: a direct student's request opens again
    await application_checklists.sync_for_documents(db, [item.id])  # ccrm-019 AC9
    await _audit(db, user, "document.verify", "student_document", item.id, review.model_dump(mode="json"))
    await db.commit()
    return {"id": item.id, "verification_status": item.verification_status}


async def _staff_document(db: AsyncSession, user: User, document_id: UUID) -> StudentDocument:
    """A counselor's / Overseas Admin's document to change, locked: the OVS-005 scope (its application, else an application of the
    student that the counselor holds), then 409 for a version a newer one replaced (ccrm-021 S3)."""
    item = await db.scalar(select(StudentDocument).where(StudentDocument.id == document_id).with_for_update())
    if not item:
        raise HTTPException(404, "Document not found")
    if item.application_id:
        await _assigned_application(db, user, item.application_id)
    elif user.role == "counselor":
        assigned = await db.scalar(select(OverseasApplication.id).where(OverseasApplication.student_id == item.student_id, OverseasApplication.counselor_id == user.id))
        if not assigned:
            raise HTTPException(403, "Document is outside your assigned scope")
    if item.archived_at is not None:
        raise HTTPException(409, DOCUMENT_REPLACED)
    return item


@router.post("/overseas/documents/{document_id}/versions", status_code=201)
async def replace_document_version(
    document_id: UUID,
    file: UploadFile = File(...),
    expiry_date: date | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ccrm-021 (DEC-SCOPE-251 S3): a counselor / Overseas Admin replaces a document with a new version. The new row starts at
    `pending` and points at the old one, which is archived with its file and history; nothing is overwritten."""
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    data, content_type, filename = await document_files.read_upload(file)
    old = await _staff_document(db, user, document_id)
    key = document_files.store(data, content_type)
    try:
        new = StudentDocument(
            student_id=old.student_id,
            agent_student_id=old.agent_student_id,
            application_id=old.application_id,
            document_type=old.document_type,
            document_label=old.document_label,
            file_url=key,
            verification_status="pending",
            original_filename=filename,
            content_type=content_type,
            file_size=len(data),
            uploaded_by_user_id=user.id,
            expiry_date=expiry_date or old.expiry_date,
            version_of_id=old.id,
        )
        db.add(new)
        old.archived_at = datetime.now(UTC)
        await db.flush()
        add_event(db, event="replaced", actor=user, document=old, from_status=old.verification_status, file_key=old.file_url)
        add_event(db, event="uploaded", actor=user, document=new, to_status="pending")
        await application_checklists.move_links(db, old.id, new.id)  # ccrm-019 AC9: the checklist counts the new version
        await application_checklists.sync_for_documents(db, [new.id])
        await _audit(db, user, "document.replace", "student_document", new.id, {"version_of_id": str(old.id)})
        await db.commit()
    except Exception:  # nothing was written: the stored object goes too (AGN-009's order)
        await db.rollback()
        document_files.discard(key)
        raise
    logger.info("document_version_replaced", extra={"extra_fields": {"document_id": str(new.id), "version_of_id": str(old.id), "actor_id": str(user.id)}})
    return {"id": new.id, "verification_status": new.verification_status, "version_of_id": new.version_of_id, "expiry_date": new.expiry_date}


@router.get("/overseas/documents/{document_id}/download")
async def download_student_document(document_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # OVS-005 security note (OVS-DOC-02): passports/financial evidence require
    # least-privilege access -- a raw, permanently-public object link was exposed
    # directly through the student's own generic table (same class of gap already
    # fixed for STU-007's certificates). Only the owning student, an assigned
    # Counselor/Agent, or Admin can exchange a document id for a real download URL --
    # verified here, never left to the frontend to hide.
    item = await db.get(StudentDocument, document_id)
    sensitivity = (await document_access.sensitivities(db, [item]))[item.id] if item else "standard"
    try:
        _require(user, {"overseas_student", "counselor", "overseas_admin", "agent"}, "overseas")
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
        elif user.role == "agent" and not await in_scope(db, user, item.id):  # AGN-009: safe for an agency-only document
            raise HTTPException(403, "Document is outside your assigned scope")
        if not document_access.may_see(user, sensitivity):  # ccrm-022 SD3: the central rule, whatever the route admits
            raise HTTPException(403, "This document is restricted")
    except HTTPException as refusal:
        # ccrm-022 SD4: a refused attempt on an identity/financial document is in the audit log too, committed before the 403.
        if item is not None and refusal.status_code == 403 and sensitivity != "standard":
            await _audit(db, user, "document.download", "student_document", item.id, {"role": user.role, "sensitivity": sensitivity}, outcome="denied")
            await db.commit()
        raise
    # `file_url` is stored in two shapes depending on which upload path a client used
    # (local-upload returns an already browser-servable "/local-files/..." path; the
    # S3 presign path returns a bare object key) -- normalize to a bare key so this
    # always calls `presign_download` uniformly, never trusting either shape blindly.
    key = item.file_url[len("/local-files/"):] if item.file_url.startswith("/local-files/") else item.file_url.lstrip("/")
    # AGN-009 (G9): every download is in the document's history and the audit log, committed before the link is handed out.
    add_event(db, event="downloaded", actor=user, document=item)
    await _audit(db, user, "document.download", "student_document", item.id, {"role": user.role, "sensitivity": sensitivity})
    await db.commit()
    return {"url": storage.presign_download(key), "expires_in": 900 if storage.bucket else None}


# VISA_CASE_STAGES and VISA_DECISION_DISCLAIMER live in services/agent_visa.py (AGN-012 moved them unchanged; imported above).


async def _checklist_verification(db: AsyncSession, application_id: UUID, checklist: list[str]) -> dict[str, str]:
    docs = (
        await db.scalars(
            select(StudentDocument)
            .where(StudentDocument.application_id == application_id, StudentDocument.archived_at.is_(None))
            .order_by(StudentDocument.created_at, StudentDocument.id)  # ascending, so the newest of a type wins (agent_visa)
        )
    ).all()
    latest_by_type = {d.document_type: d.verification_status for d in docs}
    return {item: latest_by_type.get(item, "not_uploaded") for item in checklist}


@router.get("/overseas/applications/{application_id}/visa-checklist")
async def get_visa_checklist(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # VISA-001-AC02: viewing the checklist is never blocked by an unverified document --
    # only *advancing* past the "checklist" stage is (enforced in `update_visa` below).
    _require(user, {"overseas_student", "counselor", "overseas_admin"}, "overseas")
    application = await _assigned_application(db, user, application_id)
    case = await db.scalar(select(VisaCase).where(VisaCase.application_id == application.id))
    # AGN-023 (DEC-SCOPE-090 H12): agency cases tell the counselor's screen why nothing can be changed any more.
    locked_reason = None
    if application.agent_id is not None:
        locked_reason = VISA_ENROLLED if application.status == "enrolled" else VISA_DECIDED if case is not None and case.decision is not None else None
    if not case:
        # No visa case has been started yet -- an honest empty state, not an error or a
        # fabricated one (the case is created by a Counselor once the application is far
        # enough along; not every application has reached that point).
        # ccrm-026 (D5): the visa template that would fill an empty checklist, so the start form can show it.
        empty = {"exists": False, "status": None, "checklist": [], "appointment_date": None, "tracking_reference": None, "locked_reason": locked_reason}
        template = await _visa_template(db, application) if user.role != "overseas_student" else None
        if template is not None:
            empty["template"] = template
        return empty
    staff = user.role != "overseas_student"
    out = {
        "exists": True,
        "id": case.id,
        "status": case.status,
        "appointment_date": case.appointment_date,
        "tracking_reference": case.tracking_reference,
        "locked_reason": locked_reason,
        "checklist": [{"item": item, "verification_status": status} for item, status in (await _checklist_verification(db, application.id, case.checklist)).items()],
    } | visa_lifecycle.view(case, staff=staff)  # ccrm-026: the lifecycle fields; the refusal reason for staff only
    if staff:  # the evidence picker (D3)
        out["documents"] = await _visa_documents(db, application.id)
    return out


async def _visa_template(db: AsyncSession, application: OverseasApplication) -> dict | None:
    """ccrm-026 (D5): the matching ccrm-018 visa template's name and document types, or None."""
    template = await checklist_templates.resolve(db, application, "visa")
    if template is None:
        return None
    return {"name": template.name, "items": [i["document_type"] for i in (await checklist_templates.view(db, template))["items"]]}


async def _visa_documents(db: AsyncSession, application_id: UUID) -> list[dict]:
    rows = await db.scalars(
        select(StudentDocument)
        .where(StudentDocument.application_id == application_id, StudentDocument.archived_at.is_(None))
        .order_by(StudentDocument.created_at.desc(), StudentDocument.id)
        .limit(50)
    )
    return [{"id": d.id, "document_type": d.document_type, "original_filename": d.original_filename} for d in rows]


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
    } | visa_lifecycle.view(case, staff=False)  # ccrm-026 (D8): the student's subset, whoever reads it


def _recheck_counselor_scope(user: User, application: OverseasApplication) -> None:
    """AGN-023 (DEC-SCOPE-090, final review I4): `_assigned_application` reads the counselor before the row lock; a swap committed in
    between would otherwise let the previous counselor write, so the write re-checks the counselor on the locked row."""
    if user.role == "counselor" and application.counselor_id != user.id:
        raise HTTPException(403, OUTSIDE_SCOPE)


async def _agency_record_archived(db: AsyncSession, application: OverseasApplication) -> bool:
    """AGN-023 (final review I1): the agency route's A15 rule -- an archived student's applications are read-only. The application's
    own record (AGN-008), else -- an application made before AGN-008 -- the agency organisation's record of the same logged-in
    student. Column reads, so the status is the committed one rather than a stale identity-map copy."""
    if application.agent_student_id is not None:
        return await db.scalar(select(AgentStudent.status).where(AgentStudent.id == application.agent_student_id)) == "archived"
    if application.student_id is None:
        return False
    org = select(AgentOrgMember.org_id).where(AgentOrgMember.user_id == application.agent_id).scalar_subquery()
    members = select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == org)
    stmt = select(AgentStudent.status).where(AgentStudent.student_id == application.student_id, AgentStudent.agent_id.in_(members)).order_by(AgentStudent.created_at).limit(1)
    return await db.scalar(stmt) == "archived"


async def _refuse_closed_agency_application(db: AsyncSession, application: OverseasApplication) -> None:
    """AGN-023 (final review I1): the agency's own closed-application refusals, with its messages, for a counselor's agency visa write."""
    outcomes.refuse_closed(application)  # withdrawn, or a ccrm-015 terminal outcome
    if await _agency_record_archived(db, application):
        raise HTTPException(409, ARCHIVED)


async def _update_agency_visa(db: AsyncSession, user: User, application: OverseasApplication, case: VisaCase, payload: dict) -> dict:
    """AGN-023 (DEC-SCOPE-090 H4, spec §4): a counselor's change to an agency visa case goes through the agency's own rules
    (agent_visa.update_case: decided lock, forward only, checklist lock, checklist gate). Lock order matches the agency route:
    the application, then the case; the expected stage is the one read under that lock. The decision stays with the agency."""
    await db.refresh(application, with_for_update=True)
    _recheck_counselor_scope(user, application)
    await _refuse_closed_agency_application(db, application)
    await db.refresh(case, with_for_update=True)
    if application.status == "enrolled":
        raise HTTPException(409, VISA_ENROLLED)
    if "decision" in payload:
        raise HTTPException(422, AGENCY_RECORDS_VISA_DECISION)
    # Final review I2: a typed body (the agency's checklist limits, a real date, the column's length) -- a bad body is 422, never 500.
    try:
        body = CounselorAgencyVisaUpdate.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError([{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)]) from exc
    sent = body.model_fields_set
    changes: dict = {"expected_stage": case.status}
    target = body.status
    if target is not None and target != case.status:
        if target not in VISA_CASE_STAGES:
            raise HTTPException(422, f"'{target}' is not a supported visa case stage -- must be one of {VISA_CASE_STAGES}.")
        changes["to_stage"] = target
    if "checklist" in sent:
        changes["checklist"] = body.checklist
    if "appointment_date" in sent:  # an explicit null clears the date, as on the agency route
        changes["appointment_date"] = body.appointment_date
    before = case.visa_status
    outcome = await update_case(db, case, changes)  # refuses a decided case, so the reference below is only set on an open one
    reference_changed = "tracking_reference" in sent and body.tracking_reference != case.tracking_reference
    if reference_changed:
        case.tracking_reference = body.tracking_reference
    if outcome is not None or reference_changed:
        await visa_lifecycle.apply_to_application(db, user, application, case, before)
        await _visa_notices(db, user, application, case, status_changed=case.visa_status != before)
        await _audit(db, user, "visa.update", "visa_case", case.id, body.model_dump(mode="json", exclude_unset=True))
    await db.commit()
    return {"id": case.id, "status": case.status}


@router.patch("/overseas/visa/{visa_id}")
async def update_visa(visa_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    item = await db.get(VisaCase, visa_id)
    if not item:
        raise HTTPException(404, "Visa case not found")
    application = await _assigned_application(db, user, item.application_id)
    await _require_bridged_visa_entitlement(db, user, application, grandfathered_since=item.created_at)
    if application.agent_id is not None:
        return await _update_agency_visa(db, user, application, item, payload)
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
    before = item.visa_status
    if before in VISA_DECISIONS:  # ccrm-026 (VC1): a recorded decision locks the case; the admin corrects it on /lifecycle
        raise HTTPException(409, VISA_DECIDED)
    for k in ("status", "tracking_reference", "checklist"):
        if k in payload:
            setattr(item, k, payload[k])
    if payload.get("appointment_date"):
        item.appointment_date = date.fromisoformat(payload["appointment_date"])
    sync_from_stage(item)
    await visa_lifecycle.apply_to_application(db, user, application, item, before)
    await _visa_notices(db, user, application, item, status_changed=item.visa_status != before)
    await _audit(db, user, "visa.update", "visa_case", item.id, payload)
    await db.commit()
    return {"id": item.id, "status": item.status}


VISA_STUDENT_URL = "/overseas/student/visa-status"


async def _visa_notices(db: AsyncSession, user: User, application: OverseasApplication, case: VisaCase, *, status_changed: bool) -> None:
    """ccrm-026 (D6, CC5): the student hears of a status change; on an agency application the other side hears of every change.
    Only the status label -- never the refusal reason."""
    text = f"visa {visa_status_label(case.visa_status).lower()}" if status_changed else "visa details updated"
    if status_changed and application.student_id and application.student_id != user.id:
        student = await db.get(User, application.student_id)
        if student:
            await _notify_user(db, student, "Visa update", f"Your visa case is now: {visa_status_label(case.visa_status)}.", VISA_STUDENT_URL)
    await agency_notices.visa_changed(db, application, user, text)


@router.patch("/overseas/visa/{visa_id}/lifecycle")
async def update_visa_lifecycle(visa_id: UUID, payload: VisaLifecycleUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-026 (DEC-SCOPE-254): the counselor (own applications, direct and agency, CC4) or the Overseas Admin records the Appendix A
    lifecycle. Lock order: the application, then the case, as the agency route. A decided case is the admin's to correct (VC1)."""
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    item = await db.get(VisaCase, visa_id)
    if not item:
        raise HTTPException(404, "Visa case not found")
    application = await _assigned_application(db, user, item.application_id)
    await _require_bridged_visa_entitlement(db, user, application, grandfathered_since=item.created_at)
    await db.refresh(application, with_for_update=True)
    _recheck_counselor_scope(user, application)
    if not (user.role == "overseas_admin" and application.outcome == "visa_refused"):  # D7: the admin may still correct a refusal
        outcomes.refuse_closed(application)
    if application.agent_id is not None and await _agency_record_archived(db, application):
        raise HTTPException(409, ARCHIVED)
    if application.status == "enrolled":
        raise HTTPException(409, VISA_ENROLLED)
    await db.refresh(item, with_for_update=True)
    before = item.visa_status
    try:
        changes = await visa_lifecycle.update(db, user, application, item, payload)
    except ChecklistGateRefused as refused:
        logger.warning("visa_gate_blocked", extra={"extra_fields": {"visa_case_id": str(item.id), "unverified_items": len(refused.unverified)}})
        raise
    if changes is not None:
        await visa_lifecycle.apply_to_application(db, user, application, item, before)
        await _visa_notices(db, user, application, item, status_changed=item.visa_status != before)
        await _audit(db, user, "visa.lifecycle", "visa_case", item.id, changes)
        await db.commit()
        logger.info("visa_lifecycle_updated", extra={"extra_fields": {"visa_case_id": str(item.id), "actor_id": str(user.id), **{k: changes[k] for k in ("from_status", "to_status", "correction")}}})
    return {"id": item.id, "status": item.status} | visa_lifecycle.view(item, staff=True)


@router.post("/overseas/visa", status_code=201)
async def create_visa_case(payload: VisaCaseCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    if payload.status not in VISA_CASE_STAGES:
        raise HTTPException(422, f"'{payload.status}' is not a supported visa case stage -- must be one of {VISA_CASE_STAGES}.")
    application = await _assigned_application(db, user, payload.application_id)
    if application.agent_id is not None:  # AGN-023 (DEC-SCOPE-090 H4): the agency's AGN-012 start rules, under the same lock order
        await db.refresh(application, with_for_update=True)
        _recheck_counselor_scope(user, application)
        await _refuse_closed_agency_application(db, application)  # final review I1: before the enrolled and offer checks
        if application.status == "enrolled":
            raise HTTPException(409, VISA_ENROLLED)
        if application.status not in OFFER_STAGES_ON:
            raise HTTPException(422, VISA_OFFER_NEEDED)
        if payload.status != "checklist":
            raise HTTPException(422, AGENCY_VISA_STARTS_AT_CHECKLIST)
    await _require_bridged_visa_entitlement(db, user, application)
    existing = await db.scalar(select(VisaCase).where(VisaCase.application_id == application.id))
    if existing:
        raise HTTPException(409, "A visa case already exists for this application")
    checklist = payload.checklist
    if not checklist:  # ccrm-026 (D5): the resolved visa template's documents
        template = await _visa_template(db, application)
        checklist = template["items"] if template else []
    item = VisaCase(
        application_id=application.id, status=payload.status, visa_status=VISA_FIRST_OF_STAGE[payload.status], appointment_date=payload.appointment_date,
        checklist=checklist, tracking_reference=payload.tracking_reference,
    )  # fmt: skip
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
    # already has, previously missing here. csc-001: a student linked to the counselor is assigned too -- the same scope the
    # Student reference picker offers (ENH-031 §5).
    if user.role == "counselor" and not await counselor_students.is_visible_student(db, user, student_id):
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
    await appointment_invites.queue(db, item, "booked")  # ccrm-038 (DEC-SCOPE-274 CA1)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "scheduled_at": item.scheduled_at, "status": item.status}


@router.patch("/overseas/appointments/{appointment_id}")
async def update_appointment(appointment_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"counselor", "overseas_admin"}, "overseas")
    item = await db.get(Appointment, appointment_id)
    # tel-016 AP12: a lead's appointment moves only through /lead-appointments (its lifecycle and the lead's stage), never this PATCH.
    if not item or item.division != "overseas" or item.lead_id is not None:
        raise HTTPException(404, "Appointment not found")
    if user.role == "counselor" and item.staff_id != user.id:
        raise HTTPException(403, "Appointment is outside your assigned scope")
    was_cancelled, old_time = item.status in appointment_invites.CANCELLED, item.scheduled_at
    for key in {"appointment_type", "mode", "status"}:
        if key in payload:
            setattr(item, key, payload[key])
    if payload.get("scheduled_at"):
        item.scheduled_at = datetime.fromisoformat(payload["scheduled_at"])
    await _audit(db, user, "appointment.update", "appointment", item.id, payload)
    # ccrm-038 (CA1): a cancellation or a new time re-sends the invite; other edits send nothing
    if not was_cancelled and item.status in appointment_invites.CANCELLED:
        await appointment_invites.queue(db, item, "cancelled")
    elif not was_cancelled and item.scheduled_at != old_time:
        await appointment_invites.queue(db, item, "rescheduled")
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
    # AGN-004: archived links leave this list (D5); a staff member sees only their assigned students (G4).
    rows = (
        await db.execute(
            select(AgentStudent, User).join(User, User.id == AgentStudent.student_id).where(*student_scope(user), AgentStudent.status == "active").order_by(User.full_name)
        )
    ).all()
    return [{"link_id": link.id, "student_id": student.id, "student": student.full_name, "email": student.email, "phone": student.phone, "status": link.status} for link, student in rows]


@router.post("/overseas/agent/students", status_code=201)
async def add_agent_student(payload: AgentStudentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"agent"}, "overseas")
    student = await db.get(User, payload.student_id)
    if not student or student.role != "overseas_student" or student.division != "overseas":
        raise HTTPException(404, "Overseas student not found")
    if user.agent_membership is not None:
        await lock_org(db, user.agent_membership.org_id)  # AGN-001 (E12): serialise this organisation's links
    # Organisation-wide on purpose: a staff member must not re-link another staff member's student.
    existing = await db.scalar(select(AgentStudent.status).where(AgentStudent.agent_id.in_(org_member_ids(user)), AgentStudent.student_id == student.id))
    if existing:
        raise HTTPException(409, "This student is archived — unarchive them first" if existing == "archived" else "Student is already linked to this agency")
    assigned = user.agent_membership.id if is_agent_staff(user) else None  # AGN-004 D4: a staff member's link is theirs
    item = AgentStudent(agent_id=user.id, student_id=student.id, status="active", assigned_member_id=assigned)
    db.add(item)
    await db.flush()
    await _audit(db, user, "agent.student_link", "agent_student", item.id, {"student_id": student.id, **({"assigned_member_id": str(assigned)} if assigned else {})})
    await db.commit()
    return {"id": item.id, "status": item.status}


@router.get("/overseas/agent/commissions")
async def agent_commissions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"agent"}, "overseas")
    _require_agent_master(user)
    rows = owned(
        (
            await db.execute(
                with_owner(
                    select(AgentCommission, OverseasApplication, University)
                    .select_from(AgentCommission)
                    .join(OverseasApplication, OverseasApplication.id == AgentCommission.application_id)
                    .join(University, University.id == OverseasApplication.university_id)
                )
                .where(AgentCommission.agent_id.in_(org_member_ids(user)))
                .order_by(AgentCommission.created_at.desc())
            )
        ).all()
    )
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


# AGN-014 (DEC-SCOPE-051): the agency's commission report, Master-only like the list above. `by_status` is in lifecycle order.
COMMISSION_STATUS_RANK = {status: rank for rank, status in enumerate(("estimated", "eligible", "claimed", "payout_pending", "paid"))}
# Strings, not `date`: FastAPI would answer a bad date with 422 before the Master check (spec §5.1). Documented for OpenAPI here.
REPORT_DATE_FROM = Query(None, description="Optional. YYYY-MM-DD: the first UTC day (inclusive) of the commissions' created date.")
REPORT_DATE_TO = Query(None, description="Optional. YYYY-MM-DD: the last UTC day (inclusive) of the commissions' created date; before 9999-12-31.")
_YYYY_MM_DD = re.compile(r"\d{4}-\d{2}-\d{2}")


def _report_date(value: str | None, name: str) -> date | None:
    if not value:
        return None
    # fullmatch first: `date.fromisoformat` also takes "20260930" and ISO week dates, which the contract does not offer.
    if _YYYY_MM_DD.fullmatch(value):
        with contextlib.suppress(ValueError):  # e.g. 2026-02-30
            return date.fromisoformat(value)
    raise HTTPException(422, f"{name} must be a date (YYYY-MM-DD)")


def report_range(date_from: str | None, date_to: str | None) -> tuple[date | None, date | None]:
    """An optional inclusive range of UTC days (AGN-014 R3; reused by AGN-019). Call it after the caller's guards, so a refused
    caller never sees a 422."""
    start, end = _report_date(date_from, "date_from"), _report_date(date_to, "date_to")
    if start and end and end < start:
        raise HTTPException(422, "date_to must be on or after date_from")
    if end == date.max:  # the exclusive bound is the next day, which does not exist (a date input accepts 9999-12-31)
        raise HTTPException(422, "date_to must be before 9999-12-31")
    return start, end


async def _commission_report_items(user: User, db: AsyncSession, date_from: str | None, date_to: str | None) -> tuple[list[dict], date | None, date | None]:
    """Guards first, then the dates (a refused caller never sees a 422), then one scoped read: a single snapshot for every
    breakdown. Days are inclusive UTC calendar days on the commission's created date (R3/R7)."""
    _require(user, {"agent"}, "overseas")
    _require_agent_master(user)
    start, end = report_range(date_from, date_to)
    query = (
        select(AgentCommission, OverseasApplication.intake, University.name, Country.name, func.coalesce(User.full_name, SchoolStudent.full_name))
        .select_from(AgentCommission)
        .join(OverseasApplication, OverseasApplication.id == AgentCommission.application_id)
        .join(University, University.id == OverseasApplication.university_id)
        .join(Country, Country.id == University.country_id)
        # A bridged school-student application has no login (`student_id` NULL): outer joins, never an inner join on User.
        .outerjoin(User, User.id == OverseasApplication.student_id)
        .outerjoin(SchoolStudent, SchoolStudent.id == OverseasApplication.school_student_id)
        .where(AgentCommission.agent_id.in_(org_member_ids(user)))
        .order_by(AgentCommission.created_at, AgentCommission.id)
    )
    if start:
        query = query.where(AgentCommission.created_at >= datetime.combine(start, time.min, tzinfo=UTC))
    if end:
        query = query.where(AgentCommission.created_at < datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC))
    items = [
        {
            "student": student or "—", "university": university, "country": country, "intake": intake,
            "status": commission.status, "amount": Decimal(commission.amount), "currency": commission.currency,
            "created_at": commission.created_at, "claimed_at": commission.claimed_at, "paid_at": commission.paid_at,
            "claim_reference": commission.claim_reference,
        }
        for commission, intake, university, country, student in (await db.execute(query)).all()
    ]
    return items, start, end


def _commission_groups(items: list[dict], keys: tuple[str, ...]) -> list[dict]:
    """Count and amount per (keys..., currency) -- currencies are never added together."""
    groups: dict[tuple, dict] = {}
    for item in items:
        group = groups.setdefault(
            tuple(item[k] for k in keys) + (item["currency"],),
            {**{k: item[k] for k in keys}, "currency": item["currency"], "count": 0, "amount": Decimal(0)},
        )
        group["count"] += 1
        group["amount"] += item["amount"]
    return [{**group, "amount": float(round(group["amount"], 2))} for group in groups.values()]


def _ranked(groups: list[dict], keys: tuple[str, ...]) -> list[dict]:
    return sorted(groups, key=lambda g: (-g["amount"], *(g[k] for k in keys), g["currency"]))


def _report_logged(user: User, fmt: str, rows: int, start: date | None, end: date | None) -> None:
    membership = user.agent_membership
    logger.info("agent_commission_report", extra={"extra_fields": {
        "actor_id": str(user.id), "org_id": str(membership.org_id) if membership else None, "format": fmt, "rows": rows,
        "date_from": start.isoformat() if start else None, "date_to": end.isoformat() if end else None,
    }})


@router.get("/overseas/agent/commissions/report", response_model=CommissionReportOut)
async def agent_commission_report(date_from: str | None = REPORT_DATE_FROM, date_to: str | None = REPORT_DATE_TO, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items, start, end = await _commission_report_items(user, db, date_from, date_to)
    _report_logged(user, "json", len(items), start, end)
    unknown_last = len(COMMISSION_STATUS_RANK)
    return {
        "date_from": start, "date_to": end,
        "totals": sorted(_commission_groups(items, ()), key=lambda g: g["currency"]),
        "by_status": sorted(_commission_groups(items, ("status",)), key=lambda g: (COMMISSION_STATUS_RANK.get(g["status"], unknown_last), g["status"], g["currency"])),
        "by_university": _ranked(_commission_groups(items, ("university", "country")), ("university", "country")),
        "by_country": _ranked(_commission_groups(items, ("country",)), ("country",)),
        "by_intake": _ranked(_commission_groups(items, ("intake",)), ("intake",)),
    }


COMMISSION_CSV_COLUMNS = ("Student", "University", "Country", "Intake", "Status", "Amount", "Currency", "Created", "Claimed", "Paid", "Claim reference")


def _csv_day(value: datetime | None) -> str:
    return value.astimezone(UTC).date().isoformat() if value else ""


@router.get("/overseas/agent/commissions/report.csv")
async def agent_commission_report_csv(date_from: str | None = REPORT_DATE_FROM, date_to: str | None = REPORT_DATE_TO, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-014 R4: one row per commission. Every text cell goes through `_safe_cell` -- names and references are user-entered."""
    items, start, end = await _commission_report_items(user, db, date_from, date_to)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COMMISSION_CSV_COLUMNS)
    for item in items:
        writer.writerow([
            _safe_cell(item["student"]), _safe_cell(item["university"]), _safe_cell(item["country"]), _safe_cell(item["intake"]),
            item["status"], f"{item['amount']:.2f}", _safe_cell(item["currency"]), _csv_day(item["created_at"]),
            _csv_day(item["claimed_at"]), _csv_day(item["paid_at"]), _safe_cell(item["claim_reference"] or ""),
        ])
    _report_logged(user, "csv", len(items), start, end)
    filename = f"agency-commissions-{start.isoformat() if start else 'all'}-to-{end.isoformat() if end else 'all'}.csv"
    return Response(
        content=buffer.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}", "Cache-Control": "private, no-store"},
    )


@router.get("/overseas/agent/commissions/report.xlsx")
async def agent_commission_report_xlsx(date_from: str | None = REPORT_DATE_FROM, date_to: str | None = REPORT_DATE_TO, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-004 (DEC-SCOPE-282 X3, X4): the CSV's twin -- the same rows, the amount a number and the days date cells; logged, not
    audited, as the CSV is (AGN-014)."""
    items, start, end = await _commission_report_items(user, db, date_from, date_to)
    keys = ("student", "university", "country", "intake", "status", "amount", "currency", "created_at", "claimed_at", "paid_at", "claim_reference")
    days = {"created_at", "claimed_at", "paid_at"}
    table = {
        "columns": [{"key": key, "label": label} for key, label in zip(keys, COMMISSION_CSV_COLUMNS, strict=True)],
        "items": [{key: _csv_day(item[key]) if key in days else item[key] for key in keys} for item in items],
        "totals": None,
    }
    body = to_xlsx(table, "Commissions")
    _report_logged(user, "xlsx", len(items), start, end)
    filename = f"agency-commissions-{start.isoformat() if start else 'all'}-to-{end.isoformat() if end else 'all'}.xlsx"
    return Response(content=body, media_type=XLSX_TYPE, headers={"Content-Disposition": f"attachment; filename={filename}", "Cache-Control": "private, no-store"})


@router.post("/overseas/agent/commissions/{commission_id}/claim")
async def claim_commission(commission_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"agent"}, "overseas")
    _require_agent_master(user)
    # AGN-001: organisation scope, and a row lock so two Masters claiming one commission claim it once.
    item = await db.scalar(
        select(AgentCommission).where(AgentCommission.id == commission_id, AgentCommission.agent_id.in_(org_member_ids(user))).with_for_update().execution_options(populate_existing=True)
    )
    if not item:
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
    for recipient in await notification_recipients(db, agent):  # AGN-001 (D12): every active Master
        await _notify_user(db, recipient, "Commission eligible", f"A {payload.currency} {payload.amount:,.2f} commission is available to claim.", "/overseas/agent/commissions")
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


@router.get("/notifications/unread-count", response_model=NotificationUnreadCount)
async def unread_notification_count(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-017 (DEC-SCOPE-059 N7): the caller's own unread count (it may exceed the newest-100 list above)."""
    count = await db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read.is_(False)))
    return {"unread": count or 0}


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

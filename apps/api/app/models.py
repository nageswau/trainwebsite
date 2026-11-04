from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Sequence,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column, relationship, validates
from sqlalchemy.sql import func

from app.application_checklists import MARKS as CHECKLIST_MARKS
from app.application_fields import CURRENCIES as APPLICATION_CURRENCIES
from app.application_fields import SCHOLARSHIP_STATUSES
from app.application_outcome import CLEARED as OUTCOME_CLEARED
from app.application_outcome import OUTCOMES as APPLICATION_OUTCOMES
from app.application_outcome import REQUESTERS as OUTCOME_REQUESTERS
from app.application_sub_status import fit as fit_sub_status
from app.bdm_stages import FIRST_STAGE as BDM_FIRST_STAGE
from app.bdm_stages import MANUAL_STAGES as BDM_MANUAL_STAGES
from app.core.identifiers import normalize_key
from app.document_checklists import CHECKLIST_GATE_MODES, CHECKLIST_KINDS, ITEM_STATUSES, SENSITIVITY_CLASSES
from app.lead_stages import LOSS_STAGES
from app.lead_stages import STAGES as LEAD_STAGES
from app.notifications.phone import normalise_phone
from app.partnership_event_kinds import KINDS as PARTNERSHIP_EVENT_KINDS
from app.partnership_event_kinds import STATUSES as PARTNERSHIP_EVENT_STATUSES
from app.partnership_meeting_types import EVENTS as UNIVERSITY_MEETING_EVENTS
from app.partnership_meeting_types import MODES as UNIVERSITY_MEETING_MODES
from app.partnership_meeting_types import STATUSES as UNIVERSITY_MEETING_STATUSES
from app.partnership_meeting_types import TYPES as UNIVERSITY_MEETING_TYPES
from app.partnership_milestones import MILESTONE_KEYS as UNIVERSITY_MILESTONE_KEYS
from app.partnership_onboarding import ITEM_KEYS as ONBOARDING_ITEM_KEYS
from app.partnership_onboarding import NOTE_MAX as ONBOARDING_NOTE_MAX
from app.partnership_onboarding import STATUSES as ONBOARDING_STATUSES
from app.partnership_stages import FIRST_STAGE as UNIVERSITY_FIRST_STAGE
from app.partnership_stages import STAGE_KEYS as UNIVERSITY_STAGE_KEYS
from app.partnership_target_kpis import KPI_KEYS as PARTNERSHIP_TARGET_KPI_KEYS
from app.partnership_target_kpis import TARGET_MAX as PARTNERSHIP_TARGET_MAX
from app.partnership_task_rules import KINDS as PARTNERSHIP_TASK_KINDS
from app.partnership_task_rules import PRIORITIES as PARTNERSHIP_TASK_PRIORITIES
from app.partnership_task_rules import SOURCES as PARTNERSHIP_TASK_SOURCES
from app.partnership_task_rules import STATUSES as PARTNERSHIP_TASK_STATUSES
from app.recruiter_stages import FIRST_STAGE as COMPANY_FIRST_STAGE
from app.recruiter_stages import ORDER as COMPANY_STAGES
from app.tel_content_kinds import ASSET_KINDS as TEL_ASSET_KINDS
from app.tel_content_kinds import EMAIL_KINDS as TEL_EMAIL_KINDS
from app.tel_content_kinds import WHATSAPP_KINDS as TEL_WHATSAPP_KINDS
from app.tel_sources import TEL_SOURCES
from app.visa_status import VISA_STATUSES


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(50), index=True)
    division: Mapped[str] = mapped_column(String(30), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    locale: Mapped[str] = mapped_column(String(12), default="en-GB")
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    # Business-facing unique Student ID (PRD_OPEN_ITEMS.md item 66 / CLIENT_QUESTIONS.md
    # D-09), resolved 2026-09-15: 8-character alphanumeric, all students, format left to
    # implementation -- reuses this codebase's own existing short-code convention
    # (secrets.token_hex(N).upper(), see enrollment_code/certificate_no) rather than
    # inventing a new alphabet. Only it_student/overseas_student rows get one; every other
    # role's value stays NULL (multiple NULLs are fine under a unique constraint).
    student_code: Mapped[str | None] = mapped_column(String(8), unique=True, nullable=True, index=True)
    role_assignments: Mapped[list["UserRoleAssignment"]] = relationship(
        foreign_keys="UserRoleAssignment.user_id", viewonly=True, order_by="UserRoleAssignment.assigned_at"
    )
    # AGN-001: eager-loaded (with `.org`) by `deps.get_current_user` for every request; `lazy="raise"` makes any other
    # unloaded access fail loudly instead of an async lazy-load crash.
    agent_membership: Mapped["AgentOrgMember | None"] = relationship(
        foreign_keys="AgentOrgMember.user_id", viewonly=True, uselist=False, lazy="raise"
    )
    # AGN-002 (DEC-SCOPE-040 S3, spec §5): copied into every token as `sv`; a staff reset or deactivation increments it, which ends
    # every session issued before. Tokens without the claim count as 0.
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class UserRoleAssignment(Base, TimestampMixin):
    """Division-aware role assignment, per DATA_MODEL.md §1.1.

    Separates identity (User) from role-assignment so one User can hold more than one
    active assignment -- specifically an it_student + overseas_student pair under
    DEC-ROLE-001's "same identity, extended" resolution. User.role/User.division remain
    as a back-compat primary-assignment cache the existing base-codebase routes already
    read; this table is the source of truth for deny-by-default authorization going
    forward (app.core.rbac).
    """

    __tablename__ = "user_role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "division", "role", name="uq_role_assignment_identity"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    division: Mapped[str] = mapped_column(String(30), index=True)
    role: Mapped[str] = mapped_column(String(50), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # Agent approval gate (DATA_MODEL.md §1.3) -- only meaningful for role="agent";
    # every other role defaults to "approved" and the field is otherwise unused.
    approval_status: Mapped[str] = mapped_column(String(20), default="approved")
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class Program(Base, TimestampMixin):
    __tablename__ = "programs"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    duration: Mapped[str] = mapped_column(String(80))
    eligibility: Mapped[str] = mapped_column(Text)
    fees: Mapped[float] = mapped_column(Numeric(12, 2))
    certification: Mapped[str] = mapped_column(String(200))
    curriculum: Mapped[list] = mapped_column(JSON, default=list)
    placement_assistance: Mapped[str] = mapped_column(Text)
    trainer_name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # PUB-025 (DEC-SCOPE-334): an optional card image, and ONE syllabus source -- "manual" (modules), "link" (Drive/https) or "pdf".
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    syllabus_source: Mapped[str | None] = mapped_column(String(10), nullable=True)
    syllabus_modules: Mapped[list] = mapped_column(JSON, default=list)
    syllabus_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    syllabus_pdf_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    __table_args__ = (CheckConstraint("syllabus_source IS NULL OR syllabus_source IN ('manual', 'link', 'pdf')", name="ck_programs_syllabus_source"),)

    @property
    def syllabus(self) -> dict | None:
        """PUB-025 S1: the public view of the ONE active source, or None (the page then falls back to the curriculum list)."""
        if self.syllabus_source == "manual" and self.syllabus_modules:
            return {"source": "manual", "modules": self.syllabus_modules}
        if self.syllabus_source == "link" and self.syllabus_url:
            return {"source": "link", "url": self.syllabus_url}
        if self.syllabus_source == "pdf" and self.syllabus_pdf_url:
            return {"source": "pdf", "url": self.syllabus_pdf_url}
        return None


class Batch(Base, TimestampMixin):
    __tablename__ = "batches"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("programs.id"), index=True)
    trainer_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    schedule: Mapped[str] = mapped_column(String(160))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    capacity: Mapped[int] = mapped_column(Integer, default=20)
    enrollment_open: Mapped[bool] = mapped_column(Boolean, default=True)
    mode: Mapped[str] = mapped_column(String(30), default="Online")
    status: Mapped[str] = mapped_column(String(30), default="upcoming")
    program = relationship("Program")


# itc-031 (DEC-SCOPE-359 L9): the enrolment statuses in use (was free text). Migration 0241 repeats them (test_itc_031_migration).
ENROLLMENT_STATUSES = ("pending_consent", "active", "rejected", "withdrawn", "dropped", "completed")


class Enrollment(Base, TimestampMixin):
    __tablename__ = "enrollments"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"), index=True)
    enrollment_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    enrolled_on: Mapped[date] = mapped_column(Date, default=date.today)
    slot_locked: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    # itc-012 (DEC-SCOPE-345): per-student overrides; NULL means "the batch's" (`batches.start_date/end_date/mode`). Nothing copies the
    # batch here, so a batch change never overwrites an override.
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # itc-031 (DEC-SCOPE-359 L4): the only hand-set lifecycle facts -- "not_placed" or "closed" -- set by the IT Admin with a reason. The stage
    # itself is never stored: services/it_lifecycle.py derives it from the source records on every read.
    lifecycle_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lifecycle_override_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # itc-022 (DEC-SCOPE-365 P5): set = the trainer's `progress_percent` overrides the computed figure (services/it_progress.py)
    progress_override_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    __table_args__ = (
        UniqueConstraint("student_id", "batch_id", name="uq_enrollment_student_batch"),
        CheckConstraint("status IN (" + ", ".join(f"'{s}'" for s in ENROLLMENT_STATUSES) + ")", name="ck_enrollments_status"),
        CheckConstraint("lifecycle_override IS NULL OR lifecycle_override IN ('not_placed', 'closed')", name="ck_enrollments_lifecycle_override"),
    )


class EnrollmentLifecycleHistory(Base):
    """itc-031 (DEC-SCOPE-359 L6): append-only lifecycle transitions of an enrolment, written by `it_lifecycle.sync` when the derived stage
    differs from the last row (`from_stage` NULL = the first row). `actor_user_id` NULL = the system. Never read back as the current stage."""

    __tablename__ = "enrollment_lifecycle_history"
    __table_args__ = (Index("ix_enrollment_lifecycle_history_enrollment", "enrollment_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"))
    from_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(20))
    cause: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BatchTimetableSlot(Base, TimestampMixin):
    """itc-020 (DEC-SCOPE-344): one weekly class of a batch -- `weekday` 0=Mon..6=Sun, local times in the batch's timezone. Dated
    classes are computed from these rows (`services/batch_timetable.py`), never stored (T1)."""

    __tablename__ = "batch_timetable_slots"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_batch_timetable_slots_weekday"),
        CheckConstraint("end_time > start_time", name="ck_batch_timetable_slots_times"),
        CheckConstraint("mode IN ('online', 'offline')", name="ck_batch_timetable_slots_mode"),
        CheckConstraint("mode = 'online' OR room IS NOT NULL", name="ck_batch_timetable_slots_room"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    mode: Mapped[str] = mapped_column(String(10))
    room: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(160), nullable=True)


class BatchTimetableCancellation(Base, TimestampMixin):
    """itc-020 (DEC-SCOPE-344): one cancelled class -- a slot on one date. Students no longer see it; staff see it with the reason."""

    __tablename__ = "batch_timetable_cancellations"
    __table_args__ = (UniqueConstraint("slot_id", "occurs_on", name="uq_batch_timetable_cancellations_slot_day"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    slot_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batch_timetable_slots.id", ondelete="CASCADE"))
    occurs_on: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    cancelled_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


TRAINER_CONTACT_ROUTES = ("in_app", "email", "phone")


class TrainerProfile(Base, TimestampMixin):
    """itc-019 (DEC-SCOPE-347): what a trainer shows their students. Email and phone stay on the user account; the `show_*` flags decide
    what a student response may carry (F1: email/phone hidden by default). `photo_key` is a private storage key (signed links only)."""

    __tablename__ = "trainer_profiles"
    __table_args__ = (CheckConstraint("contact_route IN ('in_app', 'email', 'phone')", name="ck_trainer_profiles_contact_route"),)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expertise: Mapped[list] = mapped_column(JSON, default=list)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    office_hours: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contact_route: Mapped[str] = mapped_column(String(10), default="in_app")
    show_email: Mapped[bool] = mapped_column(Boolean, default=False)
    show_phone: Mapped[bool] = mapped_column(Boolean, default=False)
    show_photo: Mapped[bool] = mapped_column(Boolean, default=True)
    show_bio: Mapped[bool] = mapped_column(Boolean, default=True)
    show_office_hours: Mapped[bool] = mapped_column(Boolean, default=True)
    photo_key: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Agreement(Base, TimestampMixin):
    __tablename__ = "agreements"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True, default="it")
    version: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # ccrm-040 (DEC-SCOPE-276 CN1): what the student agrees to -- the IT enrolment agreement, or the overseas data-processing and
    # document-sharing consents. The latest active row of a (division, kind) is the current one.
    kind: Mapped[str] = mapped_column(String(30), default="enrolment", server_default="enrolment")


class ConsentRecord(Base, TimestampMixin):
    """STU-009 -- DATA_MODEL.md §3.4. `created_at` (via TimestampMixin) is the acceptance
    timestamp; a record is only ever inserted, never updated, so it doubles as `accepted_at`."""

    __tablename__ = "consent_records"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    agreement_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agreements.id"), index=True)
    version: Mapped[str] = mapped_column(String(20))
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (UniqueConstraint("user_id", "agreement_id", name="uq_consent_user_agreement"),)


class Attendance(Base, TimestampMixin):
    __tablename__ = "attendance"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20))  # itc-021 (DEC-SCOPE-349 L1): "excused" is shown as "Approved leave"
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # itc-021 (L4/L5): who last set the status (NULL on rows marked before 0232) and the day's single live session, when there is one.
    marked_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    session_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("live_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("student_id", "batch_id", "session_date", name="uq_attendance_student_batch_date"),)


class AttendanceCorrection(Base, TimestampMixin):
    __tablename__ = "attendance_corrections"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    attendance_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("attendance.id"), index=True)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    requested_status: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    reviewed_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Assignment(Base, TimestampMixin):
    __tablename__ = "assignments"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_score: Mapped[int] = mapped_column(Integer, default=100)
    assignment_type: Mapped[str] = mapped_column(String(30), default="assignment")
    submission_type: Mapped[str] = mapped_column(String(30), default="text_or_file")
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class Assessment(Base, TimestampMixin):
    __tablename__ = "assessments"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_score: Mapped[int] = mapped_column(Integer, default=100)
    pass_percent: Mapped[int] = mapped_column(Integer, default=50)
    attempts_allowed: Mapped[int] = mapped_column(Integer, default=1)
    instructions: Mapped[str] = mapped_column(Text, default="")
    publish_results: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")


class AssessmentQuestion(Base, TimestampMixin):
    __tablename__ = "assessment_questions"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    assessment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    question_type: Mapped[str] = mapped_column(String(30), default="mcq_single")
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)
    correct_answers: Mapped[list] = mapped_column(JSON, default=list)
    max_score: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer, default=1)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")  # nehn-026: text questions only; never sent to students


class AssessmentAttempt(Base, TimestampMixin):
    __tablename__ = "assessment_attempts"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    assessment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="in_progress")
    score: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    percentage: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("assessment_id", "student_id", "attempt_no", name="uq_assessment_student_attempt"),)


class AssessmentAnswer(Base, TimestampMixin):
    __tablename__ = "assessment_answers"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assessment_attempts.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assessment_questions.id", ondelete="CASCADE"), index=True)
    answer: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    # nehn-026: the keyword suggestion (kept after a trainer override) and who set `score` -- mcq | keyword | trainer; NULL = not scored yet
    auto_score: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    score_source: Mapped[str | None] = mapped_column(String(10), nullable=True)
    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question_answer"),)


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assignments.id"), index=True)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)
    graded_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_submission_assignment_student"),)


class LearningResource(Base, TimestampMixin):
    __tablename__ = "learning_resources"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    resource_type: Mapped[str] = mapped_column(String(30))
    # nehn-027 (DEC-SCOPE-294 M1): a resource is a link (`url`) or an uploaded file (`stored_file_id`; filename, size and type live on
    # the `stored_files` row). `deleted_at` hides it everywhere; `sort_order` orders a batch's list.
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stored_file_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("stored_file_id", name="uq_learning_resources_stored_file"),)

    @property
    def href(self) -> str | None:
        """What a reader opens: the link, or the authorised download route for an uploaded file (nehn-027 M7)."""
        return f"/api/v1/workflows/it/materials/{self.id}/file" if self.stored_file_id else self.url


class Certificate(Base, TimestampMixin):
    __tablename__ = "certificates"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("programs.id"), index=True)
    enrollment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id"), nullable=True, index=True)
    certificate_no: Mapped[str] = mapped_column(String(80), unique=True)
    verification_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    issued_on: Mapped[date] = mapped_column(Date)
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approved_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criteria_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="issued")
    # nehn-032 (DEC-SCOPE-302 S7): the signatory versions drawn on the PDF, [{id, role, display_name, designation}]; NULL before nehn-032.
    signatory_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)


class CertificateSignatory(Base, TimestampMixin):
    """nehn-032 (DEC-SCOPE-302 S1/S2): one version of the Founder's or Coordinator's certificate signature. A new image closes the active
    row (`active_to`) and inserts another, so an issued certificate's snapshot always names the version it was signed with."""

    __tablename__ = "certificate_signatories"
    __table_args__ = (
        CheckConstraint("role IN ('founder', 'coordinator')", name="ck_certificate_signatories_role"),
        Index("uq_certificate_signatories_active_role", "role", unique=True, postgresql_where=text("active_to IS NULL")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    role: Mapped[str] = mapped_column(String(20))
    display_name: Mapped[str] = mapped_column(String(120))
    designation: Mapped[str] = mapped_column(String(120))
    image_key: Mapped[str] = mapped_column(String(200))
    active_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    active_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


# itc-021 (DEC-SCOPE-349 L2): how approved leave ("excused") counts in the attendance %: as attended, left out, or as absent.
LEAVE_POLICIES = ("attended", "excluded", "absent")


class CertificateRule(Base, TimestampMixin):
    """nehn-031 (DEC-SCOPE-297 W1): the eligibility thresholds, one row for the IT division (tel_settings' keyed-row idiom). The other
    conditions stay fixed in code."""

    __tablename__ = "certificate_rules"
    __table_args__ = (
        CheckConstraint("division = 'it'", name="ck_certificate_rules_division"),
        CheckConstraint("min_progress_percent BETWEEN 0 AND 100 AND min_attendance_percent BETWEEN 0 AND 100", name="ck_certificate_rules_percent"),
        CheckConstraint(f"leave_policy IN ({', '.join(repr(p) for p in LEAVE_POLICIES)})", name="ck_certificate_rules_leave_policy"),
    )
    division: Mapped[str] = mapped_column(String(20), primary_key=True, default="it")
    min_progress_percent: Mapped[int] = mapped_column(Integer, default=100)
    min_attendance_percent: Mapped[int] = mapped_column(Integer, default=75)
    leave_policy: Mapped[str] = mapped_column(String(20), default="attended", server_default=text("'attended'"))  # itc-021 L2
    updated_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class ItRiskThreshold(Base, TimestampMixin):
    """itc-023 (DEC-SCOPE-352 R1): one programme's at-risk thresholds. NULL turns a criterion off; no row (or all off) = not monitored.
    `min_sessions`: the attendance-% criterion waits for that many counted sessions (the first week)."""

    __tablename__ = "it_risk_thresholds"
    __table_args__ = (
        CheckConstraint("min_attendance_percent BETWEEN 0 AND 100 AND min_assessment_percent BETWEEN 0 AND 100", name="ck_it_risk_thresholds_percent"),
        CheckConstraint("max_consecutive_absences BETWEEN 1 AND 60 AND min_sessions BETWEEN 1 AND 60", name="ck_it_risk_thresholds_counts"),
    )
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True)
    min_attendance_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_assessment_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_consecutive_absences: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_sessions: Mapped[int] = mapped_column(Integer, default=3, server_default=text("3"))
    updated_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class StudentRiskFlag(Base, TimestampMixin):
    """itc-023 (R4): one at-risk episode of an enrolment -- raised by the daily sweep, `cleared_at` set when it ends (`clear_reason`
    'recovered', or 'stopped' when the enrolment/programme left monitoring). At most one open flag per enrolment (partial unique index),
    so two sweeps can never both raise one. The figures are the last check's."""

    __tablename__ = "student_risk_flags"
    __table_args__ = (
        Index("uq_student_risk_flags_open", "enrollment_id", unique=True, postgresql_where=text("cleared_at IS NULL")),
        CheckConstraint("clear_reason IS NULL OR clear_reason IN ('recovered', 'stopped')", name="ck_student_risk_flags_clear_reason"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"), index=True)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    attendance_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    assessment_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    consecutive_absences: Mapped[int] = mapped_column(Integer, default=0)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clear_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ItProgressFormula(Base, TimestampMixin):
    """itc-022 (DEC-SCOPE-365 P3): one programme's computed-progress weights, summing to 100. No row = progress stays manual."""

    __tablename__ = "it_progress_formulas"
    __table_args__ = (
        CheckConstraint(
            "topics_weight BETWEEN 0 AND 100 AND assignments_weight BETWEEN 0 AND 100 AND assessments_weight BETWEEN 0 AND 100",
            name="ck_it_progress_formulas_range",
        ),
        CheckConstraint("topics_weight + assignments_weight + assessments_weight = 100", name="ck_it_progress_formulas_sum"),
    )
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True)
    topics_weight: Mapped[int] = mapped_column(Integer)
    assignments_weight: Mapped[int] = mapped_column(Integer)
    assessments_weight: Mapped[int] = mapped_column(Integer)
    updated_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class ProgramModule(Base, TimestampMixin):
    """itc-022 (P1): an ordered module of a programme's progress plan (the structured twin of the curriculum JSON)."""

    __tablename__ = "program_modules"
    __table_args__ = (Index("ix_program_modules_program_position", "program_id", "position"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)


class ProgramTopic(Base, TimestampMixin):
    """itc-022 (P1): an ordered topic of a module; the unit a trainer marks complete per student."""

    __tablename__ = "program_topics"
    __table_args__ = (Index("ix_program_topics_module_position", "module_id", "position"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    module_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("program_modules.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)


class TopicCompletion(Base):
    """itc-022 (P6): one student's (enrolment's) completed topic. Unique per pair, so a repeated bulk mark is a no-op."""

    __tablename__ = "topic_completions"
    __table_args__ = (UniqueConstraint("topic_id", "enrollment_id", name="uq_topic_completions_topic_enrollment"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("program_topics.id", ondelete="CASCADE"))
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), index=True)
    completed_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


REMEDIATION_STATUSES = ("open", "in_progress", "completed", "cancelled")  # migration 0249 freezes a copy


class RemediationPlan(Base, TimestampMixin):
    """itc-022 (P9): actions agreed for a student who needs help, with an owner and a due date; linked to the open itc-023 flag at
    creation when there is one. Only for an active enrolment (AC3)."""

    __tablename__ = "remediation_plans"
    __table_args__ = (CheckConstraint("status IN (" + ", ".join(f"'{s}'" for s in REMEDIATION_STATUSES) + ")", name="ck_remediation_plans_status"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    risk_flag_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("student_risk_flags.id", ondelete="SET NULL"), nullable=True)
    actions: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    created_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


STUDENT_ACCESS_FEATURES = ("attendance", "assignments", "assessments", "resources", "live_classes", "questions", "feedback", "certificates")
STUDENT_PAYMENT_STATES = ("registered", "enrolled_pending_payment", "partially_paid", "fully_paid")  # lowest first


class StudentAccessRule(Base, TimestampMixin):
    """nehn-018 (DEC-SCOPE-304): the lowest payment state at which an IT student may use one feature -- one row per feature, the
    certificate_rules keyed-row idiom. A missing row means the default (services/student_access.py)."""

    __tablename__ = "student_access_rules"
    __table_args__ = (
        CheckConstraint(f"feature IN {STUDENT_ACCESS_FEATURES}", name="ck_student_access_rules_feature"),
        CheckConstraint(f"min_state IN {STUDENT_PAYMENT_STATES}", name="ck_student_access_rules_min_state"),
    )
    feature: Mapped[str] = mapped_column(String(30), primary_key=True)
    min_state: Mapped[str] = mapped_column(String(30))
    updated_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class CertificateRequest(Base, TimestampMixin):
    """nehn-031 (DEC-SCOPE-297 W6): one per enrolment -- the batch trainer's recommendation (or not-ready flag), marked issued when the
    coordinator issues the certificate."""

    __tablename__ = "certificate_requests"
    __table_args__ = (CheckConstraint("status IN ('recommended', 'not_ready', 'issued')", name="ck_certificate_requests_status"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    certificate_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("certificates.id", ondelete="SET NULL"), nullable=True)


# rec-003 (DEC-SCOPE-121 D1): CMP-000001. MAXVALUE keeps lpad from ever truncating a code; uq_companies_code is the backstop.
COMPANY_CODE_SEQ = Sequence("company_code_seq", maxvalue=999999, metadata=Base.metadata)
COMPANY_NAME_KEY_SQL = r"lower(regexp_replace(btrim(name), '\s+', ' ', 'g'))"
COMPANY_CHECKS = {
    "ck_companies_priority": "priority IS NULL OR priority IN ('hot', 'warm', 'cold')",
    "ck_companies_employee_count": "employee_count IS NULL OR employee_count BETWEEN 0 AND 10000000",
}
# rec-005 (DEC-SCOPE-127): the pipeline stage and the Lost flag (both or neither); migration 0108 keeps a frozen copy.
COMPANY_PIPELINE_CHECKS = {
    "ck_companies_stage": "stage IN (" + ", ".join(f"'{s}'" for s in COMPANY_STAGES) + ")",
    "ck_companies_lost": "(lost_at IS NULL) = (lost_reason IS NULL)",
}


class Company(Base, TimestampMixin):
    """rec-003 (DEC-SCOPE-121, R3): the recruiter lead and the company are one row; the lead ID is `company_code`, which every insert
    path gets from the server default. The recruiter columns are nullable: EMP-001 registration and `/workflows/it/jobs` auto-create
    still write only name/website/ownership, and NULL `assigned_recruiter_user_id` is the managers' unassigned queue."""

    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("company_code", name="uq_companies_code"),
        *(CheckConstraint(sql, name=name) for name, sql in COMPANY_CHECKS.items()),
        *(CheckConstraint(sql, name=name) for name, sql in COMPANY_PIPELINE_CHECKS.items()),
        Index("ix_companies_assigned_recruiter", "assigned_recruiter_user_id"),
        Index("ix_companies_stage_recruiter", "stage", "assigned_recruiter_user_id"),  # rec-005: the pipeline board
        Index("ix_companies_assigned_bdm", "assigned_bdm_user_id"),
        Index("ix_companies_name_key", text(COMPANY_NAME_KEY_SQL)),  # the duplicate check (services/recruiter_companies.NAME_KEY)
    )
    __mapper_args__ = {"eager_defaults": True}  # INSERT ... RETURNING company_code: no lazy load of the server default under asyncio
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(180), unique=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    partner_type: Mapped[str] = mapped_column(String(40), default="recruiter")
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # EMP-001 -- DATA_MODEL.md #5.1: extend the existing table with an ownership column
    # rather than fork a parallel Employer-owned table set, since the mediation question
    # (does Placement Team gate an Employer posting?) is still open (FEATURE_QUESTIONS.md
    # #1) -- a parallel table would force a premature answer.
    owner_type: Mapped[str] = mapped_column(String(30), default="internal")
    employer_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    company_code: Mapped[str] = mapped_column(String(20), server_default=text("'CMP-' || lpad(nextval('company_code_seq')::text, 6, '0')"))
    linkedin_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    industry_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_industries.id"), nullable=True)
    company_size_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_company_sizes.id"), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    head_office: Mapped[str | None] = mapped_column(String(300), nullable=True)
    branches: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    lead_source_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_lead_sources.id"), nullable=True)
    campaign_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_campaigns.id"), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(10), nullable=True)
    assigned_recruiter_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_bdm_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # rec-005 (DEC-SCOPE-127): written only by services/company_pipeline; the server defaults cover every other insert path (EMP-001).
    stage: Mapped[str] = mapped_column(String(30), default=COMPANY_FIRST_STAGE, server_default=COMPANY_FIRST_STAGE)
    stage_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class CompanyStageHistory(Base):
    """rec-005 (DEC-SCOPE-127, spec §3): one row per stage change, Lost and reopen. Append-only. `event` is `manual`, `lost`, `reopen` or
    an engine event (recruiter_stages.EVENTS); `actor_user_id` is NULL for the system. No stage CHECK: history must survive a future
    catalogue change. `position` orders rows created in one transaction."""

    __tablename__ = "company_stage_history"
    __table_args__ = (Index("ix_company_stage_history_company", "company_id", "position"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"))
    from_stage: Mapped[str] = mapped_column(String(30))
    to_stage: Mapped[str] = mapped_column(String(30))
    event: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanyAssignmentHistory(Base):
    """rec-003: one row per change of a company's recruiter. Append-only; `from_user_id` NULL = it was in the unassigned queue."""

    __tablename__ = "company_assignment_history"
    __table_args__ = (Index("ix_company_assignment_history_company", "company_id"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id"))
    from_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    to_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    changed_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# rec-004 (DEC-SCOPE-125): migration 0110 repeats COMPANY_CONTACT_CHECKS (test_rec_004_migration asserts they stay identical).
COMPANY_CONTACT_CHANNELS = ("call", "whatsapp", "email")
COMPANY_CONTACT_CHECKS = {
    "ck_company_contacts_channel": f"preferred_channel IS NULL OR preferred_channel IN ({', '.join(repr(c) for c in COMPANY_CONTACT_CHANNELS)})",
    "ck_company_contacts_primary_active": "NOT is_primary OR active",
}


class CompanyContact(Base, TimestampMixin):
    """rec-004 (EVID-018 §4, R3): a person at a company -- the §2 "recruiter" and the §3 HR / TA / Hiring-Manager contacts. Never
    deleted, only deactivated (C2); at most one primary per company (the partial unique index). `position` keeps insertion order;
    `mobile_normalized` follows `mobile` for later lookups (calls, duplicate checks)."""

    __tablename__ = "company_contacts"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in COMPANY_CONTACT_CHECKS.items()),
        Index("ix_company_contacts_company", "company_id"),
        Index("uq_company_contacts_primary", "company_id", unique=True, postgresql_where=text("is_primary")),
        Index("ix_company_contacts_mobile", "mobile_normalized"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    name: Mapped[str] = mapped_column(String(200))
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_contact_roles.id"), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    mobile_normalized: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    preferred_channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)

    @validates("mobile")
    def _derive_mobile_normalized(self, _key: str, mobile: str | None) -> str | None:
        self.mobile_normalized = normalise_phone(mobile)
        return mobile


# rec-024 (DEC-SCOPE-131): the EVID-018 §18 follow-up reasons (L738-L754, source order) and states; migration 0116 repeats
# RECRUITER_FOLLOW_UP_CHECKS (test_rec_024_migration asserts they stay identical). Labels live in the web client.
RECRUITER_FOLLOW_UP_REASONS = (
    "new_requirement", "jd", "profile_feedback", "interview_feedback", "offer_status", "joining_confirmation", "new_openings",
    "contract_mou", "payment_commercial",
)
RECRUITER_FOLLOW_UP_CHECKS = {
    "ck_recruiter_follow_ups_reason": f"reason IN ({', '.join(repr(r) for r in RECRUITER_FOLLOW_UP_REASONS)})",
    "ck_recruiter_follow_ups_status": "status IN ('open', 'done', 'cancelled')",
    "ck_recruiter_follow_ups_state": (
        "(status = 'done') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL) "
        "AND (status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)"
    ),
}


class RecruiterFollowUp(Base, TimestampMixin):
    """rec-024 (DEC-SCOPE-131): a recruiter follow-up on a company, optionally about one contact, requirement or application. It belongs
    to the company (FU4): whoever has the company in scope sees it, so a reassignment moves it with no rewrite. The company's next
    follow-up is derived from the open ones (FU9), never stored."""

    __tablename__ = "recruiter_follow_ups"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in RECRUITER_FOLLOW_UP_CHECKS.items()),
        Index("ix_recruiter_follow_ups_company", "company_id", "status", "due_at"),
        Index("ix_recruiter_follow_ups_open_due", "due_at", postgresql_where=text("status = 'open'")),
        Index("ix_recruiter_follow_ups_contact", "contact_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=True)
    job_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True)
    application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_applications.id", ondelete="RESTRICT"), nullable=True)
    reason: Mapped[str] = mapped_column(String(40))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", server_default=text("'open'"))
    outcome: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# rec-025 (DEC-SCOPE-133 CA1/CA8): the call outcomes (the source names none -- UNVERIFIED default) and directions; migration 0118 repeats
# RECRUITER_CALL_CHECKS (test_rec_025_migration asserts they stay identical). Labels live in services/recruiter_calls and the web client.
RECRUITER_CALL_OUTCOMES = ("connected", "call_back_requested", "busy", "no_answer", "switched_off", "wrong_number")
RECRUITER_CALL_DIRECTIONS = ("outgoing", "incoming")
RECRUITER_CALL_MAX_SECONDS = 14400  # 4 hours, tel-010 D7
RECRUITER_CALL_CHECKS = {
    "ck_recruiter_calls_outcome": f"outcome IN ({', '.join(repr(o) for o in RECRUITER_CALL_OUTCOMES)})",
    "ck_recruiter_calls_direction": f"direction IN ({', '.join(repr(d) for d in RECRUITER_CALL_DIRECTIONS)})",
    "ck_recruiter_calls_duration": f"duration_seconds IS NULL OR duration_seconds BETWEEN 0 AND {RECRUITER_CALL_MAX_SECONDS}",
    "ck_recruiter_calls_party": "(contact_id IS NULL) = (company_id IS NULL) AND (contact_id IS NULL) <> (candidate_id IS NULL)",
}


class RecruiterCall(Base, TimestampMixin):
    """rec-025 (DEC-SCOPE-133): a call logged on a company contact or a candidate -- exactly one (CA2). A contact call also keeps the
    contact's company, so its scope and the company's call list are the company's (rec-003) with no join. `caller_user_id` keeps who
    made it (the same-day edit gate, CA4, and the daily cap, CA9)."""

    __tablename__ = "recruiter_calls"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in RECRUITER_CALL_CHECKS.items()),
        Index("ix_recruiter_calls_company_occurred", "company_id", "occurred_at"),
        Index("ix_recruiter_calls_contact_occurred", "contact_id", "occurred_at"),
        Index("ix_recruiter_calls_candidate_occurred", "candidate_id", "occurred_at"),
        Index("ix_recruiter_calls_caller_occurred", "caller_user_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True)
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=True)
    candidate_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=True)
    caller_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    direction: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class EmployerProfile(Base, TimestampMixin):
    """EMP-001 -- DATA_MODEL.md #5.2, net-new. `registration_status` exists but is
    deliberately unenforced/nullable: whether registration requires Admin approval before
    activation is an open item (FEATURE_QUESTIONS.md #7) -- do not silently gate Employer
    activation on a workflow that was never confirmed."""

    __tablename__ = "employer_profiles"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), unique=True, index=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id"), index=True)
    registration_status: Mapped[str | None] = mapped_column(String(20), nullable=True)


# rec-007 (DEC-SCOPE-129 J1): the 11 EVID-018 §6 requirement statuses. `JOB_OPEN_STATUSES` is what students see and can apply to
# (while `closes_on` has not passed) -- every `status == "open"` reader uses it now.
# hrc-007 (DEC-SCOPE-380 A1) adds `pending_approval` and `filled`; neither is open. Migration 0257 repeats ck_jobs_status (frozen copy).
JOB_STATUSES = (
    "new", "pending_approval", "requirement_received", "sourcing", "shortlisting", "profiles_shared", "interviewing", "selected", "joined", "filled",
    "on_hold", "closed", "cancelled",
)
JOB_OPEN_STATUSES = ("requirement_received", "sourcing", "shortlisting", "profiles_shared", "interviewing")
JOB_WORK_MODES = ("onsite", "remote", "hybrid")
JOB_SHIFTS = ("day", "night", "rotational", "flexible")
JOB_EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "internship", "temporary")
JOB_PRIORITIES = ("high", "medium", "low")
JOB_SOURCES = ("recruiter", "employer", "legacy")  # hrc-007 (A3): which create path made the job; its approval setting is per source
JOB_APPROVAL_DEFAULTS = {"employer": True, "recruiter": False, "legacy": False}  # hrc-007 (A4); migration 0257 seeds a frozen copy
REQUIREMENT_CODE_SEQ = Sequence("requirement_code_seq", maxvalue=999999, metadata=Base.metadata)


def _in(column: str, values: tuple[str, ...]) -> str:
    """A nullable column limited to `values` (shared by the rec-007 job and tel-009 qualification CHECKs)."""
    return f"{column} IS NULL OR {column} IN ({', '.join(repr(v) for v in values)})"


JOB_CHECKS = {  # migration 0114 repeats these strings; test_rec_007_migration asserts they stay identical
    "ck_jobs_status": "status IN (" + ", ".join(f"'{s}'" for s in JOB_STATUSES) + ")",
    "ck_jobs_work_mode": _in("work_mode", JOB_WORK_MODES),
    "ck_jobs_shift": _in("shift", JOB_SHIFTS),
    "ck_jobs_employment_type": _in("employment_type", JOB_EMPLOYMENT_TYPES),
    "ck_jobs_priority": _in("priority", JOB_PRIORITIES),
    "ck_jobs_vacancies": "vacancies IS NULL OR vacancies BETWEEN 1 AND 10000",
    "ck_jobs_experience": "(experience_min_months IS NULL OR experience_min_months BETWEEN 0 AND 600) AND (experience_max_months IS NULL OR experience_max_months BETWEEN 0 AND 600)"
    " AND (experience_min_months IS NULL OR experience_max_months IS NULL OR experience_min_months <= experience_max_months)",
    "ck_jobs_salary": "(salary_min IS NULL OR salary_min >= 0) AND (salary_max IS NULL OR salary_max >= 0) AND (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max)",
}
JOB_SOURCE_CHECK = f"source IN ({', '.join(repr(v) for v in JOB_SOURCES)})"  # hrc-007; migration 0257 repeats it
# hrc-008 (DEC-SCOPE-385 V1): who sees an open job -- staff only, the student/candidate portal, one talent pool's members, or everyone.
# Migration 0262 repeats both checks (test_hrc_008_migration).
JOB_VISIBILITIES = ("internal", "portal", "segment", "public")
JOB_VISIBILITY_LABELS = {"internal": "Internal only", "portal": "Candidate portal", "segment": "Segment (talent pool)", "public": "Public website"}
JOB_VISIBILITY_CHECK = f"visibility IN ({', '.join(repr(v) for v in JOB_VISIBILITIES)})"
JOB_SEGMENT_POOL_CHECK = "(visibility = 'segment') = (segment_pool_id IS NOT NULL)"
JOB_FEE_BASES = ("fixed", "percent_of_ctc")  # rec-031 (RV1): the per-requirement fee override, the rec-030 CT4 shape
JOB_FEE_CHECKS = {  # migration 0147 repeats these strings (test_rec_031_migration)
    "ck_jobs_fee_pair": "(fee_basis IS NULL) = (fee_value IS NULL)",
    "ck_jobs_fee_basis": _in("fee_basis", JOB_FEE_BASES),
    "ck_jobs_fee_value": "fee_value IS NULL OR (fee_value >= 0 AND (fee_basis <> 'percent_of_ctc' OR fee_value <= 100))",
}
JOB_PAY_CHECKS = {  # hrc-005 (DEC-SCOPE-381 V1): migration 0258 repeats these strings (test_hrc_005_migration)
    "ck_jobs_salary_currency": "salary_currency IS NULL OR salary_currency ~ '^[A-Z]{3}$'",
    "ck_jobs_salary_period": "salary_period IS NULL OR salary_period IN ('year', 'month')",
}
# hrc-005 V4: the duplicate check's keys, spelled exactly as ix_jobs_company_title_key so the planner can use it.
JOB_TITLE_KEY_SQL = r"lower(regexp_replace(btrim(title), '\s+', ' ', 'g'))"
JOB_PLACE_KEY_SQL = r"lower(regexp_replace(btrim(coalesce(city, location)), '\s+', ' ', 'g'))"


class Job(Base, TimestampMixin):
    """rec-007 (DEC-SCOPE-129, R5): the job is the Job Requirement. `requirement_code` comes from the server default on every insert path
    (employer, /workflows/it/jobs, the recruiter API). `skills` (JSON) is a derived mirror of `job_skills`, rewritten by
    services.recruiter_requirements.set_skills, so the legacy readers keep their shape (J7)."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("requirement_code", name="uq_jobs_requirement_code"),
        *(CheckConstraint(sql, name=name) for name, sql in {**JOB_CHECKS, **JOB_FEE_CHECKS, **JOB_PAY_CHECKS}.items()),
        CheckConstraint(JOB_SOURCE_CHECK, name="ck_jobs_source"),
        CheckConstraint(JOB_VISIBILITY_CHECK, name="ck_jobs_visibility"),
        CheckConstraint(JOB_SEGMENT_POOL_CHECK, name="ck_jobs_segment_pool"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_status_visibility", "status", "visibility"),  # hrc-008: the public/portal listings
        Index("ix_jobs_assigned_recruiter", "assigned_recruiter_user_id"),
        Index("ix_jobs_closes_on", "closes_on"),
        Index("ix_jobs_company_title_key", "company_id", text(JOB_TITLE_KEY_SQL)),  # hrc-005 V4: the duplicate check
    )
    __mapper_args__ = {"eager_defaults": True}  # INSERT ... RETURNING requirement_code
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    location: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="requirement_received")
    closes_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    requirement_code: Mapped[str] = mapped_column(String(20), server_default=text("'REQ-' || lpad(nextval('requirement_code_seq')::text, 6, '0')"))
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    job_category_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_job_categories.id"), nullable=True)
    vacancies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualification: Mapped[str | None] = mapped_column(String(300), nullable=True)
    experience_min_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience_max_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    work_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shift: Mapped[str | None] = mapped_column(String(20), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    joining_requirement: Mapped[str | None] = mapped_column(String(300), nullable=True)
    requirement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(10), nullable=True)
    assigned_recruiter_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    fee_basis: Mapped[str | None] = mapped_column(String(20), nullable=True)  # rec-031 (RV1): overrides the contract's fee per hire
    fee_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # hrc-007 (DEC-SCOPE-380 A3/A6): the create path, and who sent it for approval (the self-approval check reads it).
    source: Mapped[str] = mapped_column(String(10), default="recruiter", server_default=text("'recruiter'"))
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # hrc-005 (DEC-SCOPE-381 V1): the §4.2 fields; `location` stays the display string every reader uses (V3)
    requisition_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lead_source_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_lead_sources.id"), nullable=True)
    certifications: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    relocation_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    travel_requirement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)  # null = INR
    salary_period: Mapped[str | None] = mapped_column(String(5), nullable=True)  # null = a year
    benefits: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    hiring_manager_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expected_joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # hrc-008 (DEC-SCOPE-385 V1/V3): public by default, so no existing listing or create path changes; a segment names its talent pool
    visibility: Mapped[str] = mapped_column(String(10), default="public", server_default=text("'public'"))
    segment_pool_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("talent_pools.id", ondelete="RESTRICT"), nullable=True)
    # hrc-018 (DEC-SCOPE-392 E6): which of the job's own values also exclude a candidate from its matches (required skills always do)
    match_hard_experience: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    match_hard_qualification: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    match_hard_location: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    match_hard_salary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    company = relationship("Company")


# hrc-018 (DEC-SCOPE-392 E1/E2): the six match factors in display order and the source's default weights; migration 0269 repeats them
# (test_hrc_018_migration asserts they stay identical). The database enforces the sum (AC1).
MATCH_FACTORS = ("skills", "experience", "qualification", "location", "role", "salary")
MATCH_DEFAULT_WEIGHTS = (40, 20, 15, 10, 10, 5)
MATCH_SETTING_CHECKS = {
    "ck_match_settings_one_row": "id = 1",
    "ck_match_settings_range": " AND ".join(f"{f}_weight BETWEEN 0 AND 100" for f in MATCH_FACTORS),
    "ck_match_settings_total": " + ".join(f"{f}_weight" for f in MATCH_FACTORS) + " = 100",
}


class MatchSetting(Base, TimestampMixin):
    """hrc-018 (E2): one row (`id = 1`) of admin factor weights; no row means MATCH_DEFAULT_WEIGHTS."""

    __tablename__ = "match_settings"
    __table_args__ = tuple(CheckConstraint(sql, name=name) for name, sql in MATCH_SETTING_CHECKS.items())
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    skills_weight: Mapped[int] = mapped_column(SmallInteger)
    experience_weight: Mapped[int] = mapped_column(SmallInteger)
    qualification_weight: Mapped[int] = mapped_column(SmallInteger)
    location_weight: Mapped[int] = mapped_column(SmallInteger)
    role_weight: Mapped[int] = mapped_column(SmallInteger)
    salary_weight: Mapped[int] = mapped_column(SmallInteger)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class JobApprovalSetting(Base, TimestampMixin):
    """hrc-007 (DEC-SCOPE-380 A4): whether a job from this source needs a `jobs.approve` holder's approval before it first opens. One row
    per source, seeded by migration 0257; super_admin changes them."""

    __tablename__ = "job_approval_settings"
    source: Mapped[str] = mapped_column(String(10), primary_key=True)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


# hrc-006 (DEC-SCOPE-384 O1/O2): a requirement's owners besides its primary (`jobs.assigned_recruiter_user_id`), and every ownership
# change. Migration 0261 repeats JOB_ASSIGNMENT_CHECKS (test_hrc_006_migration asserts they stay identical).
JOB_ASSIGNMENT_ROLES = ("placement_officer", "collaborator")
JOB_ASSIGNMENT_CHECKS = {
    "ck_job_assignments_role": "role IN ('placement_officer', 'collaborator')",
    "ck_job_assignment_history_role": "role IN ('primary', 'placement_officer', 'collaborator')",
    "ck_job_assignment_history_action": "action IN ('added', 'removed')",
    "ck_job_assignment_history_reason": "reason IS NULL OR reason IN ('reassign', 'deactivated', 'backfill')",
}


class JobAssignment(Base):
    """hrc-006 (O1): a placement-officer owner (at most one per job) or a collaborator. One role per user per job; the primary is never here."""

    __tablename__ = "job_assignments"
    __table_args__ = (
        CheckConstraint(JOB_ASSIGNMENT_CHECKS["ck_job_assignments_role"], name="ck_job_assignments_role"),
        UniqueConstraint("job_id", "user_id", name="uq_job_assignments_job_user"),
        Index("ix_job_assignments_user_job", "user_id", "job_id"),
        Index("uq_job_assignments_officer", "job_id", unique=True, postgresql_where=text("role = 'placement_officer'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id"))
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20))
    added_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobAssignmentHistory(Base):
    """hrc-006 (O2): append-only. A primary change is two rows (removed, added); `changed_by_user_id` NULL = the system (0261's backfill)."""

    __tablename__ = "job_assignment_history"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in JOB_ASSIGNMENT_CHECKS.items() if name.startswith("ck_job_assignment_history")),
        Index("ix_job_assignment_history_job", "job_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id"))
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    changed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# hrc-017 (DEC-SCOPE-388 T5): rec-011's candidate levels, lowest first (SK1); migration 0265 repeats them (test_hrc_017_migration).
JOB_SKILL_MIN_LEVELS = ("beginner", "intermediate", "advanced", "expert")
JOB_SKILL_MIN_LEVEL_CHECK = f"min_level IS NULL OR min_level IN ({', '.join(repr(v) for v in JOB_SKILL_MIN_LEVELS)})"


class JobSkill(Base):
    """rec-007 (J7): one required or preferred skill of a requirement. `skill_id` NULL = free text that did not resolve against the
    Skills Master (the "flagged" skills); `name` is the text as entered (or the skill's name when it resolved)."""

    __tablename__ = "job_skills"
    __table_args__ = (
        CheckConstraint("kind IN ('required', 'preferred')", name="ck_job_skills_kind"),
        CheckConstraint("weight BETWEEN 1 AND 10", name="ck_job_skills_weight"),
        CheckConstraint(JOB_SKILL_MIN_LEVEL_CHECK, name="ck_job_skills_min_level"),
        Index("uq_job_skills_name", "job_id", text("lower(name)"), unique=True),
        Index("ix_job_skills_skill", "skill_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id"), index=True)
    skill_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("skills.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10))
    weight: Mapped[int] = mapped_column(SmallInteger)
    position: Mapped[int] = mapped_column(SmallInteger)
    # hrc-017 (DEC-SCOPE-388 T5): the lowest candidate level that counts for this skill; NULL = any level
    min_level: Mapped[str | None] = mapped_column(String(16), nullable=True)


class JobStatusHistory(Base):
    """rec-007: append-only. `from_status` NULL = created; `changed_by_user_id` NULL = migration 0114's legacy mapping (the note keeps
    the original value). These rows are the requirement events rec-005 drives the company stage from."""

    __tablename__ = "job_status_history"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# rec-008 (DEC-SCOPE-132): one JD number per requirement (JD2), shared by its versions; 0001's create_all builds the sequence, 0117 creates
# it IF NOT EXISTS. Migration 0117 repeats JOB_DESCRIPTION_CHECKS (test_rec_008_migration asserts they stay identical).
JD_NUMBER_SEQ = Sequence("jd_number_seq", maxvalue=999999, metadata=Base.metadata)
JOB_DESCRIPTION_CHECKS = {
    "ck_job_descriptions_version": "version >= 1",
    "ck_job_descriptions_openings": "openings IS NULL OR openings BETWEEN 1 AND 10000",
    "ck_job_descriptions_file": "(storage_key IS NULL) = (content_type IS NULL) AND (storage_key IS NULL) = (size_bytes IS NULL)",
}


class JobDescription(Base):
    """rec-008 (R5, JD1): one version of a requirement's JD, append-only. Exactly one version per requirement is current (the partial
    unique index); a create or edit carries the current file forward, an upload carries the current fields forward (JD4). The company is
    the requirement's and is not stored again."""

    __tablename__ = "job_descriptions"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in JOB_DESCRIPTION_CHECKS.items()),
        UniqueConstraint("job_id", "version", name="uq_job_descriptions_version"),
        Index("uq_job_descriptions_current", "job_id", unique=True, postgresql_where=text("is_current")),
        Index("ix_job_descriptions_number", "jd_number"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="RESTRICT"))
    jd_number: Mapped[str] = mapped_column(String(12))
    version: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean)
    role: Mapped[str] = mapped_column(String(180))
    experience: Mapped[str | None] = mapped_column(String(120), nullable=True)
    qualification: Mapped[str | None] = mapped_column(String(300), nullable=True)
    skills: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    salary: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    openings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=True)
    closing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# rec-017 (DEC-SCOPE-136, A1): the §12 per-requirement statuses + withdrawn. Migration 0121 repeats them (test_rec_017_migration).
APPLICATION_STATUSES = ("sourced", "screened", "shortlisted", "profile_shared", "interview", "selected", "joined", "rejected", "withdrawn")
# hrc-026 (DEC-SCOPE-394 A3/A5/A7): where an application came from, the structured rejection reasons, and the stage the candidate sees
# (every status but the internal Profile Shared). Migration 0271 repeats them (test_hrc_026_migration). Labels live in services/applications.py.
APPLICATION_SOURCES = ("portal", "recruiter", "employer", "drive")
REJECTION_REASONS = (
    "skills_mismatch", "experience_mismatch", "qualification_mismatch", "salary_mismatch", "location_mismatch", "screening_not_cleared",
    "interview_not_cleared", "not_reachable", "client_rejected", "position_filled", "other",
)
CANDIDATE_VISIBLE_STATUSES = tuple(s for s in APPLICATION_STATUSES if s != "profile_shared")
JOB_APPLICATION_CODE_SEQ = Sequence("job_application_code_seq", metadata=Base.metadata)
JOB_APPLICATION_CODE_DEFAULT = "'JA-' || to_char(nextval('job_application_code_seq'), 'FM999999999000000')"
def _visible_status(status: str | None) -> str:
    """A row inserted directly (the seed, tests) starts the candidate's view at its own status when that is visible."""
    return status if status in CANDIDATE_VISIBLE_STATUSES else "sourced"


APPLICATION_CHECKS = {
    "ck_job_applications_status": "status IN (" + ", ".join(f"'{s}'" for s in APPLICATION_STATUSES) + ")",
    "ck_job_applications_source": "source IN (" + ", ".join(f"'{s}'" for s in APPLICATION_SOURCES) + ")",
    "ck_job_applications_candidate_status": "candidate_status IN (" + ", ".join(f"'{s}'" for s in CANDIDATE_VISIBLE_STATUSES) + ")",
    "ck_job_applications_rejection_reason": "rejection_reason IS NULL OR (status = 'rejected' AND rejection_reason IN ("
    + ", ".join(f"'{r}'" for r in REJECTION_REASONS) + "))",
}


class JobApplication(Base, TimestampMixin):
    """rec-017 (R6): one candidate on one requirement. `student_id` mirrors the candidate's login (NULL for an external candidate), so the
    legacy student/employer/HR readers that join `users` keep their shape. services/applications.py is the only status writer."""

    __tablename__ = "job_applications"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in APPLICATION_CHECKS.items()),
        UniqueConstraint("candidate_id", "job_id", name="uq_job_applications_candidate_job"),
        Index("ix_job_applications_job_status", "job_id", "status"),
        Index("ix_job_applications_candidate", "candidate_id"),
        Index("ix_job_applications_drive", "drive_id"),
        Index("ix_job_applications_needs_review", "job_id", postgresql_where=text("needs_review_since IS NOT NULL")),  # hrc-009
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id"), index=True)
    student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id"))
    status: Mapped[str] = mapped_column(String(30), default="sourced")
    resume_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stage_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    added_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # rec-029 (DR3): the one campus drive the candidate came through, set when added through it and never changed.
    drive_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("recruitment_drives.id", ondelete="RESTRICT"), nullable=True)
    # hrc-009 (DEC-SCOPE-390 R3/R4): set when the requirement's eligibility changed while the application was open; cleared by a status
    # move or a confirmed review. NULL = nothing to review.
    needs_review_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # hrc-026 (DEC-SCOPE-394): the database numbers every application (JA-000001); its source and owning recruiter; the last
    # candidate-visible stage (what the portal and notices show); and the reason while it is rejected.
    application_code: Mapped[str] = mapped_column(String(20), unique=True, server_default=text(JOB_APPLICATION_CODE_DEFAULT))
    source: Mapped[str] = mapped_column(String(20), server_default=text("'recruiter'"))
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    candidate_status: Mapped[str] = mapped_column(String(30), default=lambda ctx: _visible_status(ctx.get_current_parameters().get("status")), server_default=text("'sourced'"))
    rejection_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)


class JobApplicationStatusHistory(Base):
    """rec-017: append-only. `from_status` NULL = created; `changed_by_user_id` NULL = the system or migration 0121 (whose note keeps the
    legacy value). No status CHECK: history must survive a future catalogue change."""

    __tablename__ = "job_application_status_history"
    __table_args__ = (Index("ix_job_application_status_history_application", "application_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_applications.id", ondelete="RESTRICT"))
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rejection_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)  # hrc-026 (A9): the reason of a move into Rejected


# rec-020 (DEC-SCOPE-148, IV1/IV2): the EVID-018 §14 rounds and statuses, in source order. Migration 0133 repeats them
# (test_rec_020_migration). Labels live in services/interviews.py and the web client.
INTERVIEW_ROUNDS = ("hr_round", "technical_round", "manager_round", "final_round", "client_round")
INTERVIEW_STATUSES = ("scheduled", "confirmed", "completed", "rescheduled", "no_show", "selected", "rejected", "on_hold")
INTERVIEW_EVENTS = ("scheduled", "rescheduled", "status")
INTERVIEW_CODE_SEQ = Sequence("interview_code_seq", metadata=Base.metadata)
# The database numbers every interview, whoever inserts it (legacy routes, employers, tests): INT-000001, growing past six digits.
INTERVIEW_CODE_DEFAULT = "'INT-' || to_char(nextval('interview_code_seq'), 'FM999999999000000')"
INTERVIEW_CHECKS = {
    "ck_interviews_status": "status IN (" + ", ".join(f"'{s}'" for s in INTERVIEW_STATUSES) + ")",
    "ck_interviews_round": "round IS NULL OR round IN (" + ", ".join(f"'{s}'" for s in INTERVIEW_ROUNDS) + ")",
}
INTERVIEW_EVENT_CHECKS = {"ck_interview_events_event": "event IN (" + ", ".join(f"'{s}'" for s in INTERVIEW_EVENTS) + ")"}

# rec-018 (DEC-SCOPE-149, EVID-018 §13): the four screening results in source order (L586-L592). Migration 0134 repeats SCREENING_CHECKS
# (test_rec_018_migration). Labels live in services/application_screening.py.
SCREENING_RESULTS = ("shortlisted", "hold", "rejected", "need_more_info")
SCREENING_CHECKS = {
    "ck_application_screenings_result": "result IN (" + ", ".join(f"'{r}'" for r in SCREENING_RESULTS) + ")",
    "ck_application_screenings_rejected_remarks": "result <> 'rejected' OR remarks IS NOT NULL",
    "ck_application_screenings_communication": "communication_rating IS NULL OR communication_rating BETWEEN 1 AND 5",
    "ck_application_screenings_technical": "technical_rating IS NULL OR technical_rating BETWEEN 1 AND 5",
    "ck_application_screenings_notice": "notice_days IS NULL OR notice_days BETWEEN 0 AND 365",
    "ck_application_screenings_salary": "expected_salary IS NULL OR expected_salary >= 0",
}

# rec-021 (DEC-SCOPE-175, EVID-018 §15): the feedback's decisions are the interview's own decision statuses (FB3). Migration 0146 repeats
# FEEDBACK_CHECKS (test_rec_021_migration). Labels live in services/interviews.py and the web client.
FEEDBACK_DECISIONS = ("selected", "rejected", "on_hold")
FEEDBACK_CHECKS = {
    "ck_interview_feedback_overall": "overall_rating BETWEEN 1 AND 5",
    "ck_interview_feedback_technical": "technical_rating IS NULL OR technical_rating BETWEEN 1 AND 5",
    "ck_interview_feedback_communication": "communication_rating IS NULL OR communication_rating BETWEEN 1 AND 5",
    "ck_interview_feedback_next_round": "next_round IS NULL OR next_round IN (" + ", ".join(f"'{s}'" for s in INTERVIEW_ROUNDS) + ")",
    "ck_interview_feedback_decision": "final_decision IS NULL OR final_decision IN (" + ", ".join(f"'{s}'" for s in FEEDBACK_DECISIONS) + ")",
    "ck_interview_feedback_rejected_no_next": "final_decision IS DISTINCT FROM 'rejected' OR next_round IS NULL",
}


class ApplicationScreening(Base, TimestampMixin):
    """rec-018 (SC5): the one current screening of an application, overwritten by each save. Salary and remarks are internal: no
    employer, student or hr_team route reads this table, and the audit keeps field names only."""

    __tablename__ = "application_screenings"
    __table_args__ = tuple(CheckConstraint(sql, name=name) for name, sql in SCREENING_CHECKS.items())
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_applications.id", ondelete="RESTRICT"), primary_key=True)
    qualification_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    experience_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    skills_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    expected_salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notice_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    location_preference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    communication_rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    technical_rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    availability: Mapped[str | None] = mapped_column(String(120), nullable=True)
    willing_to_relocate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    result: Mapped[str] = mapped_column(String(20))
    screened_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class Interview(Base, TimestampMixin):
    """rec-020 (IV1-IV7): one interview round of one application. services/interviews.py is the status writer for the recruiter routes;
    `result` is the legacy free-text outcome the /workflows and employer screens still read. `round` and `created_by_user_id` are NULL on
    legacy rows."""

    __tablename__ = "interviews"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in INTERVIEW_CHECKS.items()),
        Index("ix_interviews_status_scheduled", "status", "scheduled_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    interview_code: Mapped[str] = mapped_column(String(20), unique=True, server_default=text(INTERVIEW_CODE_DEFAULT))
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_applications.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String(30), default="Online")
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result: Mapped[str | None] = mapped_column(String(40), nullable=True)
    round: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="scheduled", server_default=text("'scheduled'"))
    interviewer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


class InterviewFeedback(Base, TimestampMixin):
    """rec-021 (FB1): the one current feedback of an interview, overwritten by each save. Internal to the recruiter module: no employer,
    student or hr_team route reads this table, and the audit keeps field names only."""

    __tablename__ = "interview_feedback"
    __table_args__ = tuple(CheckConstraint(sql, name=name) for name, sql in FEEDBACK_CHECKS.items())
    interview_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("interviews.id", ondelete="RESTRICT"), primary_key=True)
    technical_rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    communication_rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    overall_rating: Mapped[int] = mapped_column(SmallInteger)
    strengths: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    weaknesses: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    recruiter_comments: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    company_feedback: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    next_round: Mapped[str | None] = mapped_column(String(20), nullable=True)
    final_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    recorded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class InterviewEvent(Base):
    """rec-020 (IV3/IV4, AC1): one row per schedule, reschedule (old and new time) and status move. Append-only; `position` orders rows
    written in one transaction. `actor_user_id` is NULL only for a system write."""

    __tablename__ = "interview_events"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in INTERVIEW_EVENT_CHECKS.items()),
        Index("ix_interview_events_interview", "interview_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    interview_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("interviews.id", ondelete="RESTRICT"))
    event: Mapped[str] = mapped_column(String(16))
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    old_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlacementProfile(Base, TimestampMixin):
    __tablename__ = "placement_profiles"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), unique=True, index=True)
    readiness_status: Mapped[str] = mapped_column(String(40), default="preparation")
    resume_status: Mapped[str] = mapped_column(String(40), default="pending")
    mock_interview_status: Mapped[str] = mapped_column(String(40), default="pending")
    aptitude_status: Mapped[str] = mapped_column(String(40), default="pending")
    available: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ADM-007-AC02: withdrawn is distinct from `available=False` (temporarily
    # unavailable but still an active candidate) -- a withdrawn candidate is removed
    # from active matching entirely, while their JobApplication/Interview/JobOffer
    # history (none of which reference this table) is untouched and stays retrievable.
    withdrawn: Mapped[bool] = mapped_column(Boolean, default=False)


# rec-022 (DEC-SCOPE-155, OF1): the EVID-018 §16 offer statuses in source order (L700). Migration 0138 repeats them
# (test_rec_022_migration). Labels live in services/offers.py and the web client.
OFFER_STATUSES = ("offer_pending", "offer_received", "accepted", "declined")
OFFER_EVENTS = ("created", "status", "revised", "letter", "joining", "joined", "did_not_join", "proof")  # rec-023 appends the last four
OFFER_CHECKS = {"ck_job_offers_status": "status IN (" + ", ".join(f"'{s}'" for s in OFFER_STATUSES) + ")"}
# rec-023 (DEC-SCOPE-158, JN2-JN5): the EVID-018 §17 joining statuses; NULL until the offer is Accepted. Migration 0140 repeats them
# (test_rec_023_migration).
JOINING_STATUSES = ("pending", "joined", "did_not_join")
JOINING_CHECKS = {
    "ck_job_offers_joining_status": "joining_status IS NULL OR joining_status IN (" + ", ".join(f"'{s}'" for s in JOINING_STATUSES) + ")",
    "ck_job_offers_not_joined_reason": "joining_status IS DISTINCT FROM 'did_not_join' OR not_joined_reason IS NOT NULL",
}
OFFER_EVENT_CHECKS = {"ck_job_offer_events_event": "event IN (" + ", ".join(f"'{s}'" for s in OFFER_EVENTS) + ")"}


class JobOffer(Base, TimestampMixin):
    """One offer per application (the unique index). rec-022: services/offers.py is the only writer; `letter_url` is the legacy typed
    link, `letter_key` the uploaded letter (OF7). `position` and `created_by_user_id` are NULL on legacy rows."""

    __tablename__ = "job_offers"
    __table_args__ = tuple(CheckConstraint(sql, name=name) for name, sql in {**OFFER_CHECKS, **JOINING_CHECKS}.items())
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_applications.id"), unique=True, index=True)
    offered_on: Mapped[date] = mapped_column(Date, default=date.today)
    compensation: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(30), default="offer_received", server_default=text("'offer_received'"))
    joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    letter_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[str | None] = mapped_column(String(160), nullable=True)
    letter_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    letter_content_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    letter_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    letter_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    # rec-023 (JN1): the joining. `joining_date` above is the Expected Joining Date; services/joinings.py is the only writer.
    joining_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actual_joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    joining_location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reporting_manager: Mapped[str | None] = mapped_column(String(160), nullable=True)
    joining_confirmed_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    joining_confirmed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    not_joined_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    proof_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proof_content_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proof_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proof_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobOfferEvent(Base):
    """rec-022 (AC2): one row per record, status move, revision (field names only) and letter upload (`letter_key` = the replaced object,
    never returned); rec-023 adds the joining's details (field names), Joined / Did Not Join (note = the reason) and the proof upload
    (`letter_key` = the replaced proof). Append-only; `position` orders rows written in one transaction. `actor_user_id` is NULL only for a system write."""

    __tablename__ = "job_offer_events"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in OFFER_EVENT_CHECKS.items()),
        Index("ix_job_offer_events_offer", "offer_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    offer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_offers.id", ondelete="RESTRICT"))
    event: Mapped[str] = mapped_column(String(16))
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fields: Mapped[list | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    letter_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# upc-002 (U12, Q-06): the nine regions, in display order. Migration 0101_country_master repeats them (test_upc_002_migration asserts it).
COUNTRY_REGIONS = ("UK", "Europe", "North America", "Latin America & Caribbean", "Middle East", "Asia", "Oceania", "Africa", "Antarctica")


class Country(Base, TimestampMixin):
    __tablename__ = "countries"
    __table_args__ = (
        UniqueConstraint("iso2", name="uq_countries_iso2"),
        CheckConstraint("iso2 ~ '^[A-Z]{2}$'", name="ck_countries_iso2"),
        CheckConstraint("region IN (" + ", ".join(f"'{r}'" for r in COUNTRY_REGIONS) + ")", name="ck_countries_region"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    # upc-002: every real country carries its ISO 3166-1 alpha-2 code and region (migration 0101 fills them). Nullable only so ad-hoc
    # test rows need no code; the ISO rows are internal (catalogue_visible=false) until a country gets catalogue content.
    iso2: Mapped[str | None] = mapped_column(String(2), nullable=True)
    region: Mapped[str | None] = mapped_column(String(40), nullable=True)
    catalogue_visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    overview: Mapped[str] = mapped_column(Text)
    tuition: Mapped[str] = mapped_column(String(160))
    living_expenses: Mapped[str] = mapped_column(String(160))
    visa_process: Mapped[list] = mapped_column(JSON, default=list)
    work_opportunities: Mapped[str] = mapped_column(Text)
    post_study_work: Mapped[str] = mapped_column(Text)
    pr_opportunities: Mapped[str] = mapped_column(Text)
    faq: Mapped[list] = mapped_column(JSON, default=list)
    # VISA-002: the actual interview-prep content is a confirmed open item
    # (PRODUCT_DECISION_REGISTER.md DEC-DATA-001/DEC-SCOPE-006) -- nullable so a country
    # with none yet exercises the real "explicit fallback, not a 500" path (VISA-002-AC02)
    # rather than a fabricated placeholder.
    interview_prep: Mapped[str | None] = mapped_column(Text, nullable=True)


# upc-003 (DEC-SCOPE-120, spec §2): the Global University Master's value lists (EVID-020 §1). Migration 0105 repeats UNIVERSITY_CHECKS;
# test_upc_003_migration asserts they stay identical.
INSTITUTION_TYPES = ("university", "college", "institute", "language_school", "training_institution")
UNIVERSITY_OWNERSHIP_TYPES = ("public", "private")
UNIVERSITY_RELATIONSHIPS = ("new", "existing")
UNIVERSITY_PRIORITIES = ("A", "B", "C")
PARTNERSHIP_POTENTIALS = ("high", "medium", "low")
COURSE_LEVELS = ("UG", "PG", "PhD", "Diploma", "Foundation")
RANKING_SYSTEMS = ("QS", "THE", "ARWU", "Other")
# upc-006 (DEC-SCOPE-123): §11's relationship status, exactly (CT4), and the channels a contact record holds (CT3).
RELATIONSHIP_STRENGTHS = ("new", "developing", "good", "strong", "strategic", "at_risk", "dormant")
CONTACT_CHANNELS = ("email", "phone", "whatsapp", "linkedin")
UNIVERSITY_CODE_SEQ = Sequence("university_code_seq", metadata=Base.metadata)
UNIVERSITY_CODE_DEFAULT = "'UNV-' || translate(format('%6s', nextval('university_code_seq')), ' ', '0')"


def _one_of(column: str, values: tuple[str, ...], *, nullable: bool = True) -> str:
    listed = f"{column} IN ({', '.join(repr(v) for v in values)})"
    return f"{column} IS NULL OR {listed}" if nullable else listed


UNIVERSITY_CHECKS = {
    "ck_universities_institution_type": _one_of("institution_type", INSTITUTION_TYPES, nullable=False),
    "ck_universities_ownership_type": _one_of("ownership_type", UNIVERSITY_OWNERSHIP_TYPES),
    "ck_universities_existing_relationship": _one_of("existing_relationship", UNIVERSITY_RELATIONSHIPS),
    "ck_universities_priority": _one_of("priority", UNIVERSITY_PRIORITIES),
    "ck_universities_partnership_potential": _one_of("partnership_potential", PARTNERSHIP_POTENTIALS),
    "ck_universities_backup_needs_primary": "backup_manager_user_id IS NULL OR (primary_manager_user_id IS NOT NULL AND backup_manager_user_id <> primary_manager_user_id)",
}
# upc-007 (DEC-SCOPE-126, spec §2): the stored partnership stage and the Lost flag. Migration 0111 repeats both dicts;
# test_upc_007_migration asserts they stay identical.
UNIVERSITY_STAGE_EVENT_KINDS = ("move", "lost", "reopened")
UNIVERSITY_PIPELINE_CHECKS = {
    "ck_universities_stage": _one_of("stage", UNIVERSITY_STAGE_KEYS, nullable=False),
    "ck_universities_lost": "(lost_at IS NULL) = (lost_reason IS NULL)",
}
# upc-023 (EX2): the optional manual probability override, 0-100, always with its reason (0143_university_probability repeats these).
UNIVERSITY_PROBABILITY_CHECKS = {
    "ck_universities_probability_override": "probability_override IS NULL OR probability_override BETWEEN 0 AND 100",
    "ck_universities_probability_reason": "(probability_override IS NULL) = (probability_override_reason IS NULL)",
}

# dtu-001 (DEC-SCOPE-209, spec §3): what EduSphere pays an agent Master per university (DT2) -- NOT upc-016's university commission.
# Exactly one of % or fixed amount; migration 0157 repeats these (test_dtu_001_migration). AED is this column's own addition:
# COUNSELING_CURRENCIES drives other CHECKs and is deliberately not widened.
AGENT_COMMISSION_CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD", "AED")
UNIVERSITY_AGENT_COMMISSION_CHECKS = {
    "ck_universities_agent_commission_one": "agent_commission_percent IS NULL OR agent_commission_amount IS NULL",
    "ck_universities_agent_commission_percent": "agent_commission_percent IS NULL OR (agent_commission_percent > 0 AND agent_commission_percent <= 100)",
    "ck_universities_agent_commission_amount": "(agent_commission_amount IS NULL) = (agent_commission_currency IS NULL) AND (agent_commission_amount IS NULL OR agent_commission_amount > 0)",
    "ck_universities_agent_commission_currency": "agent_commission_currency IS NULL OR agent_commission_currency IN ("
    + ", ".join(f"'{c}'" for c in AGENT_COMMISSION_CURRENCIES)
    + ")",
}
UNIVERSITY_STAGE_HISTORY_CHECKS = {
    "ck_university_stage_history_kind": _one_of("kind", UNIVERSITY_STAGE_EVENT_KINDS, nullable=False),
    "ck_university_stage_history_note": "kind = 'move' OR note IS NOT NULL",
}


# upc-006: added by migration 0108 (kept out of UNIVERSITY_CHECKS, which mirrors 0105).
UNIVERSITY_RELATIONSHIP_CHECK = _one_of("relationship_strength", RELATIONSHIP_STRENGTHS)


UNIVERSITY_NAME_KEY_LENGTH = 200  # = len(University.name)


class University(Base, TimestampMixin):
    """upc-003 (U5): the single source of truth for every institution. `catalogue_visible` + `active` decide what the public catalogue
    shows (public_visible); applications, shortlists and university_rep keep their FKs to these same rows."""

    __tablename__ = "universities"
    __table_args__ = (
        UniqueConstraint("university_code", name="uq_universities_code"),
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_CHECKS.items()),
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_PIPELINE_CHECKS.items()),
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_PROBABILITY_CHECKS.items()),
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_AGENT_COMMISSION_CHECKS.items()),
        Index("ix_universities_stage", "stage"),
        CheckConstraint(UNIVERSITY_RELATIONSHIP_CHECK, name="ck_universities_relationship_strength"),
        Index("ix_universities_primary_manager", "primary_manager_user_id"),
        Index("ix_universities_backup_manager", "backup_manager_user_id"),
        Index("ix_universities_priority", "priority"),
        Index("ix_universities_duplicate_key", "country_id", "name_key"),  # upc-004 UD1; not unique (overrides, legacy rows)
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    country_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("countries.id"), index=True)
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(UNIVERSITY_NAME_KEY_LENGTH))  # upc-004: normalize_key(name), kept by _derive_name_key
    city: Mapped[str] = mapped_column(String(120))
    overview: Mapped[str] = mapped_column(Text)
    eligibility: Mapped[str] = mapped_column(Text)
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    deadlines: Mapped[list] = mapped_column(JSON, default=list)
    scholarships: Mapped[list] = mapped_column(JSON, default=list)
    university_code: Mapped[str] = mapped_column(String(20), server_default=text(UNIVERSITY_CODE_DEFAULT))
    institution_type: Mapped[str] = mapped_column(String(30), default="university", server_default=text("'university'"))
    ownership_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    state_region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    course_levels: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    popular_programs: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    international_office: Mapped[str | None] = mapped_column(Text, nullable=True)
    existing_relationship: Mapped[str | None] = mapped_column(String(10), nullable=True)
    primary_manager_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    backup_manager_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(1), nullable=True)
    partnership_potential: Mapped[str | None] = mapped_column(String(10), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # UM5: true by default so the existing rows and the legacy admin create stay public; the master creates every row as false.
    catalogue_visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # upc-007: written only by services/partnership_pipeline (single writer). Lost is a flag on top of the kept stage (PS1).
    stage: Mapped[str] = mapped_column(String(40), default=UNIVERSITY_FIRST_STAGE, server_default=UNIVERSITY_FIRST_STAGE)
    stage_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    relationship_strength: Mapped[str | None] = mapped_column(String(12), nullable=True)  # upc-006 CT11: set by hand (CT1)
    # upc-008 (§5, MS8/MS9): the expected timeline. Expected month and quarter are derived from target_partnership_date (Q-10).
    target_partnership_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_intake: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expected_agreement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_recruitment_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    # upc-023 (§24, EX2/EX3): replaces the stage probability until cleared; the stage probability is a constant (partnership_stages).
    probability_override: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    probability_override_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # dtu-001 (DEC-SCOPE-209): the catalogue's logo, campus list and fee block (public), and the agent commission (DT4: restricted).
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    campuses: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list, server_default=text("'[]'"))
    fee_structure: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_commission_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    agent_commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    agent_commission_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    agent_commission_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    country = relationship("Country")

    @validates("name")
    def _derive_name_key(self, _key: str, name: str) -> str:
        """upc-004 UD1: every writer (master, legacy admin create, seed) keeps the duplicate key in step with the name."""
        self.name_key = normalize_key(name, UNIVERSITY_NAME_KEY_LENGTH)
        return name


class UniversityRanking(Base):
    """upc-003 UM2: one row per ranking system and year; `rank` is text so a band ("201-250") fits. Replaced as a list on edit."""

    __tablename__ = "university_rankings"
    __table_args__ = (
        CheckConstraint(_one_of("system", RANKING_SYSTEMS, nullable=False), name="ck_university_rankings_system"),
        CheckConstraint("(system = 'Other') = (other_name IS NOT NULL)", name="ck_university_rankings_other_name"),
        CheckConstraint("year BETWEEN 1900 AND 2100", name="ck_university_rankings_year"),
        Index("uq_university_rankings_entry", "university_id", "system", text("coalesce(other_name, '')"), "year", unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="CASCADE"))
    system: Mapped[str] = mapped_column(String(10))
    other_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    year: Mapped[int] = mapped_column(Integer)
    rank: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UniversityAssignmentHistory(Base):
    """upc-003 (§27): append-only; one row per manager slot that changed (primary or backup). Either side may be NULL (unassigned)."""

    __tablename__ = "university_assignment_history"
    __table_args__ = (
        CheckConstraint("slot IN ('primary', 'backup')", name="ck_university_assignment_history_slot"),
        Index("ix_university_assignment_history_university", "university_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    slot: Mapped[str] = mapped_column(String(10))
    from_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    to_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UniversityImportBatch(Base, TimestampMixin):
    """upc-005 (DEC-SCOPE-128, IM6/IM10): one CSV import into the University Master. The file is never stored: only its hash, the counts
    and each row's outcome {row_number, status, name, country, university_id, university_code, matches, reason}. The Idempotency-Key is
    scoped to the uploader. Migration 0113 repeats the constraints (test_upc_005_migration)."""

    __tablename__ = "university_import_batches"
    __table_args__ = (
        UniqueConstraint("uploaded_by_user_id", "idempotency_key", name="uq_university_import_batches_key"),
        CheckConstraint("created_count + duplicate_count + invalid_count = total_rows", name="ck_university_import_batches_counts"),
        Index("ix_university_import_batches_uploader", "uploaded_by_user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    file_sha256: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    invalid_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    results_json: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))


UNIVERSITY_MILESTONE_CHECKS = {"ck_university_milestones_kind": _one_of("kind", UNIVERSITY_MILESTONE_KEYS, nullable=False)}


class UniversityMilestone(Base, TimestampMixin):
    """upc-008 (DEC-SCOPE-143, MS2): a university's recorded dates for one §6 milestone. Sparse: a row exists only once a date was
    recorded (the catalogue is the template). Status is never stored (Q-11, computed by services/partnership_milestones)."""

    __tablename__ = "university_milestones"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_MILESTONE_CHECKS.items()),
        UniqueConstraint("university_id", "kind", name="uq_university_milestones_kind"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(40))
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    achieved_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


UNIVERSITY_ONBOARDING_CHECKS = {
    "ck_university_onboarding_items_kind": _one_of("kind", ONBOARDING_ITEM_KEYS, nullable=False),
    "ck_university_onboarding_items_status": _one_of("status", ONBOARDING_STATUSES, nullable=False),
    "ck_university_onboarding_items_completed": "(status = 'completed') = (completed_on IS NOT NULL)",
    "ck_university_onboarding_items_note": f"note IS NULL OR char_length(note) <= {ONBOARDING_NOTE_MAX}",
}


class UniversityOnboardingItem(Base, TimestampMixin):
    """upc-027 (DEC-SCOPE-169, OB2): a university's recorded progress on one §29 onboarding item. Sparse: a row exists only once the item
    was edited (the catalogue is the template), so a signed university shows ten Not Started items without a signing hook. The overall
    status and the automatic course item are computed on read (services/university_onboarding)."""

    __tablename__ = "university_onboarding_items"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_ONBOARDING_CHECKS.items()),
        UniqueConstraint("university_id", "kind", name="uq_university_onboarding_items_kind"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="not_started", server_default=text("'not_started'"))
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class UniversityStageHistory(Base):
    """upc-007 (spec PS9): one row per stage move, Lost or Reopen. Append-only. `from_stage` = `to_stage` for lost / reopened; `note` is
    the move note or the required reason. No stage CHECK: history must survive a future catalogue change. `position` orders rows."""

    __tablename__ = "university_stage_history"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_STAGE_HISTORY_CHECKS.items()),
        Index("ix_university_stage_history_university", "university_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(10))
    from_stage: Mapped[str] = mapped_column(String(40))
    to_stage: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# upc-006 (DEC-SCOPE-123, spec §2): the contact role catalogue (CT2) -- §10's example roles and §1's contact rows, International
# Director once. Migration 0108 seeds it (ROLE_SEED) and repeats UNIVERSITY_CONTACT_CHECKS; test_upc_006_migration keeps them identical.
UNIVERSITY_CONTACT_ROLE_SEED = (
    ("international_director", "International Director"),
    ("international_recruitment_manager", "International Recruitment Manager"),
    ("regional_manager", "Regional Manager"),
    ("admissions_manager", "Admissions Manager"),
    ("marketing_manager", "Marketing Manager"),
    ("application_officer", "Application Officer"),
    ("finance_contact", "Finance Contact"),
    ("international_office", "International Office"),
    ("partnership_contact", "Partnership Contact"),
    ("recruitment_contact", "Recruitment Contact"),
    ("application_contact", "Application Contact"),
    ("country_manager", "Country Manager"),
)
UNIVERSITY_CONTACT_CHECKS = {
    "ck_university_contacts_preferred_channel": _one_of("preferred_channel", CONTACT_CHANNELS),
    "ck_university_contacts_relationship_strength": _one_of("relationship_strength", RELATIONSHIP_STRENGTHS),
}


class UniversityContactRole(Base):
    """upc-006 CT2: a seeded, read-only catalogue (no admin UI in this item)."""

    __tablename__ = "university_contact_roles"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(SmallInteger)


class UniversityContact(Base, TimestampMixin):
    """upc-006 (§10): a named person at a university. At most one primary per university (CT6); one email once per university (CT8);
    the same person at two universities is two rows. Contact PII: audit and logs carry ids only."""

    __tablename__ = "university_contacts"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_CONTACT_CHECKS.items()),
        Index("ix_university_contacts_university", "university_id"),
        Index("uq_university_contacts_primary", "university_id", unique=True, postgresql_where=text("is_primary")),
        Index("uq_university_contacts_email", "university_id", text("lower(email)"), unique=True, postgresql_where=text("email IS NOT NULL")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role_code: Mapped[str | None] = mapped_column(String(40), ForeignKey("university_contact_roles.code", ondelete="RESTRICT"), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(30), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(300), nullable=True)
    preferred_channel: Mapped[str | None] = mapped_column(String(10), nullable=True)
    relationship_strength: Mapped[str | None] = mapped_column(String(12), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    shareable: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


# upc-010 (DEC-SCOPE-130, spec §2): §8's visit flow, exactly (VS2). Migration 0109 repeats the check; test_upc_010_migration keeps them
# identical. VIS-000123 codes (VS17): a rolled-back create skips a number.
UNIVERSITY_VISIT_STATUSES = ("planned", "approved", "travel_booked", "visit_completed", "follow_up", "closed")
UNIVERSITY_VISIT_STATUS_CHECK = _one_of("status", UNIVERSITY_VISIT_STATUSES, nullable=False)
UNIVERSITY_VISIT_CODE_SEQ = Sequence("university_visit_code_seq", metadata=Base.metadata)


class UniversityVisit(Base, TimestampMixin):
    """upc-010 (§8): one visit to one university (VS1), separate from meetings. A planned visit is a draft, waiting for approval
    (`submitted_at`) or returned (`rejection_reason`). Rules live in `services/university_visits.py`."""

    __tablename__ = "university_visits"
    __table_args__ = (
        UniqueConstraint("code", name="uq_university_visits_code"),
        CheckConstraint(UNIVERSITY_VISIT_STATUS_CHECK, name="ck_university_visits_status"),
        Index("ix_university_visits_university", "university_id"),
        Index("ix_university_visits_lead", "lead_user_id"),
        Index("ix_university_visits_pending", "submitted_at", postgresql_where=text("status = 'planned' AND submitted_at IS NOT NULL")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20))
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    city: Mapped[str] = mapped_column(String(120))
    purpose: Mapped[str] = mapped_column(Text)
    lead_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    proposed_date: Mapped[date] = mapped_column(Date)
    confirmed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    travel_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    travel_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    hotel_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    hotel_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="planned", server_default="planned")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class UniversityVisitParticipant(Base):
    """VS11: other EduSphere employees on the visit (active partnership users when added)."""

    __tablename__ = "university_visit_participants"
    visit_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_visits.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)


class UniversityVisitContact(Base):
    """VS12: the university's contacts to meet. Deleting the contact (PII) removes it from the visit."""

    __tablename__ = "university_visit_contacts"
    visit_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_visits.id", ondelete="CASCADE"), primary_key=True)
    contact_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_contacts.id", ondelete="CASCADE"), primary_key=True)


class UniversityVisitEvent(Base):
    """VS14: the append-only status history (create, edit, every transition), with the reject/close reason."""

    __tablename__ = "university_visit_events"
    __table_args__ = (Index("ix_university_visit_events_visit", "visit_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    visit_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_visits.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(20))
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


PARTNERSHIP_TASK_CHECKS = {
    "ck_partnership_tasks_kind": _one_of("kind", PARTNERSHIP_TASK_KINDS, nullable=False),
    "ck_partnership_tasks_priority": _one_of("priority", PARTNERSHIP_TASK_PRIORITIES, nullable=False),
    "ck_partnership_tasks_status": _one_of("status", PARTNERSHIP_TASK_STATUSES, nullable=False),
    "ck_partnership_tasks_source": _one_of("source", PARTNERSHIP_TASK_SOURCES, nullable=False),
    "ck_partnership_tasks_rule": "(source = 'manual') = (rule IS NULL)",
    "ck_partnership_tasks_completed": "(status = 'done') = (completed_at IS NOT NULL)",
    "ck_partnership_tasks_cancelled": "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
    "ck_partnership_tasks_cancel_reason": "cancel_reason IS NULL OR status = 'cancelled'",
}


class PartnershipTask(Base, TimestampMixin):
    """upc-020 (DEC-SCOPE-141): a university's follow-up or task (§19/§20), added by hand or by a Q-22 rule (`rule` names it:
    `stage:<key>` or `visit:<id>`; at most one open task per rule and university, TK7). Rules live in `services/partnership_tasks.py`."""

    __tablename__ = "partnership_tasks"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in PARTNERSHIP_TASK_CHECKS.items()),
        Index("ix_partnership_tasks_assignee_status_due", "assignee_user_id", "status", "due_on"),
        Index("ix_partnership_tasks_university_status_due", "university_id", "status", "due_on"),
        Index("uq_partnership_tasks_open_rule", "university_id", "rule", unique=True, postgresql_where=text("status = 'open' AND rule IS NOT NULL")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    assignee_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    due_on: Mapped[date] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(10), default="medium", server_default=text("'medium'"))
    status: Mapped[str] = mapped_column(String(20), default="open", server_default=text("'open'"))
    source: Mapped[str] = mapped_column(String(20))
    rule: Mapped[str | None] = mapped_column(String(80), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


# upc-009 (DEC-SCOPE-145, spec §2): university meetings (§7). Migration 0130 repeats these checks (test_upc_009_migration keeps them
# identical). The outcome fields are written only when the meeting is completed (MG10-MG12).
UNIVERSITY_MEETING_CODE_SEQ = Sequence("university_meeting_code_seq", metadata=Base.metadata)
UNIVERSITY_MEETING_CHECKS = {
    "ck_university_meetings_type": _one_of("meeting_type", UNIVERSITY_MEETING_TYPES, nullable=False),
    "ck_university_meetings_mode": _one_of("mode", UNIVERSITY_MEETING_MODES, nullable=False),
    "ck_university_meetings_status": _one_of("status", UNIVERSITY_MEETING_STATUSES, nullable=False),
    "ck_university_meetings_completed": "(status = 'completed') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL)",
    "ck_university_meetings_cancelled": "(status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)",
    "ck_university_meetings_next_action": "(next_action IS NULL) = (next_action_due_on IS NULL)",
    "ck_university_meetings_outcome": (
        "status = 'completed' OR (discussion_points IS NULL AND decisions IS NULL AND next_action IS NULL AND next_meeting_date IS NULL)"
    ),
    "ck_university_meeting_participants_one": "(contact_id IS NULL) <> (user_id IS NULL)",
    "ck_university_meeting_events_event": _one_of("event", UNIVERSITY_MEETING_EVENTS, nullable=False),
}


def _university_meeting_checks(*names: str) -> tuple[CheckConstraint, ...]:
    return tuple(CheckConstraint(UNIVERSITY_MEETING_CHECKS[name], name=name) for name in names)


class UniversityMeeting(Base, TimestampMixin):
    """upc-009 (DEC-SCOPE-145): a meeting with a university (§7). Never deleted: cancelled instead. The contact person's name and
    designation are copied when set (MG5), so the record keeps them after the contact changes or is deleted (FK SET NULL)."""

    __tablename__ = "university_meetings"
    __table_args__ = (
        UniqueConstraint("code", name="uq_university_meetings_code"),
        *_university_meeting_checks(
            "ck_university_meetings_type", "ck_university_meetings_mode", "ck_university_meetings_status", "ck_university_meetings_completed",
            "ck_university_meetings_cancelled", "ck_university_meetings_next_action", "ck_university_meetings_outcome",
        ),
        Index("ix_university_meetings_university_starts", "university_id", "starts_at"),
        Index("ix_university_meetings_status_starts", "status", "starts_at"),
        Index("ix_university_meetings_responsible", "responsible_user_id"),
    )  # fmt: skip
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20))
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_contacts.id", ondelete="SET NULL"), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meeting_type: Mapped[str] = mapped_column(String(40))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String(10))
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    discussion_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    decisions: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(200), nullable=True)
    next_action_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_meeting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsible_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(12), default="scheduled", server_default=text("'scheduled'"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class UniversityMeetingParticipant(Base):
    """MG6/MG7: one university contact or one EduSphere employee per row. A deleted contact leaves the list (CASCADE: PII deletion wins)."""

    __tablename__ = "university_meeting_participants"
    __table_args__ = (
        *_university_meeting_checks("ck_university_meeting_participants_one"),
        UniqueConstraint("meeting_id", "contact_id", name="uq_university_meeting_participants_contact"),
        UniqueConstraint("meeting_id", "user_id", name="uq_university_meeting_participants_user"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    meeting_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_meetings.id", ondelete="CASCADE"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_contacts.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


class UniversityMeetingEvent(Base):
    """MG9: one row per schedule, edit, reschedule (old and new time), completion and cancellation. Append-only; `position` orders rows."""

    __tablename__ = "university_meeting_events"
    __table_args__ = (
        *_university_meeting_checks("ck_university_meeting_events_event"),
        Index("ix_university_meeting_events_meeting", "meeting_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    meeting_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_meetings.id", ondelete="CASCADE"))
    event: Mapped[str] = mapped_column(String(12))
    old_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# upc-011 (DEC-SCOPE-152, spec §2): the §9 calendar's own events (conferences, fairs, webinars...; CL1-CL6). Migration 0136 repeats these
# checks (test_upc_011_migration keeps them identical). PEV-000123 codes: a rolled-back create skips a number.
PARTNERSHIP_EVENT_CODE_SEQ = Sequence("partnership_event_code_seq", metadata=Base.metadata)
PARTNERSHIP_EVENT_CHECKS = {
    "ck_partnership_events_kind": _one_of("kind", PARTNERSHIP_EVENT_KINDS, nullable=False),
    "ck_partnership_events_status": _one_of("status", PARTNERSHIP_EVENT_STATUSES, nullable=False),
    "ck_partnership_events_dates": "ends_on >= starts_on",
    "ck_partnership_events_cancelled": "(status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)",
}


class PartnershipEvent(Base, TimestampMixin):
    """upc-011: an all-day, possibly multi-day event (CL3) with an optional university. Never deleted: cancelled instead (CL6). Rules live
    in `services/partnership_events.py`."""

    __tablename__ = "partnership_events"
    __table_args__ = (
        UniqueConstraint("code", name="uq_partnership_events_code"),
        *(CheckConstraint(sql, name=name) for name, sql in PARTNERSHIP_EVENT_CHECKS.items()),
        Index("ix_partnership_events_dates", "starts_on", "ends_on"),
        Index("ix_partnership_events_owner", "owner_user_id"),
        Index("ix_partnership_events_university", "university_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    university_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"), nullable=True)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(12), default="scheduled", server_default=text("'scheduled'"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PartnershipEventParticipant(Base):
    """CL5: other EduSphere employees at the event (active partnership users when added)."""

    __tablename__ = "partnership_event_participants"
    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("partnership_events.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)


# upc-012 (DEC-SCOPE-140, spec §2): calls, WhatsApp and email stored against the university (§12, U10). Migration 0125 repeats these
# checks (test_upc_012_migration keeps them identical). Call outcomes, directions and the duration bound are rec-025's (UC1).
PARTNERSHIP_TEMPLATE_CHECKS = {
    "ck_partnership_message_templates_channel": "channel IN ('whatsapp', 'email')",
    "ck_partnership_message_templates_subject": "(channel = 'email') = (subject IS NOT NULL)",
}
UNIVERSITY_CALL_CHECKS = {
    "ck_university_calls_outcome": f"outcome IN ({', '.join(repr(o) for o in RECRUITER_CALL_OUTCOMES)})",
    "ck_university_calls_direction": f"direction IN ({', '.join(repr(d) for d in RECRUITER_CALL_DIRECTIONS)})",
    "ck_university_calls_duration": f"duration_seconds IS NULL OR duration_seconds BETWEEN 0 AND {RECRUITER_CALL_MAX_SECONDS}",
}
UNIVERSITY_MESSAGE_CHECKS = {
    "ck_university_messages_channel": "channel IN ('whatsapp', 'email')",
    "ck_university_messages_email": "(channel = 'email') = (delivery_status IS NOT NULL) AND (channel = 'email') = (subject IS NOT NULL)",
    "ck_university_messages_status": "delivery_status IS NULL OR delivery_status IN ('queued', 'sending', 'retrying', 'sent', 'failed')",
}


class PartnershipMessageTemplate(Base, TimestampMixin):
    """upc-012 (UC4): a WhatsApp or email template of the partnership head's global library -- no kind (the source names none). Only
    email has a subject; placeholders are checked on save; a name is unique per channel (case-insensitive). Never deleted."""

    __tablename__ = "partnership_message_templates"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in PARTNERSHIP_TEMPLATE_CHECKS.items()),
        Index("uq_partnership_message_templates_channel_name", "channel", text("lower(name)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    channel: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(160))
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class UniversityCall(Base, TimestampMixin):
    """upc-012 (UC1): a call with one university contact, kept on the university. Deleting the contact (upc-006 CT7, PII) nulls
    `contact_id` and keeps the call (UC2). Permanent: no edit or delete. `next_follow_up_on` is picked up by upc-020."""

    __tablename__ = "university_calls"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_CALL_CHECKS.items()),
        Index("ix_university_calls_university_occurred", "university_id", "occurred_at"),
        Index("ix_university_calls_contact_occurred", "contact_id", "occurred_at"),
        Index("ix_university_calls_caller_occurred", "caller_user_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_contacts.id", ondelete="SET NULL"), nullable=True)
    caller_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    direction: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class UniversityMessage(Base, TimestampMixin):
    """upc-012 (UC6-UC9): a WhatsApp (the row is the manager's confirmation) or an email (queued for the worker; `attempt_count` counts
    SMTP attempts) to one university contact, kept on the university (UC2). Permanent. `template_name` is the name when sent."""

    __tablename__ = "university_messages"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_MESSAGE_CHECKS.items()),
        Index("ix_university_messages_university_sent", "university_id", "sent_at"),
        Index("ix_university_messages_contact_sent", "contact_id", "sent_at"),
        Index("ix_university_messages_sender_sent", "sender_user_id", "sent_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_contacts.id", ondelete="SET NULL"), nullable=True)
    sender_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    channel: Mapped[str] = mapped_column(String(16))
    template_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("partnership_message_templates.id", ondelete="RESTRICT"), nullable=True)
    template_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# upc-017 (DEC-SCOPE-147, spec §1-§2): the §16 course master extends `overseas_courses` (U6). `tuition_fee` and `intake` stay the
# catalogue's display texts, re-derived whenever the structured amount / months are saved (CO4, CO7). The per-course commission is
# RESTRICTED (U2, CO2). Migration 0132 repeats these; test_upc_017_migration keeps them identical.
COURSE_CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")  # = COUNSELING_CURRENCIES (defined later in this module)
COURSE_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ENGLISH_TESTS = ("IELTS", "TOEFL", "PTE", "Duolingo", "Other")
# nehn-036 (DEC-SCOPE-285 I3-I4): the curated subject icons; NULL = automatic (the web client derives it from the category).
# Migration 0197 repeats these; test_nehn_036_migration keeps them identical.
COURSE_ICONS = ("ai", "security", "data", "computing", "engineering", "business", "health", "hospitality", "law", "education", "arts", "science", "general")
COURSE_CHECKS = {
    "ck_overseas_courses_tuition": "(tuition_amount IS NULL) = (tuition_currency IS NULL) AND (tuition_amount IS NULL OR tuition_amount >= 0)",
    "ck_overseas_courses_tuition_currency": _one_of("tuition_currency", COURSE_CURRENCIES),
    "ck_overseas_courses_fee": "(application_fee IS NULL) = (application_fee_currency IS NULL) AND (application_fee IS NULL OR application_fee >= 0)",
    "ck_overseas_courses_fee_currency": _one_of("application_fee_currency", COURSE_CURRENCIES),
    "ck_overseas_courses_english_test": _one_of("english_test", ENGLISH_TESTS),
    "ck_overseas_courses_english_score": "english_score IS NULL OR (english_score > 0 AND english_test IS NOT NULL)",
    "ck_overseas_courses_commission": "commission_percent IS NULL OR commission_amount IS NULL",
    "ck_overseas_courses_commission_percent": "commission_percent IS NULL OR (commission_percent > 0 AND commission_percent <= 100)",
    "ck_overseas_courses_commission_amount": "(commission_amount IS NULL) = (commission_currency IS NULL) AND (commission_amount IS NULL OR commission_amount > 0)",
    "ck_overseas_courses_commission_currency": _one_of("commission_currency", COURSE_CURRENCIES),
}
# ccrm-051 (DEC-SCOPE-327): the agent-Master commission per course (overrides the university's) -- the university CHECKs on these columns.
# Its own constant: COURSE_CHECKS is pinned by 0132's copy. Migration 0217 repeats these (test_ccrm_051_migration).
COURSE_AGENT_COMMISSION_CHECKS = {
    name.replace("ck_universities_", "ck_overseas_courses_"): sql for name, sql in UNIVERSITY_AGENT_COMMISSION_CHECKS.items()
}


class OverseasCourse(Base, TimestampMixin):
    __tablename__ = "overseas_courses"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in COURSE_CHECKS.items()),
        *(CheckConstraint(sql, name=name) for name, sql in COURSE_AGENT_COMMISSION_CHECKS.items()),
        CheckConstraint(_one_of("icon", COURSE_ICONS), name="ck_overseas_courses_icon"),  # nehn-036 (0197)
        Index("ix_overseas_courses_university_level", "university_id", "level"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    level: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(80))
    duration: Mapped[str] = mapped_column(String(80))
    tuition_fee: Mapped[str] = mapped_column(String(120))
    intake: Mapped[str] = mapped_column(String(120))
    tuition_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tuition_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    application_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    application_fee_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    intakes: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    entry_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    english_test: Mapped[str | None] = mapped_column(String(10), nullable=True)
    english_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    scholarship_ids: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    application_process: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    commission_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    commission_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # dtu-001: verbatim catalogue texts (the structured amount / months stay the source for tuition_fee / intake).
    campus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fee_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    intake_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(20), nullable=True)  # nehn-036: a COURSE_ICONS key; NULL = automatic
    agent_commission_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)  # ccrm-051: NULL = the university's
    agent_commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    agent_commission_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    agent_commission_note: Mapped[str | None] = mapped_column(String(300), nullable=True)


class CourseImportBatch(Base, TimestampMixin):
    """upc-017 (CO14): one CSV import into a university's course list -- upc-005's batch shape plus the university. The file is never
    stored: only its hash, the counts and each row's outcome {row_number, status, title, level, course_id, reason}."""

    __tablename__ = "course_import_batches"
    __table_args__ = (
        UniqueConstraint("uploaded_by_user_id", "idempotency_key", name="uq_course_import_batches_key"),
        CheckConstraint("created_count + duplicate_count + invalid_count = total_rows", name="ck_course_import_batches_counts"),
        Index("ix_course_import_batches_university", "university_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    file_sha256: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    invalid_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    results_json: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))


# ccrm-011 (DEC-SCOPE-239): APP-000001 application IDs, the LD-/UNV- idiom -- on the metadata so 0001's create_all builds it on a fresh
# database; 0166 creates and backfills it on an upgraded one. One nextval per insert: never reissued, even after a withdrawal.
APPLICATION_CODE_SEQ = Sequence("overseas_application_code_seq", metadata=Base.metadata)
APPLICATION_CODE_DEFAULT = "'APP-' || translate(format('%6s', nextval('overseas_application_code_seq')), ' ', '0')"


OUTCOME_CHECK = _in("outcome", APPLICATION_OUTCOMES)  # ccrm-015; migration 0170 repeats it
# ccrm-013 (DEC-SCOPE-256): migration 0179 repeats these (test_ccrm_013_migration).
APPLICATION_FIELD_CHECKS = {
    "ck_overseas_applications_currency": _in("currency", APPLICATION_CURRENCIES),
    "ck_overseas_applications_scholarship_status": _in("scholarship_status", SCHOLARSHIP_STATUSES),
    "ck_overseas_applications_money": "(tuition_fee IS NULL OR tuition_fee >= 0) AND (scholarship_amount IS NULL OR scholarship_amount >= 0)",
    "ck_overseas_applications_scholarship_awarded": "scholarship_amount IS NULL OR scholarship_status = 'awarded'",
}
# ccrm-023 (DEC-SCOPE-245, OF3/OF4): an application offer's types and statuses. Migration 0171 repeats them (test_ccrm_023_migration).
APPLICATION_OFFER_TYPES = ("conditional", "unconditional", "pathway", "other")
APPLICATION_OFFER_STATUSES = ("active", "superseded", "withdrawn_by_university", "expired")
# ccrm-025 (DEC-SCOPE-255): the student's decision on an offer, and the counselor's manual deposit record. Migration 0178 repeats them.
APPLICATION_OFFER_DECISIONS = ("considering", "accepted", "declined", "expired")
DEPOSIT_RECORD_STATUSES = ("not_required", "pending", "paid_to_university", "paid_via_edusphere")
# ccrm-024 (DEC-SCOPE-261): who must satisfy an offer condition, and its status. Migration 0183 repeats them (test_ccrm_024_migration).
OFFER_CONDITION_OWNERS = ("student", "counselor", "agent")
OFFER_CONDITION_STATUSES = ("open", "met", "waived", "failed")


class OverseasApplication(Base, TimestampMixin):
    __tablename__ = "overseas_applications"
    __mapper_args__ = {"eager_defaults": True}  # INSERT ... RETURNING application_code: no lazy load on an async session
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_code: Mapped[str] = mapped_column(String(20), server_default=text(APPLICATION_CODE_DEFAULT))
    # Owner (DEC-SCOPE-018, AGN-008 DEC-SCOPE-050). Exactly one of `school_student_id` or the agent pair is set, enforced at every
    # write site (app-level, this table's style). A School-bridged row has `school_student_id` only. An agency's application has
    # `agent_student_id` (its record, AGN-004), plus `student_id` when that student has a login. Rows made before AGN-008 have
    # `student_id` only. Shared lists join the owner with `services.agent_applications.with_owner` (outer joins), so a student with
    # no login is listed rather than dropped; School-bridged rows stay out of them, as before.
    student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    school_student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), nullable=True, index=True)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id"), index=True)
    course_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_courses.id"), nullable=True)
    counselor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    agent_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="enquiry")
    # ccrm-014 (DEC-SCOPE-240): the detail under `status` (app/application_sub_status.py); NULL = not set.
    sub_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # ccrm-015 (DEC-SCOPE-244): the exception outcome (app/application_outcome.py), independent of the stage; NULL = none. Detail and
    # history are `ApplicationOutcome` rows. A withdrawn application also keeps status 'withdrawn' (O1).
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    intake: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_reference: Mapped[str | None] = mapped_column(String(140), nullable=True)
    offer_letter_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agent_student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_students.id"), nullable=True, index=True)
    submitted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    application_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    offer_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    # AGN-013 (DEC-SCOPE-054): recorded by an agency Master at enrollment (PUT .../enrollment); NULL until then.
    enrollment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    university_student_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    enrollment_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ccrm-027 (DEC-SCOPE-262): the counselor/Admin confirmation (PUT …/enrollment) -- its "Enrolment confirmation" document and the
    # pre-enrolment checklist attestation (E8). An agency Master's AGN-013 confirmation sets neither.
    enrollment_document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("student_documents.id", ondelete="SET NULL", use_alter=True, name="fk_overseas_applications_enrollment_document_id"), nullable=True
    )
    pre_enrollment_checklist_complete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # ccrm-028 (DEC-SCOPE-265): arrival and orientation after enrolment (PUT …/arrival). `arrival_date` is the expected date until arrival
    # is confirmed; confirming stamps who and when (A4). Orientation needs a confirmed arrival (the CHECK below; migration 0187 repeats it).
    arrival_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    arrival_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrival_confirmed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", name="fk_overseas_applications_arrival_confirmed_by_id"), nullable=True
    )
    orientation_attended: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    arrival_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AGN-010 (DEC-SCOPE-056): the current offer, recorded by the agency. `offer_deadline` above is its deadline (O2); the letter is an
    # AGN-009 document (O3). `use_alter`: student_documents.application_id points back at this table.
    offer_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    offer_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    offer_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("student_documents.id", ondelete="SET NULL", use_alter=True, name="fk_overseas_applications_offer_document_id"), nullable=True
    )
    # ccrm-013 (DEC-SCOPE-256): the university-side fields, written by the counselor/Admin details route. The portal URL is a link only,
    # never credentials (F6); one currency serves the fee and the scholarship amount (F1); the amount only when awarded (F3).
    faculty: Mapped[str | None] = mapped_column(String(140), nullable=True)
    campus: Mapped[str | None] = mapped_column(String(140), nullable=True)
    course_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    university_portal_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    university_contact_name: Mapped[str | None] = mapped_column(String(140), nullable=True)
    university_contact_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    tuition_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    scholarship_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scholarship_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    documents_completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)  # editable now; ccrm-019 also sets it (F5)
    decision_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint("application_code", name="uq_overseas_applications_code"),
        *(CheckConstraint(sql, name=name) for name, sql in APPLICATION_FIELD_CHECKS.items()),
        CheckConstraint("offer_type IS NULL OR offer_type IN (" + ", ".join(f"'{t}'" for t in APPLICATION_OFFER_TYPES) + ")", name="ck_overseas_applications_offer_type"),
        CheckConstraint("(offer_type IS NULL) = (offer_date IS NULL)", name="ck_overseas_applications_offer_dated"),
        CheckConstraint(OUTCOME_CHECK, name="ck_overseas_applications_outcome"),
        CheckConstraint("NOT orientation_attended OR arrival_confirmed_at IS NOT NULL", name="ck_overseas_applications_orientation_arrival"),
        # AGN-017 (DEC-SCOPE-059): the daily reminder job reads agency deadlines through these partial indexes (migration 0065).
        Index("ix_overseas_applications_agent_application_deadline", "application_deadline", postgresql_where=text("agent_student_id IS NOT NULL")),
        Index("ix_overseas_applications_agent_offer_deadline", "offer_deadline", postgresql_where=text("agent_student_id IS NOT NULL")),
    )

    @validates("status")
    def _fit_sub_status(self, _key: str, status: str) -> str:
        """ccrm-014 SS3: every stage write, on any route, keeps the sub-status inside the new stage."""
        self.sub_status = fit_sub_status(status, self.sub_status)
        return status


class ApplicationOffer(Base, TimestampMixin):
    """ccrm-023 (DEC-SCOPE-245): every offer an application received. A new offer supersedes the active one; nothing is overwritten.
    The active row is mirrored to the application's offer columns, which agency routes and reports keep reading. Only
    services/application_offers.py writes this table and the mirror. `recorded_by_id` is NULL on rows backfilled by migration 0170."""

    __tablename__ = "application_offers"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id"))
    offer_type: Mapped[str] = mapped_column(String(20))
    issue_date: Mapped[date] = mapped_column(Date)
    offer_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    tuition_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    scholarship_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    deposit_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    deposit_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    offer_document_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", server_default=text("'active'"))
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    closed_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ccrm-025: the student's decision; `decided_by_id` is NULL when the daily job expired it. A decline's reason is its outcome event's.
    decision: Mapped[str] = mapped_column(String(20), default="considering", server_default=text("'considering'"))
    decision_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    decided_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(_in("decision", APPLICATION_OFFER_DECISIONS), name="ck_application_offers_decision"),
        CheckConstraint("(decision = 'considering') = (decision_date IS NULL)", name="ck_application_offers_decision_dated"),
        CheckConstraint("offer_type IN (" + ", ".join(f"'{t}'" for t in APPLICATION_OFFER_TYPES) + ")", name="ck_application_offers_type"),
        CheckConstraint("status IN (" + ", ".join(f"'{s}'" for s in APPLICATION_OFFER_STATUSES) + ")", name="ck_application_offers_status"),
        CheckConstraint("status IN ('active', 'superseded') OR status_reason IS NOT NULL", name="ck_application_offers_reason"),
        CheckConstraint("(currency IS NULL) = (tuition_amount IS NULL AND scholarship_amount IS NULL AND deposit_amount IS NULL)", name="ck_application_offers_currency"),
        CheckConstraint("tuition_amount >= 0 AND scholarship_amount >= 0 AND deposit_amount >= 0", name="ck_application_offers_amounts"),
        Index("uq_application_offers_active", "application_id", unique=True, postgresql_where=text("status = 'active'")),
        Index("ix_application_offers_application", "application_id", "created_at"),
    )


class ApplicationOfferCondition(Base, TimestampMixin):
    """ccrm-024 (DEC-SCOPE-261): a condition an offer carries -- description, owner, due date, status and the evidence that it is met.
    Conditions belong to their offer (C3) and are changed only while it is the current one. Met needs evidence and waived/failed a note
    (route rules, C2/C5). `created_by_id` is NULL on rows migrated from the offer text by 0183. Written only by services/offer_conditions.py."""

    __tablename__ = "application_offer_conditions"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    offer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("application_offers.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(20))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default=text("'open'"))
    evidence_document_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(_in("owner", OFFER_CONDITION_OWNERS), name="ck_application_offer_conditions_owner"),
        CheckConstraint(_in("status", OFFER_CONDITION_STATUSES), name="ck_application_offer_conditions_status"),
    )


class ApplicationDepositRecord(Base, TimestampMixin):
    """ccrm-025 (DEC-SCOPE-255, D2): the counselor's record of the university deposit, one per application, any currency, no payment
    taken. Beside AGN-011's `ApplicationDeposit` (agency, INR, Razorpay), which it never touches: an application with one of those
    cannot have this record. Written only by services/application_deposit_records.py."""

    __tablename__ = "application_deposit_records"
    __table_args__ = (
        CheckConstraint(_in("payment_status", DEPOSIT_RECORD_STATUSES), name="ck_application_deposit_records_status"),
        CheckConstraint("(payment_status = 'not_required') = (NOT required)", name="ck_application_deposit_records_required"),
        CheckConstraint(
            "(required AND amount > 0 AND currency IS NOT NULL) OR (NOT required AND amount IS NULL AND currency IS NULL AND due_date IS NULL AND receipt_document_id IS NULL)",
            name="ck_application_deposit_records_amount",
        ),
        CheckConstraint("(paid_on IS NOT NULL) = (payment_status IN ('paid_to_university', 'paid_via_edusphere'))", name="ck_application_deposit_records_paid"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id", ondelete="CASCADE"), unique=True)
    required: Mapped[bool] = mapped_column(Boolean)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_status: Mapped[str] = mapped_column(String(30))
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    receipt_document_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True)
    recorded_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class OverseasStudentCounselor(Base, TimestampMixin):
    """csc-001 (DEC-SCOPE-226, W3): the counselor an overseas student belongs to before (or beside) any application. One row per
    student; written by the counselor's walk-in create (csc-002) and the Overseas Admin reassign (csc-005). A counselor's students
    are their applications' students plus these (`services/counselor_students.py`); application scoping is unchanged."""

    __tablename__ = "overseas_student_counselors"
    __table_args__ = (UniqueConstraint("student_user_id", name="uq_overseas_student_counselors_student"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    counselor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    assigned_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class ItStudentCounselor(Base, TimestampMixin):
    """itc-003 (DEC-SCOPE-337, Q-03): the IT counselor an IT student belongs to -- at most one per student (not per enrolment). Set by the
    lead's student link (`lead_handover.link_student`) and moved by the IT Admin with a reason (`services/it_student_counselors.py`).
    The IT twin of `OverseasStudentCounselor`; the overseas table is untouched."""

    __tablename__ = "it_student_counselors"
    __table_args__ = (UniqueConstraint("student_user_id", name="uq_it_student_counselors_student"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    counselor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    assigned_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class ItOnboardingTemplateItem(Base, TimestampMixin):
    """itc-011 (C1, Q-09): one item of the IT onboarding checklist template; the active items, in `position` order, are copied into a new
    enrolment's checklist at conversion. Seeded by migration 0243; never deleted (deactivate instead)."""

    __tablename__ = "it_onboarding_template_items"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    label: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class ItOnboardingItem(Base, TimestampMixin):
    """itc-011 (C1): one item of an enrolment's onboarding checklist -- a copy of a template item (a later template edit never changes it).
    Ticked by the student's IT counselor or the IT Admin; `done_at` null = still to do."""

    __tablename__ = "it_onboarding_items"
    __table_args__ = (Index("ix_it_onboarding_items_enrollment", "enrollment_id", "position"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    done_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class ItConversion(Base, TimestampMixin):
    """itc-011 (C8): one completed one-step IT conversion of a lead, keyed by the caller's `Idempotency-Key` -- a retry with the same key
    on the same lead answers from this row and creates nothing."""

    __tablename__ = "it_conversions"
    __table_args__ = (UniqueConstraint("lead_id", "idempotency_key", name="uq_it_conversions_lead_key"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id"))
    created_account: Mapped[bool] = mapped_column(Boolean, default=False)


class ItStudentNote(Base, TimestampMixin):
    """itc-028 (DEC-SCOPE-351, N1): a staff note on an IT student (counselor, HR, trainer or IT Admin). Append-only; `internal` until its
    author or the IT Admin shares it (`services/it_student_notes.py`). Only `student` notes reach the student (GET /it/me/updates).
    The IT twin of `OverseasStudentNote`; the overseas table is untouched."""

    __tablename__ = "it_student_notes"
    __table_args__ = (
        CheckConstraint("visibility IN ('internal', 'student')", name="ck_it_student_notes_visibility"),
        Index("ix_it_student_notes_student_created", "student_user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    author_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(10), default="internal", server_default="internal")
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ItStudentProfile(Base, TimestampMixin):
    """itc-012 (DEC-SCOPE-345): the IT student's structured record -- personal details and the emergency contact (personal data: never
    logged or exported; read by the student, their itc-003 counselor and the IT Admin only, C1). Edited by `services/it_student_profiles.py`.
    The legacy `users.profile` JSON (education, skills) is untouched."""

    __tablename__ = "it_student_profiles"
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    qualification: Mapped[str | None] = mapped_column(String(120), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emergency_contact_relation: Mapped[str | None] = mapped_column(String(60), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class OverseasStudentArchive(Base, TimestampMixin):
    """ccrm-040 (DEC-SCOPE-276 AR4): an archived overseas student -- hidden from the staff working lists with their applications, never
    deleted. `created_at` is the archive time; a restore deletes the row (the audit log keeps the history)."""

    __tablename__ = "overseas_student_archives"
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    archived_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(500))


class OverseasStudentNote(Base, TimestampMixin):
    """ccrm-010 (DEC-SCOPE-241): an internal note on an overseas student, optionally on one of the student's applications -- the
    counselling history. Append-only (nothing updates or deletes a row); never shown to the student or the agent
    (`services/student_notes.py`)."""

    __tablename__ = "overseas_student_notes"
    __table_args__ = (Index("ix_overseas_student_notes_student_created", "student_user_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id"), nullable=True)
    author_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)


# ccrm-037 (DEC-SCOPE-273): the Overseas Admin's template library for counselors and the student message log. Migration 0191 repeats these;
# test_ccrm_037_migration keeps them identical.
COUNSELOR_TEMPLATE_CHECKS = {
    "ck_counselor_message_templates_channel": "channel IN ('whatsapp', 'email')",
    "ck_counselor_message_templates_subject": "(channel = 'email') = (subject IS NOT NULL)",
}
STUDENT_MESSAGE_CHECKS = {
    "ck_student_messages_channel": "channel IN ('whatsapp', 'email')",
    "ck_student_messages_direction": "direction IN ('outbound', 'inbound')",
    "ck_student_messages_status": "delivery_status IS NULL OR delivery_status IN ('queued', 'sending', 'retrying', 'sent', 'failed')",
    "ck_student_messages_outbound_email": (
        "direction <> 'outbound' OR ((channel = 'email') = (delivery_status IS NOT NULL) AND (channel = 'email') = (subject IS NOT NULL))"
    ),
    "ck_student_messages_inbound": "direction <> 'inbound' OR (delivery_status IS NULL AND template_id IS NULL AND (channel = 'email' OR subject IS NULL))",
}


class CounselorMessageTemplate(Base, TimestampMixin):
    """ccrm-037 (MT1): a WhatsApp or email template of the Overseas Admin's library for counselors -- no kind (upc-012's shape). Only email
    has a subject; placeholders are checked on save; a name is unique per channel (case-insensitive). Never deleted, only deactivated."""

    __tablename__ = "counselor_message_templates"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in COUNSELOR_TEMPLATE_CHECKS.items()),
        Index("uq_counselor_message_templates_channel_name", "channel", text("lower(name)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    channel: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(160))
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class StudentMessage(Base, TimestampMixin):
    """ccrm-037 (MT4-MT8): a message between a counselor and an overseas student, optionally about one application. Outbound: WhatsApp via
    wa.me (the row is the counselor's confirmation) or email (queued for the worker; `attempt_count` counts SMTP attempts). Inbound: a reply
    the counselor recorded by hand (no inbound provider) -- `sender_user_id` is who recorded it and `sent_at` when it was received.
    Permanent. `template_name` is the name when sent."""

    __tablename__ = "student_messages"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in STUDENT_MESSAGE_CHECKS.items()),
        Index("ix_student_messages_student_sent", "student_user_id", "sent_at"),
        Index("ix_student_messages_application_sent", "application_id", "sent_at"),
        Index("ix_student_messages_sender_sent", "sender_user_id", "sent_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id", ondelete="RESTRICT"), nullable=True)
    sender_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    direction: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))
    template_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("counselor_message_templates.id", ondelete="RESTRICT"), nullable=True)
    template_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApplicationStatusHistory(Base, TimestampMixin):
    __tablename__ = "application_status_history"
    __table_args__ = (CheckConstraint(_in("outcome", (*APPLICATION_OUTCOMES, OUTCOME_CLEARED)), name="ck_application_status_history_outcome"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50))
    from_sub_status: Mapped[str | None] = mapped_column(String(40), nullable=True)  # ccrm-014: written by the sub-status routes
    to_sub_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ccrm-016 (DEC-SCOPE-247, H1): the outcome this row set ('cleared' on resume / reopen) and its reason; migration 0172
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class ApplicationOutcome(Base, TimestampMixin):
    """ccrm-015 (DEC-SCOPE-244): one outcome event on an application, append-only. `outcome` is the value set, or 'cleared' when it was
    resumed / reopened; the application's current outcome detail is its latest row. Fields an outcome does not use stay NULL."""

    __tablename__ = "application_outcomes"
    __table_args__ = (
        CheckConstraint(_in("outcome", (*APPLICATION_OUTCOMES, OUTCOME_CLEARED)), name="ck_application_outcomes_outcome"),
        CheckConstraint(_in("requested_by", OUTCOME_REQUESTERS), name="ck_application_outcomes_requested_by"),
        Index("ix_application_outcomes_application_created", "application_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id", ondelete="CASCADE"))
    outcome: Mapped[str] = mapped_column(String(20))
    outcome_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True)
    previous_intake: Mapped[str | None] = mapped_column(String(80), nullable=True)
    new_intake: Mapped[str | None] = mapped_column(String(80), nullable=True)
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    hold_owner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    another_offer_preferred: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class StudentDocument(Base, TimestampMixin):
    # Owner (AGN-009, DEC-SCOPE-052): a student's account (`student_id`), an agency record (`agent_student_id`, AGN-004), or both
    # -- an agency upload for a student with a login sets both (the AGN-008 pattern). Rows made before AGN-009 have `student_id`
    # only. `file_url` is a server-generated key (`agent-documents/...`) for agency uploads; agent lists never return it.
    __tablename__ = "student_documents"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True)
    agent_student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_students.id"), index=True, nullable=True)
    application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id"), nullable=True)
    document_type: Mapped[str] = mapped_column(String(80))
    file_url: Mapped[str] = mapped_column(String(500))
    verification_status: Mapped[str] = mapped_column(String(40), default="pending")
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # One document fulfils a request (G5); the unique constraint is the database-level guard against two concurrent uploads.
    fulfils_request_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("document_requests.id"), nullable=True)
    # ccrm-021 (DEC-SCOPE-251): the review date (S5), the expiry the daily job reads (S2/S4), and versions (S3) -- a counselor's
    # replace adds a row pointing at the one it replaces and archives that one; archived rows stay out of every list.
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version_of_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("student_documents.id"), nullable=True)
    __table_args__ = (
        CheckConstraint("student_id IS NOT NULL OR agent_student_id IS NOT NULL", name="ck_student_documents_owner"),
        UniqueConstraint("fulfils_request_id", name="uq_student_documents_fulfils_request_id"),
        CheckConstraint("verification_status IN (" + ", ".join(f"'{s}'" for s in ITEM_STATUSES) + ")", name="ck_student_documents_status"),
        Index("ix_student_documents_expiry", "expiry_date", postgresql_where=text("archived_at IS NULL AND expiry_date IS NOT NULL")),
    )


class DocumentRequest(Base, TimestampMixin):
    """AGN-009 (DEC-SCOPE-052 G4/G5): an agency's request for an additional document from one of its students. Open until an upload
    made against it fulfils it, or a member cancels it.
    ccrm-020 (DEC-SCOPE-266): or a counselor's / Overseas Admin's request to a student login (`student_user_id`, exactly one owner), with a
    due date and optionally an application and its checklist item; a staff rejection of the fulfilling document reopens it (R1)."""

    __tablename__ = "document_requests"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_students.id"), nullable=True)
    student_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id"), nullable=True)
    checklist_item_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("application_checklist_items.id", ondelete="SET NULL"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_type: Mapped[str] = mapped_column(String(80))
    document_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    requested_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    closed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('open', 'fulfilled', 'cancelled')", name="ck_document_requests_status"),
        CheckConstraint("(agent_student_id IS NULL) <> (student_user_id IS NULL)", name="ck_document_requests_owner"),
        Index("ix_document_requests_student_status", "agent_student_id", "status"),
        Index("ix_document_requests_student_user_status", "student_user_id", "status"),
        Index("ix_document_requests_open_due", "due_date", postgresql_where=text("status = 'open' AND due_date IS NOT NULL")),  # ccrm-030
    )


# AGN-009 events; a review event is named after the status it set (ccrm-021 adds the 0174 codes and the daily job's 'expired').
DOCUMENT_EVENTS = ("uploaded", "replaced", "verified", "rejected", "changes_required", "requested", "fulfilled", "cancelled", "downloaded") + tuple(
    s for s in ITEM_STATUSES if s not in {"pending", "requested", "uploaded", "verified"}
)


class DocumentEvent(Base):
    """AGN-009 (DEC-SCOPE-052): a document's history, one row per event, append-only. `seq` orders events written in one
    transaction (they share `now()`). `file_key` is the replaced object's key; it is never returned by the API."""

    __tablename__ = "document_events"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    document_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("student_documents.id"), nullable=True, index=True)
    request_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("document_requests.id"), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("document_id IS NOT NULL OR request_id IS NOT NULL", name="ck_document_events_subject"),
        CheckConstraint(
            "event IN (" + ", ".join(f"'{e}'" for e in DOCUMENT_EVENTS) + ")",
            name="ck_document_events_event",
        ),
    )


class DocumentChecklistTemplate(Base, TimestampMixin):
    """ccrm-018 (DEC-SCOPE-248): an Overseas Admin's document checklist for applications matching its scope -- a country, optionally
    narrowed by university, course level and intake. One active template per (kind, scope); the most specific match applies
    (services/document_checklists.resolve). `version` counts edits so ccrm-019 can freeze the version it copies; no hard delete."""

    __tablename__ = "document_checklist_templates"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    country_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("countries.id"))
    university_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id"), nullable=True)
    course_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    intake: Mapped[str | None] = mapped_column(String(80), nullable=True)
    gate_mode: Mapped[str] = mapped_column(String(10))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    __table_args__ = (
        CheckConstraint("kind IN (" + ", ".join(f"'{k}'" for k in CHECKLIST_KINDS) + ")", name="ck_document_checklist_templates_kind"),
        CheckConstraint("gate_mode IN (" + ", ".join(f"'{m}'" for m in CHECKLIST_GATE_MODES) + ")", name="ck_document_checklist_templates_gate_mode"),
        CheckConstraint("course_level IS NULL OR course_level IN (" + ", ".join(f"'{lv}'" for lv in COURSE_LEVELS) + ")", name="ck_document_checklist_templates_course_level"),
        Index(
            "uq_document_checklist_templates_scope", "kind", "country_id", "university_id", "course_level", func.lower(text("intake")),
            unique=True, postgresql_nulls_not_distinct=True, postgresql_where=text("active"),
        ),
    )


class DocumentChecklistTemplateItem(Base):
    """ccrm-018: one document a template asks for, in `position` order. `allowed_statuses` is a subset of
    app/document_checklists.ITEM_STATUSES (never empty; the service fills the standard list)."""

    __tablename__ = "document_checklist_template_items"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    template_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("document_checklist_templates.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    document_type: Mapped[str] = mapped_column(String(80))
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed_statuses: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ccrm-022 (DEC-SCOPE-263 SD2): the item's sensitivity class; it raises (never lowers) the class of the documents it counts.
    sensitivity: Mapped[str] = mapped_column(String(20), default="standard", server_default=text("'standard'"))
    __table_args__ = (
        UniqueConstraint("template_id", "position", name="uq_document_checklist_template_items_position"),
        CheckConstraint("sensitivity IN (" + ", ".join(f"'{c}'" for c in SENSITIVITY_CLASSES) + ")", name="ck_document_checklist_template_items_sensitivity"),
    )


class ApplicationChecklist(Base, TimestampMixin):
    """ccrm-019 (DEC-SCOPE-257): an application's document checklist, made once from the matching admission template (its version
    and gate mode frozen here) or empty (gate mode `warn`, AC5). Items and links: services/application_checklists.py."""

    __tablename__ = "application_checklists"
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id", ondelete="CASCADE"), primary_key=True)
    template_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("document_checklist_templates.id"), nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gate_mode: Mapped[str] = mapped_column(String(10))
    created_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    __table_args__ = (
        CheckConstraint("gate_mode IN (" + ", ".join(f"'{m}'" for m in CHECKLIST_GATE_MODES) + ")", name="ck_application_checklists_gate_mode"),
        CheckConstraint("(template_id IS NULL) = (template_version IS NULL)", name="ck_application_checklists_template_version"),
    )


class ApplicationChecklistItem(Base, TimestampMixin):
    """ccrm-019: one document an application's checklist asks for -- a template item's copy or a counselor's own (removable, AC8).
    `mark` (AC1) overrides the linked documents' status until a document is linked."""

    __tablename__ = "application_checklist_items"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("application_checklists.application_id", ondelete="CASCADE"), index=True)
    from_template: Mapped[bool] = mapped_column(Boolean, default=False)  # a template copy (ccrm-018 re-creates its items on edit, so no FK)
    position: Mapped[int] = mapped_column(Integer)
    document_type: Mapped[str] = mapped_column(String(80))
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed_statuses: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    mark: Mapped[str | None] = mapped_column(String(20), nullable=True)
    marked_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # ccrm-022 (DEC-SCOPE-263 SD2): the item's sensitivity class; it raises (never lowers) the class of the documents it counts.
    sensitivity: Mapped[str] = mapped_column(String(20), default="standard", server_default=text("'standard'"))
    __table_args__ = (
        UniqueConstraint("application_id", "position", name="uq_application_checklist_items_position"),
        CheckConstraint("sensitivity IN (" + ", ".join(f"'{c}'" for c in SENSITIVITY_CLASSES) + ")", name="ck_application_checklist_items_sensitivity"),
        CheckConstraint("mark IS NULL OR mark IN (" + ", ".join(f"'{m}'" for m in CHECKLIST_MARKS) + ")", name="ck_application_checklist_items_mark"),
    )


class ApplicationChecklistItemDocument(Base):
    """ccrm-019: a student document counted toward a checklist item. A replaced document's links move to its new version (AC9)."""

    __tablename__ = "application_checklist_item_documents"
    item_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("application_checklist_items.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("student_documents.id", ondelete="CASCADE"), primary_key=True, index=True)
    linked_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProfileDocument(Base, TimestampMixin):
    # STU-011: `StudentDocument` above is Overseas-division-specific (FK to
    # `overseas_applications`, gated to `overseas_student`/counselor/agent roles) --
    # not reusable for an IT student's own CV/portfolio uploads without conflating two
    # different domains. DATA_MODEL.md names no table for STU-011 at all; net-new.
    __tablename__ = "profile_documents"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(80))
    file_url: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)


# itc-026 (DEC-SCOPE-350): migration 0235 repeats these. R6: `hr` -- HR may open the version; `private` -- student and IT staff only.
STUDENT_RESUME_VISIBILITIES = ("hr", "private")
STUDENT_RESUME_MAX_BYTES_CEILING = 10 * 1024 * 1024


class StudentResume(Base):
    """itc-026 (R1, R5): one uploaded resume version of an IT student, append-only. The current resume is the highest version. Separate
    from rec-009 `CandidateResume` (Q-22): the recruiter pool is the student's own opt-in."""

    __tablename__ = "student_resumes"
    __table_args__ = (
        UniqueConstraint("student_user_id", "version", name="uq_student_resumes_version"),
        CheckConstraint(f"visibility IN ({', '.join(repr(v) for v in STUDENT_RESUME_VISIBILITIES)})", name="ck_student_resumes_visibility"),
        CheckConstraint("version >= 1", name="ck_student_resumes_version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(120))
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    visibility: Mapped[str] = mapped_column(String(10), default="hr")
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StudentResumeSetting(Base, TimestampMixin):
    """itc-026 (R4): the IT Admin's resume size limit -- one row (`id = 1`); no row means the 5 MB default."""

    __tablename__ = "student_resume_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_student_resume_settings_one_row"),
        CheckConstraint(f"max_bytes BETWEEN 1048576 AND {STUDENT_RESUME_MAX_BYTES_CEILING}", name="ck_student_resume_settings_max_bytes"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    max_bytes: Mapped[int] = mapped_column(Integer)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


# itc-027 (DEC-SCOPE-354 H1): the HR resume-review stages -- open first, then the two closed ones. Migration 0237 repeats them
# (test_itc_027_migration). Labels (internal and student-safe) live in services/hr_reviews.py and the web client.
HR_REVIEW_OPEN_STAGES = ("resume_received", "under_review", "changes_requested", "screening", "interview_ready")
HR_REVIEW_STAGES = (*HR_REVIEW_OPEN_STAGES, "completed", "withdrawn")


class HrReviewTask(Base, TimestampMixin):
    """itc-027 (H2): the one HR review task of an IT student (unique student; a new shared resume version updates or re-opens it).
    `closed_at` is set while the stage is `completed` or `withdrawn`. `skill_gap_notes` are internal: HR owner and IT Admin only."""

    __tablename__ = "hr_review_tasks"
    __table_args__ = (
        UniqueConstraint("student_user_id", name="uq_hr_review_tasks_student"),
        CheckConstraint(f"stage IN ({', '.join(repr(s) for s in HR_REVIEW_STAGES)})", name="ck_hr_review_tasks_stage"),
        Index("ix_hr_review_tasks_owner_stage", "owner_user_id", "stage"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(20), default="resume_received")
    resume_version: Mapped[int] = mapped_column(Integer)
    screening_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    role_preferences: Mapped[str | None] = mapped_column(String(300), nullable=True)
    skill_gap_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class HrReviewStageHistory(Base):
    """itc-027 (H6): every stage change of a task -- `actor_user_id` NULL for the system (upload, withdrawal); `reason` a fixed token."""

    __tablename__ = "hr_review_stage_history"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("hr_review_tasks.id", ondelete="CASCADE"), index=True)
    from_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HrAssignmentRule(Base, TimestampMixin):
    """itc-027 (H3): a programme's HR reviewer -- the first choice for a new task of a student enrolled in it."""

    __tablename__ = "hr_assignment_rules"
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True)
    hr_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class VisaCase(Base, TimestampMixin):
    __tablename__ = "visa_cases"
    __table_args__ = (
        CheckConstraint("decision IN ('approved', 'refused', 'withdrawn')", name="ck_visa_cases_decision"),
        CheckConstraint("visa_status IN (" + ", ".join(f"'{s}'" for s in VISA_STATUSES) + ")", name="ck_visa_cases_visa_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="checklist")
    appointment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    tracking_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # AGN-012 (DEC-SCOPE-057; migration 0063): written only by the agency visa routes; the counselor/student routes neither read nor
    # write them (V8). `decision` is the authority's outcome as the agency records it, final once set (V2).
    visa_application_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    interview_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ccrm-026 (DEC-SCOPE-254; migration 0177): the Appendix A status every write keeps in step with `status` and `decision`
    # (app/visa_status.py). The submission date is `visa_application_date`, the reference `tracking_reference`. `refusal_reason` is
    # restricted: counselor and Overseas Admin reads only -- never in a log, audit row, notice, student or agency view.
    visa_status: Mapped[str] = mapped_column(String(40), default="not_started", server_default="not_started")
    readiness_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    visa_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    appointment_place: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expected_decision_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    decision_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    outcome_document_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True)
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)


class Scholarship(Base, TimestampMixin):
    __tablename__ = "scholarships"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200))
    country_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("countries.id"), nullable=True)
    university_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id"), nullable=True)
    eligibility: Mapped[str] = mapped_column(Text)
    amount: Mapped[str] = mapped_column(String(120))
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ScholarshipApplication(Base, TimestampMixin):
    __tablename__ = "scholarship_applications"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    scholarship_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("scholarships.id"), index=True)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="submitted")


# tel-016 (DEC-SCOPE-095): a lead's counselling appointment. Statuses EVID-019 §9; open = still to happen (AP5: one per lead).
LEAD_APPOINTMENT_STATUSES = ("scheduled", "confirmed", "rescheduled", "completed", "cancelled", "no_show")
LEAD_APPOINTMENT_OPEN = ("scheduled", "confirmed", "rescheduled")
LEAD_APPOINTMENT_TYPE_LABELS = {
    "career_counselling": "Career counselling", "it_course_counselling": "IT course counselling",
    "overseas_counselling": "Overseas counselling", "university_counselling": "University counselling",
}
LEAD_APPOINTMENT_TYPES = {  # AP4: by the lead's division
    "it": ("career_counselling", "it_course_counselling"),
    "overseas": ("career_counselling", "overseas_counselling", "university_counselling"),
}
APPOINTMENT_MODES = ("Online", "Phone", "In person")  # the student flow's own values (AP7)
APPOINTMENT_CODE_SEQ = Sequence("appointment_code_seq", metadata=Base.metadata)


class Appointment(Base, TimestampMixin):
    """A counselling appointment: a student's (the overseas flow; free-text status, AP12) or, since tel-016, a lead's (`lead_id`, a
    `CAP-` code and the EVID-019 §9 lifecycle). Every row has a student or a lead."""

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("student_id IS NOT NULL OR lead_id IS NOT NULL", name="ck_appointments_subject"),
        Index("ix_appointments_staff_scheduled", "staff_id", "scheduled_at"),
        Index("ix_appointments_lead", "lead_id"),
        Index("uq_appointments_lead_open", "lead_id", unique=True,
              postgresql_where=text("lead_id IS NOT NULL AND status IN ('scheduled', 'confirmed', 'rescheduled')")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    staff_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    appointment_type: Mapped[str] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(40), default="Online")
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    lead_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=True)
    appointment_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    purpose: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meeting_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    booked_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    # ccrm-004 (DEC-SCOPE-259 LG4): what the counselling session concluded, given when the counselor completes it. Never logged.
    outcome_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ccrm-038 (DEC-SCOPE-274 CA2): the `.ics` SEQUENCE -- +1 each time the invite is re-sent for a new time or a cancellation.
    calendar_sequence: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class StoredFile(Base):
    """nehn-003 (DEC-SCOPE-279 PS5): one file uploaded through `POST /files/upload`. `GET /files/{id}` serves it to its owner (and
    super_admin); the key is random and never returned."""

    __tablename__ = "stored_files"
    __table_args__ = (UniqueConstraint("key", name="uq_stored_files_key"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(500))
    purpose: Mapped[str] = mapped_column(String(40))
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubmissionFile(Base):
    """nehn-024 (DEC-SCOPE-292 F1): a stored file attached to an assignment submission. Filename, size and type live on the
    `stored_files` row; a file belongs to one submission."""

    __tablename__ = "submission_files"
    __table_args__ = (UniqueConstraint("stored_file_id", name="uq_submission_files_stored_file"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    submission_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    stored_file_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stored_files.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RolePermission(Base):
    """nehn-005 (DEC-SCOPE-281 P8): one grant -- `role` may `action` on `resource` (both from `rbac.CATALOGUE`). super_admin never has
    rows (it holds everything); a change is audited in `audit_logs` (`role_permissions.update`)."""

    __tablename__ = "role_permissions"
    role: Mapped[str] = mapped_column(String(50), primary_key=True)
    resource: Mapped[str] = mapped_column(String(60), primary_key=True)
    action: Mapped[str] = mapped_column(String(20), primary_key=True)
    granted_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserPermissionOverride(Base):
    """nehn-007 (DEC-SCOPE-299): one user's allow or deny of one catalogue key, on top of their role's grants. A deny wins; a row past
    `expires_at` no longer applies (read-time filter). super_admin users never have rows; a change is audited
    (`user_permission_overrides.update`)."""

    __tablename__ = "user_permission_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "resource", "action", name="uq_user_permission_overrides_user_key"),
        CheckConstraint("effect IN ('allow', 'deny')", name="ck_user_permission_overrides_effect"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resource: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(20))
    effect: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(500))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarFeed(Base):
    """ccrm-038 (DEC-SCOPE-274 CA4): a counselor's read-only iCal feed. Only the SHA-256 of the URL token is kept; regenerating replaces
    the row, revoking deletes it."""

    __tablename__ = "calendar_feeds"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_calendar_feeds_token_hash"),)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppointmentEvent(Base):
    """tel-016 (AP10): one row per lead-appointment transition (creation: from_status NULL). Append-only; `position` orders rows made in
    one transaction. A reschedule keeps the old and the new time."""

    __tablename__ = "appointment_events"
    __table_args__ = (Index("ix_appointment_events_appointment", "appointment_id", "position"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    appointment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("appointments.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    old_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EMISchedule(Base, TimestampMixin):
    """PAY-001/STU-010, DATA_MODEL.md #7.2. Admin-discretionary installment plan -- no fixed
    amortization/interest policy is confirmed anywhere, so installment amounts/due dates are
    supplied explicitly by the creating Admin rather than computed, matching this session's
    established "don't invent an unconfirmed business rule" convention (e.g. AGT commission rate).
    """

    __tablename__ = "emi_schedules"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    division: Mapped[str] = mapped_column(String(30), index=True)
    reference_type: Mapped[str] = mapped_column(String(50))
    reference_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    installment_count: Mapped[int] = mapped_column(Integer)
    created_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


# itc-013 (DEC-SCOPE-346, migration 0230 repeats it): how a payment was made, shown on the receipt. Staff record the offline ones;
# `razorpay` is set only by the gateway's own confirmation.
PAYMENT_MODES = ("cash", "upi", "card", "bank_transfer", "cheque", "razorpay")


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(_in("payment_mode", PAYMENT_MODES), name="ck_payments_payment_mode"),
        Index("ix_payments_status_due_date", "status", "due_date"),  # itc-016 (0240): the daily fee-reminder sweep
        Index("ix_payments_paid_at", "paid_at"),  # itc-017 (0248): the accounts workspace's collection reports
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    division: Mapped[str] = mapped_column(String(30), index=True)
    reference_type: Mapped[str] = mapped_column(String(50))
    reference_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    provider: Mapped[str] = mapped_column(String(30), default="manual")
    provider_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    emi_schedule_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("emi_schedules.id"), nullable=True, index=True)
    installment_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checkout_idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    checkout_provider_order_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # nehn-019 (DEC-SCOPE-315, migration 0215): `amount` stays the net payable; the discount is recorded beside it, so the gross
    # amount is `amount + discount_amount` (derived, never stored twice). Reason/actor are the latest discount's; `paid_at` is set
    # by `payments._mark_paid` and an admin-recorded paid payment.
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0, server_default="0")
    discount_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    discounted_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ccrm-049 (DEC-SCOPE-326, migration 0216): the receipt / proof staff uploaded for a manual payment -- a "Payment receipt" document
    # of the student, distinct from the system `Receipt` PDF. A deleted document leaves no proof.
    proof_document_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True)
    payment_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)  # itc-013: PAYMENT_MODES; None = not recorded

    @property
    def gross_amount(self) -> float:
        return float(self.amount) + float(self.discount_amount or 0)


# itc-016 (DEC-SCOPE-358, migration 0240 repeats them): the fee-reminder schedule and what was sent. "Overdue" is derived (an owed fee
# row whose due date is before today's IST date), never stored on the payment.
FEE_REMINDER_KINDS = ("due_soon", "overdue")
FEE_REMINDER_DEFAULTS = {"days_before": 3, "overdue_days": [1, 7, 14]}  # Q-16's recommended answer, NEEDS_CONFIRMATION


class FeeReminderSetting(Base, TimestampMixin):
    """itc-016 (F3): the IT Admin's schedule -- one row (`id = 1`); no row means `FEE_REMINDER_DEFAULTS`. `days_before` 0 and an empty
    `overdue_days` switch their rules off."""

    __tablename__ = "fee_reminder_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_fee_reminder_settings_one_row"),
        CheckConstraint("days_before BETWEEN 0 AND 30", name="ck_fee_reminder_settings_days_before"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    days_before: Mapped[int] = mapped_column(Integer)
    overdue_days: Mapped[list] = mapped_column(JSON, default=list)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class FeeReminderLog(Base):
    """itc-016 (F5/F7): one row per reminder sent -- at most one per (installment, rule, IST day), so a rerun sends nothing twice."""

    __tablename__ = "fee_reminder_log"
    __table_args__ = (
        UniqueConstraint("payment_id", "kind", "offset_days", "reminder_date", name="uq_fee_reminder_log_rule_day"),
        CheckConstraint(_in("kind", FEE_REMINDER_KINDS), name="ck_fee_reminder_log_kind"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"))
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))
    offset_days: Mapped[int] = mapped_column(Integer)
    reminder_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    counselor_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


FEE_DISCOUNT_STATUSES = ("pending", "approved", "rejected")


class FeeDiscountRequest(Base, TimestampMixin):
    """itc-014 (DEC-SCOPE-363, migration 0245 repeats it): an amount off an enrolment's owed fee, asked by one person and decided by
    another (maker-checker). Only an approval changes the fee rows; at most one request per enrolment is pending."""

    __tablename__ = "fee_discount_requests"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_fee_discount_requests_amount"),
        CheckConstraint(_in("status", FEE_DISCOUNT_STATUSES), name="ck_fee_discount_requests_status"),
        Index("uq_fee_discount_requests_one_pending", "enrollment_id", unique=True, postgresql_where=text("status = 'pending'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    decided_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)


# itc-015 (DEC-SCOPE-364, migration 0246 repeats them): credit notes and write-offs lower what an enrolment owes, a refund pays a credit
# back out, a reversal replaces a mistyped manual payment. A refund names how the money went back (the offline modes; Q-15 manual only).
FEE_ADJUSTMENT_KINDS = ("credit_note", "write_off", "refund", "reversal")
REFUND_MODES = ("cash", "upi", "card", "bank_transfer", "cheque")


class FeeAdjustment(Base):
    """itc-015 (F1/F2): one immutable fee-ledger line of an enrolment -- never updated or deleted. `applied_amount` is the part of a credit
    note / write-off that lowered owed bills (the rest is a credit). The recorder is the approver until maker-checker (Q-14)."""

    __tablename__ = "fee_adjustments"
    __table_args__ = (
        CheckConstraint(f"kind IN ({', '.join(repr(k) for k in FEE_ADJUSTMENT_KINDS)})", name="ck_fee_adjustments_kind"),
        CheckConstraint("amount > 0", name="ck_fee_adjustments_amount"),
        CheckConstraint("applied_amount >= 0 AND applied_amount <= amount", name="ck_fee_adjustments_applied"),
        CheckConstraint(_in("payment_mode", REFUND_MODES), name="ck_fee_adjustments_mode"),
        Index("uq_fee_adjustments_reversal", "payment_id", unique=True, postgresql_where=text("kind = 'reversal'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    applied_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0, server_default="0")
    reason: Mapped[str] = mapped_column(String(500))
    payment_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    payment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    replacement_payment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    document_no: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    approved_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invoice(Base, TimestampMixin):
    """DATA_MODEL.md #7.2, PRD-PAY-003: generated when a Payment is created (billed)."""

    __tablename__ = "invoices"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"), unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    division: Mapped[str] = mapped_column(String(30), index=True)
    invoice_no: Mapped[str] = mapped_column(String(60), unique=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    file_url: Mapped[str] = mapped_column(String(500))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Receipt(Base, TimestampMixin):
    """DATA_MODEL.md #7.2, PRD-PAY-003: generated when a Payment reaches paid/succeeded."""

    __tablename__ = "receipts"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"), unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    division: Mapped[str] = mapped_column(String(30), index=True)
    receipt_no: Mapped[str] = mapped_column(String(60), unique=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    file_url: Mapped[str] = mapped_column(String(500))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentWebhookEvent(Base, TimestampMixin):
    """DATA_MODEL.md #7.2, INTEGRATION_CONTRACTS.md #2: every inbound webhook is persisted,
    verified or not, keyed on Razorpay's `x-razorpay-event-id` header (confirmed via Razorpay's
    own webhook docs -- the dedup id is a header, not a JSON body field) so a retried delivery
    is acknowledged exactly once and never reprocessed (PAY-001-AC03).
    """

    __tablename__ = "payment_webhook_events"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(30))
    event_id: Mapped[str] = mapped_column(String(160), unique=True)
    signature_verified: Mapped[bool] = mapped_column(Boolean)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    payment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# tel-003 (DEC-SCOPE-077 L1): LD-000001 Lead IDs. On the metadata so 0001's create_all builds it before the table on a fresh database;
# 0078 creates it on an upgraded one. format('%6s') pads to six and, unlike lpad, never truncates (LD-1234567); one nextval, so atomic.
ENQUIRY_LEAD_CODE_SEQ = Sequence("enquiry_lead_code_seq", metadata=Base.metadata)
LEAD_CODE_DEFAULT = "'LD-' || translate(format('%6s', nextval('enquiry_lead_code_seq')), ' ', '0')"
LEAD_PRIORITIES = ("hot", "warm", "cold")
LEAD_CHECKS = {  # migration 0078 repeats these strings; test_tel_003_migration asserts they stay identical
    "ck_enquiries_source": f"source IN ({', '.join(repr(s) for s in TEL_SOURCES)})",
    "ck_enquiries_priority": f"priority IN ({', '.join(repr(p) for p in LEAD_PRIORITIES)})",
    "ck_enquiries_passing_year": "passing_year IS NULL OR passing_year BETWEEN 1950 AND 2100",
}
# tel-004 (DEC-SCOPE-081): `status` is a pipeline stage; migration 0081 repeats this string (test_tel_004_migration).
LEAD_STATUS_CHECK = f"status IN ({', '.join(repr(s) for s in LEAD_STAGES)})"
LEAD_NEXT_ACTION_MAX = 200  # ccrm-003; migration 0168 repeats it (test_ccrm_003_migration asserts they stay identical)
# ccrm-005 (DEC-SCOPE-260, LF1/LF5): the spec §3 contact, consent and referral fields; migration 0182 repeats these (test_ccrm_005_migration).
CONTACT_PREFERENCES = ("call", "whatsapp", "email", "sms")
LEAD_REFERRAL_NAME_MAX, LEAD_REFERRAL_CONTACT_MAX = 160, 120
LEAD_FIELD_CHECKS = {
    "ck_enquiries_contact_preference": _in("contact_preference", CONTACT_PREFERENCES),
    "ck_enquiries_marketing_consent": "(marketing_opt_in IS NULL) = (marketing_consent_at IS NULL)",
}
ENQUIRY_DATE_DEFAULT = "(now() AT TIME ZONE 'Asia/Kolkata')::date"  # LF4: the created date in IST
# ccrm-006 (DEC-SCOPE-264, D3/D4): a Duplicate names its surviving lead; a reason and "lost to" only on Lost / Not Interested. Migration 0186
# repeats these (test_ccrm_006_migration).
LEAD_LOST_REASON_NAME_MAX, LEAD_LOST_TO_MAX = 120, 160
_LOSS_SQL = f"status IN ({', '.join(repr(s) for s in LOSS_STAGES)})"
LEAD_CLOSURE_CHECKS = {
    "ck_enquiries_duplicate_not_self": "duplicate_of_id IS NULL OR duplicate_of_id <> id",
    "ck_enquiries_duplicate_of": "(duplicate_of_id IS NOT NULL) = (status = 'duplicate')",
    "ck_enquiries_lost_reason": f"lost_reason_id IS NULL OR {_LOSS_SQL}",
    "ck_enquiries_lost_to": f"lost_to IS NULL OR ({_LOSS_SQL} AND length(lost_to) BETWEEN 1 AND {LEAD_LOST_TO_MAX})",
}
# itc-007 (DEC-SCOPE-341): a merged lead is closed as a Duplicate of its survivor, with who merged it and when.
LEAD_MERGED_CHECK = "(merged_at IS NULL) = (merged_by_user_id IS NULL) AND (merged_at IS NULL OR status = 'duplicate')"


class LeadLostReason(Base, TimestampMixin):
    """ccrm-006 (D8): the admin-managed list a Lost / Not Interested close picks its reason from -- tel-002's catalogue pattern. Never
    deleted: deactivating hides it from the picker while closed leads keep it."""

    __tablename__ = "lead_lost_reasons"
    __table_args__ = (
        CheckConstraint(f"length(name) BETWEEN 1 AND {LEAD_LOST_REASON_NAME_MAX}", name="ck_lead_lost_reasons_name"),
        Index("uq_lead_lost_reasons_name", text("lower(name)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(LEAD_LOST_REASON_NAME_MAX))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


IT_STATUS_LABEL_MAX = 60


class ItStatusLabel(Base, TimestampMixin):
    """itc-005 (DEC-SCOPE-362 S1-S3): the IT team's override of one fixed status -- its label, order and (only for states a person
    chooses, S4) whether it is offered. No row = the code default. `kind` is `lead` (lead_stages) or `lifecycle` (it_lifecycle)."""

    __tablename__ = "it_status_labels"
    __table_args__ = (
        CheckConstraint("team = 'it'", name="ck_it_status_labels_team"),
        CheckConstraint("kind IN ('lead', 'lifecycle')", name="ck_it_status_labels_kind"),
        CheckConstraint(f"length(label) BETWEEN 1 AND {IT_STATUS_LABEL_MAX}", name="ck_it_status_labels_label"),
        CheckConstraint("sort_order BETWEEN 0 AND 9999", name="ck_it_status_labels_sort_order"),
    )
    team: Mapped[str] = mapped_column(String(20), primary_key=True, default="it")
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(IT_STATUS_LABEL_MAX))
    sort_order: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class Enquiry(Base, TimestampMixin):
    """bdm-017 (DEC-SCOPE-072): a BDM-entered lead carries its organization and BDM (both NULL for website and manual enquiries);
    a division admin's explicit conversion links it to one student account (`uq_enquiries_converted_user`: one lead per user).
    tel-003 (DEC-SCOPE-077, T6): every enquiry is a lead -- a database-assigned Lead ID and the EVID-019 §2 fields. `owner_id` stays the
    assigned counselor; `phone_normalized` follows `phone` (the validator below) for duplicate matching."""

    __tablename__ = "enquiries"
    __table_args__ = (
        CheckConstraint("(bdm_organization_id IS NULL) = (bdm_user_id IS NULL)", name="ck_enquiries_bdm_attribution"),
        CheckConstraint(
            "(converted_user_id IS NULL) = (converted_at IS NULL) AND (converted_user_id IS NULL) = (converted_by_user_id IS NULL)",
            name="ck_enquiries_conversion",
        ),
        *(CheckConstraint(sql, name=name) for name, sql in (LEAD_CHECKS | LEAD_FIELD_CHECKS | LEAD_CLOSURE_CHECKS).items()),
        CheckConstraint(LEAD_STATUS_CHECK, name="ck_enquiries_status"),
        CheckConstraint(f"next_action IS NULL OR length(next_action) BETWEEN 1 AND {LEAD_NEXT_ACTION_MAX}", name="ck_enquiries_next_action_len"),
        CheckConstraint(LEAD_MERGED_CHECK, name="ck_enquiries_merged"),  # itc-007; migration 0225 repeats it
        UniqueConstraint("lead_code", name="uq_enquiries_lead_code"),
        Index("ix_enquiries_bdm_org_created", "bdm_organization_id", "created_at"),
        Index("uq_enquiries_converted_user", "converted_user_id", unique=True, postgresql_where=text("converted_user_id IS NOT NULL")),
        Index("ix_enquiries_telecaller_status", "telecaller_user_id", "status"),
        Index("ix_enquiries_phone_normalized", "phone_normalized"),
        Index("ix_enquiries_email_lower", text("lower(email)")),
        Index("ix_enquiries_campaign", "campaign_id"),
        Index("ix_enquiries_product", "product_id"),
        # nehn-012 (migration 0205): the lead lists' India-time created range and counselor filters
        Index("ix_enquiries_created", "created_at", "id"),
        Index("ix_enquiries_owner", "owner_id"),
    )
    __mapper_args__ = {"eager_defaults": True}  # the INSERT returns lead_code / stage_changed_at: no lazy load on an async session
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)  # tel-005 I1: a manual lead may have a mobile only
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(80), default="website")
    status: Mapped[str] = mapped_column(String(40), default="new")
    owner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    crm_sync_status: Mapped[str] = mapped_column(String(40), default="pending")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    bdm_organization_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=True)
    bdm_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    converted_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    lead_code: Mapped[str] = mapped_column(String(20), server_default=text(LEAD_CODE_DEFAULT))
    phone_normalized: Mapped[str | None] = mapped_column(String(20), nullable=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    qualification: Mapped[str | None] = mapped_column(String(120), nullable=True)
    passing_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    institution: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_products.id"), nullable=True)
    campaign_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_campaigns.id"), nullable=True)
    telecaller_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    priority: Mapped[str] = mapped_column(String(10), default="warm", server_default=text("'warm'"))
    stage_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # ccrm-003 (DEC-SCOPE-243, A2): what the counselor does next and by when -- required on a counselor-owned open lead's stage move
    next_action: Mapped[str | None] = mapped_column(String(LEAD_NEXT_ACTION_MAX), nullable=True)
    next_action_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    # ccrm-005 (DEC-SCOPE-260): how the person likes to be reached, when they enquired (LF4), their marketing consent -- NULL = not asked,
    # stamped whenever it changes (LF5, the validator below) -- and who referred them
    contact_preference: Mapped[str | None] = mapped_column(String(10), nullable=True)
    enquiry_date: Mapped[date] = mapped_column(Date, server_default=text(ENQUIRY_DATE_DEFAULT))
    marketing_opt_in: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    marketing_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    referral_name: Mapped[str | None] = mapped_column(String(LEAD_REFERRAL_NAME_MAX), nullable=True)
    referral_contact: Mapped[str | None] = mapped_column(String(LEAD_REFERRAL_CONTACT_MAX), nullable=True)
    # ccrm-006 (DEC-SCOPE-264): how the lead closed -- set by lead_pipeline.person_move, cleared on reopen (D7)
    duplicate_of_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=True)
    lost_reason_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("lead_lost_reasons.id", ondelete="RESTRICT"), nullable=True)
    lost_to: Mapped[str | None] = mapped_column(String(LEAD_LOST_TO_MAX), nullable=True)
    # itc-007 (DEC-SCOPE-341): set when this lead was merged into `duplicate_of_id`; a merged lead is read only (never reopened)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

    @validates("phone")
    def _derive_phone_normalized(self, _key: str, phone: str | None) -> str | None:
        self.phone_normalized = normalise_phone(phone)
        return phone

    @validates("marketing_opt_in")
    def _stamp_consent(self, _key: str, opt_in: bool | None) -> bool | None:
        if opt_in is None:
            self.marketing_consent_at = None
        elif opt_in != self.marketing_opt_in or self.marketing_consent_at is None:
            self.marketing_consent_at = datetime.now(UTC)
        return opt_in


class LeadStageHistory(Base):
    """tel-004 (DEC-SCOPE-081, spec §3): one row per lead stage change. Append-only. `event` is a system event name, `manual`, `reopen` or
    `legacy_mapping`; `actor_user_id` is NULL for the system. No stage CHECK: history must survive a future catalogue change (bdm-004).
    `position` orders rows created in one transaction."""

    __tablename__ = "lead_stage_history"
    __table_args__ = (Index("ix_lead_stage_history_lead", "lead_id", "position"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"))
    from_stage: Mapped[str] = mapped_column(String(40))
    to_stage: Mapped[str] = mapped_column(String(40))
    event: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeadEnquiry(Base):
    """tel-005 (DEC-SCOPE-088, T12): a further enquiry from a person who is already a lead -- added by a telecaller or manager from the
    duplicate panel, or a website enquiry that matched (`created_by_user_id` NULL). Append-only; the lead's timeline lists it."""

    __tablename__ = "lead_enquiries"
    __table_args__ = (
        CheckConstraint(f"source IN ({', '.join(repr(s) for s in TEL_SOURCES)})", name="ck_lead_enquiries_source"),
        Index("ix_lead_enquiries_lead", "lead_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"))
    subject: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30))
    campaign_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_campaigns.id"), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


QUAL_SKILL_LEVELS = ("beginner", "intermediate", "advanced")
QUAL_MODES = ("online", "offline")
QUAL_STUDY_LEVELS = ("ug", "masters")
QUAL_PASSPORT = ("none", "applied", "valid")
STUDY_MODES = ("full_time", "part_time", "online")  # ccrm-007's lists; ccrm-005's lead answers use them too
ENGLISH_TEST_STATUSES = ("not_taken", "booked", "taken")
# ccrm-005 (DEC-SCOPE-260, LF1): the overseas study and academic answers; migration 0182 repeats these (test_ccrm_005_migration).
LEAD_QUAL_FIELD_CHECKS = {
    "ck_lead_qualifications_study_mode": _in("study_mode", STUDY_MODES),
    "ck_lead_qualifications_cgpa": "academic_cgpa IS NULL OR academic_cgpa BETWEEN 0 AND 10",
    "ck_lead_qualifications_backlogs": "backlogs IS NULL OR backlogs BETWEEN 0 AND 99",
}


class LeadQualification(Base, TimestampMixin):
    """tel-009 (DEC-SCOPE-093, EVID-019 §4): a lead's qualification -- the basic answers plus the IT or overseas requirement. One row per
    lead; the shared answers (qualification, passing year, city, state) stay on `enquiries` (QD1). The group not shown for the lead's
    current product keeps its values (AC3)."""

    __tablename__ = "lead_qualifications"
    __table_args__ = (
        CheckConstraint("work_experience_years IS NULL OR work_experience_years BETWEEN 0 AND 50", name="ck_lead_qualifications_experience"),
        CheckConstraint("academic_percentage IS NULL OR academic_percentage BETWEEN 0 AND 100", name="ck_lead_qualifications_percentage"),
        CheckConstraint(_in("it_skill_level", QUAL_SKILL_LEVELS), name="ck_lead_qualifications_skill_level"),
        CheckConstraint(_in("preferred_mode", QUAL_MODES), name="ck_lead_qualifications_mode"),
        CheckConstraint(_in("study_level", QUAL_STUDY_LEVELS), name="ck_lead_qualifications_study_level"),
        CheckConstraint(_in("passport_status", QUAL_PASSPORT), name="ck_lead_qualifications_passport"),
        *(CheckConstraint(sql, name=name) for name, sql in LEAD_QUAL_FIELD_CHECKS.items()),
    )
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="CASCADE"), primary_key=True)
    current_org: Mapped[str | None] = mapped_column(String(200), nullable=True)
    work_experience_years: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    it_skill_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    career_objective: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preferred_batch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    budget_range: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preferred_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    study_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    preferred_course: Mapped[str | None] = mapped_column(String(200), nullable=True)
    intake: Mapped[str | None] = mapped_column(String(40), nullable=True)
    academic_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    english_test_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    passport_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # ccrm-005 (LF1): the spec §3 study preferences and academic profile beside tel-009's overseas answers
    preferred_country_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("countries.id", ondelete="SET NULL"), nullable=True)
    study_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferred_campus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    academic_cgpa: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    backlogs: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class LeadEnglishTest(Base):
    """ccrm-005 (DEC-SCOPE-260, LF3): one English test on a lead, in the order entered -- ccrm-007's row shape, so a conversion copies it
    as is (LF8). Replaced as a list with the overseas qualification answers."""

    __tablename__ = "lead_english_tests"
    __table_args__ = (
        UniqueConstraint("lead_id", "position", name="uq_lead_english_tests_position"),
        CheckConstraint(f"test_type IN ({', '.join(repr(v) for v in ENGLISH_TESTS)})", name="ck_lead_english_tests_type"),
        CheckConstraint(_in("status", ENGLISH_TEST_STATUSES), name="ck_lead_english_tests_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    test_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    test_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(200), nullable=True)


class LeadImportBatch(Base, TimestampMixin):
    """tel-006 (DEC-SCOPE-091, IM1): one CSV lead import for a campaign. The file is never stored (R9): only its hash, the counts and each
    row's outcome {row_number, status, lead_id, error} -- no names, phones or emails. The Idempotency-Key is scoped to the uploader (R8)."""

    __tablename__ = "lead_import_batches"
    __table_args__ = (
        UniqueConstraint("uploaded_by_user_id", "idempotency_key", name="uq_lead_import_batches_key"),
        CheckConstraint("division IN ('it', 'overseas')", name="ck_lead_import_batches_division"),
        CheckConstraint("created_count + attached_count + rejected_count = total_rows", name="ck_lead_import_batches_counts"),
        Index("ix_lead_import_batches_uploader", "uploaded_by_user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_campaigns.id"))
    division: Mapped[str] = mapped_column(String(20))
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    file_sha256: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    attached_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    results_json: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))


# tel-011 (DEC-SCOPE-094): the EVID-019 §7 follow-up reasons (L284-L302) and states; migration 0090 repeats LEAD_FOLLOW_UP_CHECKS
# (test_tel_011_migration asserts they stay identical). Labels live in the web client.
LEAD_FOLLOW_UP_REASONS = (
    "discuss_with_parents", "course_details", "fee_details", "waiting_salary", "waiting_documents", "comparing_courses", "next_month",
    "next_intake", "university_information", "counselor_call",
)
LEAD_FOLLOW_UP_STATUSES = ("open", "done", "cancelled")
LEAD_FOLLOW_UP_CHECKS = {
    "ck_lead_follow_ups_reason": f"reason IN ({', '.join(repr(r) for r in LEAD_FOLLOW_UP_REASONS)})",
    "ck_lead_follow_ups_status": f"status IN ({', '.join(repr(s) for s in LEAD_FOLLOW_UP_STATUSES)})",
    "ck_lead_follow_ups_state": (
        "(status = 'done') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL) "
        "AND (status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)"
    ),
}


class LeadFollowUp(Base, TimestampMixin):
    """tel-011 (DEC-SCOPE-094): a follow-up on a lead. It belongs to the lead (F3): whoever has the lead in scope sees it, so a
    reassignment moves it with no rewrite; `created_by` / `completed_by` keep who did what. A closing stage move cancels the open ones (F4)."""

    __tablename__ = "lead_follow_ups"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in LEAD_FOLLOW_UP_CHECKS.items()),
        Index("ix_lead_follow_ups_lead", "lead_id", "status", "due_at"),
        Index("ix_lead_follow_ups_open_due", "due_at", postgresql_where=text("status = 'open'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", server_default=text("'open'"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # itc-009: escalated once, never again


# tel-010 (DEC-SCOPE-096): the EVID-019 §5 call types (CL1) and the 13 selectable outcomes (L226-L250; "Converted" is computed, T5).
# Migration 0092 repeats LEAD_CALL_CHECKS (test_tel_010_migration asserts they stay identical). Labels and effects: services/lead_calls.py.
LEAD_CALL_TYPES = ("outgoing", "incoming")
LEAD_CALL_OUTCOMES = (
    "interested", "need_information", "follow_up_required", "appointment_fixed", "not_interested", "wrong_number", "busy", "no_answer",
    "switched_off", "call_back_requested", "already_joined", "duplicate_lead", "not_eligible",
)
LEAD_CALL_MAX_SECONDS = 14400  # D7: 4 hours
LEAD_CALL_CHECKS = {
    "ck_lead_calls_call_type": f"call_type IN ({', '.join(repr(t) for t in LEAD_CALL_TYPES)})",
    "ck_lead_calls_outcome": f"outcome IN ({', '.join(repr(o) for o in LEAD_CALL_OUTCOMES)})",
    "ck_lead_calls_duration": f"duration_seconds BETWEEN 0 AND {LEAD_CALL_MAX_SECONDS}",
}


class LeadCall(Base, TimestampMixin):
    """tel-010 (DEC-SCOPE-096): a call logged on a lead (T7: manual, beside a `tel:` link). Like a follow-up it belongs to the lead, so its
    scope is the lead's; `caller_user_id` keeps who made it (the daily counts and the edit/delete gate)."""

    __tablename__ = "lead_calls"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in LEAD_CALL_CHECKS.items()),
        Index("ix_lead_calls_caller_occurred", "caller_user_id", "occurred_at"),
        Index("ix_lead_calls_lead_occurred", "lead_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"))
    caller_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    call_type: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(32))
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


LEAD_NOTE_MAX = 4000  # migration 0167 repeats it (test_ccrm_002_migration asserts they stay identical)


class LeadNote(Base):
    """ccrm-002 (DEC-SCOPE-242): a free-text note on a lead. Append-only (N2: no edit or delete, so no `updated_at`); its scope is the
    lead's, read through each lead route's own scope. Plain text, never logged."""

    __tablename__ = "lead_notes"
    __table_args__ = (
        CheckConstraint(f"length(body) BETWEEN 1 AND {LEAD_NOTE_MAX}", name="ck_lead_notes_body"),
        Index("ix_lead_notes_lead_created", "lead_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"))
    author_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


LEAD_MEETING_NOTES_MAX = 2000  # migration 0181 repeats it (test_ccrm_004_migration asserts they stay identical)


class LeadMeeting(Base):
    """ccrm-004 (DEC-SCOPE-259 LG3): a meeting the lead's counselor held with them -- when, how (the appointment modes) and notes.
    Append-only, as ccrm-002 notes; its scope is the lead's. The notes are never logged."""

    __tablename__ = "lead_meetings"
    __table_args__ = (
        CheckConstraint("mode IN ({})".format(", ".join(f"'{m}'" for m in APPOINTMENT_MODES)), name="ck_lead_meetings_mode"),
        CheckConstraint(f"length(notes) BETWEEN 1 AND {LEAD_MEETING_NOTES_MAX}", name="ck_lead_meetings_notes"),
        Index("ix_lead_meetings_lead_occurred", "lead_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"))
    author_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# itc-010 (DEC-SCOPE-343): the IT counseling record. Migration 0227 repeats LEAD_COUNSELING_CHECKS (test_itc_010_migration).
COUNSELING_DECISION_MAKERS = ("self", "parent", "spouse", "employer", "other")
COUNSELING_OUTCOMES = ("interested", "needs_time", "not_interested", "enrolled")
COUNSELING_NOTES_MAX, COUNSELING_OBJECTION_NOTES_MAX, COUNSELING_OBJECTION_NAME_MAX = 4000, 1000, 120
LEAD_COUNSELING_CHECKS = {
    "ck_lead_counseling_records_decision_maker": "decision_maker IS NULL OR decision_maker IN ({})".format(", ".join(repr(v) for v in COUNSELING_DECISION_MAKERS)),
    "ck_lead_counseling_records_outcome": "outcome IN ({})".format(", ".join(repr(v) for v in COUNSELING_OUTCOMES)),
    "ck_lead_counseling_records_fee": "fee_quoted IS NULL OR fee_quoted >= 0",
    "ck_lead_counseling_records_notes": f"notes IS NULL OR length(notes) <= {COUNSELING_NOTES_MAX}",
    "ck_lead_counseling_records_objection_notes": f"objection_notes IS NULL OR length(objection_notes) <= {COUNSELING_OBJECTION_NOTES_MAX}",
}


class LeadCounselingObjection(Base, TimestampMixin):
    """itc-010 (C6): the managed list a counseling session's objections are picked from -- the lost-reason catalogue pattern. Never
    deleted: deactivating hides it from the picker while past sessions keep it."""

    __tablename__ = "lead_counseling_objections"
    __table_args__ = (
        CheckConstraint(f"length(name) BETWEEN 1 AND {COUNSELING_OBJECTION_NAME_MAX}", name="ck_lead_counseling_objections_name"),
        Index("uq_lead_counseling_objections_name", text("lower(name)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(COUNSELING_OBJECTION_NAME_MAX))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class LeadCounselingRecord(Base, TimestampMixin):
    """itc-010 (DEC-SCOPE-343, C1): one counseling session an IT counselor held with a lead. Career goal and current skills are the
    lead's qualification (C2). Internal: never shown to the student; the notes are never logged (C11)."""

    __tablename__ = "lead_counseling_records"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in LEAD_COUNSELING_CHECKS.items()),
        Index("ix_lead_counseling_records_lead_created", "lead_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"))
    author_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    recommended_product_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_products.id", ondelete="RESTRICT"), nullable=True)
    objection_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    fee_quoted: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    decision_maker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20))
    next_follow_up: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class LeadCounselingRecordObjection(Base):
    """itc-010: the objections picked for one session (the set is replaced whole on an edit)."""

    __tablename__ = "lead_counseling_record_objections"
    record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lead_counseling_records.id", ondelete="CASCADE"), primary_key=True)
    objection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lead_counseling_objections.id", ondelete="RESTRICT"), primary_key=True)


# Migration 0095 repeats LEAD_MESSAGE_CHECKS (test_tel_013_migration asserts they stay identical).
LEAD_MESSAGE_CHECKS = {
    "ck_lead_messages_channel": "channel IN ('whatsapp', 'email')",
    "ck_lead_messages_body": "length(body) BETWEEN 1 AND 5000",
    "ck_lead_messages_whatsapp": "channel <> 'whatsapp' OR (subject IS NULL AND delivery_status IS NULL)",
}
# tel-014 (DEC-SCOPE-106 E5): an email row has a subject and a delivery status. Migration 0097 repeats it (test_tel_014_migration).
LEAD_EMAIL_STATUSES = ("queued", "sending", "retrying", "sent", "failed")
LEAD_MESSAGE_EMAIL_CHECK = {
    "ck_lead_messages_email": f"channel <> 'email' OR (subject IS NOT NULL AND delivery_status IS NOT NULL AND delivery_status IN ({', '.join(repr(s) for s in LEAD_EMAIL_STATUSES)}))",
}


class LeadMessage(Base, TimestampMixin):
    """tel-013 (DEC-SCOPE-100): a message sent to a lead -- WhatsApp via wa.me (T8; the row is the telecaller's confirmation, WA1 keeps the
    full text) and, from tel-014, email (subject + delivery status; `attempt_count` counts SMTP attempts, DEC-SCOPE-106 E5). It belongs to
    the lead, so its scope is the lead's. `template_name` is the template's name when sent (D6), so a rename never rewrites history."""

    __tablename__ = "lead_messages"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in (LEAD_MESSAGE_CHECKS | LEAD_MESSAGE_EMAIL_CHECK).items()),
        Index("ix_lead_messages_lead_sent", "lead_id", "sent_at"),
        Index("ix_lead_messages_sender_sent", "sender_user_id", "sent_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"))
    sender_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    channel: Mapped[str] = mapped_column(String(16))
    template_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_message_templates.id", ondelete="RESTRICT"), nullable=True)
    template_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContentPage(Base, TimestampMixin):
    __tablename__ = "content_pages"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    slug: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    seo: Mapped[dict] = mapped_column(JSON, default=dict)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("division", "slug", name="uq_content_division_slug"),)


class BlogPost(Base, TimestampMixin):
    __tablename__ = "blog_posts"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(220))
    summary: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100))
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class Event(Base, TimestampMixin):
    __tablename__ = "events"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(220))
    event_type: Mapped[str] = mapped_column(String(80))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    registration_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


# PUB-022 (DEC-SCOPE-210 SP4/SP6): nothing is public until published, and nothing is published without recorded consent.
# Migration 0158_social_proof repeats these exactly (test_pub_022_migration).
TESTIMONIAL_CHECKS = {
    "ck_testimonials_publish_needs_consent": "NOT published OR consent_confirmed",
    "ck_testimonials_rating_range": "rating BETWEEN 1 AND 5",
    "ck_testimonials_division": "division IN ('it', 'overseas')",
}
RATING_BADGE_CHECKS = {
    "ck_site_rating_badge_single": "id = 1",
    "ck_site_rating_badge_rating": "rating >= 0 AND rating <= 5",
    "ck_site_rating_badge_count": "review_count >= 0",
}


class Testimonial(Base, TimestampMixin):
    __tablename__ = "testimonials"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in TESTIMONIAL_CHECKS.items()),
        Index("ix_testimonials_strip", "division", "published", "featured", "display_order"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    person_name: Mapped[str] = mapped_column(String(160))
    headline: Mapped[str] = mapped_column(String(200))
    quote: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer, default=5)
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    context: Mapped[str | None] = mapped_column(String(160), nullable=True)
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    consent_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    photo_key: Mapped[str | None] = mapped_column(String(300), nullable=True)  # a storage key; never sent to any client
    photo_content_type: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SiteRatingBadge(Base, TimestampMixin):
    """PUB-022 SP5: the one organisation-wide rating badge (e.g. "4.8 on Google"), entered by a Super Admin."""

    __tablename__ = "site_rating_badge"
    __table_args__ = tuple(CheckConstraint(sql, name=name) for name, sql in RATING_BADGE_CHECKS.items())
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    source_name: Mapped[str] = mapped_column(String(60))
    rating: Mapped[Decimal] = mapped_column(Numeric(2, 1))
    review_count: Mapped[int] = mapped_column(Integer)
    review_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    as_of: Mapped[date] = mapped_column(Date)
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class CareerPath(Base, TimestampMixin):
    """PUB-001 / PRD-PUB-004: career-path roadmaps with skills/related-courses/outcomes detail."""

    __tablename__ = "career_paths"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True, default="it")
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    related_program_slugs: Mapped[list] = mapped_column(JSON, default=list)
    outcomes: Mapped[str] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class RealProject(Base, TimestampMixin):
    """PUB-001 / PRD-PUB-005: real-world project examples with a detail view."""

    __tablename__ = "real_projects"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True, default="it")
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    tech_stack: Mapped[list] = mapped_column(JSON, default=list)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    # AGN-017 (DEC-SCOPE-059 N6): only scheduled reminders set `dedupe_key`; the partial unique index makes a repeat run a no-op.
    # itc-002 (DEC-SCOPE-336): the inbox index serves GET /workflows/notifications and the unread count.
    __table_args__ = (
        Index("ux_notifications_dedupe_key", "dedupe_key", unique=True, postgresql_where=text("dedupe_key IS NOT NULL")),
        Index("ix_notifications_user_read_created", "user_id", "read", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # itc-002: set only by app.notifications.events.notify (an EVENTS key and the record it is about); older notices stay NULL.
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)


class NotificationDelivery(Base, TimestampMixin):
    __tablename__ = "notification_deliveries"
    # ENH-014: the stale-delivery sweeper filters on (status, updated_at).
    __table_args__ = (Index("ix_notification_deliveries_status_updated_at", "status", "updated_at"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    notification_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    provider_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ENH-014: what the worker needs to render the email exactly as the old inline path did --
    # {"kind": "school", "school_name": ...} for the School path, null for the generic path and every pre-ENH-014 row.
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class NotificationPreference(Base, TimestampMixin):
    """ENH-014 (DEC-NOT-001 2026-09-30, D4): opt-in to WhatsApp and SMS. No row means both off; email and in-app are
    always on and are not stored. The *_opted_in_at timestamps are the consent evidence (with the audit log)."""

    __tablename__ = "notification_preferences"
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    whatsapp_opted_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sms_opted_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # itc-033 (DEC-SCOPE-357 C1): phone calls are allowed unless the user opts out (no row = allowed); the timestamp is the evidence
    calls_opt_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    calls_opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SupportTicket(Base, TimestampMixin):
    __tablename__ = "support_tickets"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    division: Mapped[str] = mapped_column(String(30), index=True)
    subject: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    status: Mapped[str] = mapped_column(String(30), default="open")
    # STU-005: DATA_MODEL.md §4.5's own stated field -- nullable so an unassigned ticket
    # stays visible/open rather than hidden (STU-005-AC02); server auto-claims it to the
    # first staff member who acts on it (never client-supplied, see PATCH /workflows/support).
    assigned_to_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CourseFeedback(Base, TimestampMixin):
    # STU-008: DATA_MODEL.md §4.6 describes this table as "carries over" from the reference
    # implementation, but no such table (or any other feedback model) actually exists in this
    # codebase -- net new, same pattern as STU-005's assigned_to_user_id correction.
    __tablename__ = "course_feedback"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)


class QuestionThread(Base, TimestampMixin):
    # TRN-009: DATA_MODEL.md §4.8 describes `QuestionThread`/`QuestionReply` as "carries
    # over" from the reference implementation, but neither table (nor any Q&A model)
    # actually exists in this codebase -- net new, same "carries over but never existed"
    # pattern already found for STU-005's assigned_to_user_id and STU-008's CourseFeedback.
    __tablename__ = "question_threads"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"), index=True)
    subject: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)


class QuestionReply(Base, TimestampMixin):
    __tablename__ = "question_replies"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("question_threads.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)


class DataSubjectRequest(Base, TimestampMixin):
    """SEC-002 -- DATA_MODEL.md §7.4 describes two conceptual tables (DataExportRequest/
    DataDeletionRequest) sharing one field set; API_CONTRACT.md §11 exposes one endpoint
    family keyed by `type` (`POST /account/data-requests`). Implemented as a single table
    with a `type` discriminator, matching the approved API contract exactly."""

    __tablename__ = "data_subject_requests"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    requesting_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="received")
    idempotency_key: Mapped[str] = mapped_column(String(200))
    export_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fulfilled_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("requesting_user_id", "idempotency_key", name="uq_data_subject_request_idempotency"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    # AGN-015 (DEC-SCOPE-061, migration 0067): one entity's history -- the student journey timeline reads audit rows by entity.
    # nehn-042 (DEC-SCOPE-289 A6, migration 0199): the admin audit log pages newest first.
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id", "created_at"), Index("ix_audit_logs_created_at", "created_at"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    outcome: Mapped[str] = mapped_column(String(30), default="recorded")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BdmProfile(Base, TimestampMixin):
    """bdm-001 (DEC-SCOPE-055): a BDM's §1 profile, 1:1 with a `bdm` user. Name, email, mobile and active stay on `users`.
    The reporting manager must be an active `bdm_manager` -- enforced in `services/bdm.py` under a row lock (no cross-table CHECK)."""

    __tablename__ = "bdm_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_bdm_profiles_user"),
        CheckConstraint("bdm_type IN ('agent', 'school', 'college')", name="ck_bdm_profiles_type"),
        Index("uq_bdm_profiles_employee_id", text("lower(employee_id)"), unique=True),
        Index("ix_bdm_profiles_reporting_manager", "reporting_manager_user_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    bdm_type: Mapped[str] = mapped_column(String(20))
    employee_id: Mapped[str] = mapped_column(String(40))
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    territory: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reporting_manager_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class TelecallerProfile(Base, TimestampMixin):
    """tel-001 (DEC-SCOPE-073): a telecaller's profile, 1:1 with a `telecaller` user. Name, email, mobile and active stay on `users`.
    `team` is the user's division (T22); the reporting manager must be an active `telecaller_manager`. Both rules span tables, so
    `services/telecaller.py` enforces them under a row lock (no cross-table CHECK)."""

    __tablename__ = "telecaller_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_telecaller_profiles_user"),
        CheckConstraint("team IN ('it', 'overseas')", name="ck_telecaller_profiles_team"),
        Index("uq_telecaller_profiles_employee_id", text("lower(employee_id)"), unique=True),
        Index("ix_telecaller_profiles_reporting_manager", "reporting_manager_user_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    team: Mapped[str] = mapped_column(String(20))
    employee_id: Mapped[str] = mapped_column(String(40))
    reporting_manager_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class TelProduct(Base, TimestampMixin):
    """tel-002 (DEC-SCOPE-074 P2, T17/T18): a product/interest a lead can name. IT and Overseas products route to their own team;
    only an `other` product's team is chosen (none = the unassigned queue). The optional course link is IT-only. Never deleted:
    deactivating hides it from pickers while leads keep the link."""

    __tablename__ = "tel_products"
    __table_args__ = (
        CheckConstraint("product_group IN ('it', 'overseas', 'other')", name="ck_tel_products_group"),
        CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_products_team"),
        CheckConstraint("product_group = 'other' OR team = product_group", name="ck_tel_products_team_matches_group"),
        CheckConstraint("program_id IS NULL OR product_group = 'it'", name="ck_tel_products_program_it_only"),
        Index("uq_tel_products_group_name", "product_group", text("lower(name)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_group: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    team: Mapped[str | None] = mapped_column(String(20), nullable=True)
    program_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("programs.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class TelCampaign(Base, TimestampMixin):
    """tel-002 (T16, P3/P4): a marketing campaign -- the "Instagram → Cyber Security → September 2026" of EVID-019 §2. The source is
    one of the fixed §2 sources; the product must be active when it is set (services/telecaller_catalogue)."""

    __tablename__ = "tel_campaigns"
    __table_args__ = (
        CheckConstraint(f"source IN ({', '.join(repr(s) for s in TEL_SOURCES)})", name="ck_tel_campaigns_source"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_tel_campaigns_dates"),
        Index("uq_tel_campaigns_name", text("lower(name)"), unique=True),
        Index("ix_tel_campaigns_product", "product_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(30))
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_products.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class TelDistributionRule(Base, TimestampMixin):
    """tel-007 (DEC-SCOPE-087, T11): a manager's routing rule for one team -- a product or a city sends new leads to one telecaller.
    The telecaller's team, role and active state span tables, so `services/lead_distribution.py` checks them on write and again at
    distribution time (an inactive telecaller's rule is skipped). Deleted, not deactivated, to stop it (audited).
    itc-006 (DEC-SCOPE-339): a `source` rule matches one of the 13 lead sources and is tried before product and city."""

    __tablename__ = "tel_distribution_rules"
    __table_args__ = (
        CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_distribution_rules_team"),
        CheckConstraint("kind IN ('product', 'city', 'source')", name="ck_tel_distribution_rules_kind"),
        CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND city IS NULL AND source IS NULL)"
            " OR (kind = 'city' AND city IS NOT NULL AND product_id IS NULL AND source IS NULL)"
            " OR (kind = 'source' AND source IS NOT NULL AND product_id IS NULL AND city IS NULL)",
            name="ck_tel_distribution_rules_shape",
        ),
        CheckConstraint(f"source IS NULL OR source IN ({', '.join(repr(s) for s in TEL_SOURCES)})", name="ck_tel_distribution_rules_source"),
        Index("uq_tel_distribution_rules_product", "team", "product_id", unique=True, postgresql_where=text("kind = 'product'")),
        Index("uq_tel_distribution_rules_city", "team", text("lower(city)"), unique=True, postgresql_where=text("kind = 'city'")),
        Index("uq_tel_distribution_rules_source", "team", "source", unique=True, postgresql_where=text("kind = 'source'")),
        Index("ix_tel_distribution_rules_telecaller", "telecaller_user_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    team: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(10))
    product_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_products.id"), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    telecaller_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class TelRoundRobinCursor(Base):
    """tel-007 (D2): the last telecaller a team's round robin chose. Locked FOR UPDATE per distribution, so concurrent intakes serialise.
    Created on first use (0001's create_all seeds nothing)."""

    __tablename__ = "tel_round_robin_cursors"
    __table_args__ = (CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_round_robin_cursors_team"),)
    team: Mapped[str] = mapped_column(String(20), primary_key=True)
    last_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TelScript(Base, TimestampMixin):
    """tel-012 (DEC-SCOPE-083 C3, EVID-019 §6): a product's standard call script -- ordered `{title, notes}` steps. At most one active
    script per product (partial unique index). Never deleted; deactivating hides it from telecallers."""

    __tablename__ = "tel_scripts"
    __table_args__ = (Index("uq_tel_scripts_active_product", "product_id", unique=True, postgresql_where=text("active")),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_products.id"))
    name: Mapped[str] = mapped_column(String(160))
    steps: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class TelAsset(Base, TimestampMixin):
    """tel-012 (C1): a brochure/fee PDF. The object lives at a server-generated `tel-assets/<uuid>` key that no API returns; leads
    reach it only through a signed 7-day link (services/telecaller_content). Deactivating it ends every link at once."""

    __tablename__ = "tel_assets"
    __table_args__ = (
        CheckConstraint(f"kind IN ({', '.join(repr(k) for k in TEL_ASSET_KINDS)})", name="ck_tel_assets_kind"),
        Index("uq_tel_assets_storage_key", "storage_key", unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))
    product_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_products.id"), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class TelMessageTemplate(Base, TimestampMixin):
    """tel-012 (T9, C4): a WhatsApp (§11) or email (§12) template. Only email has a subject. Placeholders are checked on save;
    `{brochure_link}` needs `asset_id`. A name is unique per channel (case-insensitive)."""

    __tablename__ = "tel_message_templates"
    __table_args__ = (
        CheckConstraint("channel IN ('whatsapp', 'email')", name="ck_tel_message_templates_channel"),
        CheckConstraint(
            f"(channel = 'whatsapp' AND kind IN ({', '.join(repr(k) for k in TEL_WHATSAPP_KINDS)})) OR "
            f"(channel = 'email' AND kind IN ({', '.join(repr(k) for k in TEL_EMAIL_KINDS)}))",
            name="ck_tel_message_templates_kind",
        ),
        CheckConstraint("(channel = 'email') = (subject IS NOT NULL)", name="ck_tel_message_templates_subject"),
        Index("uq_tel_message_templates_channel_name", "channel", text("lower(name)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    channel: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    product_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_products.id"), nullable=True)
    asset_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_assets.id"), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


TEL_TARGET_KPIS = ("calls", "connected_calls", "qualified_leads", "follow_ups", "counselling_appointments", "conversions")


class TelTarget(Base, TimestampMixin):
    """tel-022 (DEC-SCOPE-080, T28): one target value -- a team default or a per-telecaller override -- for one KPI and period,
    effective from a date. Append-only history: a row is only ever updated while its date is still in the future (the route's date
    rule), so a past day always resolves to the value it had. A NULL value (user scope only) ends an override from its date.
    Resolution lives in `services/telecaller_targets.py`."""

    __tablename__ = "tel_targets"
    __table_args__ = (
        CheckConstraint("scope IN ('team', 'user')", name="ck_tel_targets_scope"),
        CheckConstraint(
            "(scope = 'team' AND team IS NOT NULL AND user_id IS NULL) OR (scope = 'user' AND user_id IS NOT NULL AND team IS NULL)",
            name="ck_tel_targets_subject",
        ),
        CheckConstraint("period IN ('daily', 'monthly')", name="ck_tel_targets_period"),
        CheckConstraint(f"kpi IN ({', '.join(repr(k) for k in TEL_TARGET_KPIS)})", name="ck_tel_targets_kpi"),
        CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_targets_team"),
        CheckConstraint("value IS NULL OR value BETWEEN 0 AND 100000", name="ck_tel_targets_value"),
        CheckConstraint("value IS NOT NULL OR scope = 'user'", name="ck_tel_targets_value_null_user_only"),
        CheckConstraint("period = 'daily' OR EXTRACT(DAY FROM effective_from) = 1", name="ck_tel_targets_monthly_first"),
        Index("uq_tel_targets_team", "team", "period", "kpi", "effective_from", unique=True, postgresql_where=text("scope = 'team'")),
        Index("uq_tel_targets_user", "user_id", "period", "kpi", "effective_from", unique=True, postgresql_where=text("scope = 'user'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(String(10))
    team: Mapped[str | None] = mapped_column(String(20), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    period: Mapped[str] = mapped_column(String(10))
    kpi: Mapped[str] = mapped_column(String(40))
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date)
    set_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


TEL_SETTING_DEFAULTS = {"not_contacted_hours": 24, "hot_pending_hours": 4}  # DEC-SCOPE-111 AL1; migration 0099 seeds both teams with them
TEL_SETTING_MAX_HOURS = 168
TEL_STRATEGIES = ("round_robin", "workload")  # itc-006 D3; migration 0224 keeps a frozen copy


class TelSetting(Base, TimestampMixin):
    """tel-020 (DEC-SCOPE-111, T14): a team's alert thresholds -- Lead Not Contacted and Hot Lead Pending, in whole hours. One row per team,
    seeded; any telecaller manager edits both (AL11) and the beat reads them on every run (AC4).
    itc-006 (DEC-SCOPE-339 D3): `distribution_strategy` -- who gets a new lead no rule matched: in turn, or the fewest open leads.
    itc-009 (DEC-SCOPE-342): `escalate_after_hours` -- how overdue a follow-up gets before its owner's manager hears of it; 0 = off."""

    __tablename__ = "tel_settings"
    __table_args__ = (
        CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_settings_team"),
        *(CheckConstraint(f"{col} BETWEEN 1 AND {TEL_SETTING_MAX_HOURS}", name=f"ck_tel_settings_{col}") for col in TEL_SETTING_DEFAULTS),
        CheckConstraint(f"distribution_strategy IN ({', '.join(repr(s) for s in TEL_STRATEGIES)})", name="ck_tel_settings_distribution_strategy"),
        CheckConstraint(f"escalate_after_hours BETWEEN 0 AND {TEL_SETTING_MAX_HOURS}", name="ck_tel_settings_escalate_after_hours"),
    )
    team: Mapped[str] = mapped_column(String(20), primary_key=True)
    not_contacted_hours: Mapped[int] = mapped_column(Integer, default=TEL_SETTING_DEFAULTS["not_contacted_hours"])
    hot_pending_hours: Mapped[int] = mapped_column(Integer, default=TEL_SETTING_DEFAULTS["hot_pending_hours"])
    distribution_strategy: Mapped[str] = mapped_column(String(20), default="round_robin", server_default=text("'round_robin'"))
    escalate_after_hours: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))  # itc-009: 0 = escalation off
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


# bdm-010 (DEC-SCOPE-063, T6): TRV-000123 codes. On the metadata so 0001's create_all makes it on a fresh database; 0068 makes it
# on an upgraded one. A rolled-back create skips a number; codes stay unique and increasing.
BDM_TRIP_CODE_SEQ = Sequence("bdm_trip_code_seq", metadata=Base.metadata)


class BdmTrip(Base, TimestampMixin):
    """bdm-010 (DEC-SCOPE-063): one BDM trip (§3). Organization and appointment time are not stored -- bdm-011 links appointments.
    Actual cost is never stored: it is the sum of `bdm_trip_expenses` (D15). Rules live in `services/bdm_travel.py`."""

    __tablename__ = "bdm_trips"
    __table_args__ = (
        UniqueConstraint("code", name="uq_bdm_trips_code"),
        CheckConstraint("return_date >= travel_date", name="ck_bdm_trips_dates"),
        CheckConstraint("mode IN ('flight', 'train', 'bus', 'car', 'cab', 'local')", name="ck_bdm_trips_mode"),
        CheckConstraint("estimated_cost >= 0", name="ck_bdm_trips_estimated_cost"),
        CheckConstraint("currency = 'INR'", name="ck_bdm_trips_currency"),
        CheckConstraint("approval_status IN ('draft', 'submitted', 'approved', 'rejected')", name="ck_bdm_trips_approval_status"),
        CheckConstraint("travel_status IN ('planned', 'in_progress', 'completed', 'cancelled')", name="ck_bdm_trips_travel_status"),
        CheckConstraint("travel_status IN ('planned', 'cancelled') OR approval_status = 'approved'", name="ck_bdm_trips_status_pair"),
        Index("ix_bdm_trips_bdm_travel_date", "bdm_user_id", "travel_date"),
        Index("ix_bdm_trips_submitted", "bdm_user_id", postgresql_where=text("approval_status = 'submitted'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20))
    bdm_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    travel_date: Mapped[date] = mapped_column(Date)
    return_date: Mapped[date] = mapped_column(Date)
    from_place: Mapped[str] = mapped_column(String(120))
    to_place: Mapped[str] = mapped_column(String(120))
    purpose: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(10))
    accommodation_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    approval_status: Mapped[str] = mapped_column(String(12), default="draft", server_default="draft")
    travel_status: Mapped[str] = mapped_column(String(12), default="planned", server_default="planned")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class BdmTripExpense(Base, TimestampMixin):
    """bdm-010 (T7): one itemized INR expense line on an approved trip. No receipt (owner, 2026-10-03)."""

    __tablename__ = "bdm_trip_expenses"
    __table_args__ = (
        CheckConstraint("category IN ('travel', 'stay', 'food', 'local', 'other')", name="ck_bdm_trip_expenses_category"),
        CheckConstraint("amount > 0", name="ck_bdm_trip_expenses_amount"),
        Index("ix_bdm_trip_expenses_trip", "trip_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    trip_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_trips.id"))
    category: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    expense_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


BDM_ORG_TYPES = ("college", "university", "agent", "school", "corporate", "training_institute", "other")
BDM_CONTACT_ROLES = ("principal", "dean", "hod", "placement_officer", "counselor", "management", "owner", "other")
# bdm-003 (DEC-SCOPE-065, spec §4): the type-specific profile. `board` keeps ENH-009's exact values so bdm-018 can copy it onto
# `schools.board`; the other enums are lower snake case like `org_type`. Grades: -2 Nursery, -1 LKG, 0 UKG, then 1-12.
BDM_ORG_SOURCES = ("referral", "website", "event", "cold_call", "walk_in", "other")
BDM_SCHOOL_BOARDS = ("CBSE", "ICSE", "State", "IB", "Other")
BDM_SCHOOL_TYPES = ("private", "government", "aided", "international", "other")
BDM_COLLEGE_TYPES = ("engineering", "arts_science", "management", "medical", "polytechnic", "other")
BDM_GRADE_MIN, BDM_GRADE_MAX = -2, 12
BDM_STAFF_MAX = 100_000
BDM_PROFILE_GROUP = {"agent": "agent", "school": "school", "college": "college", "university": "college"}
BDM_PROFILE_FIELDS = {
    "agent": ("country", "territory", "source", "staff_count"),
    "school": ("board", "school_type", "grade_from", "grade_to"),
    "college": ("affiliation", "college_type", "courses"),
}
BDM_UNIVERSITY_LINK_SQL = "university_id IS NULL OR org_type = 'university'"  # upc-004 UD7
# bdm-002: on the metadata so 0001's create_all builds it for a fresh database; 0066 creates it IF NOT EXISTS.
BDM_ORGANIZATION_CODE_SEQ = Sequence("bdm_organization_code_seq", metadata=Base.metadata)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _group_only(group: str) -> str:
    """A group's columns stay NULL unless org_type belongs to the group (spec §4.2) -- the backstop under check_profile."""
    types = tuple(t for t, g in BDM_PROFILE_GROUP.items() if g == group)
    return f"{_in_list('org_type', types)} OR ({' AND '.join(f'{c} IS NULL' for c in BDM_PROFILE_FIELDS[group])})"


def _grade(column: str) -> str:
    return f"{column} IS NULL OR {column} BETWEEN {BDM_GRADE_MIN} AND {BDM_GRADE_MAX}"


BDM_PROFILE_CHECKS = {  # migration 0069 repeats these strings; test_bdm_003_migration asserts they stay identical
    "ck_bdm_organizations_source": f"source IS NULL OR {_in_list('source', BDM_ORG_SOURCES)}",
    "ck_bdm_organizations_staff_count": f"staff_count IS NULL OR staff_count BETWEEN 0 AND {BDM_STAFF_MAX}",
    "ck_bdm_organizations_board": f"board IS NULL OR {_in_list('board', BDM_SCHOOL_BOARDS)}",
    "ck_bdm_organizations_school_type": f"school_type IS NULL OR {_in_list('school_type', BDM_SCHOOL_TYPES)}",
    "ck_bdm_organizations_grades": f"({_grade('grade_from')}) AND ({_grade('grade_to')}) AND (grade_from IS NULL OR grade_to IS NULL OR grade_from <= grade_to)",
    "ck_bdm_organizations_college_type": f"college_type IS NULL OR {_in_list('college_type', BDM_COLLEGE_TYPES)}",
    "ck_bdm_organizations_agent_profile": _group_only("agent"),
    "ck_bdm_organizations_school_profile": _group_only("school"),
    "ck_bdm_organizations_college_profile": _group_only("college"),
}
# bdm-004 (DEC-SCOPE-071, spec §5.1): only a manual stage of the organization's own pipeline is stored (S3: live stages arrive with
# bdm-018 / bdm-019, which widen this CHECK). Lost is a flag with a reason on top of the stage (S5). Migration 0072 repeats these
# strings; test_bdm_004_migration asserts they stay identical.
BDM_PIPELINE_CHECKS = {
    "ck_bdm_organizations_pipeline_stage": " OR ".join(
        f"(bdm_type = '{bdm_type}' AND {_in_list('pipeline_stage', stages)})" for bdm_type, stages in BDM_MANUAL_STAGES.items()
    ),
    "ck_bdm_organizations_lost": "(lost_at IS NULL) = (lost_reason IS NULL)",
}
BDM_PIPELINE_EVENT_KINDS = ("move", "lost", "revived")


class BdmOrganization(Base, TimestampMixin):
    """bdm-002 (DEC-SCOPE-060): an institution a BDM meets (§9). `bdm_type` is the owning module (Q-03), copied from the creator and
    never changed; `name_key`/`city_key` are the server-normalized duplicate key (Q-18). Never hard-deleted: archived instead (C5).
    bdm-003 (DEC-SCOPE-065): a common address plus one typed profile group per org_type (BDM_PROFILE_FIELDS); a group's columns are
    NULL for every other type.
    bdm-004 (DEC-SCOPE-071): pipeline_stage (a manual stage of bdm_type's pipeline) and the Lost flag."""

    __tablename__ = "bdm_organizations"
    __table_args__ = (
        UniqueConstraint("code", name="uq_bdm_organizations_code"),
        CheckConstraint(_in_list("org_type", BDM_ORG_TYPES), name="ck_bdm_organizations_org_type"),
        CheckConstraint("bdm_type IN ('agent', 'school', 'college')", name="ck_bdm_organizations_bdm_type"),
        CheckConstraint("student_count IS NULL OR student_count >= 0", name="ck_bdm_organizations_student_count"),
        *(CheckConstraint(sql, name=name) for name, sql in BDM_PROFILE_CHECKS.items()),
        *(CheckConstraint(sql, name=name) for name, sql in BDM_PIPELINE_CHECKS.items()),
        Index("ix_bdm_organizations_type_assignee", "bdm_type", "assigned_bdm_user_id"),
        Index("ix_bdm_organizations_duplicate_key", "bdm_type", "name_key", "city_key"),
        Index("ix_bdm_organizations_type_stage", "bdm_type", "pipeline_stage"),
        Index("ix_bdm_organizations_university", "university_id"),
        CheckConstraint(BDM_UNIVERSITY_LINK_SQL, name="ck_bdm_organizations_university_link"),
        UniqueConstraint("school_id", name="uq_bdm_organizations_school"),
        UniqueConstraint("agent_org_id", name="uq_bdm_organizations_agent_org"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20))
    org_type: Mapped[str] = mapped_column(String(30))
    bdm_type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(120))
    city_key: Mapped[str] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    existing_partner: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    courses_interested: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    student_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    territory: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    staff_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    board: Mapped[str | None] = mapped_column(String(10), nullable=True)
    school_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    grade_from: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    grade_to: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    affiliation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    college_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    courses: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    assigned_bdm_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pipeline_stage: Mapped[str] = mapped_column(String(40), default=BDM_FIRST_STAGE, server_default=BDM_FIRST_STAGE)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # bdm-018 (DEC-SCOPE-085 H1): the onboarded School; one organization <-> at most one School. The School's BDM is derived from it.
    school_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id", ondelete="RESTRICT"), nullable=True)
    # bdm-019 (DEC-SCOPE-107): the onboarded Agent Organization; one organization <-> at most one agency. The live Agent stages read it.
    agent_org_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_orgs.id", ondelete="RESTRICT"), nullable=True)
    # upc-004 (U13, UD7): a University organization's record in the Global University Master; optional, never merged.
    university_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"), nullable=True)


class BdmOrganizationContact(Base, TimestampMixin):
    """bdm-002: a named person at an organization (C10: the primary contact is §9's Contact Person). Data only (D29). `position` keeps
    insertion order -- contacts created in one request share created_at."""

    __tablename__ = "bdm_organization_contacts"
    __table_args__ = (
        CheckConstraint(f"role IS NULL OR {_in_list('role', BDM_CONTACT_ROLES)}", name="ck_bdm_organization_contacts_role"),
        Index("ix_bdm_organization_contacts_org", "organization_id"),
        Index("uq_bdm_organization_contacts_primary", "organization_id", unique=True, postgresql_where=text("is_primary")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    name: Mapped[str] = mapped_column(String(200))
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class BdmPipelineEvent(Base):
    """bdm-004 (DEC-SCOPE-071, spec §5.2): one row per stage move, Lost or Revive. Append-only. `from_stage` = `to_stage` for lost /
    revived; `note` is the move note or the required reason. No stage CHECK: history must survive a future catalogue change.
    `position` orders rows created in one transaction."""

    __tablename__ = "bdm_pipeline_events"
    __table_args__ = (
        CheckConstraint(_in_list("kind", BDM_PIPELINE_EVENT_KINDS), name="ck_bdm_pipeline_events_kind"),
        CheckConstraint("kind = 'move' OR note IS NOT NULL", name="ck_bdm_pipeline_events_note"),
        Index("ix_bdm_pipeline_events_org", "organization_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(10))
    from_stage: Mapped[str] = mapped_column(String(40))
    to_stage: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# bdm-005 (DEC-SCOPE-078, spec §4): the MoU statuses in source order and wording (EVID-016 §10). `expired` is derived on read (M2):
# a signed / active MoU past `valid_until`; it is never stored, so the status CHECK lists only the settable keys.
BDM_MOU_STATUS_LABELS: dict[str, str] = {
    "prospect": "Prospect",
    "discussion_started": "Discussion Started",
    "proposal_sent": "Proposal Sent",
    "under_negotiation": "Under Negotiation",
    "draft_shared": "Draft Shared",
    "signed": "Signed",
    "active": "Active",
    "expired": "Expired",
    "rejected": "Rejected",
}
BDM_MOU_STATUSES = tuple(BDM_MOU_STATUS_LABELS)
BDM_MOU_SETTABLE = tuple(k for k in BDM_MOU_STATUSES if k != "expired")
BDM_MOU_EXPIRING = ("signed", "active")  # M7
BDM_MOU_EVENT_KINDS = ("created", "status", "updated", "document", "renewed")
BDM_MOU_CHECKS = {  # migration 0076 repeats these strings; test_bdm_005_migration asserts they stay identical
    "ck_bdm_mous_status": _in_list("status", BDM_MOU_SETTABLE),
    "ck_bdm_mous_window": "valid_from IS NULL OR valid_until IS NULL OR valid_until >= valid_from",
    "ck_bdm_mous_signed_on": "status NOT IN ('signed', 'active') OR signed_on IS NOT NULL",
    "ck_bdm_mous_active_window": "status <> 'active' OR (valid_from IS NOT NULL AND valid_until IS NOT NULL)",
    "ck_bdm_mous_document": "(document_key IS NULL) = (document_content_type IS NULL)",
}


class BdmMou(Base, TimestampMixin):
    """bdm-005 (DEC-SCOPE-078, spec §5.1): an organization's MoU. At most one `is_current` row per organization (M6: a renewal is a
    new row; the old one is kept). `document_key` is server-generated and never returned or logged; the service owns every rule, the
    CHECKs are the backstop."""

    __tablename__ = "bdm_mous"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in BDM_MOU_CHECKS.items()),
        Index("uq_bdm_mous_current", "organization_id", unique=True, postgresql_where=text("is_current")),
        Index("ix_bdm_mous_org", "organization_id", "created_at"),
        Index("ix_bdm_mous_status", "status", "valid_until"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="prospect", server_default="prospect")
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    proposal_sent_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    signed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    document_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    document_content_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class BdmMouEvent(Base):
    """bdm-005 (spec §5.2): one row per MoU write, append-only. `from_status` / `to_status` are the effective statuses (so a date
    correction that revives an Expired MoU is recorded as expired -> active); `changed` lists field names only. `document_key` is the
    replaced object's key on a `document` row; it is never returned."""

    __tablename__ = "bdm_mou_events"
    __table_args__ = (
        CheckConstraint(_in_list("kind", BDM_MOU_EVENT_KINDS), name="ck_bdm_mou_events_kind"),
        Index("ix_bdm_mou_events_mou", "mou_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    mou_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_mous.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(10))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    changed: Mapped[list] = mapped_column(JSON, default=list)
    document_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# bdm-018 (DEC-SCOPE-085, spec §3): the onboarding handover. `kind` is 'school' only; bdm-019 widens it for agents.
BDM_ONBOARDING_STATUSES = ("pending", "completed", "rejected")
BDM_ONBOARDING_CHECKS = {  # migrations 0084 and 0098 (bdm-019) repeat these strings; test_bdm_018/019_migration pin them
    "ck_bdm_onboarding_requests_kind": "kind IN ('school', 'agent')",
    "ck_bdm_onboarding_requests_status": _in_list("status", BDM_ONBOARDING_STATUSES),
    "ck_bdm_onboarding_requests_resolution": "resolution IS NULL OR resolution IN ('created', 'linked')",
    "ck_bdm_onboarding_requests_resolved": "(status = 'pending') = (resolved_at IS NULL)",
    "ck_bdm_onboarding_requests_completed": "status <> 'completed' OR (resolution IS NOT NULL AND (school_id IS NOT NULL OR agent_org_id IS NOT NULL))",
    # bdm-019: a request names only its own kind's target (a School, or an Agent Organization)
    "ck_bdm_onboarding_requests_target": "(kind = 'school' AND agent_org_id IS NULL) OR (kind = 'agent' AND school_id IS NULL)",
    "ck_bdm_onboarding_requests_rejected": "status <> 'rejected' OR reject_reason IS NOT NULL",
}


class BdmOnboardingRequest(Base, TimestampMixin):
    """bdm-018: a BDM's request that Overseas Admin onboard a signed organization. At most one pending per organization (H8); a
    completed one names the School it was resolved with (created or linked). The service owns every rule; the CHECKs are the backstop."""

    __tablename__ = "bdm_onboarding_requests"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in BDM_ONBOARDING_CHECKS.items()),
        Index("uq_bdm_onboarding_requests_pending", "organization_id", unique=True, postgresql_where=text("status = 'pending'")),
        Index("ix_bdm_onboarding_requests_status", "status", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20), default="school", server_default="school")
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    school_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id", ondelete="RESTRICT"), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agent_org_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_orgs.id", ondelete="RESTRICT"), nullable=True)  # bdm-019


# bdm-006 (DEC-SCOPE-068, spec §4.1): appointment catalogues. Stable keys; the CHECKs accept every key, the service validates each value
# against the owner's bdm_type (the database cannot see it).
BDM_APPOINTMENT_STATUSES = ("scheduled", "confirmed", "rescheduled", "completed", "cancelled", "no_show")
BDM_APPOINTMENT_OPEN = ("scheduled", "confirmed", "rescheduled")
BDM_APPOINTMENT_COMMON_TYPES = (
    "college_meeting", "agent_meeting", "school_meeting", "mou_discussion", "student_institution_meeting", "seminar_workshop",
    "corporate_meeting", "other",
)
BDM_APPOINTMENT_MODULE_TYPES = {
    "agent": (
        "agent_meeting", "new_agent_presentation", "product_training", "agreement_discussion", "performance_review", "agent_onboarding",
        "agent_visit", "commission_discussion", "business_review",
    ),
    "school": (
        "principal_meeting", "management_meeting", "career_guidance_presentation", "psychometric_presentation",
        "profile_building_presentation", "parent_orientation", "teacher_orientation", "seminar", "workshop", "mou_discussion",
        "renewal_meeting",
    ),
    "college": (
        "principal_meeting", "hod_meeting", "placement_cell_meeting", "course_promotion", "it_training_presentation", "student_seminar",
        "workshop", "internship_discussion", "placement_discussion", "mou_discussion", "corporate_connect", "faculty_meeting",
    ),
}
BDM_APPOINTMENT_ALL_TYPES = tuple(dict.fromkeys(BDM_APPOINTMENT_COMMON_TYPES + sum(BDM_APPOINTMENT_MODULE_TYPES.values(), ())))
BDM_APPOINTMENT_COMMON_OUTCOMES = (
    "interested", "mou_discussion_required", "student_leads_expected", "course_promotion_interested", "follow_up_required",
    "commercial_discussion", "not_interested", "reschedule", "other",
)
BDM_APPOINTMENT_AGENT_OUTCOMES = (
    "interested", "agreement_required", "product_training_required", "follow_up", "documents_required", "onboarding_required",
    "active_business_expected", "not_interested",
)
BDM_APPOINTMENT_ALL_OUTCOMES = tuple(dict.fromkeys(BDM_APPOINTMENT_COMMON_OUTCOMES + BDM_APPOINTMENT_AGENT_OUTCOMES))
# On the metadata so 0001's create_all builds it for a fresh database; 0070 creates it IF NOT EXISTS.
BDM_APPOINTMENT_CODE_SEQ = Sequence("bdm_appointment_code_seq", metadata=Base.metadata)


class BdmAppointment(Base, TimestampMixin):
    """bdm-006 (DEC-SCOPE-068): a BDM's meeting at an organization (§2). The contact is copied at booking (A5: the copy outlives a contact
    delete). Never deleted: cancelled instead. Not the legacy `Appointment` (overseas counselling slots)."""

    __tablename__ = "bdm_appointments"
    __table_args__ = (
        UniqueConstraint("code", name="uq_bdm_appointments_code"),
        CheckConstraint(_in_list("status", BDM_APPOINTMENT_STATUSES), name="ck_bdm_appointments_status"),
        CheckConstraint(_in_list("appointment_type", BDM_APPOINTMENT_ALL_TYPES), name="ck_bdm_appointments_type"),
        CheckConstraint(f"outcome IS NULL OR {_in_list('outcome', BDM_APPOINTMENT_ALL_OUTCOMES)}", name="ck_bdm_appointments_outcome"),
        CheckConstraint("(status = 'completed') = (outcome IS NOT NULL)", name="ck_bdm_appointments_outcome_completed"),
        CheckConstraint("next_follow_up_on IS NULL OR status = 'completed'", name="ck_bdm_appointments_follow_up"),
        CheckConstraint("duration_minutes BETWEEN 15 AND 720", name="ck_bdm_appointments_duration"),
        CheckConstraint("expected_leads IS NULL OR expected_leads >= 0", name="ck_bdm_appointments_expected_leads"),
        CheckConstraint("expected_revenue IS NULL OR expected_revenue >= 0", name="ck_bdm_appointments_expected_revenue"),
        Index("ix_bdm_appointments_bdm_starts", "bdm_user_id", "starts_at"),
        Index("ix_bdm_appointments_org_starts", "organization_id", "starts_at"),
        Index("ix_bdm_appointments_contact", "contact_id"),
        Index("ix_bdm_appointments_trip", "trip_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20))
    bdm_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organization_contacts.id", ondelete="SET NULL"), nullable=True)
    contact_name: Mapped[str] = mapped_column(String(200))
    contact_designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default=text("60"))
    appointment_type: Mapped[str] = mapped_column(String(40))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", server_default=text("'scheduled'"))
    outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)
    next_follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_leads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_revenue: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # bdm-011 (DEC-SCOPE-092): the trip this meeting is part of -- the BDM's own, covering its IST date (services/bdm_travel).
    trip_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_trips.id", ondelete="RESTRICT"), nullable=True)


class BdmAppointmentEvent(Base):
    """bdm-006: one row per status transition (and creation: from_status NULL). Append-only. `position` orders rows created in one
    transaction."""

    __tablename__ = "bdm_appointment_events"
    __table_args__ = (
        CheckConstraint(_in_list("to_status", BDM_APPOINTMENT_STATUSES), name="ck_bdm_appointment_events_to_status"),
        Index("ix_bdm_appointment_events_appointment", "appointment_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    appointment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_appointments.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    old_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# tel-019 (DEC-SCOPE-098): a telecaller's request for a BDM meeting. Corporate meetings go to college BDMs (T26).
BDM_MEETING_REQUEST_TYPES = ("college", "agent", "school", "corporate")
BDM_MEETING_REQUEST_BDM_TYPE = {"college": "college", "agent": "agent", "school": "school", "corporate": "college"}
BDM_MEETING_REQUEST_STATUSES = ("pending", "accepted", "declined")
BDM_MEETING_REQUEST_CODE_SEQ = Sequence("bdm_meeting_request_code_seq", metadata=Base.metadata)


class BdmMeetingRequest(Base, TimestampMixin):
    """tel-019 (DEC-SCOPE-098): filed by a telecaller for a BDM of `bdm_type` -- a named one (`bdm_user_id` set while pending) or the
    type's pool (NULL while pending; MR1). A BDM accepts it into exactly one `bdm_appointments` row or declines it with a reason; either is
    final (MR2), and `bdm_user_id` is then whoever decided. Never deleted."""

    __tablename__ = "bdm_meeting_requests"
    __table_args__ = (
        UniqueConstraint("code", name="uq_bdm_meeting_requests_code"),
        UniqueConstraint("bdm_appointment_id", name="uq_bdm_meeting_requests_appointment"),
        CheckConstraint(_in_list("request_type", BDM_MEETING_REQUEST_TYPES), name="ck_bdm_meeting_requests_type"),
        CheckConstraint("bdm_type IN ('agent', 'school', 'college')", name="ck_bdm_meeting_requests_bdm_type"),
        CheckConstraint(_in_list("mode", APPOINTMENT_MODES), name="ck_bdm_meeting_requests_mode"),
        CheckConstraint(_in_list("status", BDM_MEETING_REQUEST_STATUSES), name="ck_bdm_meeting_requests_status"),
        CheckConstraint("(status = 'accepted') = (bdm_appointment_id IS NOT NULL)", name="ck_bdm_meeting_requests_accepted"),
        CheckConstraint("(status = 'declined') = (decline_reason IS NOT NULL)", name="ck_bdm_meeting_requests_declined"),
        CheckConstraint("status = 'pending' OR (bdm_user_id IS NOT NULL AND decided_at IS NOT NULL)", name="ck_bdm_meeting_requests_decided"),
        Index("ix_bdm_meeting_requests_type_status", "bdm_type", "status"),
        Index("ix_bdm_meeting_requests_bdm", "bdm_user_id"),
        Index("ix_bdm_meeting_requests_requester", "requester_user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20))
    requester_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    request_type: Mapped[str] = mapped_column(String(20))
    bdm_type: Mapped[str] = mapped_column(String(20))
    organization_name: Mapped[str] = mapped_column(String(200))
    person_name: Mapped[str] = mapped_column(String(200))
    contact_phone: Mapped[str] = mapped_column(String(30))
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String(20))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purpose: Mapped[str] = mapped_column(String(1000))
    remarks: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default=text("'pending'"))
    bdm_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    bdm_appointment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_appointments.id", ondelete="RESTRICT"), nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


BDM_TASK_KINDS = ("follow_up", "task")
BDM_TASK_SOURCES = ("appointment_outcome", "mou", "manual")
BDM_TASK_STATUSES = ("open", "done", "cancelled")


class BdmMeetingReport(Base, TimestampMixin):
    """bdm-007 (DEC-SCOPE-070): the meeting report filed on completing an appointment (one per appointment). The outcome and next
    follow-up date stay on the appointment. `legacy` rows were backfilled by 0072 for bdm-006 completions (outcome only, read-only)."""

    __tablename__ = "bdm_meeting_reports"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_bdm_meeting_reports_appointment"),
        CheckConstraint("legacy OR discussion IS NOT NULL", name="ck_bdm_meeting_reports_discussion"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    appointment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_appointments.id", ondelete="RESTRICT"))
    author_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    discussion: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    requirements: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    opportunity: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    responsible_person: Mapped[str | None] = mapped_column(String(200), nullable=True)
    legacy: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BdmTask(Base, TimestampMixin):
    """bdm-007 creates follow-ups (`source = appointment_outcome`, one per appointment); bdm-008 (DEC-SCOPE-075) adds manual tasks,
    notes, completion, the cancellation time and reason, and the pages. `mou` stays reserved for bdm-005."""

    __tablename__ = "bdm_tasks"
    __table_args__ = (
        UniqueConstraint("source_appointment_id", name="uq_bdm_tasks_source_appointment"),
        CheckConstraint(_in_list("kind", BDM_TASK_KINDS), name="ck_bdm_tasks_kind"),
        CheckConstraint(_in_list("source", BDM_TASK_SOURCES), name="ck_bdm_tasks_source"),
        CheckConstraint(_in_list("status", BDM_TASK_STATUSES), name="ck_bdm_tasks_status"),
        CheckConstraint("(source = 'appointment_outcome') = (source_appointment_id IS NOT NULL)", name="ck_bdm_tasks_source_link"),
        CheckConstraint("(status = 'done') = (completed_at IS NOT NULL)", name="ck_bdm_tasks_completed"),
        CheckConstraint("(status = 'cancelled') = (cancelled_at IS NOT NULL)", name="ck_bdm_tasks_cancelled"),
        CheckConstraint("cancel_reason IS NULL OR status = 'cancelled'", name="ck_bdm_tasks_cancel_reason"),
        Index("ix_bdm_tasks_assignee_status_due", "assignee_user_id", "status", "due_on"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    due_on: Mapped[date] = mapped_column(Date)
    organization_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=True)
    source: Mapped[str] = mapped_column(String(30))
    source_appointment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_appointments.id", ondelete="RESTRICT"), nullable=True)
    assignee_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="open", server_default=text("'open'"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


BDM_ASSIGNMENT_ENTITIES = ("organization", "appointment", "task")
BDM_ASSIGNMENT_REASONS = ("bdm_deactivated", "portfolio_handover", "organization_reassigned")


class BdmAssignmentHistory(Base):
    """bdm-025 (DEC-SCOPE-082): one row per organization, appointment or task that changed owner. Append-only; `entity_id` has no
    foreign key (polymorphic) -- those rows are never deleted (archived / cancelled instead)."""

    __tablename__ = "bdm_assignment_history"
    __table_args__ = (
        CheckConstraint(_in_list("entity_type", BDM_ASSIGNMENT_ENTITIES), name="ck_bdm_assignment_history_entity_type"),
        CheckConstraint(_in_list("reason", BDM_ASSIGNMENT_REASONS), name="ck_bdm_assignment_history_reason"),
        Index("ix_bdm_assignment_history_entity", "entity_type", "entity_id"),
        Index("ix_bdm_assignment_history_from", "from_user_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    from_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    to_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


BDM_ACTIVITY_CHANNELS = ("call", "whatsapp", "email", "visit", "meeting", "other")
BDM_ACTIVITY_DIRECTIONAL = ("call", "whatsapp", "email")  # V6: these need a direction; the rest must have none


class BdmActivity(Base, TimestampMixin):
    """bdm-009 (DEC-SCOPE-069): one call, WhatsApp, email, visit, meeting or other contact a BDM logged by hand (D9; nothing is sent).
    `contact_name` is the contact's name at save, kept when bdm-002 hard-deletes the contact (`contact_id` -> NULL)."""

    __tablename__ = "bdm_activities"
    __table_args__ = (
        CheckConstraint(_in_list("channel", BDM_ACTIVITY_CHANNELS), name="ck_bdm_activities_channel"),
        CheckConstraint("direction IS NULL OR direction IN ('outbound', 'inbound')", name="ck_bdm_activities_direction"),
        CheckConstraint(f"({_in_list('channel', BDM_ACTIVITY_DIRECTIONAL)}) = (direction IS NOT NULL)", name="ck_bdm_activities_direction_channel"),
        Index("ix_bdm_activities_bdm_user_id_occurred_at", "bdm_user_id", "occurred_at"),
        Index("ix_bdm_activities_organization_id_occurred_at", "organization_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bdm_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organization_contacts.id", ondelete="SET NULL"), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channel: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


BDM_DAILY_REPORT_CHECKS = {  # migration 0092 repeats these strings; test_bdm_015_migration asserts they stay identical
    "ck_bdm_daily_reports_bdm_type": "bdm_type IN ('agent', 'school', 'college')",
    "ck_bdm_daily_reports_comment": "(manager_comment IS NULL) = (manager_comment_by_user_id IS NULL) "
    "AND (manager_comment IS NULL) = (manager_commented_at IS NULL)",
}


class BdmDailyReport(Base, TimestampMixin):
    """bdm-015 (DEC-SCOPE-099): a BDM's submitted end-of-day report. A row exists only once submitted (the draft is a live preview);
    `counts` is the snapshot of the day's metrics at submission (`services/bdm_metrics.daily_counts`), so later record edits never
    rewrite it. The manager's comment (D22) is the only later write."""

    __tablename__ = "bdm_daily_reports"
    __table_args__ = (
        UniqueConstraint("bdm_user_id", "report_date", name="uq_bdm_daily_reports_bdm_date"),
        *(CheckConstraint(sql, name=name) for name, sql in BDM_DAILY_REPORT_CHECKS.items()),
    )
    __mapper_args__ = {"eager_defaults": True}  # the INSERT returns submitted_at: no lazy load on an async session
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bdm_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    report_date: Mapped[date] = mapped_column(Date)
    bdm_type: Mapped[str] = mapped_column(String(20))
    counts: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    manager_comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    manager_comment_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    manager_commented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


BDM_TARGET_MAX = 100_000  # R4: the tel-022 bound
BDM_TARGET_CHECKS = {  # migration 0096 repeats these strings; test_bdm_016_migration asserts they stay identical
    "ck_bdm_targets_month_start": "EXTRACT(DAY FROM month) = 1",
    "ck_bdm_targets_target_range": f"target >= 0 AND target <= {BDM_TARGET_MAX}",
}


class BdmTarget(Base, TimestampMixin):
    """bdm-016 (DEC-SCOPE-103): a manager-set monthly target for one KPI of one BDM. `month` is the month's first day; `kpi_key` is a key
    of the BDM type's catalogue (`services/bdm_metrics.TARGET_KPIS`, checked in the service). Achieved is never stored: it is computed
    live from the month's records (`bdm_metrics.monthly_counts`). Clearing a target deletes the row."""

    __tablename__ = "bdm_targets"
    __table_args__ = (
        UniqueConstraint("bdm_user_id", "month", "kpi_key", name="uq_bdm_targets_bdm_month_kpi"),
        *(CheckConstraint(sql, name=name) for name, sql in BDM_TARGET_CHECKS.items()),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bdm_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    month: Mapped[date] = mapped_column(Date)
    kpi_key: Mapped[str] = mapped_column(String(40))
    target: Mapped[int] = mapped_column(Integer)
    set_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LiveSession(Base, TimestampMixin):
    __tablename__ = "live_sessions"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"), index=True)
    trainer_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(30), default="manual")
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    host_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    provider_meeting_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    recording_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recording_external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recording_status: Mapped[str] = mapped_column(String(30), default="not_available")
    sync_status: Mapped[str] = mapped_column(String(30), default="manual")
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # nehn-029: set with status "cancelled"


class AgentStudent(Base, TimestampMixin):
    """AGT-002 link of an agent to a student with an account; AGN-004 (DEC-SCOPE-042) adds students with no login
    (`student_id` NULL, identity on the row), assignment to a staff member, and archive. `agent_id` is the member who created
    or linked the row; it fixes the agency (membership is permanent)."""

    __tablename__ = "agent_students"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    full_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone_digits: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # nehn-040 (DEC-SCOPE-280 N2): the Student ID of a row with no login; a linked row shows its account's users.student_code.
    student_code: Mapped[str | None] = mapped_column(String(8), unique=True, nullable=True, index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    highest_qualification: Mapped[str | None] = mapped_column(String(200), nullable=True)
    institution: Mapped[str | None] = mapped_column(String(200), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    preferred_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preferred_course: Mapped[str | None] = mapped_column(String(200), nullable=True)
    preferred_intake: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_member_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_org_members.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    __table_args__ = (
        UniqueConstraint("agent_id", "student_id", name="uq_agent_student"),
        CheckConstraint("student_id IS NOT NULL OR full_name IS NOT NULL", name="ck_agent_students_identity"),
        CheckConstraint("status IN ('active', 'archived')", name="ck_agent_students_status"),
        Index("ix_agent_students_agent_status", "agent_id", "status"),
        Index("ix_agent_students_agent_phone_digits", "agent_id", "phone_digits"),
        Index("ix_agent_students_assigned_member", "assigned_member_id"),
    )


COUNSELING_CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")  # AGN-006 C2; schemas.CounselingCurrency mirrors it


class AgentStudentCounseling(Base, TimestampMixin):
    """AGN-006 (DEC-SCOPE-048, EVID-015 §5 Step 2): one counseling record per agency student with no login. Replaced whole on every
    save (C1); its history is the audit log. `completed_at`/`completed_by_user_id` are stamped by the server (C5)."""

    __tablename__ = "agent_student_counseling"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_students.id"))
    counseling_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    career_interest: Mapped[str | None] = mapped_column(String(200), nullable=True)
    course_preference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country_preference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    budget_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    __table_args__ = (
        UniqueConstraint("agent_student_id", name="uq_agent_student_counseling_student"),
        CheckConstraint(
            "counseling_completed = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL)",
            name="ck_agent_student_counseling_completed",
        ),
        CheckConstraint("budget_amount IS NULL OR budget_amount >= 0", name="ck_agent_student_counseling_budget"),
        CheckConstraint(
            "budget_currency IS NULL OR budget_currency IN (" + ", ".join(f"'{c}'" for c in COUNSELING_CURRENCIES) + ")",
            name="ck_agent_student_counseling_currency",
        ),
        CheckConstraint("(budget_amount IS NULL) = (budget_currency IS NULL)", name="ck_agent_student_counseling_budget_pair"),
    )


# ccrm-007 (DEC-SCOPE-249): the structured overseas student profile; its test types are the course master's ENGLISH_TESTS. Migration
# 0174 repeats these (test_ccrm_007_migration).
QUALIFICATION_LEVELS = ("class_10", "class_12", "diploma", "bachelor", "master", "phd", "other")
SCORE_TYPES = ("percentage", "cgpa")  # STUDY_MODES and ENGLISH_TEST_STATUSES are above LeadQualification, which shares them (ccrm-005)


class OverseasStudentProfile(Base, TimestampMixin):
    """ccrm-007 (DEC-SCOPE-249): one per overseas student user -- personal, passport, work experience and study preferences; the
    qualifications and English tests are child rows. The counselor (csc-001 scope), the Overseas Admin and the student edit it (P1, last
    write wins); the agency reads it without the passport (P2/P3). Replaced whole on every save (P5, `services/student_profiles.py`)."""

    __tablename__ = "overseas_student_profiles"
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    passport_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    passport_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    work_experience_months: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    work_experience_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_country_ids: Mapped[list] = mapped_column(JSON, default=list)
    preferred_course: Mapped[str | None] = mapped_column(String(200), nullable=True)
    preferred_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferred_intake: Mapped[str | None] = mapped_column(String(40), nullable=True)
    study_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    budget_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    __table_args__ = (
        CheckConstraint(_in("preferred_level", COURSE_LEVELS), name="ck_overseas_student_profiles_level"),
        CheckConstraint(_in("study_mode", STUDY_MODES), name="ck_overseas_student_profiles_study_mode"),
        CheckConstraint(_in("budget_currency", COUNSELING_CURRENCIES), name="ck_overseas_student_profiles_currency"),
        CheckConstraint("work_experience_months IS NULL OR work_experience_months BETWEEN 0 AND 600", name="ck_overseas_student_profiles_experience"),
    )


class OverseasStudentQualification(Base):
    """ccrm-007: one qualification on a student profile, in the order entered (`position`)."""

    __tablename__ = "overseas_student_qualifications"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_student_profiles.student_user_id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    level: Mapped[str] = mapped_column(String(20))
    qualification_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    institution: Mapped[str | None] = mapped_column(String(200), nullable=True)
    board_university: Mapped[str | None] = mapped_column(String(200), nullable=True)
    year_completed: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    backlogs: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    __table_args__ = (
        UniqueConstraint("student_user_id", "position", name="uq_overseas_student_qualifications_position"),
        CheckConstraint(f"level IN ({', '.join(repr(v) for v in QUALIFICATION_LEVELS)})", name="ck_overseas_student_qualifications_level"),
        CheckConstraint(_in("score_type", SCORE_TYPES), name="ck_overseas_student_qualifications_score_type"),
    )


class OverseasStudentEnglishTest(Base):
    """ccrm-007: one English test on a student profile. `status` is nullable only for a test copied from the old free-text profile
    (migration 0174, P4); a save always sends one or none."""

    __tablename__ = "overseas_student_english_tests"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_student_profiles.student_user_id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    test_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    test_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (
        UniqueConstraint("student_user_id", "position", name="uq_overseas_student_english_tests_position"),
        CheckConstraint(f"test_type IN ({', '.join(repr(v) for v in ENGLISH_TESTS)})", name="ck_overseas_student_english_tests_type"),
        CheckConstraint(_in("status", ENGLISH_TEST_STATUSES), name="ck_overseas_student_english_tests_status"),
    )


class AgentCommission(Base, TimestampMixin):
    __tablename__ = "agent_commissions"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id"), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(30), default="estimated")
    created_by: Mapped[str] = mapped_column(String(20), default="admin_manual")
    claim_reference: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payout_approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    payout_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentOrg(Base, TimestampMixin):
    """AGN-001 / DEC-SCOPE-038: an agent company -- a separate tenant. Its `status` is the agent approval gate
    (`core.rbac.agent_denial_reason`); `master_seq` is the highest Master number ever issued, so codes are never reused.
    `staff_seq` is the highest staff number ever issued (AGN-002)."""

    __tablename__ = "agent_orgs"
    __table_args__ = (
        UniqueConstraint("prefix", name="uq_agent_orgs_prefix"),
        CheckConstraint("status IN ('pending', 'active', 'rejected', 'suspended')", name="ck_agent_orgs_status"),
        CheckConstraint("master_seq >= 0", name="ck_agent_orgs_master_seq"),
        CheckConstraint("staff_seq >= 0", name="ck_agent_orgs_staff_seq"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    prefix: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(20), index=True)
    master_seq: Mapped[int] = mapped_column(Integer, default=0)
    staff_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status_changed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # AGN-024 (DEC-SCOPE-224 K4): set only by self-registration; when true the org cannot become active until its three KYC documents
    # are verified (`services.agent_kyc.assert_complete`). Every org that existed before AGN-024 stays false.
    kyc_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class AgentOrgMember(Base, TimestampMixin):
    """AGN-001: a user's membership of exactly one agent organisation, for good (`user_id` unique). AGN-002 adds `staff`
    (DEC-SCOPE-040): Masters and staff are numbered separately (M001 and S001 coexist). AGN-003 adds two per-staff permission
    flags (DEC-SCOPE-044)."""

    __tablename__ = "agent_org_members"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_agent_org_members_user"),
        UniqueConstraint("code", name="uq_agent_org_members_code"),
        UniqueConstraint("org_id", "role", "seq", name="uq_agent_org_members_org_role_seq"),
        CheckConstraint("role IN ('master', 'staff')", name="ck_agent_org_members_role"),
        CheckConstraint("status IN ('active', 'deactivated')", name="ck_agent_org_members_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_orgs.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20), default="master")
    seq: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20), default="active")
    invited_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    deactivated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # AGN-003 (DEC-SCOPE-044 P1/P2): the two optional §6 rows for staff. Stored on every member but never read for a Master
    # (`core.rbac.agent_may` always allows Masters).
    can_verify_documents: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    can_view_reports: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    org: Mapped["AgentOrg"] = relationship(lazy="raise")


KYC_DOC_TYPES = ("pan", "aadhaar", "business_license")
KYC_CHECKS = {  # must equal alembic 0164_agent_org_kyc.CHECKS
    "ck_agent_org_kyc_documents_type": "doc_type IN ('pan', 'aadhaar', 'business_license')",
    "ck_agent_org_kyc_documents_status": "status IN ('pending', 'verified', 'rejected')",
    "ck_agent_org_kyc_documents_reason": "(status = 'rejected') = (rejection_reason IS NOT NULL)",
}


class AgentOrgKycDocument(Base, TimestampMixin):
    """AGN-024 / DEC-SCOPE-224: one current KYC document per agency per type (K1). `doc_number` is the full PAN, the licence number,
    or only the LAST 4 Aadhaar digits (K2) -- never the full Aadhaar. `file_key` is server-generated under `agent-kyc/`; the file is
    served only by the admin streaming route. A re-upload replaces the row's file in place; history is the audit log."""

    __tablename__ = "agent_org_kyc_documents"
    __table_args__ = (
        UniqueConstraint("org_id", "doc_type", name="uq_agent_org_kyc_documents_org_type"),
        *(CheckConstraint(sql, name=name) for name, sql in KYC_CHECKS.items()),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_orgs.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[str] = mapped_column(String(32))
    doc_number: Mapped[str] = mapped_column(String(64))
    file_key: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default=text("'pending'"))
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class AgentUniversity(Base, TimestampMixin):
    """AGN-007 / DEC-SCOPE-049 D1: an agency's private university ("Add University", Master only). Never part of the shared
    catalogue (`universities`) and never on /public; `org_id` is the tenant key every read filters on."""

    __tablename__ = "agent_universities"
    __table_args__ = (
        Index("uq_agent_universities_org_name_country", "org_id", text("lower(name)"), text("lower(country)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_orgs.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entry_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class AgentStudentShortlistEntry(Base, TimestampMixin):
    """AGN-007 / DEC-SCOPE-049: one university on an agency student's shortlist. The university is exactly one of a catalogue
    university or the agency's own (D6); a catalogue course needs a catalogue university (D4). Country is read from the university,
    never stored (D7). Scope is the parent student's (AGN-004 `load_scoped`)."""

    __tablename__ = "agent_student_shortlist_entries"
    __table_args__ = (
        CheckConstraint("(university_id IS NULL) <> (agent_university_id IS NULL)", name="ck_shortlist_one_university"),
        CheckConstraint("course_id IS NULL OR university_id IS NOT NULL", name="ck_shortlist_catalogue_course"),
        CheckConstraint("course_id IS NULL OR course_title IS NULL", name="ck_shortlist_one_course_form"),
        Index("ix_shortlist_student_created", "agent_student_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_students.id", ondelete="RESTRICT"))
    university_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"), nullable=True)
    agent_university_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_universities.id", ondelete="RESTRICT"), nullable=True, index=True)
    course_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_courses.id", ondelete="RESTRICT"), nullable=True)
    course_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    intake: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tuition_fee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entry_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class AgentTask(Base, TimestampMixin):
    """AGN-016 / DEC-SCOPE-053 (EVID-015 §4 "Tasks & Follow-ups"): a follow-up on an agency student. There is no assignee: the task
    belongs to its student, so scope is the student's (AGN-004 `student_scope`) and a reassigned student's tasks follow it (T1).
    `done` and `cancelled` are final (T2, T6); `closed_at`/`closed_by_user_id` are stamped by the server."""

    __tablename__ = "agent_tasks"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'done', 'cancelled')", name="ck_agent_tasks_status"),
        CheckConstraint("(status = 'open') = (closed_at IS NULL) AND (closed_at IS NULL) = (closed_by_user_id IS NULL)", name="ck_agent_tasks_closed"),
        Index("ix_agent_tasks_student_status_due", "agent_student_id", "status", "due_at"),
        Index("ix_agent_tasks_open_due", "due_at", postgresql_where=text("status = 'open'")),  # AGN-017: the overdue digest's scan
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_students.id", ondelete="RESTRICT"))
    application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id", ondelete="RESTRICT"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


DEPOSIT_STATUSES = ("not_required", "pending", "paid", "remitted", "refunded")


class ApplicationDeposit(Base, TimestampMixin):
    """AGN-011 / DEC-SCOPE-058 (EVID-015 §5 Step 7): the university deposit on an agency application, one per application. The agency
    sets it (`not_required` / `pending`) and pays it through EduSphere Razorpay; every pay attempt is a payer-owned `Payment`
    (`reference_type="agent_deposit"`, `reference_id` = this id) and `active_payment_id` is the open one. Only the paid hook moves it to
    `paid`; only an Overseas Admin records `remitted` / `refunded` (D3, D5). INR only (D1)."""

    __tablename__ = "application_deposits"
    __table_args__ = (
        CheckConstraint("status IN ('not_required', 'pending', 'paid', 'remitted', 'refunded')", name="ck_application_deposits_status"),
        CheckConstraint("currency = 'INR'", name="ck_application_deposits_currency"),
        CheckConstraint("(status = 'not_required') = (NOT required)", name="ck_application_deposits_required"),
        CheckConstraint("(required AND amount IS NOT NULL AND amount > 0) OR (NOT required AND amount IS NULL AND due_date IS NULL)", name="ck_application_deposits_amount"),
        CheckConstraint("(paid_payment_id IS NULL) = (status IN ('not_required', 'pending')) AND (paid_payment_id IS NULL) = (paid_at IS NULL)", name="ck_application_deposits_paid"),
        CheckConstraint("(remitted_at IS NULL) = (remittance_reference IS NULL)", name="ck_application_deposits_remitted"),
        CheckConstraint(
            "(refunded_at IS NULL) = (refund_amount IS NULL) AND (refunded_at IS NULL) = (refund_reason IS NULL) AND (refunded_at IS NULL) = (status <> 'refunded') AND (refund_amount IS NULL OR refund_amount > 0)",
            name="ck_application_deposits_refund",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id", ondelete="RESTRICT"), unique=True)
    required: Mapped[bool] = mapped_column(Boolean)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    active_payment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    paid_payment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remitted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    remittance_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    refunded_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    refund_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class InboundUniversityEmail(Base, TimestampMixin):
    __tablename__ = "inbound_university_emails"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_message_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    sender: Mapped[str] = mapped_column(String(320), index=True)
    recipient: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id"), nullable=True, index=True)
    match_status: Mapped[str] = mapped_column(String(30), default="unmatched")
    match_confidence: Mapped[int] = mapped_column(Integer, default=0)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    raw_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    sender_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    recipient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    context_type: Mapped[str] = mapped_column(String(50), default="direct")
    context_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class GalleryItem(Base, TimestampMixin):
    __tablename__ = "gallery_items"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(180))
    image_url: Mapped[str] = mapped_column(String(500))
    alt_text: Mapped[str] = mapped_column(String(220))
    category: Mapped[str] = mapped_column(String(80), default="General")
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class CareerApplication(Base, TimestampMixin):
    __tablename__ = "career_applications"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resume_url: Mapped[str] = mapped_column(String(500))
    cover_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    tracking_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    # hrc-023 (DEC-SCOPE-389): the candidate the application created or matched (W3), the visit's UTM (W1) and the consent shown (W4)
    candidate_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=True, index=True)
    utm: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    consent_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebinarRegistration(Base, TimestampMixin):
    """PUB-004: reuses the existing Event model (division-aware, already seeded with
    IT-division webinar content) for listing -- Event.registration_url only ever pointed
    at an external link, so there was no in-app "register" capture anywhere in the
    codebase. This table is the genuinely net-new piece."""

    __tablename__ = "webinar_registrations"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("events.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PasswordResetToken(Base, TimestampMixin):
    __tablename__ = "password_reset_tokens"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ENH-003 / DEC-SCOPE-019: "reset" (forgot-password, 30 min) or "welcome" (admin-provisioned
    # first-time set-password link, 72 h). `superseded_at` is set when an admin Re-send (or an
    # `active` change) replaces/revokes an unused welcome token.
    purpose: Mapped[str] = mapped_column(String(20), default="reset", server_default="reset")
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# mgmt-022 (SD13): migration 0162 repeats these (test_mgmt_022_migration).
SCHOOL_VALUE_CHECKS = {
    "ck_schools_contract_value": "contract_value IS NULL OR contract_value >= 0",
    "ck_schools_renewal_value": "renewal_value IS NULL OR renewal_value >= 0",
}
LEDGER_SCHOOL_CHECK = "school_id IS NULL OR (kind = 'income' AND vertical = 'school')"  # mgmt-022 SD14


class School(Base, TimestampMixin):
    """School partner record (SCH-003, DATA_MODEL.md §6.11; profile fields added ENH-009,
    DEC-SCOPE-025). `EVID-014`'s full field list is now confirmed in scope -- see the
    design doc for what's stored here vs. computed at read time in `SchoolOut`."""

    __tablename__ = "schools"
    __table_args__ = tuple(CheckConstraint(sql, name=name) for name, sql in SCHOOL_VALUE_CHECKS.items())  # mgmt-022 SD13
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tier_valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # ENH-009 / DEC-SCOPE-025: School Profile fields (EVID-014). All nullable, additive.
    school_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grades_available: Mapped[str | None] = mapped_column(String(200), nullable=True)
    board: Mapped[str | None] = mapped_column(String(20), nullable=True)
    partnership_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    mou_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    edusphere_bdm: Mapped[str | None] = mapped_column(String(200), nullable=True)
    monthly_visit_schedule: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vice_principal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # mgmt-022 (SD13, Q-23): the agreement's value and its renewal's, in rupees. Finance tier only (M13): set on the management school
    # dashboard, never part of the school admin forms or `SchoolOut`.
    contract_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    renewal_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)


class AcademicYear(Base, TimestampMixin):
    """Global, admin-managed academic-year calendar (ENH-001, DEC-DATA-004). No `school_id`
    -- one shared calendar across every partnered school, per the user's explicit decision
    recorded in docs/superpowers/specs/2026-09-18-enh-001-academic-year-design.md."""

    __tablename__ = "academic_years"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    label: Mapped[str] = mapped_column(String(20), unique=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")


class SchoolAccountInvite(Base, TimestampMixin):
    """Coordinator-issued invite for Principal/Teacher/Parent accounts (SCH-003,
    DATA_MODEL.md §6.15). Net-new. Provisions the four school-side accounts only --
    how academic_team/career_counselor/psychometric_team accounts are created is a
    separate path (DEC-SCOPE-014, SCH-004/005/006 scope, not this table).
    """

    __tablename__ = "school_account_invites"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"), index=True)
    role: Mapped[str] = mapped_column(String(50))
    invited_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


# ENH-025 (DEC-SCOPE-029 item 4): the fixed Gender list, shared by the CHECK below and schemas.StudentMasterFields.
GENDERS = ("female", "male", "other", "prefer_not_to_say")


class SchoolStudent(Base, TimestampMixin):
    """School-affiliated student (SCH-001, DATA_MODEL.md §6.11).

    Resolves DATA_MODEL.md §6.11's open schema question (also tracked under `DEC-ROLE-004`/
    `PRD_OPEN_ITEMS.md` item 68) as technical contract design, per this document's own
    precedent (`ADR-011`/`ADR-012`): a School-affiliated student never logs in at all
    (`DEC-ROLE-004` -- no individual login for School-affiliated students, an EduSphere-wide
    Student login-scope decision, not specific to this table). Unlike Agent-referred
    students, who at least belong to the existing overseas_student login-capable identity
    (`DEC-ROLE-001`), there is no login concept to attach here -- creating a `User` row with
    unusable credentials just to satisfy a FK pattern designed for authenticating identities
    would be needless complexity. Identity fields therefore live directly on this table, no
    `student_user_id` FK.
    """

    __tablename__ = "school_students"
    __table_args__ = (
        # ENH-025 (DEC-SCOPE-029): a roll number is unique within school + academic year + grade + section.
        # NULLS NOT DISTINCT makes a blank section/grade/year its own group; students with no roll number are
        # never constrained. lower(section) so "A" and "a" are the same section.
        Index(
            "uq_school_students_roll",
            "school_id", "academic_year_id", "grade_level", func.lower(text("section")), "roll_number",
            unique=True, postgresql_where=text("roll_number IS NOT NULL"), postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(f"gender IS NULL OR gender IN ({', '.join(repr(g) for g in GENDERS)})", name="ck_school_students_gender"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"), index=True)
    # Business-facing unique Student ID (PRD_OPEN_ITEMS.md item 66 / CLIENT_QUESTIONS.md
    # D-09), resolved 2026-09-15 -- see User.student_code's own comment for the format
    # rationale. Every school-affiliated student gets one (unlike User.student_code, this
    # column is never NULL -- every row here is a student, no other role shares the table).
    student_code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    grade_or_class: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    # school_teacher assignment (DATA_MODEL.md §6.12: "proposed as the simpler per-student
    # FK... not confirmed" -- adopted here as the working build default, the documented
    # leaning, not an invented mechanism).
    assigned_teacher_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # Roster-driven parent invite (DATA_MODEL.md §6.11 addendum): set when a Coordinator
    # enters a parent email that has no matching school_parent account yet, cleared once
    # SchoolParentLink exists -- lets invite-accept auto-link every student that named this
    # email, including a second child added while the first invite is still pending.
    pending_parent_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ENH-001: system-assigned only -- create_student/update_student must never read
    # this from a client payload (spec's security review, role-escalation finding).
    academic_year_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("academic_years.id"), nullable=True, index=True)
    grade_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ENH-013: the Career Counselor's one-line Career Passport goal (School CRM.md §8 "Career Interest"). Nullable, no
    # default, no backfill (migration 0039); written only by PATCH /school/students/{id}/career-goal.
    career_goal: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # ENH-025 (DEC-SCOPE-029): School CRM.md §3 Student Master fields. All optional; validated at the API
    # boundary by schemas.StudentMasterFields. grade_or_class stays the free-text display label.
    section: Mapped[str | None] = mapped_column(String(20), nullable=True)
    roll_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    student_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    subjects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    career_interests: Mapped[list | None] = mapped_column(JSON, nullable=True)
    global_education_interest: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    preferred_countries: Mapped[list | None] = mapped_column(JSON, nullable=True)
    preferred_courses: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Internal only -- never serialized or logged (spec §5: in local storage mode the random key is the barrier).
    photo_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SchoolParentLink(Base, TimestampMixin):
    """Many-to-many Parent<->Student link (SCH-001, DATA_MODEL.md §6.12) -- a student may
    have more than one linked parent, a parent more than one linked child."""

    __tablename__ = "school_parent_links"
    __table_args__ = (UniqueConstraint("parent_user_id", "school_student_id", name="uq_school_parent_link"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    parent_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    linked_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class SchoolStudentGradeHistory(Base, TimestampMixin):
    """ENH-004 append-only ledger of a student's grade/academic-year transitions
    (docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md §5.1). Each row is
    self-contained -- it records the state the student left (`from_*`) and the state they entered
    (`to_*`) -- so no backfill of existing students is needed and `school_students` stays the
    source of the *current* grade/year. `UNIQUE (school_student_id, to_academic_year_id)` is the
    database backstop against promoting the same student twice into the same year."""

    __tablename__ = "school_student_grade_history"
    __table_args__ = (UniqueConstraint("school_student_id", "to_academic_year_id", name="uq_school_student_grade_history_year"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    action: Mapped[str] = mapped_column(String(20))  # promoted | held_back
    from_academic_year_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("academic_years.id"), nullable=True)
    from_grade_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_grade_or_class: Mapped[str | None] = mapped_column(String(60), nullable=True)
    to_academic_year_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("academic_years.id"))
    to_grade_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_grade_or_class: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # ENH-025: previous class details survive roll-number clearing on a year move (DEC-SCOPE-029 item 6).
    from_section: Mapped[str | None] = mapped_column(String(20), nullable=True)
    from_roll_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_section: Mapped[str | None] = mapped_column(String(20), nullable=True)
    performed_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class SchoolStudentTransferRequest(Base, TimestampMixin):
    """ENH-005 -- a coordinator's request to move a student to another school, and (once approved) that student's
    transfer history (docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md §5.1). One table is
    both the workflow and the history. `filed_by_school_id` is the filing coordinator's school, always taken from their
    profile; `direction` is derived (outgoing when it equals `from_school_id`). The partial unique index is the database
    backstop for "at most one open request per student"; the CHECKs keep a request between two different schools, one
    of which filed it. Both are also in migration 0034 (dev startup can build the schema with `create_all`)."""

    __tablename__ = "school_student_transfer_requests"
    __table_args__ = (
        CheckConstraint("from_school_id <> to_school_id", name="ck_school_transfer_distinct_schools"),
        CheckConstraint("filed_by_school_id IN (from_school_id, to_school_id)", name="ck_school_transfer_filed_by_side"),
        Index("uq_school_transfer_pending_student", "school_student_id", unique=True, postgresql_where=text("status = 'pending'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    from_school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"))
    to_school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"))
    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    filed_by_school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected | cancelled
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # set on approval: the counts of what the transfer changed


class PortfolioEntry(Base, TimestampMixin):
    """ENH-012 -- self-entry Digital Portfolio content
    (docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md §5). One generic table with
    a `section` discriminator covers every list-shaped section (project/internship/competition/sport/
    leadership/volunteering/extracurricular/award/certification/skill) -- per-section tables were
    rejected in the spec's Approach section as unnecessary duplication of one shared shape. Net-new."""

    __tablename__ = "portfolio_entries"
    __table_args__ = (
        Index("ix_portfolio_entries_student_section", "school_student_id", "section"),
        CheckConstraint("attendance_percent IS NULL OR attendance_percent BETWEEN 0 AND 100", name="ck_portfolio_attendance_percent"),
        CheckConstraint("completion_status IS NULL OR completion_status IN ('not_started', 'in_progress', 'completed', 'discontinued')", name="ck_portfolio_completion_status"),
        CheckConstraint(
            "section = 'internship' OR (mentor_name IS NULL AND mentor_designation IS NULL AND attendance_percent IS NULL AND completion_status IS NULL "
            "AND feedback IS NULL AND skills_acquired IS NULL AND certificate_key IS NULL AND certificate_content_type IS NULL)",
            name="ck_portfolio_internship_fields",
        ),
        # ENH-024 (spec §4): mirrored verbatim in migration 0044 -- the API rejects each of these first; the CHECKs are the last line.
        CheckConstraint("certification_type IS NULL OR (certification_type = 'skill_india' AND section = 'certification')", name="ck_portfolio_cert_type"),
        CheckConstraint("certification_status IS NULL OR certification_status IN ('enrolled', 'in_progress', 'certified')", name="ck_portfolio_cert_status"),
        CheckConstraint(
            "(certification_type IS NULL AND certification_status IS NULL AND certificate_number IS NULL AND issued_on IS NULL) "
            "OR (certification_type IS NOT NULL AND certification_status IS NOT NULL)",
            name="ck_portfolio_cert_fields",
        ),
        CheckConstraint("certification_status IS DISTINCT FROM 'certified' OR (certificate_number IS NOT NULL AND issued_on IS NOT NULL)", name="ck_portfolio_cert_certified"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    section: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization: Mapped[str | None] = mapped_column(String(200), nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    # ENH-021 (DEC-SCOPE-032): internship tracking, section='internship' only (CHECK above). All nullable.
    mentor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mentor_designation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attendance_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_acquired: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    certificate_key: Mapped[str | None] = mapped_column(String(300), nullable=True)  # never serialized (spec S9)
    certificate_content_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    @property
    def has_certificate(self) -> bool:
        return self.certificate_key is not None
    # ENH-024 -- Skill India certification details; all NULL on every other entry (spec §4, DEC-SCOPE-033).
    certification_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    certification_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    certificate_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class PortfolioProfile(Base, TimestampMixin):
    """ENH-012 -- one row per student holding the free-text personal statement; separate from
    `PortfolioEntry` because it isn't list-shaped (spec §5). Net-new."""

    __tablename__ = "portfolio_profiles"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), unique=True, index=True)
    personal_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class SchoolActivity(Base, TimestampMixin):
    """School-wide scheduled activity (SCH-001's "schedule activities, track attendance"
    main workflow). Net-new -- no equivalent exists in `DATA_MODEL.md`'s original §6.11-6.18
    listing; added during this feature's own build to cover the confirmed workflow line
    that had no table proposed for it."""

    __tablename__ = "school_activities"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    # Optional entitlement-tracking category (`DEC-SCOPE-017`), e.g. "career_seminar" /
    # "parent_orientation" / "campus_visit" -- nullable so every pre-existing free-text
    # activity keeps working unchanged; only new tier-relevant activities need to set it.
    activity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SchoolActivityAttendance(Base, TimestampMixin):
    __tablename__ = "school_activity_attendance"
    __table_args__ = (UniqueConstraint("activity_id", "school_student_id", name="uq_school_activity_attendance"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    activity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_activities.id"), index=True)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    marked_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


# ENH-030 (DEC-SCOPE-041 D4): the IT `Attendance.status` values; a missing row is "not marked", never absent.
ATTENDANCE_STATUSES = ("present", "absent", "late", "excused")


class SchoolAttendanceRecord(Base, TimestampMixin):
    """ENH-030 -- one School student's daily class attendance (docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md §4).

    One row per student per day per school (D5 as amended after the final review): re-marking updates it, and after a transfer each
    school keeps its own register, so the new school never overwrites or re-stamps the old school's row (C1/AC10). Readers see only
    the student's current school's rows. No single-column indexes: the unique (school_student_id, school_id, session_date) index
    serves every query (spec §11 A4)."""

    __tablename__ = "school_attendance_records"
    __table_args__ = (
        UniqueConstraint("school_student_id", "school_id", "session_date", name="uq_school_attendance_student_school_date"),
        CheckConstraint("status IN ('present', 'absent', 'late', 'excused')", name="ck_school_attendance_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"))
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"))
    session_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    marked_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class SchoolActivityFeedback(Base, TimestampMixin):
    """ENH-018 -- a School Coordinator's feedback on one completed Edusphere activity (`School CRM.md §31`,
    docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md §4). One row per activity (D5) and immutable;
    `school_id` is copied from the activity so reads stay scoped without a join. Student participation is NOT stored: it is
    computed from `school_activity_attendance` at read time (D4). `created_at` is the submission time."""

    __tablename__ = "school_activity_feedback"
    __table_args__ = (
        UniqueConstraint("activity_id", name="uq_activity_feedback_activity"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_activity_feedback_rating"),
        CheckConstraint("satisfaction BETWEEN 1 AND 5", name="ck_activity_feedback_satisfaction"),
        Index("ix_school_activity_feedback_created_at", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    activity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_activities.id"))
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"), index=True)
    submitted_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    trainer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)
    satisfaction: Mapped[int] = mapped_column(Integer)
    feedback: Mapped[str] = mapped_column(Text)
    suggestions: Mapped[str | None] = mapped_column(Text, nullable=True)


class SchoolRosterUploadBatch(Base, TimestampMixin):
    """SCH-002 bulk roster upload audit trail (DATA_MODEL.md §6.13). Net-new."""

    __tablename__ = "school_roster_upload_batches"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"), index=True)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="processing")


class SchoolRosterUploadRow(Base, TimestampMixin):
    __tablename__ = "school_roster_upload_rows"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_roster_upload_batches.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), nullable=True)


BULK_TARGET_TYPES = ("academic_result", "psychometric_record", "test_prep_record", "language_record", "school_onboarding")  # ENH-029 (0054)


class SchoolBulkUploadBatch(Base, TimestampMixin):
    """ENH-028 -- one bulk data-entry upload (docs/superpowers/specs/2026-10-01-enh-028-bulk-data-entry-design.md §4). The
    roster upload keeps its own SCH-002 tables. The idempotency key is scoped to the uploader and the module, so one user's key
    can never replay another user's report. No status column (S3): the row only becomes visible already complete."""

    __tablename__ = "school_bulk_upload_batches"
    __table_args__ = (
        UniqueConstraint("uploaded_by_user_id", "target_type", "idempotency_key", name="uq_school_bulk_upload_key"),
        CheckConstraint(f"target_type IN {BULK_TARGET_TYPES}", name="ck_school_bulk_upload_target_type"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    target_type: Mapped[str] = mapped_column(String(30))
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    file_sha256: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)


class SchoolBulkUploadRow(Base, TimestampMixin):
    """ENH-028 -- one filled-in CSV row's outcome. `created_record_id` points into the batch's target table (no FK: it is
    polymorphic); `student_code` is what the row named, kept for the report even when it matched nobody. `created_user_id` (ENH-029)
    is the Coordinator a `school_onboarding` row created (`created_record_id` is then its school); NULL for every other target."""

    __tablename__ = "school_bulk_upload_rows"
    __table_args__ = (CheckConstraint("status IN ('accepted', 'rejected')", name="ck_school_bulk_upload_row_status"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_bulk_upload_batches.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    student_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_record_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class SchoolStaffAssignment(Base, TimestampMixin):
    """School-staff portfolio assignment (`DEC-SCOPE-013`) -- scopes an `academic_team`/
    `career_counselor`/`psychometric_team` member to one or more entire schools. Many-to-
    many: one member may cover several schools, one school may have several members of the
    same role (needed for `DEC-ROLE-007`'s same-actor restriction on `SCH-006` -- a
    portfolio needs at least two `academic_team` members to publish anything)."""

    __tablename__ = "school_staff_assignments"
    __table_args__ = (UniqueConstraint("user_id", "school_id", name="uq_school_staff_assignment"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"), index=True)
    role: Mapped[str] = mapped_column(String(50))
    assigned_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class SchoolCareerRecord(Base, TimestampMixin):
    """SCH-004 -- Career Guidance & Counselling. Net-new, `DATA_MODEL.md` §6.17. No
    Draft/Published gate -- visible to readers as soon as it's created.
    ENH-026 (DEC-SCOPE-031): the §7 structured fields and status lifecycle, all nullable. `status` NULL means the
    record predates tracking (or is a `recommendation`, which never has one)."""

    __tablename__ = "school_career_records"
    __table_args__ = (
        CheckConstraint("status IS NULL OR status IN ('not_started', 'scheduled', 'completed', 'follow_up_required')", name="ck_career_record_status"),
        Index("ix_school_career_records_student_type_status", "school_student_id", "record_type", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    career_counselor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    record_type: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    career_interests: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    global_education_interest: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    academic_strengths: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    weak_areas: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recommended_careers: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recommended_courses: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recommended_stream: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recommended_skills: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    parent_participated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    parent_participation_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class SchoolFundingRecord(Base, TimestampMixin):
    """ENH-020 (DEC-SCOPE-045) -- School CRM.md §21 financial support / loan assistance case, `DATA_MODEL.md` §6.25.
    `school_id` is the student's school when the case was opened (D12): staff see a case only while the student is still
    there; a linked parent always sees it. One open case per student, school and type (partial unique index, D7)."""

    __tablename__ = "school_funding_records"
    __table_args__ = (
        CheckConstraint("support_type IN ('education_loan', 'financial_assistance', 'scholarship', 'funding_guidance')", name="ck_funding_record_support_type"),
        CheckConstraint("status IN ('required', 'counselling', 'documents', 'application', 'approved', 'completed', 'closed')", name="ck_funding_record_status"),
        CheckConstraint("(status = 'closed') = (closure_reason IS NOT NULL)", name="ck_funding_record_closure"),
        Index("uq_funding_record_open_student_type", "school_student_id", "school_id", "support_type", unique=True, postgresql_where=text("status NOT IN ('completed', 'closed')")),
        Index("ix_school_funding_records_school_type", "school_id", "support_type"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"))
    support_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    status_changed_on: Mapped[date] = mapped_column(Date)
    provider_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    closure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    career_counselor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class SchoolPsychometricRecord(Base, TimestampMixin):
    """SCH-005 -- Psychometric Assessment. Net-new, `DATA_MODEL.md` §6.18."""

    __tablename__ = "school_psychometric_records"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    psychometric_team_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    assessment_type: Mapped[str] = mapped_column(String(120))
    report_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="assigned")
    # ENH-027 (DEC-SCOPE-035): School CRM.md §6's structured result. All optional; `status` still flips only on
    # `report_url`. Lists are JSON arrays of short strings (ENH-025's `_clean_list` rule); empty is stored as SQL NULL
    # (`none_as_null=True`, same as ENH-026's career-record lists). Names match ENH-026's where the concept is shared.
    test_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    strengths: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    interest_areas: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    personality_indicators: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recommended_careers: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recommended_stream: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    counsellor_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_discussion_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    parent_discussion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class SchoolTestPrepRecord(Base, TimestampMixin):
    """SCH-009 -- Test Preparation (IELTS/SAT coaching), resolved 2026-09-15
    (`DEC-SCOPE-018`, closes `DEC-SCOPE-015` item 78 for this specific module). Delivered
    by the existing `academic_team` role (no new role) -- same "one table, no Draft/
    Published gate" shape as `SchoolCareerRecord`/`SchoolPsychometricRecord`, not
    `SchoolAcademicResult`'s formal-results gate."""

    __tablename__ = "school_test_prep_records"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    academic_team_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    test_type: Mapped[str] = mapped_column(String(10))
    mock_scores: Mapped[list] = mapped_column(JSON, default=list)
    target_score: Mapped[str | None] = mapped_column(String(20), nullable=True)
    actual_score: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")


class SchoolLanguageRecord(Base, TimestampMixin):
    """SCH-009 -- Foreign Language Classes, resolved 2026-09-15 (`DEC-SCOPE-018`, closes
    `DEC-SCOPE-015` item 78 for this specific module). Same actor/shape rationale as
    `SchoolTestPrepRecord` above."""

    __tablename__ = "school_language_records"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    academic_team_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    language: Mapped[str] = mapped_column(String(60))
    level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    classes_attended: Mapped[int] = mapped_column(Integer, default=0)
    assessment_score: Mapped[str | None] = mapped_column(String(20), nullable=True)
    certification_status: Mapped[str] = mapped_column(String(20), default="not_started")


# --- ENH-011: school skills tracker (docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md §4) ---
# Soft Skills / Digital Skills batches run by a `career_counselor` for ONE school (`DEC-SCOPE-026`). Deliberately separate
# from SCH-009's per-student rows (left as-is, D3) and from the IT training `Batch`/`Enrollment` (keyed to `users`, not
# school students). "Frozen" (the student has since transferred) is computed, never stored (D9).


class SchoolSkillBatch(Base, TimestampMixin):
    __tablename__ = "school_skill_batches"
    __table_args__ = (
        CheckConstraint("module_type IN ('soft_skills', 'digital_skills')", name="ck_skill_batch_module"),
        CheckConstraint("status IN ('open', 'closed')", name="ck_skill_batch_status"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_skill_batch_dates"),
        Index("ix_school_skill_batches_school_module", "school_id", "module_type"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"))
    module_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(160))
    topic: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trainer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class SchoolSkillEnrollment(Base, TimestampMixin):
    __tablename__ = "school_skill_enrollments"
    __table_args__ = (
        UniqueConstraint("batch_id", "school_student_id", name="uq_skill_enrollment_batch_student"),
        CheckConstraint("status IN ('enrolled', 'completed', 'certified', 'withdrawn')", name="ck_skill_enrollment_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_skill_batches.id"))
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="enrolled")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    certified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrolled_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class SchoolSkillSession(Base, TimestampMixin):
    __tablename__ = "school_skill_sessions"
    __table_args__ = (UniqueConstraint("batch_id", "session_date", name="uq_skill_session_batch_date"),)  # D10
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_skill_batches.id"))
    session_date: Mapped[date] = mapped_column(Date)
    topic: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class SchoolSkillAttendance(Base, TimestampMixin):
    __tablename__ = "school_skill_attendance"
    __table_args__ = (UniqueConstraint("session_id", "enrollment_id", name="uq_skill_attendance_session_enrollment"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_skill_sessions.id"))
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_skill_enrollments.id"), index=True)
    present: Mapped[bool] = mapped_column(Boolean)
    marked_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class SchoolSkillAssessment(Base, TimestampMixin):
    __tablename__ = "school_skill_assessments"
    __table_args__ = (
        UniqueConstraint("batch_id", "name", name="uq_skill_assessment_batch_name"),
        CheckConstraint("max_score > 0", name="ck_skill_assessment_max"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_skill_batches.id"))
    name: Mapped[str] = mapped_column(String(120))
    max_score: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class SchoolSkillScore(Base, TimestampMixin):
    __tablename__ = "school_skill_scores"
    __table_args__ = (
        UniqueConstraint("assessment_id", "enrollment_id", name="uq_skill_score_assessment_enrollment"),
        CheckConstraint("score >= 0", name="ck_skill_score_nonneg"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    assessment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_skill_assessments.id"))
    enrollment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_skill_enrollments.id"), index=True)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class SchoolAcademicResult(Base, TimestampMixin):
    """SCH-006 -- Academic Results (Draft -> Verified -> Published). Net-new,
    `DATA_MODEL.md` §6.16. `DEC-ROLE-007`: `verified_by_user_id`/`published_by_user_id`
    must each be a different `academic_team` member than `uploaded_by_user_id`, enforced
    at the application layer (SCH-006-AC04)."""

    __tablename__ = "school_academic_results"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    academic_year: Mapped[str] = mapped_column(String(20))
    term: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(80))
    max_marks: Mapped[float] = mapped_column(Numeric(6, 2))
    marks_obtained: Mapped[float] = mapped_column(Numeric(6, 2))
    grade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    teacher_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    verified_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SchoolResultStatusHistory(Base, TimestampMixin):
    __tablename__ = "school_result_status_history"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_academic_results.id"), index=True)
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    changed_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecruiterProfile(Base, TimestampMixin):
    """rec-001 (DEC-SCOPE-116, R2): a recruiter's profile, 1:1 with a `placement_team` user. Name, email, mobile and active stay on
    `users`. Employee ID and reporting manager are nullable only for rows that predate the Recruiter Staff page (the 0100 backfill)
    or come from the generic Users form; that page requires both. The manager must be an active `placement_manager` -- a cross-table
    rule, so `services/recruiter.py` enforces it under a row lock."""

    __tablename__ = "recruiter_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_recruiter_profiles_user"),
        Index("uq_recruiter_profiles_employee_id", text("lower(employee_id)"), unique=True),
        Index("ix_recruiter_profiles_reporting_manager", "reporting_manager_user_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    employee_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reporting_manager_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class _RecCatalogueValue(TimestampMixin):
    """rec-002 (DEC-SCOPE-117): one value of a recruiter managed list. Deactivated, never deleted; a rename keeps the id, so records
    that point at it keep their link. Names are unique per list, case-insensitively; `sort_order` keeps the source order."""

    @declared_attr.directive
    def __table_args__(cls):
        return (Index(f"uq_{cls.__tablename__}_name", text("lower(name)"), unique=True),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class RecLeadSource(_RecCatalogueValue, Base):
    __tablename__ = "rec_lead_sources"  # EVID-018 §2


class RecCandidateSource(_RecCatalogueValue, Base):
    __tablename__ = "rec_candidate_sources"  # §9


class RecIndustry(_RecCatalogueValue, Base):
    __tablename__ = "rec_industries"  # §3; starts empty (C1)


class RecJobCategory(_RecCatalogueValue, Base):
    __tablename__ = "rec_job_categories"  # §6, §26


class RecContactRole(_RecCatalogueValue, Base):
    __tablename__ = "rec_contact_roles"  # §4


class RecCompanySize(_RecCatalogueValue, Base):
    __tablename__ = "rec_company_sizes"  # §3 Company Size; the owner's bands (C2)


# The URL slug of each simple list (api/recruiter_catalogue.py).
REC_CATALOGUE_MODELS = {
    "lead-sources": RecLeadSource,
    "candidate-sources": RecCandidateSource,
    "industries": RecIndustry,
    "job-categories": RecJobCategory,
    "contact-roles": RecContactRole,
    "company-sizes": RecCompanySize,
}


class RecCampaign(Base, TimestampMixin):
    """rec-002 (§2 "Campaign"): a recruiter campaign under one lead source -- the tel-002 campaign shape without a product. The source
    must be active when it is set (services/recruiter_catalogue)."""

    __tablename__ = "rec_campaigns"
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_rec_campaigns_dates"),
        Index("uq_rec_campaigns_name", text("lower(name)"), unique=True),
        Index("ix_rec_campaigns_lead_source", "lead_source_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    lead_source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_lead_sources.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

class PartnershipProfile(Base, TimestampMixin):
    """upc-001 (DEC-SCOPE-118): a partnership manager's profile, 1:1 with a `partnership_manager` user (the user id is the key). Name,
    email, mobile and active status stay on `users` (PU2). The reporting head must be an active `partnership_head`; that spans tables, so
    `services/partnership.py` enforces it under a row lock (no cross-table CHECK)."""

    __tablename__ = "partnership_profiles"
    __table_args__ = (
        Index("uq_partnership_profiles_employee_id", text("lower(employee_id)"), unique=True),
        Index("ix_partnership_profiles_reporting_head", "reporting_head_user_id"),
    )
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(40))
    reporting_head_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


SKILL_DOMAINS = ("it", "non_it")  # hrc-017 (DEC-SCOPE-388 T1): the top-level grouping of a Skills Master category


class SkillCategory(Base, TimestampMixin):
    """rec-006 (DEC-SCOPE-119, EVID-018 S2-§2): a Skills Master category. Never deleted: deactivating hides it from new picks while
    skills keep the link."""

    __tablename__ = "skill_categories"
    __table_args__ = (
        Index("uq_skill_categories_name", text("lower(name)"), unique=True),
        CheckConstraint(f"domain IN ({', '.join(repr(v) for v in SKILL_DOMAINS)})", name="ck_skill_categories_domain"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    domain: Mapped[str] = mapped_column(String(10), default="it", server_default=text("'it'"))  # hrc-017 (T1)


class Skill(Base, TimestampMixin):
    """rec-006: one searchable skill with a primary category (secondary categories are `skill_category_tags`). A skill name and an
    alias share one case-insensitive term space -- a cross-table rule, so services/skills.py enforces it under an advisory lock."""

    __tablename__ = "skills"
    __table_args__ = (Index("uq_skills_name", text("lower(name)"), unique=True), Index("ix_skills_category", "category_id"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80))
    category_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("skill_categories.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class SkillCategoryTag(Base):
    """rec-006 (S5): a skill's secondary category (JavaScript: Programming + Frontend)."""

    __tablename__ = "skill_category_tags"
    skill_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("skill_categories.id"), primary_key=True)


class SkillAlias(Base):
    """rec-006 (S2-§16): another spelling that resolves to the skill ("J2EE" → Java). Unique case-insensitively across all skills."""

    __tablename__ = "skill_aliases"
    __table_args__ = (Index("uq_skill_aliases_alias", text("lower(alias)"), unique=True), Index("ix_skill_aliases_skill", "skill_id"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    skill_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SkillRelated(Base):
    """rec-006 (S4): two related skills (Java ⇄ Core Java), stored once per unordered pair (a < b); search expansion reads both ways."""

    __tablename__ = "skill_related"
    __table_args__ = (CheckConstraint("skill_a_id < skill_b_id", name="ck_skill_related_order"),)
    skill_a_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    skill_b_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)


# rec-009 (DEC-SCOPE-122, spec §3): the central candidate master. Q-08: the status is set by hand, from these values.
CANDIDATE_STATUSES = ("available", "interviewing", "placed", "not_looking", "do_not_contact")
# On the metadata so 0001's create_all builds it for a fresh database; 0107 creates it IF NOT EXISTS.
CANDIDATE_CODE_SEQ = Sequence("candidate_code_seq", metadata=Base.metadata)
CANDIDATE_CHECKS = {  # migration 0107 repeats these strings; test_rec_009_migration asserts they stay identical
    "ck_candidates_contact": "mobile IS NOT NULL OR email IS NOT NULL",
    "ck_candidates_status": "status IN (" + ", ".join(f"'{s}'" for s in CANDIDATE_STATUSES) + ")",
    "ck_candidates_passing_year": "passing_year IS NULL OR passing_year BETWEEN 1950 AND 2100",
    "ck_candidates_experience": "experience_months IS NULL OR experience_months BETWEEN 0 AND 600",
    "ck_candidates_notice": "notice_days IS NULL OR notice_days BETWEEN 0 AND 365",
    "ck_candidates_salary": "(current_salary IS NULL OR current_salary >= 0) AND (expected_salary IS NULL OR expected_salary >= 0)",
}
CANDIDATE_PACKAGE_CHECKS = {  # hrc-011 (DEC-SCOPE-375): migration 0251 repeats these strings; test_hrc_011_migration asserts they stay identical
    "ck_candidates_minimum_salary": "minimum_salary IS NULL OR minimum_salary >= 0",
    "ck_candidates_salary_periods": "coalesce(current_salary_period, 'year') IN ('year', 'month') AND coalesce(expected_salary_period, 'year') IN ('year', 'month') AND coalesce(minimum_salary_period, 'year') IN ('year', 'month')",
}
CANDIDATE_MERGE_CHECKS = {  # hrc-014 (DEC-SCOPE-377 D8): migration 0258 repeats these strings; test_hrc_014_migration asserts they stay identical
    "ck_candidates_merged": "(merged_into_id IS NULL) = (merged_at IS NULL) AND (merged_at IS NULL) = (merged_by_user_id IS NULL) AND (merged_into_id IS NULL OR archived_at IS NOT NULL)",
    "ck_candidates_merged_self": "merged_into_id IS NULL OR merged_into_id <> id",
}
# hrc-011 C2: the pay periods (Q-10) and how many of each make a year.
SALARY_PERIODS = {"year": 1, "month": 12}
# hrc-010 (DEC-SCOPE-383 P9): how the person likes to be reached; migration 0260 repeats these checks (test_hrc_010_migration).
CANDIDATE_CONTACT_METHODS = ("phone", "whatsapp", "email")
CANDIDATE_PROFILE_CHECKS = {
    "ck_candidates_preferred_contact": _in("preferred_contact", CANDIDATE_CONTACT_METHODS),
    "ck_candidates_relevant_experience": "relevant_experience_months IS NULL OR relevant_experience_months BETWEEN 0 AND 600",
}
# hrc-035 (DEC-SCOPE-396 K3): why a candidate was anonymised; migration 0273 repeats these checks (test_hrc_035_migration).
CANDIDATE_ANONYMISED_REASONS = ("request", "retention")
CANDIDATE_PRIVACY_CHECKS = {
    "ck_candidates_anonymised": "(anonymised_at IS NULL) = (anonymised_reason IS NULL)",
    "ck_candidates_anonymised_reason": _in("anonymised_reason", CANDIDATE_ANONYMISED_REASONS),
}
CANDIDATE_EMPLOYMENT_CHECKS = {
    "ck_candidate_employment_dates": "end_date IS NULL OR end_date >= start_date",
    "ck_candidate_employment_type": _in("employment_type", JOB_EMPLOYMENT_TYPES),
}
CANDIDATE_CERTIFICATION_CHECKS = {"ck_candidate_certifications_dates": "expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on"}


class Candidate(Base, TimestampMixin):
    """rec-009: one person in the recruiter pool -- external (no login) or, from rec-010, an IT student who opted in (`user_id`).
    Q-07: one person is one candidate -- the normalised mobile and the lower-cased email are each unique. Archived, never deleted."""

    __tablename__ = "candidates"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in (CANDIDATE_CHECKS | CANDIDATE_PACKAGE_CHECKS | CANDIDATE_MERGE_CHECKS | CANDIDATE_PROFILE_CHECKS
                                                            | CANDIDATE_PRIVACY_CHECKS).items()),
        Index("uq_candidates_mobile", "mobile_normalized", unique=True, postgresql_where=text("mobile_normalized IS NOT NULL")),
        Index("uq_candidates_email", text("lower(email)"), unique=True, postgresql_where=text("email IS NOT NULL")),
        Index("ix_candidates_source_id", "source_id"),
        Index("ix_candidates_status", "status"),
        Index("ix_candidates_created_at", "created_at"),
        Index("ix_candidates_expected_annual_inr", "expected_annual_inr"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_code: Mapped[str] = mapped_column(String(12), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    mobile_normalized: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    qualification: Mapped[str | None] = mapped_column(String(120), nullable=True)
    college: Mapped[str | None] = mapped_column(String(200), nullable=True)
    passing_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    experience_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # hrc-011 (DEC-SCOPE-375 C3/C8): each amount as entered (currency, pay period) and its normalised annual INR; null = not provided.
    current_salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    current_salary_period: Mapped[str | None] = mapped_column(String(5), nullable=True)
    expected_salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    expected_salary_period: Mapped[str | None] = mapped_column(String(5), nullable=True)
    minimum_salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    minimum_salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    minimum_salary_period: Mapped[str | None] = mapped_column(String(5), nullable=True)
    salary_negotiable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    current_annual_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    expected_annual_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    minimum_annual_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    notice_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    preferred_locations: Mapped[list] = mapped_column(JSON, default=list)
    preferred_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_candidate_sources.id"))
    source_detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # hrc-023 (DEC-SCOPE-389 W1): the website visit's UTM parameters (the five standard keys) for a candidate the website created
    utm: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="available", server_default=text("'available'"))
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=True)
    opted_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # hrc-023 (W3): empty for a candidate a public website job application created ("added by the website")
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # hrc-014 (DEC-SCOPE-377 D8): a merged candidate is archived for good and names the candidate it was merged into.
    merged_into_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=True)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    # hrc-010 (DEC-SCOPE-383): structured location (sets `location`, P5), contact preference and verification (P9), the skills extras
    # (P7) and the preferences (P8). The lists hold job-enum values (work modes, employment types, shifts) or short texts.
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    preferred_contact: Mapped[str | None] = mapped_column(String(10), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    relevant_experience_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tools: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    languages: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    preferred_roles: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    work_modes: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    employment_types: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    shifts: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    available_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    willing_to_relocate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # hrc-012 (DEC-SCOPE-382 O2/O3): the one primary recruiter (NULL = unassigned) and the placement-officer owner. Visibility stays
    # pool-wide (O1); services/candidate_ownership decides who may change them.
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    placement_officer_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    # hrc-035 (DEC-SCOPE-396 K3/K4): set once by the anonymiser; an anonymised candidate is outside `candidates.pool_filter()` for good.
    anonymised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anonymised_reason: Mapped[str | None] = mapped_column(String(10), nullable=True)


# hrc-035 (DEC-SCOPE-396 K8): one row (`id = 1`); `months` NULL = the retention rule is off (the default until legal sign-off).
CANDIDATE_RETENTION_CHECKS = {
    "ck_candidate_retention_settings_one_row": "id = 1",
    "ck_candidate_retention_settings_months": "months IS NULL OR months BETWEEN 6 AND 120",
}


class CandidateRetentionSetting(Base, TimestampMixin):
    """hrc-035 (K8): how many months after a candidate's last activity the daily sweep anonymises them, and its last run."""

    __tablename__ = "candidate_retention_settings"
    __table_args__ = tuple(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_RETENTION_CHECKS.items())
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    months: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CandidateEducation(Base):
    """hrc-010 (P2): one degree, in the recruiter's order (`position`); row 1 sets qualification, college and passing year (P5)."""

    __tablename__ = "candidate_education"
    __table_args__ = (
        CheckConstraint("year IS NULL OR year BETWEEN 1950 AND 2100", name="ck_candidate_education_year"),
        Index("ix_candidate_education_candidate", "candidate_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(SmallInteger)
    degree: Mapped[str | None] = mapped_column(String(120), nullable=True)
    specialisation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    institution: Mapped[str | None] = mapped_column(String(200), nullable=True)
    year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)


class CandidateEmployment(Base):
    """hrc-010 (P3/P4): one job; no end date = current. The union of the periods is the derived total experience."""

    __tablename__ = "candidate_employment"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_EMPLOYMENT_CHECKS.items()),
        Index("ix_candidate_employment_candidate", "candidate_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(SmallInteger)
    employer: Mapped[str] = mapped_column(String(200))
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class CandidateCertification(Base):
    """hrc-010 (P7): a certification record (the certificate file itself is an hrc-015 document)."""

    __tablename__ = "candidate_certifications"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_CERTIFICATION_CHECKS.items()),
        Index("ix_candidate_certifications_candidate", "candidate_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(String(200))
    issuer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    credential_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


# hrc-012 (DEC-SCOPE-382 O4/O6): collaborators and the append-only assignment history. Migration 0259 repeats the checks.
CANDIDATE_ASSIGNMENT_KINDS = ("owner", "placement_officer", "collaborator_added", "collaborator_removed")
CANDIDATE_ASSIGNMENT_REASONS = ("create", "assign", "reassign", "route")  # hrc-024 (DEC-SCOPE-393 R8): `route`, migration 0270


class CandidateCollaborator(Base):
    """hrc-012 (O4): a recruiter or placement officer sharing a candidate with its primary recruiter -- added only while shared ownership
    is switched on; removing one is always allowed."""

    __tablename__ = "candidate_collaborators"
    __table_args__ = (UniqueConstraint("candidate_id", "user_id", name="uq_candidate_collaborators_pair"), Index("ix_candidate_collaborators_user", "user_id"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    added_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CandidateAssignmentHistory(Base):
    """hrc-012 (O6, AC3): one row per ownership change; `from_user_id` NULL = nobody before, `to_user_id` NULL = cleared/removed.
    hrc-024 (R8): `changed_by_user_id` NULL = the system (reason `route`)."""

    __tablename__ = "candidate_assignment_history"
    __table_args__ = (
        CheckConstraint("kind IN ('owner', 'placement_officer', 'collaborator_added', 'collaborator_removed')", name="ck_candidate_assignment_history_kind"),
        CheckConstraint(f"reason IN ({', '.join(repr(r) for r in CANDIDATE_ASSIGNMENT_REASONS)})", name="ck_candidate_assignment_history_reason"),
        Index("ix_candidate_assignment_history_candidate", "candidate_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    from_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    to_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    changed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# hrc-024 (DEC-SCOPE-393, migration 0270): candidate routing -- rules by kind, one settings row and a round-robin cursor per rule group.
CANDIDATE_ROUTING_KINDS = ("source", "skill_category", "location")  # R1: the routing order
CANDIDATE_ROUTING_STRATEGIES = ("round_robin", "least_workload")
CANDIDATE_ROUTING_RULE_CHECKS = {
    "ck_candidate_routing_rules_kind": f"kind IN ({', '.join(repr(k) for k in CANDIDATE_ROUTING_KINDS)})",
    "ck_candidate_routing_rules_value": (
        "(kind = 'source') = (source_id IS NOT NULL) AND (kind = 'skill_category') = (skill_category_id IS NOT NULL)"
        " AND (kind = 'location') = (location IS NOT NULL)"
    ),
}
CANDIDATE_ROUTING_RULE_VALUE = "coalesce(source_id::text, skill_category_id::text, lower(location))"


class CandidateRoutingRule(Base, TimestampMixin):
    """hrc-024 (R2): a candidate whose source, skill category or location is the rule's value goes to its recruiter. Rules on one
    (kind, value) form a group the strategy picks from. A rule is added or deleted, never edited."""

    __tablename__ = "candidate_routing_rules"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_ROUTING_RULE_CHECKS.items()),
        Index("uq_candidate_routing_rules_rule", "kind", text(CANDIDATE_ROUTING_RULE_VALUE), "recruiter_user_id", unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_candidate_sources.id"), nullable=True)
    skill_category_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("skill_categories.id"), nullable=True)
    location: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recruiter_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class CandidateRoutingSetting(Base, TimestampMixin):
    """hrc-024 (R4/R6): the one settings row (id 1); no row = round robin and no default recruiter."""

    __tablename__ = "candidate_routing_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_candidate_routing_settings_one_row"),
        CheckConstraint(f"strategy IN ({', '.join(repr(s) for s in CANDIDATE_ROUTING_STRATEGIES)})", name="ck_candidate_routing_settings_strategy"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    default_recruiter_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    strategy: Mapped[str] = mapped_column(String(16), default="round_robin", server_default=text("'round_robin'"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class CandidateRoutingCursor(Base):
    """hrc-024 (R6/R12): the last recruiter a rule group gave a candidate to; locked FOR UPDATE so concurrent intakes take turns."""

    __tablename__ = "candidate_routing_cursors"
    group_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    last_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class CandidateOwnershipSetting(Base, TimestampMixin):
    """hrc-012 (O4): one row (`id = 1`); no row means shared ownership is off."""

    __tablename__ = "candidate_ownership_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_candidate_ownership_settings_one_row"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    shared_ownership: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class CandidateSelfServiceSetting(Base, TimestampMixin):
    """hrc-022 (DEC-SCOPE-386 C7): one row (`id = 1`) -- the candidate fields an external candidate may edit in the portal. No row means
    the default (services/candidate_portal.DEFAULT_FIELDS)."""

    __tablename__ = "candidate_self_service_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_candidate_self_service_settings_one_row"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    fields: Mapped[list] = mapped_column(JSON, default=list)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


# hrc-022 (DEC-SCOPE-386 C3): migration 0263 repeats these strings; test_hrc_022_migration asserts they stay identical.
USER_VERIFICATION_PURPOSES = ("verify_email", "email_change")
USER_VERIFICATION_CHECKS = {
    "ck_user_verification_tokens_purpose": f"purpose IN ({', '.join(repr(v) for v in USER_VERIFICATION_PURPOSES)})",
    "ck_user_verification_tokens_new_email": "(purpose = 'email_change') = (new_email IS NOT NULL)",
}


class UserVerificationToken(Base):
    """hrc-022 (C3): a single-use, hashed-at-rest link proving control of an email address -- the account's own (`verify_email`) or the
    address it is changing to (`email_change`, which names it). Never the raw token."""

    __tablename__ = "user_verification_tokens"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in USER_VERIFICATION_CHECKS.items()),
        Index("ix_user_verification_tokens_user", "user_id", "purpose", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    new_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# hrc-016 (DEC-SCOPE-387 T2/T3): candidate notes and tasks. Migration 0264 repeats CANDIDATE_NOTE_TASK_CHECKS (its test asserts identity).
CANDIDATE_NOTE_MAX = 2000
CANDIDATE_TASK_TYPES = ("follow_up", "resume_screening", "interview_coordination", "employer_feedback")
CANDIDATE_NOTE_TASK_CHECKS = {
    "ck_candidate_notes_body": f"char_length(body) BETWEEN 1 AND {CANDIDATE_NOTE_MAX}",
    "ck_candidate_tasks_type": "task_type IN ('follow_up', 'resume_screening', 'interview_coordination', 'employer_feedback')",
    "ck_candidate_tasks_status": "status IN ('open', 'done', 'cancelled')",
    "ck_candidate_tasks_state": (
        "(status = 'done') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL) "
        "AND (status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancelled_by_user_id IS NULL)"
    ),
}


class CandidateNote(Base):
    """hrc-016 (T2): a private note on a candidate. Append-only (no edit or delete); internal only -- no candidate, student, employer or
    public route reads this table. Never logged; the audit row carries ids only."""

    __tablename__ = "candidate_notes"
    __table_args__ = (
        CheckConstraint(CANDIDATE_NOTE_TASK_CHECKS["ck_candidate_notes_body"], name="ck_candidate_notes_body"),
        Index("ix_candidate_notes_candidate_created", "candidate_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"))
    author_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CandidateTask(Base, TimestampMixin):
    """hrc-016 (T1/T3, Q-16): a task about a candidate, assigned to one team member, optionally about one of its applications or a
    requirement. Not a rec-024 follow-up: those belong to a company's scope and have no assignee."""

    __tablename__ = "candidate_tasks"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_NOTE_TASK_CHECKS.items() if name.startswith("ck_candidate_tasks_")),
        Index("ix_candidate_tasks_candidate", "candidate_id", "status", "due_at"),
        Index("ix_candidate_tasks_assignee_open", "assignee_user_id", "due_at", postgresql_where=text("status = 'open'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"))
    application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_applications.id", ondelete="RESTRICT"), nullable=True)
    job_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assignee_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default="open", server_default=text("'open'"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# hrc-014 (DEC-SCOPE-377 D1/D2/D9): one probable-duplicate pair, stored once (lower id first). Migration 0256 repeats the checks.
CANDIDATE_DUPLICATE_SIGNALS = ("name_location_college", "phone_variant")
CANDIDATE_DUPLICATE_STATUSES = ("open", "dismissed", "merged")
CANDIDATE_DUPLICATE_CHECKS = {
    "ck_candidate_duplicates_order": "candidate_id < other_id",
    "ck_candidate_duplicates_status": "status IN ('open', 'dismissed', 'merged')",
    "ck_candidate_duplicates_decided": "(status = 'open') = (decided_at IS NULL)",
    "ck_candidate_duplicates_note": "note IS NULL OR char_length(note) <= 500",
}


class CandidateDuplicate(Base):
    """hrc-014: a pair the detector (services/candidate_duplicates) thinks may be one person. `open` until someone dismisses it ("not the
    same person", never queued again) or merges one into the other. Never deleted."""

    __tablename__ = "candidate_duplicates"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_DUPLICATE_CHECKS.items()),
        UniqueConstraint("candidate_id", "other_id", name="uq_candidate_duplicates_pair"),
        Index("ix_candidate_duplicates_status", "status", "created_at"),
        Index("ix_candidate_duplicates_other", "other_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"))
    other_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"))
    signals: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(10), default="open", server_default=text("'open'"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# hrc-013 (DEC-SCOPE-391 I9): migration 0268 repeats these checks.
CANDIDATE_IMPORT_ROW_STATUSES = ("created", "matched", "error")
CANDIDATE_IMPORT_BATCH_CHECKS = {"ck_candidate_import_batches_counts": "created_count + matched_count + error_count = total_rows"}
CANDIDATE_IMPORT_ROW_CHECKS = {
    "ck_candidate_import_rows_status": "status IN ('created', 'matched', 'error')",
    "ck_candidate_import_rows_outcome": "(status = 'error') = (candidate_id IS NULL) AND (status <> 'error' OR reason IS NOT NULL)",
}


class CandidateImportBatch(Base):
    """hrc-013 (I8/I9): one committed candidate file. Only its hash, name, source and counts are kept -- never the file. The
    Idempotency-Key is scoped to the uploader."""

    __tablename__ = "candidate_import_batches"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_IMPORT_BATCH_CHECKS.items()),
        UniqueConstraint("uploaded_by_user_id", "idempotency_key", name="uq_candidate_import_batches_key"),
        Index("ix_candidate_import_batches_uploader", "uploaded_by_user_id", "created_at"),
        Index("ix_candidate_import_batches_file", "uploaded_by_user_id", "file_sha256"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("rec_candidate_sources.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str] = mapped_column(String(200))
    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    matched_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CandidateImportRow(Base):
    """hrc-013 (I9): one row's outcome. No name, mobile or email: a created or matched row names its candidate (a match says why); an error row only its
    file row number and reason. hrc-034 reads the error rows as "failed imports"."""

    __tablename__ = "candidate_import_rows"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_IMPORT_ROW_CHECKS.items()),
        UniqueConstraint("batch_id", "row_number", name="uq_candidate_import_rows_row"),
        Index("ix_candidate_import_rows_candidate", "candidate_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidate_import_batches.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))
    candidate_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class RecFxRate(Base):
    """hrc-011 (DEC-SCOPE-375 C1, Q-10): the placement manager's manual exchange rate, rupees per one unit of the currency. INR is
    implicit (1) and never stored; no rate is seeded. Never deleted: a currency in use keeps its rate."""

    __tablename__ = "rec_fx_rates"
    __table_args__ = (CheckConstraint("inr_per_unit > 0 AND inr_per_unit <= 10000", name="ck_rec_fx_rates_rate"),)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    inr_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


# rec-014 (DEC-SCOPE-154): English stemming and stop words over the extracted text; scans ('') and unextracted (null) resumes are empty.
RESUME_SEARCH_VECTOR = "to_tsvector('english'::regconfig, coalesce(extracted_text, ''))"


class CandidateResume(Base):
    """rec-009 (AC4): one uploaded resume version, append-only. The current resume is the candidate's highest version."""

    __tablename__ = "candidate_resumes"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version", name="uq_candidate_resumes_version"),
        Index("ix_candidate_resumes_search", "search_vector", postgresql_using="gin"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id"))
    version: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(120))
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # rec-012 (DEC-SCOPE-150): the last extraction -- null until extracted, '' when the file had no text (a scan). Derived from the file,
    # so recomputable; rec-014 searches the text. Nothing here reaches the candidate until the recruiter applies it (AC2).
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # rec-014 (DEC-SCOPE-154, FT8): the resume search vector, generated by Postgres from the extracted text (migration 0137 repeats the
    # expression), so every extraction refreshes it. Never loaded into Python; candidate_search matches and ranks it in SQL.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(RESUME_SEARCH_VECTOR, persisted=True), nullable=True, deferred=True
    )
    # hrc-015 (DEC-SCOPE-379 D3): a DOC/DOCX's converted PDF rendition -- null for a PDF, which previews itself.
    preview_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    preview_key: Mapped[str | None] = mapped_column(String(300), nullable=True)


# hrc-015 (DEC-SCOPE-379 D3/D6/D7): migration 0255 repeats CANDIDATE_DOCUMENT_CHECKS (test_hrc_015_migration asserts they stay identical).
# Labels live in the web client.
CANDIDATE_PREVIEW_STATUSES = ("pending", "ready", "failed")
CANDIDATE_DOCUMENT_TYPES = ("certificate", "education", "experience_letter", "relieving_letter", "payslip", "id_proof", "other")
CANDIDATE_DOCUMENT_REQUEST_STATUSES = ("pending", "received", "cancelled")
CANDIDATE_DOCUMENT_CHECKS = {
    "ck_candidate_documents_type": f"document_type IN ({', '.join(repr(v) for v in CANDIDATE_DOCUMENT_TYPES)})",
    "ck_candidate_documents_preview": f"preview_status IS NULL OR preview_status IN ({', '.join(repr(v) for v in CANDIDATE_PREVIEW_STATUSES)})",
}
CANDIDATE_DOCUMENT_REQUEST_CHECKS = {
    "ck_candidate_document_requests_type": f"document_type IN ({', '.join(repr(v) for v in CANDIDATE_DOCUMENT_TYPES)})",
    "ck_candidate_document_requests_status": f"status IN ({', '.join(repr(v) for v in CANDIDATE_DOCUMENT_REQUEST_STATUSES)})",
}


class CandidateDocumentRequest(Base):
    """hrc-015 (D7): staff ask a candidate for one document type. Pending until the first upload against it (received) or a staff
    cancel. One pending request per type per candidate (partial unique index)."""

    __tablename__ = "candidate_document_requests"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_DOCUMENT_REQUEST_CHECKS.items()),
        Index("uq_candidate_document_requests_pending", "candidate_id", "document_type", unique=True, postgresql_where=text("status = 'pending'")),
        Index("ix_candidate_document_requests_candidate", "candidate_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id"))
    document_type: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class CandidateDocument(Base):
    """hrc-015 (D6): a certificate or other document of a candidate, append-only. `request_id` is the request it fulfilled (unique)."""

    __tablename__ = "candidate_documents"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_DOCUMENT_CHECKS.items()),
        UniqueConstraint("request_id", name="uq_candidate_documents_request"),
        Index("ix_candidate_documents_candidate", "candidate_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id"))
    document_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(120))
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    preview_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    preview_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    request_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidate_document_requests.id"), nullable=True)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# rec-010 (DEC-SCOPE-138): migration 0123 repeats CANDIDATE_CONSENT_CHECKS (test_rec_010_migration asserts they stay identical).
CANDIDATE_CONSENT_ACTIONS = ("opt_in", "opt_out")
CANDIDATE_CONSENT_CHECKS = {"ck_candidate_consents_action": f"action IN ({', '.join(repr(v) for v in CANDIDATE_CONSENT_ACTIONS)})"}
# hrc-035 (DEC-SCOPE-396 K1): where the record came from and the basis for holding it; migration 0273 repeats these checks.
CANDIDATE_CONSENT_SOURCES = ("student", "portal", "website", "manual", "import")
CANDIDATE_LAWFUL_BASES = ("consent", "provided_for_placement")
CANDIDATE_CONSENT_BASIS_CHECKS = {
    "ck_candidate_consents_source": _in("source", CANDIDATE_CONSENT_SOURCES),
    "ck_candidate_consents_basis": _in("lawful_basis", CANDIDATE_LAWFUL_BASES),
}


class CandidateConsent(Base):
    """rec-010 (AC4): one opt-in or opt-out of the placement candidate pool by the student themselves -- the ConsentRecord idiom,
    append-only. `candidates.opted_in` is the gate; this is its history and the consent evidence."""

    __tablename__ = "candidate_consents"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in (CANDIDATE_CONSENT_CHECKS | CANDIDATE_CONSENT_BASIS_CHECKS).items()),
        Index("ix_candidate_consents_candidate", "candidate_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"))
    # hrc-023 (DEC-SCOPE-389 W4): empty when the consent was given on the public website job application form (no login)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    action: Mapped[str] = mapped_column(String(10))
    consent_version: Mapped[str] = mapped_column(String(20))
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str | None] = mapped_column(String(10), nullable=True)  # hrc-035 K1
    lawful_basis: Mapped[str | None] = mapped_column(String(25), nullable=True)


# rec-011 (DEC-SCOPE-137): EVID-018 S2-§3 levels (SK1), the six S2-§17 skill sources and the three statuses. Migration 0122 repeats
# CANDIDATE_SKILL_CHECKS (test_rec_011_migration asserts they stay identical). Labels live in the web client.
CANDIDATE_SKILL_LEVELS = ("beginner", "intermediate", "advanced", "expert")
CANDIDATE_SKILL_SOURCES = ("resume", "interview_verified", "assessment_verified", "course_completed", "certification", "employer_verified")
CANDIDATE_SKILL_STATUSES = ("claimed", "verified", "assessed")
CANDIDATE_SKILL_CHECKS = {
    "ck_candidate_skills_level": f"level IN ({', '.join(repr(v) for v in CANDIDATE_SKILL_LEVELS)})",
    "ck_candidate_skills_source": f"source IN ({', '.join(repr(v) for v in CANDIDATE_SKILL_SOURCES)})",
    "ck_candidate_skills_status": f"status IN ({', '.join(repr(v) for v in CANDIDATE_SKILL_STATUSES)})",
    "ck_candidate_skills_verified": "(status = 'claimed') = (verified_at IS NULL) AND (verified_at IS NULL) = (verified_by_user_id IS NULL)",
    "ck_candidate_skills_experience": "experience_months IS NULL OR experience_months BETWEEN 0 AND 600",
    "ck_candidate_skills_last_used": "last_used_year IS NULL OR last_used_year >= 1950",
}


class CandidateSkill(Base, TimestampMixin):
    """rec-011: one skill on a candidate's profile -- its own row, so it is searchable (S2-§1). `status` changes only through the status
    route, which records who and when (AC3); `claimed` carries neither. A skill merge (SK7) re-points these rows before deleting a skill."""

    __tablename__ = "candidate_skills"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CANDIDATE_SKILL_CHECKS.items()),
        UniqueConstraint("candidate_id", "skill_id", name="uq_candidate_skills_skill"),
        Index("ix_candidate_skills_skill_candidate", "skill_id", "status", "candidate_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"))
    skill_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("skills.id", ondelete="RESTRICT"))
    level: Mapped[str] = mapped_column(String(16))
    experience_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_used_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="resume", server_default=text("'resume'"))
    status: Mapped[str] = mapped_column(String(12), default="claimed", server_default=text("'claimed'"))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))  # hrc-010 (P7): primary vs secondary
    verified_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    added_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


class ProgramSkill(Base):
    """rec-036 (DEC-SCOPE-179, CI1): a Skills Master skill a program teaches. A student holding the program's issued certificate gets it as
    a `course_completed` skill once opted in (services/course_skills). A skill merge re-points these rows (CI8)."""

    __tablename__ = "program_skills"
    __table_args__ = (Index("ix_program_skills_skill", "skill_id"),)
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True)
    added_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# rec-028 (DEC-SCOPE-134): EVID-018 §20 company meetings -- the 7 types in source order (L800-L812), the states (MT6) and the events of the
# append-only history. Migration 0119 repeats RECRUITER_MEETING_CHECKS (test_rec_028_migration asserts they stay identical). Labels live in
# the web client.
RECRUITER_MEETING_TYPES = (
    "company_meeting", "hr_meeting", "requirement_discussion", "recruitment_presentation", "contract_discussion",
    "campus_recruitment_discussion", "placement_drive_discussion",
)
RECRUITER_MEETING_STATUSES = ("scheduled", "completed", "cancelled")
RECRUITER_MEETING_EVENTS = ("scheduled", "rescheduled", "completed", "cancelled")
RECRUITER_MEETING_CODE_SEQ = Sequence("recruiter_meeting_code_seq", metadata=Base.metadata)
RECRUITER_MEETING_CHECKS = {
    "ck_recruiter_meetings_type": _in_list("meeting_type", RECRUITER_MEETING_TYPES),
    "ck_recruiter_meetings_mode": _in_list("mode", APPOINTMENT_MODES),
    "ck_recruiter_meetings_status": _in_list("status", RECRUITER_MEETING_STATUSES),
    "ck_recruiter_meetings_state": (
        "(status = 'completed') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL) "
        "AND (completed_at IS NULL) = (outcome IS NULL) AND (status = 'cancelled') = (cancelled_at IS NOT NULL) "
        "AND (cancelled_at IS NULL) = (cancel_reason IS NULL) AND (status = 'completed' OR (next_action IS NULL AND follow_up_id IS NULL))"
    ),
    "ck_recruiter_meeting_participants_one": "(contact_id IS NULL) <> (user_id IS NULL)",
    "ck_recruiter_meeting_events_event": _in_list("event", RECRUITER_MEETING_EVENTS),
}


def _meeting_checks(*names: str) -> tuple[CheckConstraint, ...]:
    return tuple(CheckConstraint(RECRUITER_MEETING_CHECKS[name], name=name) for name in names)


class RecruiterMeeting(Base, TimestampMixin):
    """rec-028 (DEC-SCOPE-134): a recruiter's meeting with a company (§20). It belongs to the company, like rec-024's follow-ups: whoever
    has the company in scope sees it. Never deleted: cancelled instead. The outcome's next action is a rec-024 follow-up (`follow_up_id`)."""

    __tablename__ = "recruiter_meetings"
    __table_args__ = (
        UniqueConstraint("meeting_code", name="uq_recruiter_meetings_code"),
        *_meeting_checks("ck_recruiter_meetings_type", "ck_recruiter_meetings_mode", "ck_recruiter_meetings_status", "ck_recruiter_meetings_state"),
        Index("ix_recruiter_meetings_company_starts", "company_id", "starts_at"),
        Index("ix_recruiter_meetings_status_starts", "status", "starts_at"),
        Index("ix_recruiter_meetings_contact", "contact_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    meeting_code: Mapped[str] = mapped_column(String(20))
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=True)
    meeting_type: Mapped[str] = mapped_column(String(40))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String(20))
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="scheduled", server_default=text("'scheduled'"))
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(500), nullable=True)
    follow_up_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("recruiter_follow_ups.id", ondelete="RESTRICT"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class RecruiterMeetingParticipant(Base):
    """rec-028 (MT5): one company contact or one recruiter per row; replaced as a set when the meeting is edited."""

    __tablename__ = "recruiter_meeting_participants"
    __table_args__ = (
        *_meeting_checks("ck_recruiter_meeting_participants_one"),
        UniqueConstraint("meeting_id", "contact_id", name="uq_recruiter_meeting_participants_contact"),
        UniqueConstraint("meeting_id", "user_id", name="uq_recruiter_meeting_participants_user"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    meeting_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("recruiter_meetings.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


class RecruiterMeetingEvent(Base):
    """rec-028 (MT6): one row per schedule, reschedule (old and new time), completion and cancellation. Append-only; `position` orders rows
    written in one transaction."""

    __tablename__ = "recruiter_meeting_events"
    __table_args__ = (
        *_meeting_checks("ck_recruiter_meeting_events_event"),
        Index("ix_recruiter_meeting_events_meeting", "meeting_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    meeting_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("recruiter_meetings.id", ondelete="RESTRICT"))
    event: Mapped[str] = mapped_column(String(16))
    old_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# rec-026 (DEC-SCOPE-135): the EVID-018 §19 message kinds (WhatsApp L766-L776, email L778-L792, source order) and the message rules;
# migration 0119 repeats them (test_rec_026_migration asserts they stay identical). Labels live in the web client.
REC_WHATSAPP_KINDS = ("candidate_profiles", "jd_confirmation", "interview_reminder", "follow_up", "requirement_update")
REC_EMAIL_KINDS = (
    "company_introduction", "recruitment_proposal", "candidate_profiles", "jd_acknowledgement", "interview_confirmation", "offer_follow_up",
    "joining_confirmation",
)
RECRUITER_TEMPLATE_CHECKS = {
    "ck_recruiter_message_templates_channel": "channel IN ('whatsapp', 'email')",
    "ck_recruiter_message_templates_kind": (
        f"(channel = 'whatsapp' AND kind IN ({', '.join(repr(k) for k in REC_WHATSAPP_KINDS)})) OR "
        f"(channel = 'email' AND kind IN ({', '.join(repr(k) for k in REC_EMAIL_KINDS)}))"
    ),
    "ck_recruiter_message_templates_subject": "(channel = 'email') = (subject IS NOT NULL)",
}
RECRUITER_MESSAGE_CHECKS = {
    "ck_recruiter_messages_party": "(contact_id IS NULL) = (company_id IS NULL) AND (contact_id IS NULL) <> (candidate_id IS NULL)",
    "ck_recruiter_messages_channel": "channel IN ('whatsapp', 'email')",
    "ck_recruiter_messages_email": "(channel = 'email') = (delivery_status IS NOT NULL) AND (channel = 'email') = (subject IS NOT NULL)",
    "ck_recruiter_messages_status": "delivery_status IS NULL OR delivery_status IN ('queued', 'sending', 'retrying', 'sent', 'failed')",
}


class RecruiterMessageTemplate(Base, TimestampMixin):
    """rec-026 (MS1-MS3): a WhatsApp or email template of the placement manager's global library. Only email has a subject; placeholders
    are checked on save; a name is unique per channel (case-insensitive). Never deleted, only deactivated."""

    __tablename__ = "recruiter_message_templates"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in RECRUITER_TEMPLATE_CHECKS.items()),
        Index("uq_recruiter_message_templates_channel_name", "channel", text("lower(name)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    channel: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class RecruiterMessage(Base, TimestampMixin):
    """rec-026 (MS4-MS9): a message to one company contact (with its company, for scope) or one candidate -- WhatsApp via wa.me (the row is
    the recruiter's confirmation) or email (queued for the worker; `attempt_count` counts SMTP attempts). Permanent: never edited or
    deleted. `template_name` is the name when sent, so a rename never rewrites history."""

    __tablename__ = "recruiter_messages"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in RECRUITER_MESSAGE_CHECKS.items()),
        Index("ix_recruiter_messages_company_sent", "company_id", "sent_at"),
        Index("ix_recruiter_messages_contact_sent", "contact_id", "sent_at"),
        Index("ix_recruiter_messages_candidate_sent", "candidate_id", "sent_at"),
        Index("ix_recruiter_messages_sender_sent", "sender_user_id", "sent_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True)
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=True)
    candidate_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=True)
    sender_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    channel: Mapped[str] = mapped_column(String(16))
    template_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("recruiter_message_templates.id", ondelete="RESTRICT"), nullable=True)
    template_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# upc-026 (DEC-SCOPE-139, spec §2): the §28 document centre. The 12 kinds in source order (DC1); the commission agreement is never
# shareable (DC2). Migration 0123 repeats the checks; test_upc_026_migration keeps them identical.
UNIVERSITY_DOCUMENT_KINDS = (
    "mou", "partnership_agreement", "commission_agreement", "brochure", "course_list", "fee_structure", "entry_requirements",
    "scholarship_information", "marketing_materials", "application_guidelines", "contact_documents", "training_documents",
)  # fmt: skip
UNIVERSITY_DOCUMENT_CHECKS = {
    "ck_university_documents_kind": _one_of("kind", UNIVERSITY_DOCUMENT_KINDS, nullable=False),
    "ck_university_documents_commission_internal": "kind <> 'commission_agreement' OR NOT shareable",
    "ck_university_documents_current_version": "current_version >= 1",
}
UNIVERSITY_DOCUMENT_VERSION_CHECKS = {
    "ck_university_document_versions_version": "version >= 1",
    "ck_university_document_versions_size": "size_bytes > 0",
}


class UniversityDocument(Base, TimestampMixin):
    """upc-026 (§28): one document of a university -- kind, title and who may see it. Its files are append-only versions (DC6); the title
    is unique per university and kind (DC11). `updated_at` moves on every new version, for the menu list's order."""

    __tablename__ = "university_documents"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_DOCUMENT_CHECKS.items()),
        Index("uq_university_documents_title", "university_id", "kind", text("lower(title)"), unique=True),
        Index("ix_university_documents_updated", "updated_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    shareable: Mapped[bool] = mapped_column(Boolean)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class UniversityDocumentVersion(Base):
    """upc-026 DC6: one stored file of a document, never changed or deleted. The key is server-generated (DC14)."""

    __tablename__ = "university_document_versions"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_DOCUMENT_VERSION_CHECKS.items()),
        UniqueConstraint("document_id", "version", name="uq_university_document_versions_version"),
        UniqueConstraint("storage_key", name="uq_university_document_versions_key"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_documents.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300))
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# upc-014 (DEC-SCOPE-142, spec §2): §13 MoU / agreement management. Types = the document centre's agreement kinds (AG2); the stored
# statuses of §13's flow (AG4: Expiring and Expired are derived from the expiry date, never stored). Migration 0127 repeats these;
# test_upc_014_migration keeps them identical. MOU-000123 numbers (AG1): a rolled-back create skips a number.
UNIVERSITY_AGREEMENT_TYPES = ("mou", "partnership_agreement", "commission_agreement")
UNIVERSITY_AGREEMENT_STATUSES = ("draft", "sent", "under_review", "negotiation", "approved", "signed", "active", "renewed")
UNIVERSITY_AGREEMENT_EXCLUSIVITY = ("exclusive", "non_exclusive")
UNIVERSITY_AGREEMENT_EVENT_KINDS = ("create", "update", "status", "renew")
UNIVERSITY_AGREEMENT_CHECKS = {
    "ck_university_agreements_type": _one_of("agreement_type", UNIVERSITY_AGREEMENT_TYPES, nullable=False),
    "ck_university_agreements_status": _one_of("status", UNIVERSITY_AGREEMENT_STATUSES, nullable=False),
    "ck_university_agreements_exclusivity": _one_of("exclusivity", UNIVERSITY_AGREEMENT_EXCLUSIVITY, nullable=False),
    "ck_university_agreements_dates": "expiry_date > start_date",
    "ck_university_agreements_renewal_window": "renewal_date IS NULL OR (renewal_date >= start_date AND renewal_date <= expiry_date)",
    "ck_university_agreements_signed_complete": (
        "status NOT IN ('signed', 'active', 'renewed') OR (document_id IS NOT NULL AND edusphere_signatory_user_id IS NOT NULL AND "
        "edusphere_signed_on IS NOT NULL AND university_signatory_name IS NOT NULL AND university_signed_on IS NOT NULL)"
    ),
}
UNIVERSITY_AGREEMENT_MOU_SEQ = Sequence("university_agreement_mou_seq", metadata=Base.metadata)


class UniversityAgreement(Base, TimestampMixin):
    """upc-014 (§13): one agreement with one university -- the 17 tracked fields (AG3; commission is upc-016's). A renewal is a new row
    pointing at the one it renews (AG8, at most one successor). Rules live in `services/university_agreements.py`; the CHECKs are the
    backstop (AC2: a signed row carries its document and both signatories)."""

    __tablename__ = "university_agreements"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_AGREEMENT_CHECKS.items()),
        UniqueConstraint("mou_number", name="uq_university_agreements_mou_number"),
        Index("uq_university_agreements_previous", "previous_agreement_id", unique=True, postgresql_where=text("previous_agreement_id IS NOT NULL")),
        Index("ix_university_agreements_university", "university_id", "created_at"),
        Index("ix_university_agreements_expiry", "status", "expiry_date"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    mou_number: Mapped[str] = mapped_column(String(20))
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    agreement_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    start_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    renewal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    commercial_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusivity: Mapped[str] = mapped_column(String(20))
    territory: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recruitment_rights: Mapped[str | None] = mapped_column(Text, nullable=True)
    all_courses: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    course_ids: Mapped[list] = mapped_column(JSON, default=list)
    country_ids: Mapped[list] = mapped_column(JSON, default=list)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    marketing_rights: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_documents.id", ondelete="RESTRICT"), nullable=True)
    edusphere_signatory_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    edusphere_signed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    university_signatory_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    university_signed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_agreement_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_agreements.id", ondelete="RESTRICT"), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class UniversityAgreementEvent(Base):
    """upc-014: one row per agreement write, append-only -- create, edit (`changed` = field names), a status move (with its note) and a
    renewal. Ordered by `position`."""

    __tablename__ = "university_agreement_events"
    __table_args__ = (
        CheckConstraint(_in_list("kind", UNIVERSITY_AGREEMENT_EVENT_KINDS), name="ck_university_agreement_events_kind"),
        Index("ix_university_agreement_events_agreement", "agreement_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agreement_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_agreements.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(10))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed: Mapped[list] = mapped_column(JSON, default=list)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# upc-016 (DEC-SCOPE-144, spec §2): §15 commercial / commission terms -- what a university pays EduSphere under one agreement, optionally
# for some programmes / student countries (CM5). RESTRICTED (U2): only `partnership_access.COMMISSION_ROLES` ever see a row. Exactly one
# rate per term, % or fixed (CM2); the currency list is the project's (CM3); the triggers answer Q-19 (CM1). Migration 0128 repeats
# these; test_upc_016_migration keeps them identical.
COMMISSION_TRIGGERS = ("enrolment", "visa_and_enrolment", "tuition_paid")
COMMISSION_CURRENCIES = COUNSELING_CURRENCIES
COMMISSION_TERM_CHECKS = {
    "ck_university_commission_terms_one_rate": "(commission_percent IS NULL) <> (fixed_amount IS NULL)",
    "ck_university_commission_terms_percent": "commission_percent IS NULL OR (commission_percent > 0 AND commission_percent <= 100)",
    "ck_university_commission_terms_fixed": "fixed_amount IS NULL OR fixed_amount > 0",
    "ck_university_commission_terms_currency": _in_list("currency", COMMISSION_CURRENCIES),
    "ck_university_commission_terms_trigger": _in_list("trigger", COMMISSION_TRIGGERS),
}


class UniversityCommissionTerm(Base, TimestampMixin):
    """upc-016 (§15): one commission term of an agreement -- the 9 terms. Empty `course_ids` = every programme, empty `country_ids` = every
    student country. Rules live in `services/university_commission.py`; the CHECKs are the backstop."""

    __tablename__ = "university_commission_terms"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in COMMISSION_TERM_CHECKS.items()),
        Index("ix_university_commission_terms_agreement", "agreement_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agreement_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("university_agreements.id", ondelete="RESTRICT"))
    commission_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    fixed_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_ids: Mapped[list] = mapped_column(JSON, default=list)
    country_ids: Mapped[list] = mapped_column(JSON, default=list)
    payment_timeline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trigger: Mapped[str] = mapped_column(String(30))
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# upc-019 (DEC-SCOPE-165, spec §2): commission a university actually paid EduSphere, recorded by hand until a Finance module is decided
# (U4, Q-20 CL10: a lump sum per university, optionally linked to enrolled applications). RESTRICTED (U2). Migration 0143 repeats these;
# test_upc_019_migration keeps them identical.
COMMISSION_RECEIPT_CHECKS = {
    "ck_university_commission_receipts_amount": "amount > 0",
    "ck_university_commission_receipts_currency": _in_list("currency", COMMISSION_CURRENCIES),
    "ck_university_commission_receipts_note": "note IS NULL OR char_length(note) <= 500",
}


class UniversityCommissionReceipt(Base, TimestampMixin):
    """upc-019: one commission receipt from a university. Never edited; a mistaken row is removed (audited) and re-entered (CL12). Rules
    live in `services/university_commission.py`; the CHECKs and the per-university reference index are the backstop."""

    __tablename__ = "university_commission_receipts"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in COMMISSION_RECEIPT_CHECKS.items()),
        Index("ix_university_commission_receipts_university", "university_id", "received_on"),
        Index("uq_university_commission_receipts_reference", "university_id", text("lower(reference)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    received_on: Mapped[date] = mapped_column(Date)
    reference: Mapped[str] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_ids: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# upc-021 (DEC-SCOPE-146, spec §3): monthly partnership targets. Migration 0131 repeats these strings; test_upc_021_migration asserts they
# stay identical.
PARTNERSHIP_TARGET_CHECKS = {
    "ck_partnership_targets_month_start": "EXTRACT(DAY FROM month) = 1",
    "ck_partnership_targets_kpi": _one_of("kpi_key", PARTNERSHIP_TARGET_KPI_KEYS, nullable=False),
    "ck_partnership_targets_target_range": f"target >= 0 AND target <= {PARTNERSHIP_TARGET_MAX}",
}


class PartnershipTarget(Base, TimestampMixin):
    """upc-021 (DEC-SCOPE-146): a head-set monthly target for one §21 KPI of one partnership manager. `month` is the month's first day.
    Actuals are never stored: `services/partnership_metrics.target_actuals` derives them from append-only history (TG9). Clearing a target
    deletes the row; every change is in the audit log (Q-23: history kept)."""

    __tablename__ = "partnership_targets"
    __table_args__ = (
        UniqueConstraint("manager_user_id", "month", "kpi_key", name="uq_partnership_targets_manager_month_kpi"),
        *(CheckConstraint(sql, name=name) for name, sql in PARTNERSHIP_TARGET_CHECKS.items()),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    manager_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    month: Mapped[date] = mapped_column(Date)
    kpi_key: Mapped[str] = mapped_column(String(40))
    target: Mapped[int] = mapped_column(Integer)
    set_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# rec-030 (DEC-SCOPE-156, spec §2): recruiter contracts / MoU (EVID-018 §22), the bdm-005 MoU pattern. The six stored statuses in source
# order; Expired (CT2) is derived from end_date and never stored. Migration 0139 repeats these (test_rec_030_migration pins them).
RECRUITER_CONTRACT_STATUSES = ("discussion", "proposal_sent", "negotiation", "contract_sent", "signed", "active")
RECRUITER_CONTRACT_EXPIRING = ("signed", "active")
RECRUITER_CONTRACT_FEE_BASES = ("fixed", "percent_of_ctc")
RECRUITER_CONTRACT_EVENT_KINDS = ("created", "status", "updated", "document", "renewed")
RECRUITER_CONTRACT_CHECKS = {
    "ck_recruiter_contracts_status": _in_list("status", RECRUITER_CONTRACT_STATUSES),
    "ck_recruiter_contracts_window": "start_date IS NULL OR end_date IS NULL OR end_date >= start_date",
    "ck_recruiter_contracts_fee_pair": "(fee_basis IS NULL) = (fee_value IS NULL)",
    "ck_recruiter_contracts_fee_basis": "fee_basis IS NULL OR " + _in_list("fee_basis", RECRUITER_CONTRACT_FEE_BASES),
    "ck_recruiter_contracts_fee_value": "fee_value IS NULL OR (fee_value >= 0 AND (fee_basis <> 'percent_of_ctc' OR fee_value <= 100))",
    "ck_recruiter_contracts_signed_document": "status NOT IN ('signed', 'active') OR contract_document_key IS NOT NULL",
    "ck_recruiter_contracts_active_window": "status <> 'active' OR (start_date IS NOT NULL AND end_date IS NOT NULL)",
    "ck_recruiter_contracts_contract_document": "(contract_document_key IS NULL) = (contract_document_content_type IS NULL)",
    "ck_recruiter_contracts_mou_document": "(mou_document_key IS NULL) = (mou_document_content_type IS NULL)",
}


class RecruiterContract(Base, TimestampMixin):
    """rec-030: a company's contract. At most one `is_current` row per company (CT7: a renewal is a new row; the old one is kept). The
    document keys are server-generated and never returned or logged; the service owns every rule, the CHECKs are the backstop."""

    __tablename__ = "recruiter_contracts"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in RECRUITER_CONTRACT_CHECKS.items()),
        Index("uq_recruiter_contracts_current", "company_id", unique=True, postgresql_where=text("is_current")),
        Index("ix_recruiter_contracts_company", "company_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="discussion", server_default="discussion")
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    agreement_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fee_basis: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fee_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    replacement_policy: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    contract_document_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contract_document_content_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contract_document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contract_document_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mou_document_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mou_document_content_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mou_document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mou_document_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class RecruiterContractEvent(Base):
    """rec-030: one row per contract write, append-only. `from_status` / `to_status` are effective statuses; `changed` lists field names
    only. `document_key` is the replaced object's key on a `document` row; it is never returned."""

    __tablename__ = "recruiter_contract_events"
    __table_args__ = (
        CheckConstraint(_in_list("kind", RECRUITER_CONTRACT_EVENT_KINDS), name="ck_recruiter_contract_events_kind"),
        Index("ix_recruiter_contract_events_contract", "contract_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    contract_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("recruiter_contracts.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(10))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    changed: Mapped[list] = mapped_column(JSON, default=list)
    document_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


TALENT_POOL_EXPERIENCE_CHECK = (
    "(experience_min_months IS NULL OR experience_min_months BETWEEN 0 AND 600) "
    "AND (experience_max_months IS NULL OR experience_max_months BETWEEN 0 AND 600) "
    "AND (experience_min_months IS NULL OR experience_max_months IS NULL OR experience_min_months <= experience_max_months)"
)


class TalentPool(Base, TimestampMixin):
    """rec-015 (DEC-SCOPE-159): a manager-defined pool. Its rule is a rec-013 expression -- `all_terms` (skill names, AND), `any_terms`
    (lists of skill names, each at least one of) -- plus an experience band. Membership is computed on read (P1); nothing is copied.
    `created_by_user_id` is null for the seeded examples (P3)."""

    __tablename__ = "talent_pools"
    __table_args__ = (
        CheckConstraint(TALENT_POOL_EXPERIENCE_CHECK, name="ck_talent_pools_experience"),
        Index("uq_talent_pools_name", text("lower(name)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80))
    all_terms: Mapped[list] = mapped_column(JSON, default=list)
    any_terms: Mapped[list] = mapped_column(JSON, default=list)
    experience_min_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience_max_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

# rec-019 (DEC-SCOPE-160, spec §2): profile sharing (EVID-018 §11). One share is one requirement, one company and one channel; each item is
# one candidate with the company's response. Email / WhatsApp shares point at their `recruiter_messages` row and carry a contact; Portal /
# Other have no message. Migration 0142 repeats these (test_rec_019_migration pins them).
PROFILE_SHARE_CHANNELS = ("email", "whatsapp", "portal", "other")
PROFILE_SHARE_RESPONSES = ("pending", "interested", "not_interested", "interview_requested")
PROFILE_SHARE_CHECKS = {
    "ck_profile_shares_channel": _in_list("channel", PROFILE_SHARE_CHANNELS),
    "ck_profile_shares_message": "(channel IN ('email', 'whatsapp')) = (message_id IS NOT NULL) AND (channel NOT IN ('email', 'whatsapp') OR contact_id IS NOT NULL)",
    "ck_profile_shares_note": "note IS NULL OR char_length(note) <= 500",
}
PROFILE_SHARE_ITEM_CHECKS = {
    "ck_profile_share_items_response": _in_list("response", PROFILE_SHARE_RESPONSES),
    "ck_profile_share_items_token": "(token_hash IS NULL) = (token_expires_at IS NULL)",
    "ck_profile_share_items_feedback": "feedback IS NULL OR char_length(feedback) <= 1000",
}


class ProfileShare(Base, TimestampMixin):
    """rec-019: one share of 1-20 candidates for one requirement, to its company over one channel. Permanent: never edited or deleted (S13).
    `note` is the recruiter side's own remark and is never sent."""

    __tablename__ = "profile_shares"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in PROFILE_SHARE_CHECKS.items()),
        Index("ix_profile_shares_job", "job_id", "created_at"),
        Index("ix_profile_shares_company", "company_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="RESTRICT"))
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=True)
    channel: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("recruiter_messages.id", ondelete="RESTRICT"), nullable=True)
    shared_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class ProfileShareItem(Base, TimestampMixin):
    """rec-019: one candidate of a share. `resume_id` is the version current at share time; `token_hash` is the SHA-256 of the resume
    link's random token (the token itself is never stored or logged, S7). The response is the company's, recorded by the recruiter or, on a
    Portal share, by an employer user (S9)."""

    __tablename__ = "profile_share_items"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in PROFILE_SHARE_ITEM_CHECKS.items()),
        UniqueConstraint("share_id", "candidate_id", name="uq_profile_share_items_candidate"),
        Index("ix_profile_share_items_candidate", "candidate_id"),
        Index("uq_profile_share_items_token", "token_hash", unique=True, postgresql_where=text("token_hash IS NOT NULL")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    share_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profile_shares.id", ondelete="RESTRICT"))
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"))
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_applications.id", ondelete="RESTRICT"))
    resume_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("candidate_resumes.id", ondelete="RESTRICT"), nullable=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response: Mapped[str] = mapped_column(String(24), default="pending", server_default="pending")
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# rec-031 (DEC-SCOPE-176, RV6-RV8): manually recorded invoices and payments per requirement (track only, R9). Migration 0147 repeats
# these strings (test_rec_031_migration). services/recruiter_revenue.py owns every rule; the CHECKs are the backstop.
RECRUITER_INVOICE_CHECKS = {
    "ck_recruiter_invoices_amount": "amount > 0",
    "ck_recruiter_invoices_due": "due_date >= invoice_date",
    "ck_recruiter_invoices_cancel": "(cancelled_at IS NULL) = (cancelled_by_user_id IS NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)",
}
RECRUITER_PAYMENT_CHECKS = {"ck_recruiter_payments_amount": "amount > 0"}


class RecruiterInvoice(Base, TimestampMixin):
    """rec-031: an invoice EduSphere issued for a requirement, recorded by hand (no PDF, no GST). Never edited or deleted (RV8): a mistake is
    cancelled with a reason, and its number stays used (the unique index ignores case and cancellation)."""

    __tablename__ = "recruiter_invoices"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in RECRUITER_INVOICE_CHECKS.items()),
        Index("uq_recruiter_invoices_number", text("lower(invoice_number)"), unique=True),
        Index("ix_recruiter_invoices_job", "job_id", "invoice_date"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="RESTRICT"))
    invoice_number: Mapped[str] = mapped_column(String(40))
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class RecruiterPayment(Base):
    """rec-031 (RV7): money received against an invoice. Append-only; the received total never exceeds the invoice amount."""

    __tablename__ = "recruiter_payments"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in RECRUITER_PAYMENT_CHECKS.items()),
        Index("ix_recruiter_payments_invoice", "invoice_id", "received_on"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("recruiter_invoices.id", ondelete="RESTRICT"))
    received_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

# rec-029 (DEC-SCOPE-178, DR1-DR7): campus recruitment drives (§21). Migration 0148 repeats the statuses and checks
# (test_rec_029_migration). Labels live in services/recruitment_drives.py and the web client.
RECRUITMENT_DRIVE_STATUSES = ("planned", "completed", "cancelled")
RECRUITMENT_DRIVE_CODE_SEQ = Sequence("recruitment_drive_code_seq", metadata=Base.metadata)
RECRUITMENT_DRIVE_CHECKS = {
    "ck_recruitment_drives_status": _in_list("status", RECRUITMENT_DRIVE_STATUSES),
    "ck_recruitment_drives_college": "(college_org_id IS NULL) <> (college_name IS NULL)",
    "ck_recruitment_drives_counts": "students_registered >= 0 AND students_attended >= 0",
    "ck_recruitment_drives_attended": "students_attended <= students_registered",
    "ck_recruitment_drives_vacancies": "vacancies >= 1",
}


class RecruitmentDrive(Base, TimestampMixin):
    """rec-029 (DEC-SCOPE-178): a campus drive of one company at one college -- a BDM college organisation or a typed name (R15, DR2).
    Registered and attended are typed counts; shortlisted to joined are computed from the applications tagged with the drive (DR7).
    Never deleted: cancelled instead (DR3)."""

    __tablename__ = "recruitment_drives"
    __table_args__ = (
        UniqueConstraint("drive_code", name="uq_recruitment_drives_code"),
        *(CheckConstraint(sql, name=name) for name, sql in RECRUITMENT_DRIVE_CHECKS.items()),
        Index("ix_recruitment_drives_company_date", "company_id", "drive_date"),
        Index("ix_recruitment_drives_date", "drive_date"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    drive_code: Mapped[str] = mapped_column(String(20))
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"))
    college_org_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=True)
    college_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    drive_date: Mapped[date] = mapped_column(Date)
    job_role: Mapped[str] = mapped_column(String(150))
    vacancies: Mapped[int] = mapped_column(Integer)
    eligibility: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    students_registered: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    students_attended: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), default="planned", server_default=text("'planned'"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class DriveRequirement(Base):
    """rec-029 (DR4): the requirements a drive recruits for -- each a requirement of the drive's company."""

    __tablename__ = "drive_requirements"
    __table_args__ = (Index("ix_drive_requirements_job", "job_id"),)
    drive_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("recruitment_drives.id", ondelete="RESTRICT"), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="RESTRICT"), primary_key=True)


# mgmt-004 (management ledger, spec ML1-ML16): manual income and expense entries, their categories and their history. Rules live in
# `services/ledger.py`; only approved entries count in the money figures (ML10).
LEDGER_KINDS = ("income", "expense")
LEDGER_NATURES = ("fixed", "variable")
LEDGER_VERTICALS = ("abroad", "it", "recruitment", "school", "other", "shared")
LEDGER_STATUSES = ("draft", "submitted", "approved", "rejected")
LEDGER_EVENTS = ("created", "updated", "submitted", "approved", "rejected", "reversed", "receipt")


class LedgerCategory(Base, TimestampMixin):
    """ML1/ML2: the managed category list. Kind and nature are fixed once created; a deactivated category keeps its entries (ML3)."""

    __tablename__ = "ledger_categories"
    __table_args__ = (
        CheckConstraint(_in_list("kind", LEDGER_KINDS), name="ck_ledger_categories_kind"),
        CheckConstraint("(kind = 'expense' AND nature IN ('fixed', 'variable')) OR (kind = 'income' AND nature IS NULL)", name="ck_ledger_categories_nature"),
        Index("uq_ledger_categories_kind_name", "kind", func.lower(text("name")), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(10))
    nature: Mapped[str | None] = mapped_column(String(10), nullable=True)
    name: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


class LedgerEntry(Base, TimestampMixin):
    """ML4-ML13: one manual income or expense line, INR only. A reversal (ML11) points at the approved entry it cancels and counts as
    the negative of its amount."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint(_in_list("kind", LEDGER_KINDS), name="ck_ledger_entries_kind"),
        CheckConstraint(_in_list("vertical", LEDGER_VERTICALS), name="ck_ledger_entries_vertical"),
        CheckConstraint(_in_list("status", LEDGER_STATUSES), name="ck_ledger_entries_status"),
        CheckConstraint("amount > 0", name="ck_ledger_entries_amount"),
        CheckConstraint(f"channel IS NULL OR (kind = 'expense' AND channel IN ({', '.join(repr(s) for s in TEL_SOURCES)}))", name="ck_ledger_entries_channel"),
        Index("ix_ledger_entries_date", "entry_date"),
        Index("ix_ledger_entries_category_date", "category_id", "entry_date"),
        Index("ix_ledger_entries_vertical_date", "vertical", "entry_date"),
        Index("ix_ledger_entries_status", "status"),
        Index("uq_ledger_entries_live_reversal", "reversal_of_id", unique=True, postgresql_where=text("status <> 'rejected'")),
        CheckConstraint(LEDGER_SCHOOL_CHECK, name="ck_ledger_entries_school"),
        Index("ix_ledger_entries_school_date", "school_id", "entry_date", postgresql_where=text("school_id IS NOT NULL")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entry_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(10))
    category_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ledger_categories.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    description: Mapped[str] = mapped_column(String(500))
    vertical: Mapped[str] = mapped_column(String(12))
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)
    program_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("programs.id", ondelete="RESTRICT"), nullable=True)
    batch_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id", ondelete="RESTRICT"), nullable=True)
    school_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id", ondelete="RESTRICT"), nullable=True)  # mgmt-022 SD14
    status: Mapped[str] = mapped_column(String(10), default="draft", server_default=text("'draft'"))
    reversal_of_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("ledger_entries.id", ondelete="RESTRICT"), nullable=True)
    receipt_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    receipt_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class LedgerEntryEvent(Base):
    """ML14: an entry's history, one row per write. `receipt_key` keeps a replaced receipt's key (never returned)."""

    __tablename__ = "ledger_entry_events"
    __table_args__ = (
        CheckConstraint(_in_list("event", LEDGER_EVENTS), name="ck_ledger_entry_events_event"),
        Index("ix_ledger_entry_events_entry", "entry_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entry_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ledger_entries.id", ondelete="CASCADE"))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    event: Mapped[str] = mapped_column(String(10))
    from_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fields: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# mgmt-014 (DEC-SCOPE-190, spec MI1-MI6): EVID-017 §23's investment register. Partner-only (M13); ROI is computed, never stored.
# Migration 0151 repeats the CHECKs (test_mgmt_014_migration keeps them identical). INV-000123 codes: a rolled-back create skips a number.
INVESTMENT_STATUSES = ("planned", "active", "completed", "cancelled")
INVESTMENT_VERTICALS = ("abroad", "it", "recruitment", "school", "shared", "other")
INVESTMENT_CHECKS = {
    "ck_investments_status": _one_of("status", INVESTMENT_STATUSES, nullable=False),
    "ck_investments_vertical": _one_of("vertical", INVESTMENT_VERTICALS, nullable=False),
    "ck_investments_investor": "(investor_kind = 'company' AND investor_user_id IS NULL) OR (investor_kind = 'partner' AND investor_user_id IS NOT NULL)",
    "ck_investments_amount": "amount > 0",
    "ck_investments_returns": "(expected_return IS NULL OR expected_return >= 0) AND (actual_return IS NULL OR actual_return >= 0)",
}
INVESTMENT_CODE_SEQ = Sequence("investment_code_seq", metadata=Base.metadata)


class Investment(Base, TimestampMixin):
    """mgmt-014 (§23): money EduSphere invested and what it returned. Never deleted: a mistake is set to `cancelled`. Rules live in
    `services/investments.py`; every write is audited as `mgmt.investment` (mgmt-002)."""

    __tablename__ = "investments"
    __table_args__ = (
        UniqueConstraint("code", name="uq_investments_code"),
        *(CheckConstraint(sql, name=name) for name, sql in INVESTMENT_CHECKS.items()),
        Index("ix_investments_invested_on", "invested_on"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20))
    invested_on: Mapped[date] = mapped_column(Date)
    investor_kind: Mapped[str] = mapped_column(String(10))
    investor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    purpose: Mapped[str] = mapped_column(String(200))
    vertical: Mapped[str] = mapped_column(String(16))
    expected_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    actual_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default=text("'active'"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# mgmt-015 (spec CP1-CP15): EVID-017 §24's partner capital accounts. Partner-only (M13); every figure is computed, never stored. Migration
# 0159 repeats the CHECKs (test_mgmt_015_migration keeps them identical).
CAPITAL_ENTRY_KINDS = ("initial", "additional", "withdrawal", "profit_distribution")
CAPITAL_ENTRY_CHECKS = {
    "ck_partner_capital_entries_kind": _one_of("kind", CAPITAL_ENTRY_KINDS, nullable=False),
    "ck_partner_capital_entries_amount": "amount > 0",
}
PARTNER_SHARE_CHECKS = {
    "ck_partner_shares_month": "EXTRACT(DAY FROM effective_from) = 1",
    "ck_partner_shares_share_pct": "share_pct >= 0 AND share_pct <= 100",
    "ck_partner_shares_commitment": "commitment IS NULL OR commitment >= 0",
}


class PartnerCapitalEntry(Base):
    """mgmt-015 (CP2-CP4): one capital movement of a partner. Never edited or deleted: a mistake gets an opposing entry with a note."""

    __tablename__ = "partner_capital_entries"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in CAPITAL_ENTRY_CHECKS.items()),
        Index("ix_partner_capital_entries_partner_date", "partner_user_id", "entry_date"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    partner_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    entry_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PartnerShare(Base, TimestampMixin):
    """mgmt-015 (CP5): a partner's profit share % and capital commitment from the first day of a month; the rows are the history."""

    __tablename__ = "partner_shares"
    __table_args__ = (
        UniqueConstraint("partner_user_id", "effective_from", name="uq_partner_shares_partner_month"),
        *(CheckConstraint(sql, name=name) for name, sql in PARTNER_SHARE_CHECKS.items()),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    partner_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    effective_from: Mapped[date] = mapped_column(Date)
    share_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    commitment: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# mgmt-011 (salary management, spec SM1-SM14): EVID-017 §9 as department totals per month (M6), never per person. Finance tier only
# (M13). Rules live in `services/salaries.py`; migration 0153 repeats the CHECKs (test_mgmt_011_migration keeps them identical).
SALARY_MONEY = ("payable", "paid", "incentives", "commissions", "employer_cost")
SALARY_CHECKS = {
    "ck_salary_month_totals_month": "EXTRACT(DAY FROM month) = 1",
    "ck_salary_month_totals_headcount": "headcount >= 0",
    "ck_salary_month_totals_money": " AND ".join(f"{c} >= 0" for c in SALARY_MONEY),
}


class Department(Base, TimestampMixin):
    """SM1/SM2: the managed department list. A deactivated department keeps its months."""

    __tablename__ = "departments"
    __table_args__ = (Index("uq_departments_name", func.lower(text("name")), unique=True),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


class SalaryMonthTotal(Base, TimestampMixin):
    """SM3: one department's salary totals for one month (`month` is its 1st day), in rupees."""

    __tablename__ = "salary_month_totals"
    __table_args__ = (
        UniqueConstraint("month", "department_id", name="uq_salary_month_totals_month_department"),
        *(CheckConstraint(sql, name=name) for name, sql in SALARY_CHECKS.items()),
        Index("ix_salary_month_totals_month", "month"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    month: Mapped[date] = mapped_column(Date)
    department_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"))
    headcount: Mapped[int] = mapped_column(Integer)
    payable: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    paid: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    incentives: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    commissions: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    employer_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# mgmt-027 (management discussions & decisions, spec MD1-MD14): EVID-017 §27. Rules live in `services/management_discussions.py`; the
# responsible person sees only the decision line (MD8/MD14).
DISCUSSION_STATUSES = ("open", "in_progress", "completed", "cancelled")


class ManagementDiscussion(Base, TimestampMixin):
    """MD1/MD5: one discussion and at most one decision. A responsible person needs a decision (CHECK)."""

    __tablename__ = "management_discussions"
    __table_args__ = (
        CheckConstraint(_in_list("status", DISCUSSION_STATUSES), name="ck_management_discussions_status"),
        CheckConstraint("responsible_user_id IS NULL OR decision IS NOT NULL", name="ck_management_discussions_responsible_decision"),
        Index("ix_management_discussions_date", "discussion_date"),
        Index("ix_management_discussions_responsible_status", "responsible_user_id", "status"),
        Index("ix_management_discussions_status_deadline", "status", "deadline"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    topic: Mapped[str] = mapped_column(String(200))
    discussion_date: Mapped[date] = mapped_column(Date)
    department: Mapped[str | None] = mapped_column(String(80), nullable=True)
    points: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(500), nullable=True)
    responsible_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="open", server_default=text("'open'"))
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # mgmt-029 (MM8): the meeting whose minutes produced this decision; null for a discussion recorded on its own.
    meeting_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("management_meetings.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class ManagementDiscussionParticipant(Base):
    """MD2: staff users only; replaced as a whole on edit."""

    __tablename__ = "management_discussion_participants"
    discussion_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("management_discussions.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)


class ManagementDiscussionAttachment(Base):
    """MD10: a stored file; only `shareable` ones reach the responsible person. The key is server-generated and never returned."""

    __tablename__ = "management_discussion_attachments"
    __table_args__ = (Index("ix_management_discussion_attachments_discussion", "discussion_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    discussion_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("management_discussions.id", ondelete="CASCADE"))
    storage_key: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shareable: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# mgmt-028 (spec MT1-MT5): the management to-do. `source` / `source_id` let mgmt-029 (meetings) and mgmt-026 (plans) link a task later;
# every task mgmt-028 creates is `manual`.
TASK_STATUSES = ("open", "in_progress", "completed", "cancelled")
TASK_PRIORITIES = ("high", "medium", "low")
TASK_SOURCES = ("manual", "decision", "meeting", "plan")


class ManagementTask(Base, TimestampMixin):
    """MT1: one task for one staff owner. `completed_at` drives the 7-day Completed band (MT3)."""

    __tablename__ = "management_tasks"
    __table_args__ = (
        CheckConstraint(_in_list("status", TASK_STATUSES), name="ck_management_tasks_status"),
        CheckConstraint(_in_list("priority", TASK_PRIORITIES), name="ck_management_tasks_priority"),
        CheckConstraint(_in_list("source", TASK_SOURCES), name="ck_management_tasks_source"),
        Index("ix_management_tasks_owner_deadline_status", "owner_user_id", "deadline", "status"),
        Index("ix_management_tasks_status_deadline", "status", "deadline"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200))
    owner_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    priority: Mapped[str] = mapped_column(String(8), default="medium", server_default=text("'medium'"))
    deadline: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="open", server_default=text("'open'"))
    source: Mapped[str] = mapped_column(String(10), default="manual", server_default=text("'manual'"))
    source_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# ccrm-029 (DEC-SCOPE-250, T1-T4): an overseas counselor's to-do, due on an IST day, about at most one lead, student or application.
# `source` / `rule_key` are ccrm-030's (rules create tasks); every task ccrm-029 creates is `manual`. Migration 0175 repeats the CHECKs.
COUNSELOR_TASK_STATUSES = ("open", "done", "cancelled")
COUNSELOR_TASK_SOURCES = ("manual", "rule")
COUNSELOR_TASK_CHECKS = {
    "ck_counselor_tasks_status": _in_list("status", COUNSELOR_TASK_STATUSES),
    "ck_counselor_tasks_priority": _in_list("priority", TASK_PRIORITIES),
    "ck_counselor_tasks_source": _in_list("source", COUNSELOR_TASK_SOURCES),
    "ck_counselor_tasks_one_link": "num_nonnulls(lead_id, student_user_id, application_id) <= 1",
}


class CounselorTask(Base, TimestampMixin):
    __tablename__ = "counselor_tasks"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in COUNSELOR_TASK_CHECKS.items()),
        Index("ix_counselor_tasks_counselor_status_due", "counselor_user_id", "status", "due_on"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200))
    counselor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    due_on: Mapped[date] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(8), default="medium", server_default=text("'medium'"))
    status: Mapped[str] = mapped_column(String(10), default="open", server_default=text("'open'"))
    source: Mapped[str] = mapped_column(String(10), default="manual", server_default=text("'manual'"))
    rule_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    lead_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="SET NULL"), nullable=True)
    student_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# ccrm-030 (DEC-SCOPE-270): the reminder rules the Overseas Admin configures (catalogue: services/counselor_reminders.RULES) and the log of
# every firing -- its unique `dedupe_key` (rule:subject:anchor) is what keeps a re-run from sending twice. Migration 0189 repeats the CHECKs.
COUNSELOR_REMINDER_RULE_KEYS = (
    "first_contact", "no_response", "document_overdue", "application_deadline", "decision_overdue",
    "offer_deadline", "deposit_due", "condition_due", "visa_appointment", "hold_review", "overdue_escalation",  # ccrm-031 (0190)
)
COUNSELOR_REMINDER_MAX_OFFSET = 60
COUNSELOR_REMINDER_CHECKS = {
    "ck_counselor_reminder_rules_key": _in_list("rule_key", COUNSELOR_REMINDER_RULE_KEYS),
    "ck_counselor_reminder_rules_offset": f"offset_days BETWEEN 0 AND {COUNSELOR_REMINDER_MAX_OFFSET}",
}


class CounselorReminderRule(Base, TimestampMixin):
    __tablename__ = "counselor_reminder_rules"
    __table_args__ = tuple(CheckConstraint(sql, name=name) for name, sql in COUNSELOR_REMINDER_CHECKS.items())
    rule_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    offset_days: Mapped[int] = mapped_column(Integer)
    notify_student: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class CounselorReminderLog(Base):
    __tablename__ = "counselor_reminder_log"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_counselor_reminder_log_dedupe_key"), Index("ix_counselor_reminder_log_created", "created_at"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    rule_key: Mapped[str] = mapped_column(String(40))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    summary: Mapped[str] = mapped_column(String(200))
    task_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("counselor_tasks.id", ondelete="SET NULL"), nullable=True)
    recipients: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# mgmt-026 (spec PN2-PN4): EVID-017 §25's monthly plan per vertical; §26's target vs actual is computed live, never stored (PN6). The
# KPI key is checked by the schema against `management_metrics.PLAN_KPIS`, not here, so the catalogue can grow without a migration.
# Migration 0159 repeats the CHECKs (test_mgmt_026_migration keeps them identical).
PLAN_STATUSES = ("draft", "active", "closed")
PLAN_VERTICALS = ("abroad", "it", "school", "recruitment", "other")
PLAN_ITEM_CHECKS = {
    "ck_management_plan_items_vertical": _in_list("vertical", PLAN_VERTICALS),
    "ck_management_plan_items_kpi_target": "(kpi IS NULL) = (target IS NULL)",
    "ck_management_plan_items_target": "target IS NULL OR target > 0",
    "ck_management_plan_items_done": "kpi IS NULL OR NOT done",
}


class ManagementPlan(Base, TimestampMixin):
    """PN2: one plan per IST month (`month` is its 1st day)."""

    __tablename__ = "management_plans"
    __table_args__ = (
        UniqueConstraint("month", name="uq_management_plans_month"),
        CheckConstraint("EXTRACT(DAY FROM month) = 1", name="ck_management_plans_month"),
        CheckConstraint(_in_list("status", PLAN_STATUSES), name="ck_management_plans_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    month: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(8), default="draft", server_default=text("'draft'"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class ManagementPlanItem(Base, TimestampMixin):
    """PN4: a KPI item (`kpi` + `target`, live actual) or a free-text item (`done`)."""

    __tablename__ = "management_plan_items"
    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in PLAN_ITEM_CHECKS.items()),
        Index("ix_management_plan_items_plan_order", "plan_id", "vertical", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("management_plans.id", ondelete="CASCADE"))
    vertical: Mapped[str] = mapped_column(String(12))
    text: Mapped[str] = mapped_column(String(200))
    kpi: Mapped[str | None] = mapped_column(String(20), nullable=True)
    target: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    position: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# mgmt-032 (Monthly Business Review, spec MR2): EVID-017 §32. Rules live in `services/monthly_review.py`.
REVIEW_STATUSES = ("draft", "final")
REVIEW_CHECKS = {
    "ck_monthly_reviews_month": "EXTRACT(DAY FROM month) = 1",
    "ck_monthly_reviews_status": "status IN ('draft', 'final')",
    "ck_monthly_reviews_final": "(status = 'final') = (finalised_at IS NOT NULL)",
}


class MonthlyReview(Base, TimestampMixin):
    """MR2: one review per IST month (`month` is its 1st). `snapshot` is frozen when drafted (or regenerated while a draft);
    `narrative` holds the partners' §9/§10 answers. `updated_by_user_id` is null while only the beat job has written it."""

    __tablename__ = "monthly_reviews"
    __table_args__ = (UniqueConstraint("month", name="uq_monthly_reviews_month"), *(CheckConstraint(sql, name=name) for name, sql in REVIEW_CHECKS.items()))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    month: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(8), default="draft", server_default=text("'draft'"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    narrative: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalised_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


# mgmt-029 (management meetings + minutes chain, spec MM1-MM14): EVID-017 §29. Rules live in `services/management_meetings.py`; the
# decisions and tasks recorded from the minutes are mgmt-027 discussions (`meeting_id`) and mgmt-028 tasks (`source` meeting / decision).
MEETING_KINDS = ("partner", "department", "school", "university", "agent", "recruiter", "marketing_review")
MEETING_STATUSES = ("scheduled", "completed", "cancelled")


class ManagementMeeting(Base, TimestampMixin):
    """MM2: one meeting. Recording minutes completes it (MM6); `minutes_recorded_at` keeps the first time."""

    __tablename__ = "management_meetings"
    __table_args__ = (
        CheckConstraint(_in_list("kind", MEETING_KINDS), name="ck_management_meetings_kind"),
        CheckConstraint(_in_list("status", MEETING_STATUSES), name="ck_management_meetings_status"),
        CheckConstraint(_in_list("mode", APPOINTMENT_MODES), name="ck_management_meetings_mode"),
        Index("ix_management_meetings_starts_at", "starts_at"),
        Index("ix_management_meetings_status_starts_at", "status", "starts_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String(12))
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    minutes: Mapped[str | None] = mapped_column(Text, nullable=True)
    minutes_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="scheduled", server_default=text("'scheduled'"))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


class ManagementMeetingParticipant(Base):
    """MM5: staff users only; replaced as a whole on edit."""

    __tablename__ = "management_meeting_participants"
    __table_args__ = (Index("ix_management_meeting_participants_user", "user_id"),)
    meeting_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("management_meetings.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)


# mgmt-013 (accounts dashboard, spec AD1-AD14): EVID-017 §22's hand-entered month-end figures (R10, Q-15 interim). Each is nullable (not
# entered); cash may be negative (an overdraft). Rules live in `services/accounts.py`; migration 0155 repeats the CHECKs
# (test_mgmt_013_migration keeps them identical).
FINANCE_BALANCE_CHECKS = {
    "ck_finance_balances_month": "EXTRACT(DAY FROM month) = 1",
    "ck_finance_balances_payables": "payables >= 0",
    "ck_finance_balances_tax": "tax_liabilities >= 0",
}


class FinanceBalance(Base, TimestampMixin):
    """AD7: one month's cash/bank, payables and tax liabilities (`month` is its 1st day), in rupees."""

    __tablename__ = "finance_balances"
    __table_args__ = (
        UniqueConstraint("month", name="uq_finance_balances_month"),
        *(CheckConstraint(sql, name=name) for name, sql in FINANCE_BALANCE_CHECKS.items()),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    month: Mapped[date] = mapped_column(Date)
    cash_bank: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    payables: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tax_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# mgmt-012 (spec MK3): one month's marketing budget per channel (the 13 lead sources, MK1); migration 0156 keeps a frozen copy.
MARKETING_BUDGET_CHECKS = {
    "ck_marketing_budgets_month": "EXTRACT(DAY FROM month) = 1",
    "ck_marketing_budgets_amount": "amount >= 0",
    "ck_marketing_budgets_channel": f"channel IN ({', '.join(repr(s) for s in TEL_SOURCES)})",
}


class MarketingBudget(Base, TimestampMixin):
    """MK3: a channel's budget for a month (`month` is its 1st day), in rupees. No row = no budget; 0 is a budget of nothing."""

    __tablename__ = "marketing_budgets"
    __table_args__ = (
        UniqueConstraint("month", "channel", name="uq_marketing_budgets_month_channel"),
        *(CheckConstraint(sql, name=name) for name, sql in MARKETING_BUDGET_CHECKS.items()),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    month: Mapped[date] = mapped_column(Date)
    channel: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))


# nehn-037 part 4 (DEC-SCOPE-296): admission interviews on an overseas application. Migration 0203 repeats these
# (test_nehn_037_migration). Labels live in app/api/application_interviews.py and the web client.
APPLICATION_INTERVIEW_MODES = ("online", "in_person", "phone")
APPLICATION_INTERVIEW_OUTCOMES = ("passed", "not_successful", "cancelled")


class ApplicationInterview(Base, TimestampMixin):
    """nehn-037 part 4 (DEC-SCOPE-296): one admission interview a university holds for an application -- when, how, where, and its
    result (NULL = awaiting). Never deleted: a called-off interview is `cancelled` (I5). Moves no stage. Everything on the row is shown
    to the student (I8); internal notes stay in ccrm-010's student notes."""

    __tablename__ = "application_interviews"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id", ondelete="CASCADE"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String(20))
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    student_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        CheckConstraint(_in_list("mode", APPLICATION_INTERVIEW_MODES), name="ck_application_interviews_mode"),
        CheckConstraint(_in("outcome", APPLICATION_INTERVIEW_OUTCOMES), name="ck_application_interviews_outcome"),
        Index("ix_application_interviews_application", "application_id", "scheduled_at"),
    )

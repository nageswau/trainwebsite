from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
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
    UniqueConstraint,
    Uuid,
    false,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates
from sqlalchemy.sql import func

from app.bdm_stages import FIRST_STAGE as BDM_FIRST_STAGE
from app.bdm_stages import MANUAL_STAGES as BDM_MANUAL_STAGES
from app.lead_stages import STAGES as LEAD_STAGES
from app.notifications.phone import normalise_phone
from app.tel_content_kinds import ASSET_KINDS as TEL_ASSET_KINDS
from app.tel_content_kinds import EMAIL_KINDS as TEL_EMAIL_KINDS
from app.tel_content_kinds import WHATSAPP_KINDS as TEL_WHATSAPP_KINDS
from app.tel_sources import TEL_SOURCES


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
    __table_args__ = (UniqueConstraint("student_id", "batch_id", name="uq_enrollment_student_batch"),)


class Agreement(Base, TimestampMixin):
    __tablename__ = "agreements"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True, default="it")
    version: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


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
    status: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    url: Mapped[str] = mapped_column(String(500))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


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


class Company(Base, TimestampMixin):
    __tablename__ = "companies"
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


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    location: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="open")
    closes_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    company = relationship("Company")


class JobApplication(Base, TimestampMixin):
    __tablename__ = "job_applications"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id"), index=True)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="applied")
    resume_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Interview(Base, TimestampMixin):
    __tablename__ = "interviews"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_applications.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String(30), default="Online")
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result: Mapped[str | None] = mapped_column(String(40), nullable=True)


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


class JobOffer(Base, TimestampMixin):
    __tablename__ = "job_offers"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_applications.id"), unique=True, index=True)
    offered_on: Mapped[date] = mapped_column(Date, default=date.today)
    compensation: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(30), default="offered")
    joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    letter_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Country(Base, TimestampMixin):
    __tablename__ = "countries"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
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


class University(Base, TimestampMixin):
    __tablename__ = "universities"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    country_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("countries.id"), index=True)
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(120))
    overview: Mapped[str] = mapped_column(Text)
    eligibility: Mapped[str] = mapped_column(Text)
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    deadlines: Mapped[list] = mapped_column(JSON, default=list)
    scholarships: Mapped[list] = mapped_column(JSON, default=list)
    country = relationship("Country")


class OverseasCourse(Base, TimestampMixin):
    __tablename__ = "overseas_courses"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    level: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(80))
    duration: Mapped[str] = mapped_column(String(80))
    tuition_fee: Mapped[str] = mapped_column(String(120))
    intake: Mapped[str] = mapped_column(String(120))


class OverseasApplication(Base, TimestampMixin):
    __tablename__ = "overseas_applications"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
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
    # AGN-010 (DEC-SCOPE-056): the current offer, recorded by the agency. `offer_deadline` above is its deadline (O2); the letter is an
    # AGN-009 document (O3). `use_alter`: student_documents.application_id points back at this table.
    offer_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    offer_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    offer_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("student_documents.id", ondelete="SET NULL", use_alter=True, name="fk_overseas_applications_offer_document_id"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("offer_type IS NULL OR offer_type IN ('conditional', 'unconditional')", name="ck_overseas_applications_offer_type"),
        CheckConstraint("(offer_type IS NULL) = (offer_date IS NULL)", name="ck_overseas_applications_offer_dated"),
        # AGN-017 (DEC-SCOPE-059): the daily reminder job reads agency deadlines through these partial indexes (migration 0065).
        Index("ix_overseas_applications_agent_application_deadline", "application_deadline", postgresql_where=text("agent_student_id IS NOT NULL")),
        Index("ix_overseas_applications_agent_offer_deadline", "offer_deadline", postgresql_where=text("agent_student_id IS NOT NULL")),
    )


class ApplicationStatusHistory(Base, TimestampMixin):
    __tablename__ = "application_status_history"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50))
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


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
    __table_args__ = (
        CheckConstraint("student_id IS NOT NULL OR agent_student_id IS NOT NULL", name="ck_student_documents_owner"),
        UniqueConstraint("fulfils_request_id", name="uq_student_documents_fulfils_request_id"),
    )


class DocumentRequest(Base, TimestampMixin):
    """AGN-009 (DEC-SCOPE-052 G4/G5): an agency's request for an additional document from one of its students. Open until an upload
    made against it fulfils it, or a member cancels it."""

    __tablename__ = "document_requests"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_students.id"))
    document_type: Mapped[str] = mapped_column(String(80))
    document_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    requested_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    closed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('open', 'fulfilled', 'cancelled')", name="ck_document_requests_status"),
        Index("ix_document_requests_student_status", "agent_student_id", "status"),
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
            "event IN ('uploaded', 'replaced', 'verified', 'rejected', 'changes_required', 'requested', 'fulfilled', 'cancelled', 'downloaded')",
            name="ck_document_events_event",
        ),
    )


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


class VisaCase(Base, TimestampMixin):
    __tablename__ = "visa_cases"
    __table_args__ = (CheckConstraint("decision IN ('approved', 'refused', 'withdrawn')", name="ck_visa_cases_decision"),)
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


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    staff_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    appointment_type: Mapped[str] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(40), default="Online")
    status: Mapped[str] = mapped_column(String(30), default="scheduled")


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


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
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
        *(CheckConstraint(sql, name=name) for name, sql in LEAD_CHECKS.items()),
        CheckConstraint(LEAD_STATUS_CHECK, name="ck_enquiries_status"),
        UniqueConstraint("lead_code", name="uq_enquiries_lead_code"),
        Index("ix_enquiries_bdm_org_created", "bdm_organization_id", "created_at"),
        Index("uq_enquiries_converted_user", "converted_user_id", unique=True, postgresql_where=text("converted_user_id IS NOT NULL")),
        Index("ix_enquiries_telecaller_status", "telecaller_user_id", "status"),
        Index("ix_enquiries_phone_normalized", "phone_normalized"),
        Index("ix_enquiries_email_lower", text("lower(email)")),
        Index("ix_enquiries_campaign", "campaign_id"),
        Index("ix_enquiries_product", "product_id"),
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

    @validates("phone")
    def _derive_phone_normalized(self, _key: str, phone: str | None) -> str | None:
        self.phone_normalized = normalise_phone(phone)
        return phone


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


# tel-011 (DEC-SCOPE-093): the EVID-019 §7 follow-up reasons (L284-L302) and states; migration 0089 repeats LEAD_FOLLOW_UP_CHECKS
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
    """tel-011 (DEC-SCOPE-093): a follow-up on a lead. It belongs to the lead (F3): whoever has the lead in scope sees it, so a
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


class Testimonial(Base, TimestampMixin):
    __tablename__ = "testimonials"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    person_name: Mapped[str] = mapped_column(String(160))
    headline: Mapped[str] = mapped_column(String(200))
    quote: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer, default=5)


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
    __table_args__ = (Index("ux_notifications_dedupe_key", "dedupe_key", unique=True, postgresql_where=text("dedupe_key IS NOT NULL")),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)


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
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id", "created_at"),)
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
    distribution time (an inactive telecaller's rule is skipped). Deleted, not deactivated, to stop it (audited)."""

    __tablename__ = "tel_distribution_rules"
    __table_args__ = (
        CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_distribution_rules_team"),
        CheckConstraint("kind IN ('product', 'city')", name="ck_tel_distribution_rules_kind"),
        CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND city IS NULL) OR (kind = 'city' AND city IS NOT NULL AND product_id IS NULL)",
            name="ck_tel_distribution_rules_shape",
        ),
        Index("uq_tel_distribution_rules_product", "team", "product_id", unique=True, postgresql_where=text("kind = 'product'")),
        Index("uq_tel_distribution_rules_city", "team", text("lower(city)"), unique=True, postgresql_where=text("kind = 'city'")),
        Index("ix_tel_distribution_rules_telecaller", "telecaller_user_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    team: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(10))
    product_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_products.id"), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
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
        UniqueConstraint("school_id", name="uq_bdm_organizations_school"),
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
BDM_ONBOARDING_CHECKS = {  # migration 0084 repeats these strings; test_bdm_018_migration asserts they stay identical
    "ck_bdm_onboarding_requests_kind": "kind IN ('school')",
    "ck_bdm_onboarding_requests_status": _in_list("status", BDM_ONBOARDING_STATUSES),
    "ck_bdm_onboarding_requests_resolution": "resolution IS NULL OR resolution IN ('created', 'linked')",
    "ck_bdm_onboarding_requests_resolved": "(status = 'pending') = (resolved_at IS NULL)",
    "ck_bdm_onboarding_requests_completed": "status <> 'completed' OR (school_id IS NOT NULL AND resolution IS NOT NULL)",
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


class School(Base, TimestampMixin):
    """School partner record (SCH-003, DATA_MODEL.md §6.11; profile fields added ENH-009,
    DEC-SCOPE-025). `EVID-014`'s full field list is now confirmed in scope -- see the
    design doc for what's stored here vs. computed at read time in `SchoolOut`."""

    __tablename__ = "schools"
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

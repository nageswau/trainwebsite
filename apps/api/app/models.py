from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


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
    # Nullable as of `DEC-SCOPE-018` (2026-09-15): a bridged application created on behalf
    # of a School-affiliated student (`DEC-ROLE-004` -- no login, no `users` row) has
    # school_student_id set instead. Application code enforces "exactly one of the two is
    # set" at every write site; this is not a DB CHECK constraint, matching this table's
    # existing style of app-level invariants over DB-level ones. Every pre-existing query
    # that inner-joins `User` on this column is unaffected -- a bridged row (student_id
    # NULL) simply never matches those joins, which is correct: those views are for real
    # logged-in overseas students/agents, not bridged School students.
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
    __tablename__ = "student_documents"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    application_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id"), nullable=True)
    document_type: Mapped[str] = mapped_column(String(80))
    file_url: Mapped[str] = mapped_column(String(500))
    verification_status: Mapped[str] = mapped_column(String(40), default="pending")
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)


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
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="checklist")
    appointment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    tracking_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)


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


class Enquiry(Base, TimestampMixin):
    __tablename__ = "enquiries"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    division: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(80), default="website")
    status: Mapped[str] = mapped_column(String(40), default="new")
    owner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    crm_sync_status: Mapped[str] = mapped_column(String(40), default="pending")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


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
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class NotificationDelivery(Base, TimestampMixin):
    __tablename__ = "notification_deliveries"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    notification_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    provider_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    outcome: Mapped[str] = mapped_column(String(30), default="recorded")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    __tablename__ = "agent_students"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    __table_args__ = (UniqueConstraint("agent_id", "student_id", name="uq_agent_student"),)


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


class School(Base, TimestampMixin):
    """School partner record (SCH-003, DATA_MODEL.md §6.11). Net-new.

    Minimal, confirmed-scope-only fields -- EVID-014's elaborate profile field list
    (Board, Principal name, partnership package, MoU, BDM assignment, etc.) is
    DERIVED_BLUEPRINT only, not confirmed (DEC-SCOPE-012). Add fields as BRD/PRD
    confirms them, not preemptively from that document.
    """

    __tablename__ = "schools"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    # Partnership tier (Bronze/Silver/Gold/Platinum), resolved 2026-09-15 (`DEC-SCOPE-017`,
    # closes `CLIENT_QUESTIONS.md` item 9) -- unlike the rest of EVID-014's field list, this
    # one is now confirmed, not derived-blueprint-only. Nullable: a School can exist before
    # a tier is assigned.
    tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tier_valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)


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


class SchoolParentLink(Base, TimestampMixin):
    """Many-to-many Parent<->Student link (SCH-001, DATA_MODEL.md §6.12) -- a student may
    have more than one linked parent, a parent more than one linked child."""

    __tablename__ = "school_parent_links"
    __table_args__ = (UniqueConstraint("parent_user_id", "school_student_id", name="uq_school_parent_link"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    parent_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    linked_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


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
    Draft/Published gate -- visible to readers as soon as it's created."""

    __tablename__ = "school_career_records"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    career_counselor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    record_type: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text)


class SchoolPsychometricRecord(Base, TimestampMixin):
    """SCH-005 -- Psychometric Assessment. Net-new, `DATA_MODEL.md` §6.18."""

    __tablename__ = "school_psychometric_records"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    psychometric_team_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    assessment_type: Mapped[str] = mapped_column(String(120))
    report_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="assigned")


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

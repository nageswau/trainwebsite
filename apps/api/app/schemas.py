import unicodedata
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class LoginRequest(BaseModel):
    # Demo/seed accounts intentionally use the reserved `.local` domain, which
    # EmailStr rejects even though these addresses are valid application accounts.
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=320)
    password: str
    division: str = Field(pattern="^(it|overseas|global)$")


class RoleAssignmentOut(BaseModel):
    division: str
    role: str
    is_active: bool
    approval_status: str
    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    division: str
    phone: str | None = None
    student_code: str | None = None
    profile: dict = Field(default_factory=dict)
    role_assignments: list[RoleAssignmentOut] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    user: UserOut
    expires_in_minutes: int


class RegistrationRequest(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=320)
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    division: str = Field(pattern="^(it|overseas)$")
    account_type: str = Field(default="student", pattern="^(student|agent)$")

    @field_validator("account_type")
    @classmethod
    def agent_is_overseas(cls, value: str, info):
        if value == "agent" and info.data.get("division") == "it":
            raise ValueError("Agent accounts are available only for Overseas Education")
        return value


class EmployerRegistrationRequest(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=320)
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    company_name: str = Field(min_length=2, max_length=180)
    company_website: str | None = Field(default=None, max_length=300)


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    profile: dict | None = None


class EmployerJobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    location: str = Field(default="Remote", max_length=120)
    description: str = Field(default="", max_length=10000)
    skills: list[str] = Field(default_factory=list, max_length=50)
    closes_on: date | None = None


class EmployerShortlistCreate(BaseModel):
    job_id: UUID
    student_id: UUID


class EmployerInterviewCreate(BaseModel):
    application_id: UUID
    scheduled_at: datetime
    mode: str = Field(default="Online", max_length=30)
    meeting_url: str | None = Field(default=None, max_length=500)


class EmployerJobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=180)
    location: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=10000)
    skills: list[str] | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, pattern="^(draft|open|closed)$")
    closes_on: date | None = None


class BatchCreate(BaseModel):
    program_id: UUID
    trainer_id: UUID | None = None
    name: str = Field(min_length=2, max_length=120)
    start_date: date
    end_date: date
    schedule: str = Field(min_length=2, max_length=160)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    capacity: int = Field(default=20, ge=1, le=20)  # ADM-003-AC02 / DEC-WF-002: 20 students per slot, no more
    mode: str = Field(default="Online", max_length=30)
    status: str = Field(default="upcoming", pattern="^(upcoming|active|completed|cancelled)$")
    enrollment_open: bool = True


class EnrollmentCreate(BaseModel):
    batch_id: UUID
    student_id: UUID | None = None


class AttendanceRecordIn(BaseModel):
    student_id: UUID
    status: str = Field(pattern="^(present|absent|late|excused)$")
    notes: str | None = Field(default=None, max_length=1000)


class AttendanceBulkIn(BaseModel):
    batch_id: UUID
    session_date: date
    records: list[AttendanceRecordIn] = Field(min_length=1, max_length=500)


class AttendanceCorrectionIn(BaseModel):
    attendance_id: UUID
    requested_status: str = Field(pattern="^(present|absent|late|excused)$")
    reason: str = Field(min_length=5, max_length=2000)


class AssignmentCreate(BaseModel):
    batch_id: UUID
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=10000)
    due_date: datetime
    max_score: int = Field(default=100, ge=1, le=10000)
    assignment_type: str = Field(default="assignment", pattern="^(assignment|project)$")
    submission_type: str = Field(default="text_or_file", pattern="^(text|file|text_or_file)$")
    published: bool = True


class AssignmentUpdate(BaseModel):
    """TRN-005: partial update -- batch_id is deliberately not editable (moving an
    assignment to a different batch would orphan its existing submissions' roster scope)."""

    title: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    due_date: datetime | None = None
    max_score: int | None = Field(default=None, ge=1, le=10000)
    assignment_type: str | None = Field(default=None, pattern="^(assignment|project)$")
    submission_type: str | None = Field(default=None, pattern="^(text|file|text_or_file)$")
    published: bool | None = None


class AssignmentSubmissionIn(BaseModel):
    answer: str | None = Field(default=None, max_length=50000)
    file_url: str | None = Field(default=None, max_length=500)


class LearningResourceCreate(BaseModel):
    batch_id: UUID
    title: str = Field(min_length=2, max_length=180)
    resource_type: str = Field(default="link", pattern="^(link|document|video|recording|notes)$")
    url: str = Field(min_length=1, max_length=500)
    metadata: dict = Field(default_factory=dict)


class EnrollmentProgressUpdate(BaseModel):
    progress_percent: int = Field(ge=0, le=100)


class SubmissionGradeIn(BaseModel):
    score: int = Field(ge=0, le=10000)
    feedback: str | None = Field(default=None, max_length=5000)
    status: str = Field(default="graded", pattern="^(graded|revision_required)$")


class AssessmentCreate(BaseModel):
    batch_id: UUID
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=10000)
    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=1, le=1440)
    max_score: int = Field(default=100, ge=1, le=10000)
    pass_percent: int = Field(default=50, ge=0, le=100)
    attempts_allowed: int = Field(default=1, ge=1, le=20)
    instructions: str = Field(default="", max_length=10000)
    publish_results: bool = True
    status: str = Field(default="scheduled", pattern="^(draft|scheduled|open|closed|published)$")


class AssessmentUpdate(BaseModel):
    """TRN-006: partial update -- batch_id is deliberately not editable, same reasoning
    as `AssignmentUpdate` (moving an assessment to a different batch would orphan its
    existing attempts' roster scope)."""

    title: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    max_score: int | None = Field(default=None, ge=1, le=10000)
    pass_percent: int | None = Field(default=None, ge=0, le=100)
    attempts_allowed: int | None = Field(default=None, ge=1, le=20)
    instructions: str | None = Field(default=None, max_length=10000)
    publish_results: bool | None = None
    status: str | None = Field(default=None, pattern="^(draft|scheduled|open|closed|published)$")


class AssessmentQuestionIn(BaseModel):
    question_type: str = Field(default="mcq_single", pattern="^(mcq_single|mcq_multiple|text|file)$")
    prompt: str = Field(min_length=2, max_length=10000)
    options: list[str] = Field(default_factory=list, max_length=20)
    correct_answers: list[str] = Field(default_factory=list, max_length=20)
    max_score: int = Field(default=1, ge=1, le=10000)
    position: int = Field(default=1, ge=1)
    required: bool = True


class AssessmentAnswerIn(BaseModel):
    question_id: UUID
    value: str | list[str] | dict


class AssessmentSubmitIn(BaseModel):
    answers: list[AssessmentAnswerIn]


class AssessmentGradeIn(BaseModel):
    answer_scores: dict[str, float] = Field(default_factory=dict)
    score: float | None = Field(default=None, ge=0)
    feedback: str | None = Field(default=None, max_length=5000)


class MeetingCreate(BaseModel):
    batch_id: UUID
    title: str = Field(min_length=2, max_length=180)
    starts_at: datetime
    ends_at: datetime
    provider: str = Field(default="manual", pattern="^(manual|google_meet|zoho_meeting)$")
    meeting_url: str | None = Field(default=None, max_length=500)
    attendee_emails: list[EmailStr] = Field(default_factory=list, max_length=500)
    agenda: str = Field(default="", max_length=5000)


class RecordingLinkUpdate(BaseModel):
    recording_url: str = Field(max_length=500)
    recording_external_id: str | None = Field(default=None, max_length=200)
    recording_status: str = Field(default="available", pattern="^(not_available|processing|available|failed)$")


class OverseasApplicationCreate(BaseModel):
    university_id: UUID
    course_id: UUID | None = None
    student_id: UUID | None = None
    counselor_id: UUID | None = None
    agent_id: UUID | None = None
    intake: str = Field(default="Next intake", max_length=80)
    application_reference: str | None = Field(default=None, max_length=140)
    next_action: str | None = Field(default=None, max_length=5000)


class OverseasApplicationUpdate(BaseModel):
    counselor_id: UUID | None = None
    intake: str | None = Field(default=None, max_length=80)
    status: str | None = Field(default=None, max_length=50)
    application_reference: str | None = Field(default=None, max_length=140)
    offer_letter_url: str | None = Field(default=None, max_length=500)
    next_action: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=10000)
    notify_channels: list[str] = Field(default_factory=lambda: ["email"])


class OverseasApplicationAdvance(BaseModel):
    to_status: str = Field(max_length=50)
    next_action: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=10000)
    notify_channels: list[str] = Field(default_factory=lambda: ["email"])


class StudentDocumentCreate(BaseModel):
    student_id: UUID | None = None
    application_id: UUID | None = None
    document_type: str = Field(min_length=2, max_length=80)
    file_url: str = Field(min_length=1, max_length=500)
    original_filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=120)
    file_size: int | None = Field(default=None, ge=0, le=50 * 1024 * 1024)


class AppointmentCreate(BaseModel):
    student_id: UUID | None = None
    staff_id: UUID | None = None
    scheduled_at: datetime
    appointment_type: str = Field(default="Career Counseling", max_length=80)
    mode: str = Field(default="Online", max_length=40)


class VisaCaseCreate(BaseModel):
    application_id: UUID
    status: str = Field(default="checklist", max_length=50)
    appointment_date: date | None = None
    checklist: list[str] = Field(default_factory=list, max_length=100)
    tracking_reference: str | None = Field(default=None, max_length=120)


class SupportTicketCreate(BaseModel):
    subject: str = Field(min_length=2, max_length=180)
    description: str = Field(min_length=5, max_length=10000)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")


class SupportTicketUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|in_progress|resolved|closed)$")
    resolution_note: str | None = Field(default=None, max_length=10000)


class CourseFeedbackCreate(BaseModel):
    batch_id: UUID
    rating: int = Field(ge=1, le=5)
    comments: str | None = Field(default=None, max_length=5000)


class QuestionThreadCreate(BaseModel):
    batch_id: UUID
    subject: str = Field(min_length=2, max_length=180)
    body: str = Field(min_length=2, max_length=10000)


class QuestionReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class ProfileDocumentCreate(BaseModel):
    document_type: str = Field(min_length=2, max_length=80)
    file_url: str = Field(min_length=1, max_length=500)
    original_filename: str | None = Field(default=None, max_length=255)
    content_type: str = Field(max_length=120)
    file_size: int = Field(gt=0)


class AgentStudentCreate(BaseModel):
    student_id: UUID


class CommissionCreate(BaseModel):
    agent_id: UUID
    application_id: UUID
    amount: float = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=10)


class CommissionAmountUpdate(BaseModel):
    amount: float = Field(ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=10)


class InboundUniversityEmailIn(BaseModel):
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: EmailStr
    recipient: str | None = Field(default=None, max_length=320)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=200000)
    received_at: datetime | None = None
    attachments: list[dict] = Field(default_factory=list, max_length=50)
    metadata: dict = Field(default_factory=dict)


class EnquiryIn(BaseModel):
    division: str = Field(pattern="^(it|overseas)$")
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    subject: str = Field(min_length=2, max_length=180)
    message: str = Field(min_length=5, max_length=5000)
    source: str = Field(default="website", max_length=80)
    metadata: dict = Field(default_factory=dict)


class WebinarRegistrationIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)


class ProgramOut(BaseModel):
    id: UUID
    slug: str
    category: str
    title: str
    summary: str
    duration: str
    eligibility: str
    fees: float
    certification: str
    curriculum: list
    placement_assistance: str
    trainer_name: str
    model_config = {"from_attributes": True}


class CareerPathOut(BaseModel):
    id: UUID
    division: str
    slug: str
    title: str
    summary: str
    skills: list
    related_program_slugs: list
    outcomes: str
    model_config = {"from_attributes": True}


class RealProjectOut(BaseModel):
    id: UUID
    division: str
    slug: str
    title: str
    summary: str
    description: str
    tech_stack: list
    model_config = {"from_attributes": True}


class TestimonialOut(BaseModel):
    id: UUID
    division: str
    person_name: str
    headline: str
    quote: str
    rating: int
    model_config = {"from_attributes": True}


class CountryOut(BaseModel):
    id: UUID
    slug: str
    name: str
    overview: str
    tuition: str
    living_expenses: str
    visa_process: list
    work_opportunities: str
    post_study_work: str
    pr_opportunities: str
    faq: list
    model_config = {"from_attributes": True}


class UniversityOut(BaseModel):
    id: UUID
    country_id: UUID
    slug: str
    name: str
    city: str
    overview: str
    eligibility: str
    requirements: list
    deadlines: list
    scholarships: list
    model_config = {"from_attributes": True}


# --- ENH-004: student promotion (docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md) ---


class PromotionItem(BaseModel):
    # `extra="forbid"`: a client-supplied `academic_year_id`/`school_id` is a loud 422, never silently ignored
    # (the target year and the school are server-decided; spec §14).
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}
    student_id: UUID
    action: Literal["promote", "hold_back"]
    grade_or_class: str | None = Field(default=None, min_length=1, max_length=60)

    @field_validator("grade_or_class")
    @classmethod
    def _no_control_characters(cls, value: str | None) -> str | None:
        # A NUL byte cannot be stored in PostgreSQL text (it would surface as a 500), and newlines or other
        # control characters have no place in a grade label that is later rendered and exported.
        if value is not None and any(unicodedata.category(ch) == "Cc" for ch in value):
            raise ValueError("grade_or_class must not contain control characters")
        return value


class StudentPromotionRequest(BaseModel):
    model_config = {"extra": "forbid"}
    items: list[PromotionItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _reject_duplicates_and_hold_back_labels(self):
        seen: set[UUID] = set()
        for item in self.items:
            if item.student_id in seen:
                raise ValueError(f"student_id {item.student_id} appears more than once")
            seen.add(item.student_id)
            if item.action == "hold_back" and item.grade_or_class is not None:
                raise ValueError("grade_or_class is only allowed with action 'promote'")
        return self


class PromotionResult(BaseModel):
    student_id: UUID
    status: Literal["promoted", "held_back", "failed", "skipped"]
    reason: str | None = None
    message: str | None = None
    grade_level: int | None = None
    grade_or_class: str | None = None


class PromotionCounts(BaseModel):
    promoted: int = 0
    held_back: int = 0
    failed: int = 0
    skipped: int = 0


class PromotionYear(BaseModel):
    id: UUID
    label: str


class StudentPromotionResponse(BaseModel):
    academic_year: PromotionYear
    counts: PromotionCounts
    results: list[PromotionResult]


class GradeHistoryState(BaseModel):
    academic_year_id: UUID | None = None
    academic_year_label: str | None = None
    grade_level: int | None = None
    grade_or_class: str | None = None


class GradeHistoryEntry(BaseModel):
    model_config = {"populate_by_name": True}
    id: UUID
    action: Literal["promoted", "held_back"]
    from_: GradeHistoryState = Field(alias="from")
    to: GradeHistoryState
    created_at: datetime


class GradeHistoryStudent(BaseModel):
    id: UUID
    full_name: str


class GradeHistoryResponse(BaseModel):
    student: GradeHistoryStudent
    history: list[GradeHistoryEntry]

import re
import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


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

    @field_validator("full_name")
    @classmethod
    def full_name_is_a_real_name(cls, value: str | None) -> str:
        # ENH-007: `str | None` lets an explicit `null` or an all-whitespace string satisfy
        # min_length (which only constrains RAW string length, not content, and runs before this
        # validator) and reach auth.py's `changes["full_name"].strip()`, which either crashes
        # (None -> AttributeError, unhandled 500) or silently blanks the account's display name
        # (whitespace -> "", 200 "success"). Pydantic v2 does not validate unset defaults, so this
        # only fires when the key is actually present -- omitting `full_name` is unaffected (still
        # means "don't change it"). Mirrors ChangePasswordRequest.new_password_is_not_blank below --
        # same bug class, same fix shape.
        if value is None:
            raise PydanticCustomError("null_full_name", "full_name cannot be null")
        stripped = value.strip()
        if not stripped:
            raise PydanticCustomError("blank_full_name", "full_name must not consist only of spaces")
        # Codex review: raw min_length=2 lets padding through -- "A " has raw length 2 but strips to
        # a single character, which auth.py then saves as-is, bypassing the "at least 2 real
        # characters" intent. Check the STRIPPED length, not the raw one.
        if len(stripped) < 2:
            raise PydanticCustomError("full_name_too_short_after_trim", "full_name must be at least 2 characters, not counting leading/trailing spaces")
        return value


class ChangePasswordRequest(BaseModel):
    # ENH-006. Passwords are never stripped or normalised. current_password is bounded (not at 128) so a legacy
    # long password still works while the input stays finite; new_password follows the registration/reset rule.
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def new_password_is_not_blank(cls, value: str) -> str:
        # QA-007: ten spaces satisfy the length rule but are not a password. Only an ALL-whitespace value is refused; spaces
        # inside or around real characters are kept exactly. A custom error keeps the message free of pydantic's "Value error, ".
        if not value.strip():
            raise PydanticCustomError("blank_password", "Password must not consist only of spaces")
        return value


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


# --- ENH-005: student school transfer (docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md) ---

FREE_TEXT_MAX = 500
_BIDI_CONTROLS = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
_STUDENT_CODE = re.compile(r"[0-9A-F]{8}")

TransferStatus = Literal["pending", "approved", "rejected", "cancelled"]
TransferStatusFilter = Literal["pending", "approved", "rejected", "cancelled", "all"]
TransferDirection = Literal["outgoing", "incoming"]


def clean_free_text(value: str | None) -> str | None:
    """Coordinator/admin free text (`reason`, `note`). Blank becomes None. A NUL byte would surface as a 500 from
    PostgreSQL text, and bidirectional overrides could visually reorder text shown to an admin (security review S7).
    Line breaks and tabs stay (it is a textarea); zero-width joiners stay (Indic scripts need them)."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > FREE_TEXT_MAX:
        raise ValueError(f"must be {FREE_TEXT_MAX} characters or fewer")
    for ch in value:
        if ch in _BIDI_CONTROLS or (unicodedata.category(ch) == "Cc" and ch not in "\n\t"):
            raise ValueError("must not contain control or bidirectional-override characters")
    return value


FreeText = Annotated[str | None, AfterValidator(clean_free_text)]  # `reason` and `note`: one rule, declared once


class TransferRequestCreate(BaseModel):
    # `extra="forbid"`: a client-supplied school, status or student is a loud 422; the from-school comes from the
    # student row and the filing school from the caller's profile (spec §6).
    model_config = {"extra": "forbid"}
    to_school_id: UUID
    reason: FreeText = None


class IncomingTransferCreate(BaseModel):
    model_config = {"extra": "forbid"}
    student_code: str
    reason: FreeText = None

    @field_validator("student_code")
    @classmethod
    def _code(cls, value: str) -> str:
        code = value.strip().upper()
        if not _STUDENT_CODE.fullmatch(code):  # explicit ASCII class: Unicode digits and look-alikes fail
            raise ValueError("student_code must be 8 characters, 0-9 and A-F")
        return code


class TransferRejectRequest(BaseModel):
    model_config = {"extra": "forbid"}
    note: FreeText = None


class SchoolRef(BaseModel):
    id: UUID
    name: str


class UserRef(BaseModel):
    id: UUID
    name: str


class AcceptedOut(BaseModel):
    accepted: bool


class TransferRequestOut(BaseModel):
    """One shape for every coordinator-facing request row. A not-yet-approved incoming row has `student_id`,
    `student_name` and `from_school` set to null (the gaining coordinator knows only the code they typed)."""

    id: UUID
    direction: TransferDirection
    status: TransferStatus
    student_id: UUID | None
    student_code: str
    student_name: str | None
    from_school: SchoolRef | None
    to_school: SchoolRef
    reason: str | None
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


class TransferRequestPage(BaseModel):
    items: list[TransferRequestOut]
    total: int
    limit: int
    offset: int


class TransferHistoryEntry(BaseModel):
    id: UUID
    decided_at: datetime
    from_school: SchoolRef
    to_school: SchoolRef


class TransferHistoryStudent(BaseModel):
    id: UUID
    full_name: str


class TransferHistoryResponse(BaseModel):
    student: TransferHistoryStudent
    history: list[TransferHistoryEntry]


class TransferOutcome(BaseModel):
    parents_moved: int = 0
    parents_kept: int = 0
    results_withdrawn: int = 0
    teacher_cleared: bool = False
    pending_parent_email_cleared: bool = False


class AdminTransferPreview(BaseModel):
    linked_parents: int
    in_flight_results: int
    to_school_has_portfolio_staff: bool
    # True when the student still has a parent invited but not yet accepted: approval clears that invite, so the parent would later hold an
    # account at the losing school and no linked child (DEC-SCOPE-022 open item). A boolean, never the invited address.
    pending_parent_invite: bool = False


class AdminTransferRequestOut(BaseModel):
    """Admin view: always complete (no redaction)."""

    id: UUID
    direction: TransferDirection
    status: TransferStatus
    student_id: UUID
    student_code: str
    student_name: str
    from_school: SchoolRef
    to_school: SchoolRef
    filed_by_school: SchoolRef
    requester: UserRef
    reason: str | None
    decision_note: str | None
    decided_by: UserRef | None
    outcome: TransferOutcome | None
    preview: AdminTransferPreview | None
    created_at: datetime
    decided_at: datetime | None


class AdminTransferPage(BaseModel):
    items: list[AdminTransferRequestOut]
    total: int
    limit: int
    offset: int


class AdminTransferHistoryResponse(BaseModel):
    student: TransferHistoryStudent
    history: list[AdminTransferRequestOut]


# --- ENH-009 / DEC-SCOPE-025: School Profile field coverage (EVID-014) ---

SchoolBoard = Literal["CBSE", "ICSE", "State", "IB", "Other"]


class SchoolCreate(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    tier: str | None = None
    # Restored (ENH-009 final review): the pre-ENH-009 dict-bodied create_school() accepted this,
    # so dropping it would have quietly narrowed a contract the design doc calls additive-compatible.
    tier_valid_until: date | None = None
    coordinator_full_name: str = Field(min_length=1, max_length=160)
    coordinator_email: str
    branch: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    contact_number: str | None = Field(default=None, max_length=30)
    # Demo/seed accounts intentionally use the reserved `.local` domain, which
    # EmailStr rejects even though these addresses are valid application accounts.
    email: str | None = Field(default=None, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=255)
    website: str | None = Field(default=None, max_length=255)
    grades_available: str | None = Field(default=None, max_length=200)
    board: SchoolBoard | None = None
    partnership_date: date | None = None
    mou_reference: str | None = Field(default=None, max_length=255)
    edusphere_bdm: str | None = Field(default=None, max_length=200)
    monthly_visit_schedule: str | None = Field(default=None, max_length=200)
    vice_principal_name: str | None = Field(default=None, max_length=200)


class SchoolUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    tier: str | None = None
    tier_valid_until: date | None = None
    branch: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    contact_number: str | None = Field(default=None, max_length=30)
    # Demo/seed accounts intentionally use the reserved `.local` domain, which
    # EmailStr rejects even though these addresses are valid application accounts.
    email: str | None = Field(default=None, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=255)
    website: str | None = Field(default=None, max_length=255)
    grades_available: str | None = Field(default=None, max_length=200)
    board: SchoolBoard | None = None
    partnership_date: date | None = None
    mou_reference: str | None = Field(default=None, max_length=255)
    edusphere_bdm: str | None = Field(default=None, max_length=200)
    monthly_visit_schedule: str | None = Field(default=None, max_length=200)
    vice_principal_name: str | None = Field(default=None, max_length=200)


class SchoolOut(BaseModel):
    id: UUID
    name: str
    city: str | None
    state: str | None
    tier: str | None
    tier_valid_until: date | None
    school_code: str | None
    branch: str | None
    address: str | None
    contact_number: str | None
    email: str | None
    website: str | None
    grades_available: str | None
    board: str | None
    partnership_date: date | None
    mou_reference: str | None
    edusphere_bdm: str | None
    monthly_visit_schedule: str | None
    vice_principal_name: str | None
    student_count: int
    teacher_count: int
    principal_name: str | None
    school_coordinator_name: str | None
    career_counsellor_names: list[str]
    created_at: datetime

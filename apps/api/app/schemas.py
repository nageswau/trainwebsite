import math
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    WrapValidator,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.models import GENDERS
from app.services.agent_visa import VISA_CASE_STAGES


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
    # AGN-002: set by GET /auth/me only (login/refresh do not load the membership); "master" | "staff" | None.
    agent_member_role: str | None = None
    # AGN-003: set by GET /auth/me only -- effective permissions (a Master gets both True); None for non-agents.
    agent_permissions: dict[str, bool] | None = None
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
    # AGN-001 (E2): optional; blank -> None, and the organisation is then named after the agent's full name.
    agency_name: str | None = Field(default=None, max_length=160)

    @field_validator("agency_name")
    @classmethod
    def blank_agency_name_is_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

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


class NotificationPreferencesIn(BaseModel):
    """ENH-014 (spec §5.2): the only two writable values. Strict booleans; any other field is a 422 (AC15)."""

    model_config = ConfigDict(extra="forbid")
    whatsapp: StrictBool
    sms: StrictBool


class NotificationPreferencesOut(BaseModel):
    whatsapp: bool
    sms: bool
    phone_valid: bool


class NotificationUnreadCount(BaseModel):
    """AGN-017 (DEC-SCOPE-059 N7): the caller's own unread notifications, for the nav badge."""

    unread: int


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


class AgentDocumentReview(BaseModel):
    """AGN-003 (DEC-SCOPE-044 P5/P6, spec §7): an agency member's decision on a pending document. The counselor/admin body of the
    same route is not parsed by this (unchanged)."""

    model_config = {"extra": "forbid"}
    verification_status: Literal["verified", "rejected", "changes_required"]
    notes: str | None = Field(default=None, max_length=10000)


# AGN-009 (DEC-SCOPE-052 G3): EVID-015 §5 Step 4, stored as written (the free-text style the visa checklist compares); the web mirrors
# it in lib/agentDocuments.ts DOCUMENT_TYPES.
AgentDocumentType = Literal["Passport", "Academic certificates", "Transcripts", "English test", "CV", "SOP", "LOR", "Financial documents", "Other"]
# AGN-010 (DEC-SCOPE-056 O3): uploads also take an offer letter (against one application); requests keep the list above.
AgentUploadDocumentType = Literal[AgentDocumentType, "Offer letter"]


class AgentDocumentRequestCreate(BaseModel):
    """AGN-009 (G4): ask one of the agency's students for an additional document. "Other" needs a label (checked by the service)."""

    model_config = {"extra": "forbid"}
    agent_student_id: UUID
    document_type: AgentDocumentType
    document_label: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


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


_EMAIL_SHAPE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def _required_full_name(value: str | None) -> str:
    """Trimmed; blank (or null) is refused with a plain message, not pydantic's "Value error, ..." prefix (browser QA-06)."""
    value = (value or "").strip()
    if not value:
        raise PydanticCustomError("blank_full_name", "Full name is required")
    return value


class AgentMasterInvite(BaseModel):
    """AGN-001 (D9): a Master inviting another Master to their agency."""

    full_name: str = Field(min_length=1, max_length=160)
    email: str = Field(max_length=320)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("full_name")
    @classmethod
    def full_name_not_blank(cls, value: str) -> str:
        return _required_full_name(value)

    @field_validator("email")
    @classmethod
    def email_looks_valid(cls, value: str) -> str:
        # AGN-002 browser QA-01: the same rule as before (something@domain.tld), worded for people -- a `pattern=` constraint
        # showed the raw regex ("String should match pattern ...") for an address the browser itself accepts (`a@b`).
        if not _EMAIL_SHAPE.fullmatch(value):
            raise PydanticCustomError("invalid_email", "Enter a valid email address, like name@example.com")
        return value


_RECORD_LIMITS = {"full_name": 160, "phone": 40, "highest_qualification": 200, "institution": 200, "preferred_country": 120, "preferred_course": 200, "preferred_intake": 40, "notes": 2000}
_RECORD_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class _AgentStudentRecordFields(BaseModel):
    """AGN-004 (DEC-SCOPE-042, EVID-015 §5 Step 1): a student with no login. Server-owned fields (agent, account, status,
    assignment, archive) are not accepted -- `extra="forbid"` answers 422 (mass assignment)."""

    model_config = {"extra": "forbid"}
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = None
    date_of_birth: date | None = None
    highest_qualification: str | None = None
    institution: str | None = None
    graduation_year: int | None = None
    preferred_country: str | None = None
    preferred_course: str | None = None
    preferred_intake: str | None = None
    notes: str | None = None
    confirm_duplicate: bool = False

    @field_validator("phone", "highest_qualification", "institution", "preferred_country", "preferred_course", "preferred_intake", "notes")
    @classmethod
    def _text(cls, value, info):
        return clean_free_text(value, _RECORD_LIMITS[info.field_name])

    @field_validator("phone")
    @classmethod
    def _phone(cls, value):
        # AGN-005 browser QA5-01 (owner, 2026-10-01): the school mobile rule, so "abc" can no longer be saved and every saved phone
        # has digits for the duplicate check. Runs after `_text` (trimmed, blank -> None); only a sent phone is checked.
        if value is not None and not _is_mobile(value):
            raise PydanticCustomError("invalid_phone", "Enter a phone number of 7–20 digits, spaces, +, -, ( or ) with at least 7 digits")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value):
        value = (value or "").strip().lower()
        if not value:
            return None
        if not _RECORD_EMAIL.match(value):
            raise PydanticCustomError("invalid_email", "Enter a valid email address")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, value):
        if value is not None and not (date(1900, 1, 1) <= value <= date.today()):
            raise PydanticCustomError("invalid_date_of_birth", "Date of birth must be between 1900 and today")
        return value

    @field_validator("graduation_year")
    @classmethod
    def _year(cls, value):
        if value is not None and not (1950 <= value <= date.today().year + 6):
            raise PydanticCustomError("invalid_graduation_year", "Graduation year is out of range")
        return value


def _record_name(value: str | None) -> str:
    value = clean_free_text(value, _RECORD_LIMITS["full_name"]) if value is not None else None
    if not value:
        raise PydanticCustomError("blank_full_name", "Full name is required")
    return value


class AgentStudentRecordCreate(_AgentStudentRecordFields):
    full_name: str

    @field_validator("full_name")
    @classmethod
    def _name(cls, value):
        return _record_name(value)


class AgentStudentRecordUpdate(_AgentStudentRecordFields):
    """Omitted = unchanged; null clears an optional field; the name cannot be cleared."""

    full_name: str | None = None

    @model_validator(mode="after")
    def _name_present_when_sent(self):
        if "full_name" in self.model_fields_set:
            self.full_name = _record_name(self.full_name)
        return self


class AgentStudentAssign(BaseModel):
    """AGN-004 D4: a Master assigns a student to an active staff member of the agency, or unassigns (null)."""

    model_config = {"extra": "forbid"}
    member_id: UUID | None


CounselingCurrency = Literal["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD"]  # models.COUNSELING_CURRENCIES; test_agn_006_schemas
_COUNSELING_LIMITS = {"career_interest": 200, "course_preference": 200, "country_preference": 120, "remarks": 2000}


class AgentStudentCounselingSave(BaseModel):
    """AGN-006 (DEC-SCOPE-048 C1-C5, EVID-015 §5 Step 2): the whole counseling record, replaced on every save -- an omitted optional
    field is stored as null. Server-owned fields (completed at/by, updated by) are not accepted: `extra="forbid"` answers 422."""

    model_config = {"extra": "forbid"}
    counseling_completed: bool
    career_interest: str | None = None
    course_preference: str | None = None
    country_preference: str | None = None
    budget_amount: Annotated[Decimal, Field(ge=0, le=Decimal("99999999.99"), max_digits=10, decimal_places=2)] | None = None
    budget_currency: CounselingCurrency | None = None
    remarks: str | None = None

    @field_validator("career_interest", "course_preference", "country_preference", "remarks")
    @classmethod
    def _text(cls, value, info):
        return clean_free_text(value, _COUNSELING_LIMITS[info.field_name])

    @model_validator(mode="after")
    def _budget_pair(self):
        if self.budget_amount is None and self.budget_currency is not None:
            raise PydanticCustomError("currency_without_amount", "Enter a budget amount, or leave the currency empty")
        if self.budget_amount is not None and self.budget_currency is None:
            self.budget_currency = "INR"
        return self


# AGN-007 (DEC-SCOPE-049, spec §5.3): agency universities and shortlist entries. Server-owned fields (agency, student, authors) are
# never accepted -- `extra="forbid"` answers 422 (mass assignment). Text goes through clean_free_text (NUL/bidi refused, blank -> None).
UNIVERSITY_LIMITS = {"name": 200, "country": 120, "city": 120, "entry_requirements": 2000}
ENTRY_LIMITS = {"course_title": 200, "intake": 120, "tuition_fee": 120, "entry_requirements": 2000}


class _AgentUniversityFields(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = None
    country: str | None = None
    city: str | None = None
    entry_requirements: str | None = None

    @field_validator("name", "country", "city", "entry_requirements")
    @classmethod
    def _text(cls, value, info):
        return clean_free_text(value, UNIVERSITY_LIMITS[info.field_name])


class AgentUniversityCreate(_AgentUniversityFields):
    name: str
    country: str

    @model_validator(mode="after")
    def _required(self):
        if not self.name or not self.country:
            raise PydanticCustomError("required", "Name and country are required")
        return self


class AgentUniversityUpdate(_AgentUniversityFields):
    """Omitted = unchanged; null clears city / entry requirements; name and country cannot be cleared."""

    @model_validator(mode="after")
    def _not_cleared(self):
        for field in ("name", "country"):
            if field in self.model_fields_set and not getattr(self, field):
                raise PydanticCustomError("required", "Name and country cannot be empty")
        return self


class _ShortlistEntryFields(BaseModel):
    model_config = {"extra": "forbid"}
    university_id: UUID | None = None
    agent_university_id: UUID | None = None
    course_id: UUID | None = None
    course_title: str | None = None
    intake: str | None = None
    tuition_fee: str | None = None
    entry_requirements: str | None = None

    @field_validator("course_title", "intake", "tuition_fee", "entry_requirements")
    @classmethod
    def _text(cls, value, info):
        return clean_free_text(value, ENTRY_LIMITS[info.field_name])


class ShortlistEntryCreate(_ShortlistEntryFields):
    """The university rules (exactly one source, course belongs) need the database: services/agent_shortlist.validate_entry."""


class ShortlistEntryUpdate(_ShortlistEntryFields):
    """Omitted = unchanged; null clears. The merged row is validated as a whole (spec §5.4)."""


# --- AGN-008: agent applications (DEC-SCOPE-050; docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md §5.4) ---

_APPLICATION_DATE_MIN, _APPLICATION_DATE_MAX = date(2000, 1, 1), date(2100, 12, 31)


def _application_date(value: date | None) -> date | None:
    """Catches typed-year slips (0202, 20226) before they reach a deadline list."""
    if value is not None and not (_APPLICATION_DATE_MIN <= value <= _APPLICATION_DATE_MAX):
        raise PydanticCustomError("invalid_application_date", "Dates must be between 2000 and 2100")
    return value


def _intake(value: str | None) -> str:
    value = clean_free_text(value, 80)
    if not value:
        raise PydanticCustomError("blank_intake", "Intake is required")
    return value


def _not_future(value: date | None, code: str, message: str) -> date | None:
    # One day ahead of UTC is allowed: a user east of UTC (IST after midnight) is already on tomorrow's date.
    if value is not None and value > datetime.now(UTC).date() + timedelta(days=1):
        raise PydanticCustomError(code, message)
    return value


# One rule for both the edit and the status change; the lambda defers the lookup of `clean_free_text` (defined further down).
ApplicationNextAction = Annotated[str | None, AfterValidator(lambda value: clean_free_text(value, 500))]


class _AgentApplicationFields(BaseModel):
    """Server-owned fields (agent, student, status, university on edit) are not accepted -- `extra="forbid"` answers 422."""

    model_config = {"extra": "forbid"}
    course_id: UUID | None = None
    application_reference: str | None = None
    submitted_on: date | None = None
    application_deadline: date | None = None
    offer_deadline: date | None = None
    next_action: ApplicationNextAction = None

    @field_validator("application_reference")
    @classmethod
    def _reference(cls, value):
        return clean_free_text(value, 140)

    @field_validator("application_deadline", "offer_deadline")
    @classmethod
    def _deadline(cls, value):
        return _application_date(value)

    @field_validator("submitted_on")
    @classmethod
    def _submitted(cls, value):
        return _not_future(_application_date(value), "future_submission_date", "Submission date cannot be in the future")


class AgentApplicationCreate(_AgentApplicationFields):
    agent_student_id: UUID
    university_id: UUID
    intake: str

    @field_validator("intake")
    @classmethod
    def _intake_required(cls, value):
        return _intake(value)


class AgentApplicationUpdate(_AgentApplicationFields):
    """Omitted = unchanged; null clears an optional field; intake cannot be cleared; the university is fixed (A10)."""

    intake: str | None = None

    @model_validator(mode="after")
    def _intake_when_sent(self):
        if "intake" in self.model_fields_set:
            self.intake = _intake(self.intake)
        return self


class AgentApplicationStatus(BaseModel):
    """`expected_status`: the status the caller saw; a mismatch is a 409, so a stale screen cannot act on a changed application."""

    model_config = {"extra": "forbid"}
    to_status: str = Field(max_length=50)
    expected_status: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    next_action: ApplicationNextAction = None

    @field_validator("notes")
    @classmethod
    def _notes(cls, value):
        return clean_free_text(value, 2000)


class AgentApplicationEnrollment(BaseModel):
    """AGN-013 (DEC-SCOPE-054): confirm or correct an application's enrollment. `expected_status` is required: confirming is the
    commission-triggering act, so a stale screen gets a 409 instead of acting."""

    model_config = {"extra": "forbid"}
    enrollment_date: date
    university_student_id: str | None = None
    expected_status: str = Field(max_length=50)
    notes: str | None = None

    @field_validator("enrollment_date")
    @classmethod
    def _enrollment_date(cls, value):
        return _application_date(value)

    @field_validator("university_student_id")
    @classmethod
    def _student_id(cls, value):
        return clean_free_text(value, 60)

    @field_validator("notes")
    @classmethod
    def _notes(cls, value):
        return clean_free_text(value, 2000)


# --- AGN-012: the visa case of an agency's application (DEC-SCOPE-057; docs/superpowers/specs/2026-10-02-agn-012-agent-visa-design.md §4) ---


def _visa_checklist(value: list[str] | None) -> list[str]:
    """V6: named agency document types only (an "Other" document has no fixed type to match), each once."""
    if value is None:
        raise PydanticCustomError("not_clearable", "The checklist cannot be cleared; send an empty list")
    if "Other" in value:
        raise PydanticCustomError("visa_checklist_other", "Choose a named document type for the checklist")
    if len(set(value)) != len(value):
        raise PydanticCustomError("visa_checklist_duplicate", "Each document type can appear once")
    return value


class _AgentVisaDates(BaseModel):
    model_config = {"extra": "forbid"}
    visa_application_date: date | None = None
    appointment_date: date | None = None
    interview_date: date | None = None

    @field_validator("visa_application_date", "appointment_date", "interview_date")
    @classmethod
    def _dates(cls, value):
        return _application_date(value)


class AgentVisaStart(_AgentVisaDates):
    """Start a case. There is no stage field: a case always starts at `checklist` (V3), so the checklist gate cannot be skipped at
    creation. `expected_status` is the application stage the screen shows (stale screen -> 409)."""

    expected_status: str = Field(max_length=50)
    checklist: list[AgentDocumentType] = Field(default_factory=list, max_length=8)

    @field_validator("checklist")
    @classmethod
    def _checklist(cls, value):
        return _visa_checklist(value)


class AgentVisaUpdate(_AgentVisaDates):
    """A partial update: an absent key is unchanged, an explicit null clears a date. The checklist, the target stage and the decision
    cannot be cleared. `expected_stage` is the visa stage the screen shows."""

    expected_stage: str = Field(max_length=50)
    checklist: list[AgentDocumentType] | None = Field(default=None, max_length=8)
    to_stage: str | None = None
    decision: Literal["approved", "refused", "withdrawn"] | None = None

    @field_validator("checklist")
    @classmethod
    def _checklist(cls, value):
        return _visa_checklist(value)

    @field_validator("to_stage")
    @classmethod
    def _to_stage(cls, value):
        if value not in VISA_CASE_STAGES:
            raise PydanticCustomError("visa_stage", "Choose a visa stage: {stages}", {"stages": ", ".join(VISA_CASE_STAGES)})
        return value

    @field_validator("decision")
    @classmethod
    def _decision(cls, value):
        if value is None:
            raise PydanticCustomError("not_clearable", "A recorded decision cannot be cleared")
        return value


# --- AGN-010: offer details (DEC-SCOPE-056; docs/superpowers/specs/2026-10-02-agn-010-offer-details-design.md §4.1) ---

OFFER_DEADLINE_BEFORE = "Offer deadline cannot be before the offer date"  # also the AGN-008 PATCH's answer once an offer exists (O2)


class AgentApplicationOffer(BaseModel):
    """The whole current offer (PUT replaces it, O1). `offer_deadline` is the application's existing column (O2); null clears it.
    `expected_status`: as on the status change, a mismatch is a 409."""

    model_config = {"extra": "forbid"}
    offer_type: Literal["conditional", "unconditional"]
    offer_date: date
    offer_deadline: date | None = None
    conditions: str | None = None
    offer_document_id: UUID | None = None
    expected_status: str | None = Field(default=None, max_length=50)

    @field_validator("offer_date")
    @classmethod
    def _offer_date(cls, value):
        return _not_future(_application_date(value), "future_offer_date", "Offer date cannot be in the future")

    @field_validator("offer_deadline")
    @classmethod
    def _offer_deadline(cls, value):
        return _application_date(value)

    @field_validator("conditions")
    @classmethod
    def _conditions(cls, value):
        return clean_free_text(value, 2000)

    @model_validator(mode="after")
    def _offer_rules(self):
        if self.offer_deadline is not None and self.offer_deadline < self.offer_date:
            raise PydanticCustomError("offer_deadline_before_date", OFFER_DEADLINE_BEFORE)
        if self.offer_type == "conditional" and not self.conditions:
            raise PydanticCustomError("offer_conditions_required", "A conditional offer needs its conditions")
        if self.offer_type == "unconditional" and self.conditions:
            raise PydanticCustomError("offer_conditions_unconditional", "An unconditional offer has no conditions")
        return self


# --- AGN-011: deposit collection (DEC-SCOPE-058; docs/superpowers/specs/2026-10-02-agn-011-deposit-collection-design.md §4) ---

DEPOSIT_AMOUNT_FORMAT = "Enter an amount in rupees with up to 2 decimals, for example 50000.50"


def _deposit_amount(value):
    """QA11-07: every amount error in plain words (the agency's deposit and the admin's refund): rupees, more than 0, at most
    99,999,999.99 (Numeric(12, 2) with headroom), at most 2 decimals."""
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise PydanticCustomError("deposit_amount_format", DEPOSIT_AMOUNT_FORMAT) from None
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise PydanticCustomError("deposit_amount_format", DEPOSIT_AMOUNT_FORMAT)
    if amount <= 0:
        raise PydanticCustomError("deposit_amount_positive", "The amount must be more than ₹0")
    if amount > Decimal("99999999.99"):
        raise PydanticCustomError("deposit_amount_max", "The amount can be at most ₹99,999,999.99")
    return amount


DepositAmount = Annotated[Decimal, BeforeValidator(_deposit_amount)]


class AgentDepositSave(BaseModel):
    """The agency's deposit on an application (§4.2). Currency (INR, D1) and status are server-owned: `extra="forbid"` answers 422."""

    model_config = {"extra": "forbid"}
    required: bool
    amount: DepositAmount | None = None
    due_date: date | None = None

    @field_validator("due_date")
    @classmethod
    def _due_date(cls, value):
        return _application_date(value)

    @model_validator(mode="after")
    def _deposit_rules(self):
        if not self.required and (self.amount is not None or self.due_date is not None):
            raise PydanticCustomError("deposit_not_required", "A deposit that is not required has no amount or due date")
        if self.required and self.amount is None:
            raise PydanticCustomError("deposit_amount_required", "Enter the deposit amount")
        return self


DEPOSIT_DATE_FUTURE = "The date cannot be in the future"


class DepositRemit(BaseModel):
    """Overseas Admin records that EduSphere finance remitted the deposit to the university (D12/§4.7)."""

    model_config = {"extra": "forbid"}
    remitted_on: date
    reference: str

    @field_validator("remitted_on")
    @classmethod
    def _date(cls, value):
        return _not_future(_application_date(value), "future_remitted_on", DEPOSIT_DATE_FUTURE)  # QA11-01: UTC + 1 day, like AGN-008/010

    @field_validator("reference")
    @classmethod
    def _reference(cls, value):
        value = clean_free_text(value, 100)
        if not value:
            raise PydanticCustomError("blank_reference", "Enter the remittance reference")
        return value


class DepositRefund(BaseModel):
    """Overseas Admin records the one refund (D3). The paid-amount ceiling is checked against the payment in the route."""

    model_config = {"extra": "forbid"}
    refunded_on: date
    amount: DepositAmount
    reason: str

    @field_validator("refunded_on")
    @classmethod
    def _date(cls, value):
        return _not_future(_application_date(value), "future_refunded_on", DEPOSIT_DATE_FUTURE)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value):
        value = clean_free_text(value, 500)
        if not value:
            raise PydanticCustomError("blank_reason", "Enter the refund reason")
        return value


# --- AGN-016: agent tasks and follow-ups (DEC-SCOPE-053; docs/superpowers/specs/2026-10-02-agn-016-tasks-followups-design.md §3) ---


def _task_title(value) -> str:
    if value is not None and not isinstance(value, str):  # runs before type coercion: a number or list is a 422, never a 500
        raise PydanticCustomError("task_title_text", "Title must be text")
    value = clean_free_text(value, 200)
    if not value:
        raise PydanticCustomError("task_title_required", "Title is required")
    return value


TaskNotes = Annotated[str | None, AfterValidator(lambda value: clean_free_text(value, 2000))]


class AgentTaskCreate(BaseModel):
    """`due_at` must carry an offset (AwareDatetime): a browser's local time is never silently read as UTC. Status, owner and
    closing fields are the server's -- `extra="forbid"` answers 422."""

    model_config = {"extra": "forbid"}
    agent_student_id: UUID
    title: str
    due_at: AwareDatetime
    notes: TaskNotes = None
    application_id: UUID | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, value):
        return _task_title(value)


class AgentTaskUpdate(BaseModel):
    """Omitted = unchanged; null clears `notes` or `application_id`; `title` and `due_at` cannot be cleared. Closing (T2, T6) is
    `status` sent ALONE, so every audit event is either an edit or a close; the student is fixed after create."""

    model_config = {"extra": "forbid"}
    title: str | None = None
    due_at: AwareDatetime | None = None
    notes: TaskNotes = None
    application_id: UUID | None = None
    status: Literal["done", "cancelled"] | None = None

    @model_validator(mode="after")
    def _rules(self):
        sent = self.model_fields_set
        if "title" in sent:
            self.title = _task_title(self.title)
        if "due_at" in sent and self.due_at is None:
            raise PydanticCustomError("task_due_required", "Due date and time is required")
        if "status" in sent and (self.status is None or sent != {"status"}):
            raise PydanticCustomError("task_status_alone", "Change the status on its own, without other fields")
        return self


class AgentStaffCreate(AgentMasterInvite):
    """AGN-002 (DEC-SCOPE-040 S4): a Master adding a staff login -- the same fields and rules as a Master invite."""


class AgentStaffUpdate(BaseModel):
    """AGN-002 (DEC-SCOPE-040 S4): name and phone only. Email is fixed after creation, so a Master can never redirect a staff
    member's set-password link to an address they control. Omitted = unchanged; phone null or "" clears it."""

    model_config = {"extra": "forbid"}
    full_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("full_name")
    @classmethod
    def full_name_present(cls, value: str | None) -> str:
        return _required_full_name(value)  # an explicit null is refused too (omitting the field leaves the name unchanged)

    @field_validator("phone")
    @classmethod
    def phone_blank_is_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @model_validator(mode="after")
    def something_to_update(self):
        if not self.model_fields_set:
            raise PydanticCustomError("nothing_to_update", "Nothing to update")
        return self


class AgentStaffPermissions(BaseModel):
    """AGN-003 (DEC-SCOPE-044 P1/P2): one staff member's whole optional-permission set. PUT replaces both; strict booleans and no
    other key, so no other privilege can be named."""

    model_config = {"extra": "forbid"}
    can_verify_documents: StrictBool
    can_view_reports: StrictBool


class CommissionCreate(BaseModel):
    agent_id: UUID
    application_id: UUID
    amount: float = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=10)


class CommissionAmountUpdate(BaseModel):
    amount: float = Field(ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=10)


# AGN-014 (DEC-SCOPE-051): the agency's commission report -- every amount is per currency, never summed across currencies.
class CommissionReportTotal(BaseModel):
    currency: str
    count: int
    amount: float


class CommissionReportStatusRow(CommissionReportTotal):
    status: str


class CommissionReportUniversityRow(CommissionReportTotal):
    university: str
    country: str


class CommissionReportCountryRow(CommissionReportTotal):
    country: str


class CommissionReportIntakeRow(CommissionReportTotal):
    intake: str


class CommissionReportOut(BaseModel):
    date_from: date | None
    date_to: date | None
    totals: list[CommissionReportTotal]
    by_status: list[CommissionReportStatusRow]
    by_university: list[CommissionReportUniversityRow]
    by_country: list[CommissionReportCountryRow]
    by_intake: list[CommissionReportIntakeRow]


# --- AGN-018 agency dashboard (DEC-SCOPE-062; spec §5.3) ---


class AgentBreakdownItem(BaseModel):
    label: str
    count: int


class AgentBreakdownOut(BaseModel):
    items: list[AgentBreakdownItem]
    other: int


class AgentStaffRowOut(BaseModel):
    code: str
    name: str
    active: bool
    students: int
    applications: int
    offers: int
    enrollments: int


class AgentCommissionSummaryOut(BaseModel):
    claimable: list[CommissionReportTotal]
    claims: int
    revenue: list[CommissionReportTotal]


class AgentDashboardOut(BaseModel):
    """One shape for Masters and staff; the Master-only fields are null for staff. No ids: codes and names only."""

    scope: Literal["agency", "own"]
    member_code: str | None
    students: int
    applications: int
    offers: int
    visa_applications: int
    visa_approvals: int
    enrollments: int
    pending_documents: int
    pending_actions: int
    by_country: AgentBreakdownOut
    by_university: AgentBreakdownOut
    staff: list[AgentStaffRowOut] | None
    unassigned_students: int | None
    commission: AgentCommissionSummaryOut | None
    reports_available: bool
    as_of: datetime


class AgentFunnelOut(BaseModel):
    """AGN-019 (DEC-SCOPE-065 P3): distinct students who reached each stage or a later one, so the stages never increase."""

    students: int
    applications: int
    submitted: int
    offers: int
    visa: int
    enrolled: int


class AgentPerformanceCountsOut(BaseModel):
    """AGN-018's G3 column definitions over the date cohort (P5), plus that cohort's funnel."""

    students: int
    applications: int
    offers: int
    visa_applications: int
    visa_approvals: int
    enrollments: int
    funnel: AgentFunnelOut


class AgentPerformanceRowOut(AgentPerformanceCountsOut):
    code: str
    name: str
    active: bool


class AgentPerformanceOut(BaseModel):
    """Master only. No ids, emails or phones: codes and names only (as AgentDashboardOut). `total` = rows + unassigned."""

    date_from: date | None
    date_to: date | None
    rows: list[AgentPerformanceRowOut]
    unassigned: AgentPerformanceCountsOut | None
    total: AgentPerformanceCountsOut
    as_of: datetime


# AGN-022 (DEC-SCOPE-064): Overseas Admin's agent network. Field lists are allowlists -- the drill-down rows never carry email,
# phone or date of birth (N1), and the detail carries a staff count, not a staff list (spec R-API-3).
class AgentNetworkCounts(BaseModel):
    students: int
    applications: int
    enrollments: int


class AgentOrgMasterOut(BaseModel):
    id: UUID
    code: str
    full_name: str
    email: str
    status: str


class AgentNetworkDepositsOut(BaseModel):
    currency: Literal["INR"]
    count: int
    collected: float
    remitted: float
    refunded: float


class AgentOrgDetailOut(BaseModel):
    id: UUID
    name: str
    prefix: str
    status: str
    created_at: datetime
    status_changed_at: datetime | None
    masters: list[AgentOrgMasterOut]
    staff_count: int
    counts: AgentNetworkCounts
    commission: AgentCommissionSummaryOut
    deposits: AgentNetworkDepositsOut
    as_of: datetime


class AgentNetworkStudentOut(BaseModel):
    id: UUID
    full_name: str | None
    status: str
    assigned_code: str | None
    has_login: bool
    applications: int
    created_at: datetime


class AgentNetworkStudentPage(BaseModel):
    items: list[AgentNetworkStudentOut]
    total: int
    limit: int
    offset: int


class AgentNetworkApplicationOut(BaseModel):
    id: UUID
    student_name: str | None
    university: str
    country: str
    status: str
    enrollment_date: date | None
    created_at: datetime
    updated_at: datetime


class AgentNetworkApplicationPage(BaseModel):
    items: list[AgentNetworkApplicationOut]
    total: int
    limit: int
    offset: int


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
    # ENH-025: additive. `roll_number` is only ever set on `from` (a year move clears it).
    section: str | None = None
    roll_number: str | None = None


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


# --- ENH-025: Student Master fields (docs/superpowers/specs/2026-09-23-enh-025-student-master-fields-design.md §2.1) ---

_BIDI_OVERRIDES = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
_MOBILE = re.compile(r"^[0-9+\-() ]{7,20}$")
LIST_MAX_ITEMS = 20
LIST_ITEM_MAX_LENGTH = 80


def _is_mobile(value: str) -> bool:
    """The mobile rule (ENH-025; agency student phones too, AGN-005 QA5-01): 7-20 of digits, spaces, + - ( ), at least 7 digits."""
    return bool(_MOBILE.match(value)) and sum(ch.isdigit() for ch in value) >= 7


def _clean_text(value, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("must be text")
    value = value.strip()
    if not value:
        return None
    if len(value) > max_length:
        raise ValueError(f"must be at most {max_length} characters")
    # Cc (NUL, newlines, ...) and explicit bidi overrides only -- not all of Cf, because zero-width joiners are
    # legitimate inside Indic names.
    if any(unicodedata.category(ch) == "Cc" or ch in _BIDI_OVERRIDES for ch in value):
        raise ValueError("must not contain control or bidirectional-override characters")
    return value


def _clean_list(value) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("must be a list of text values")
    if len(value) > LIST_MAX_ITEMS:
        raise ValueError(f"must have at most {LIST_MAX_ITEMS} items")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        try:
            item_text = _clean_text(item, LIST_ITEM_MAX_LENGTH)
        except ValueError as exc:
            raise ValueError(f"items {exc}") from None
        if item_text is None or item_text.casefold() in seen:
            continue
        seen.add(item_text.casefold())
        cleaned.append(item_text)
    return cleaned or None


class CareerPreferencesUpdate(BaseModel):
    """The four career fields a Career Counsellor may write (DEC-SCOPE-029 item 2). extra="forbid": any other
    key is a 422, so the counsellor route cannot reach roll number, mobile, photo, school or year."""

    model_config = {"extra": "forbid"}
    career_interests: list[str] | None = None
    global_education_interest: StrictBool | None = None
    preferred_countries: list[str] | None = None
    preferred_courses: list[str] | None = None

    @field_validator("career_interests", "preferred_countries", "preferred_courses", mode="before")
    @classmethod
    def _lists(cls, value):
        return _clean_list(value)


class StudentMasterFields(CareerPreferencesUpdate):
    """All ten ENH-025 value fields, validated at the API boundary. Only keys the client sent are in
    model_fields_set, which gives PATCH its absent = unchanged / null = clear semantics."""

    section: str | None = None
    roll_number: str | None = None
    gender: str | None = None
    student_mobile: str | None = None
    city: str | None = None
    subjects: list[str] | None = None

    @field_validator("section", "roll_number", mode="before")
    @classmethod
    def _short_text(cls, value):
        return _clean_text(value, 20)

    @field_validator("city", mode="before")
    @classmethod
    def _city(cls, value):
        return _clean_text(value, 120)

    @field_validator("subjects", mode="before")
    @classmethod
    def _subjects(cls, value):
        return _clean_list(value)

    @field_validator("gender", mode="before")
    @classmethod
    def _gender(cls, value):
        value = _clean_text(value, 20)
        if value is None:
            return None
        if value.lower() not in GENDERS:
            raise ValueError(f"must be one of: {', '.join(GENDERS)}")
        return value.lower()

    @field_validator("student_mobile", mode="before")
    @classmethod
    def _mobile(cls, value):
        value = _clean_text(value, 20)
        if value is None:
            return None
        if not _is_mobile(value):
            raise ValueError("must be 7-20 characters of digits, spaces, +, -, ( or ) with at least 7 digits")
        return value


MASTER_FIELD_KEYS: tuple[str, ...] = (
    "section", "roll_number", "gender", "student_mobile", "city", "subjects",
    "career_interests", "global_education_interest", "preferred_countries", "preferred_courses",
)
CAREER_PREFERENCE_KEYS: tuple[str, ...] = tuple(CareerPreferencesUpdate.model_fields)
LIST_FIELD_KEYS: tuple[str, ...] = ("subjects", "career_interests", "preferred_countries", "preferred_courses")


def validation_message(exc: ValidationError) -> str:
    """First error as one '<field> <reason>' string, matching the existing handlers' HTTPException(422, str)
    shape. Never includes the submitted value (spec §5, sensitive logs)."""
    error = exc.errors()[0]
    field = ".".join(str(part) for part in error["loc"] if not isinstance(part, int)) or "request"
    if error["type"] == "extra_forbidden":
        return f"{field} is not an accepted field"
    reason = error["msg"].removeprefix("Value error, ")
    return f"{field} {reason[:1].lower()}{reason[1:]}"


# --- ENH-026: Career Counselling record (docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md §3.1) ---

CareerStatus = Literal["not_started", "scheduled", "completed", "follow_up_required"]
CAREER_STATUS_LABEL: dict[str | None, str] = {
    "not_started": "Not Started", "scheduled": "Scheduled", "completed": "Completed", "follow_up_required": "Follow-up Required", None: "No status",
}
CAREER_RECORD_TYPES: tuple[str, ...] = ("guidance_session", "counselling_note", "recommendation")
STRUCTURED_RECORD_TYPES: frozenset[str] = frozenset({"guidance_session", "counselling_note"})  # C1
CAREER_STATUS_INITIAL: frozenset[str] = frozenset({"not_started", "scheduled", "completed"})  # C2: allowed on create
CAREER_STATUS_NEXT: dict[str | None, frozenset[str]] = {  # C2 / C4 (None = a legacy row, recorded before tracking)
    "not_started": frozenset({"scheduled"}),
    "scheduled": frozenset({"completed"}),
    "completed": frozenset({"follow_up_required"}),
    "follow_up_required": frozenset({"scheduled", "completed"}),
    None: frozenset({"completed", "follow_up_required"}),
}
COUNTED_CAREER_STATUSES: tuple[str, ...] = ("completed", "follow_up_required")  # C5, plus NULL
CAREER_LIST_KEYS: tuple[str, ...] = (
    "career_interests", "academic_strengths", "weak_areas",
    "recommended_careers", "recommended_courses", "recommended_stream", "recommended_skills",
)
CAREER_STRUCTURED_KEYS: tuple[str, ...] = (*CAREER_LIST_KEYS, "global_education_interest", "parent_participated", "parent_participation_note")
CAREER_DATE_KEYS: tuple[str, ...] = ("scheduled_for", "completed_on", "next_follow_up_date")


def career_transition_allowed(current: str | None, requested: str) -> bool:
    return requested == current or requested in CAREER_STATUS_NEXT[current]


def counts_as_completed(status: str | None) -> bool:
    """C5: one rule for KPIs, overview status and entitlement usage. A legacy NULL row was a held session."""
    return status is None or status in COUNTED_CAREER_STATUSES


def _career_notes(value) -> str:
    """SCH-004's own rule, unchanged (any value, str() then strip, no length cap) -- plus NUL refused, which PostgreSQL
    text cannot store (it surfaced as a 500 before). NOT NULL column: absent/None is the empty string."""
    text_value = "" if value is None else str(value).strip()
    if "\x00" in text_value:
        raise ValueError("must not contain NUL characters")
    return text_value


class CareerRecordFields(BaseModel):
    """ENH-026 body fields shared by create and update. extra="forbid" (A10): ids, owners and record_type are never
    writable here."""

    model_config = {"extra": "forbid"}
    notes: str = ""
    status: CareerStatus | None = None
    scheduled_for: AwareDatetime | None = None
    completed_on: date | None = None
    next_follow_up_date: date | None = None
    career_interests: list[str] | None = None
    academic_strengths: list[str] | None = None
    weak_areas: list[str] | None = None
    recommended_careers: list[str] | None = None
    recommended_courses: list[str] | None = None
    recommended_stream: list[str] | None = None
    recommended_skills: list[str] | None = None
    global_education_interest: StrictBool | None = None
    parent_participated: StrictBool | None = None
    parent_participation_note: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def _notes(cls, value):
        return _career_notes(value)

    @field_validator(*CAREER_LIST_KEYS, mode="before")
    @classmethod
    def _lists(cls, value):
        return _clean_list(value)

    @field_validator("parent_participation_note", mode="before")
    @classmethod
    def _note(cls, value):
        return _clean_text(value, 500)


class CareerRecordUpdate(CareerRecordFields):
    """PATCH body. `expected_status` is an optional precondition (spec §5.1 step 5): present ⇒ must equal the locked
    record's status (None matches a legacy row), else 409."""

    expected_status: CareerStatus | None = None


# --- ENH-020: financial support / loan assistance (docs/superpowers/specs/2026-10-01-enh-020-funding-support-tracking-design.md §3) ---

FundingSupportType = Literal["education_loan", "financial_assistance", "scholarship", "funding_guidance"]
FundingStatus = Literal["required", "counselling", "documents", "application", "approved", "completed", "closed"]
FUNDING_SUPPORT_TYPE_LABEL: dict[str, str] = {
    "education_loan": "Education loan", "financial_assistance": "Financial assistance", "scholarship": "Scholarship", "funding_guidance": "Funding guidance",
}
FUNDING_STATUS_LABEL: dict[str, str] = {
    "required": "Required", "counselling": "Counselling", "documents": "Documents", "application": "Application",
    "approved": "Approved", "completed": "Completed", "closed": "Closed",
}
FUNDING_STATUS_NEXT: dict[str, frozenset[str]] = {  # D3: one step forward, or Closed from any open stage; finals go nowhere
    "required": frozenset({"counselling", "closed"}), "counselling": frozenset({"documents", "closed"}),
    "documents": frozenset({"application", "closed"}), "application": frozenset({"approved", "closed"}),
    "approved": frozenset({"completed", "closed"}), "completed": frozenset(), "closed": frozenset(),
}
FUNDING_FINAL_STATUSES: frozenset[str] = frozenset({"completed", "closed"})
FUNDING_NOTES_MAX = 4000


def funding_transition_allowed(current: str, requested: str) -> bool:
    return requested == current or requested in FUNDING_STATUS_NEXT[current]


def _funding_notes(value) -> str:
    """The career-notes rule (trimmed, NUL refused, absent = "") plus a cap the career notes never had (new endpoint, spec §3.3)."""
    text_value = _career_notes(value)
    if len(text_value) > FUNDING_NOTES_MAX:
        raise ValueError(f"must be at most {FUNDING_NOTES_MAX} characters")
    return text_value


class FundingRecordFields(BaseModel):
    """ENH-020 body fields shared by create and update. extra="forbid": ids, owners, the school, status dates are never writable."""

    model_config = {"extra": "forbid"}
    provider_name: str | None = None
    amount_text: str | None = None
    notes: str = ""

    @field_validator("provider_name", mode="before")
    @classmethod
    def _provider(cls, value):
        return _clean_text(value, 200)

    @field_validator("amount_text", mode="before")
    @classmethod
    def _amount(cls, value):
        return _clean_text(value, 120)

    @field_validator("notes", mode="before")
    @classmethod
    def _notes(cls, value):
        return _funding_notes(value)


class FundingRecordCreate(FundingRecordFields):
    """POST body. Every case starts at `required`, so `status` is not a field (spec §3.3)."""

    school_student_id: UUID
    support_type: FundingSupportType


class FundingRecordUpdate(FundingRecordFields):
    """PATCH body, presence-aware (`model_fields_set`). `expected_status` is the optional precondition: a mismatch is a 409."""

    status: FundingStatus | None = None
    closure_reason: str | None = None
    expected_status: FundingStatus | None = None

    @field_validator("closure_reason", mode="before")
    @classmethod
    def _reason(cls, value):
        return _clean_text(value, 500)


# --- ENH-027: psychometric record result fields (docs/superpowers/specs/2026-09-28-enh-027-psychometric-result-fields-design.md §4.1) ---

PSYCHOMETRIC_LIST_KEYS: tuple[str, ...] = ("strengths", "interest_areas", "personality_indicators", "recommended_careers", "recommended_stream")
PSYCHOMETRIC_DATE_KEYS: tuple[str, ...] = ("test_date", "parent_discussion_on", "follow_up_on")
PSYCHOMETRIC_RESULT_KEYS: tuple[str, ...] = (
    "test_date", *PSYCHOMETRIC_LIST_KEYS, "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on",
)
COUNSELLOR_REMARKS_MAX = 4000
PARENT_DISCUSSION_NOTES_MAX = 2000
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso_date_or_none(value) -> date | None:
    """Only None, "" (an emptied <input type="date">) or exactly YYYY-MM-DD. Pydantic's lax date parsing would also accept
    a Unix timestamp or a datetime string; `strict` would reject the ISO string itself when validating a dict."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("must be a date in YYYY-MM-DD format")


class PsychometricResultFields(BaseModel):
    """The ten ENH-027 fields, validated at the API boundary. Fed only the keys the client sent (so PATCH gets
    absent = unchanged / null = clear through `model_fields_set`); every other request key keeps its existing handling.
    List names match ENH-026's `CareerRecordFields` where the concept is shared (DEC-SCOPE-035 Q8)."""

    test_date: date | None = None
    strengths: list[str] | None = None
    interest_areas: list[str] | None = None
    personality_indicators: list[str] | None = None
    recommended_careers: list[str] | None = None
    recommended_stream: list[str] | None = None
    counsellor_remarks: str | None = Field(default=None, max_length=COUNSELLOR_REMARKS_MAX)
    parent_discussion_on: date | None = None
    parent_discussion_notes: str | None = Field(default=None, max_length=PARENT_DISCUSSION_NOTES_MAX)
    follow_up_on: date | None = None

    @field_validator(*PSYCHOMETRIC_LIST_KEYS, mode="before")
    @classmethod
    def _lists(cls, value):
        return _clean_list(value)

    @field_validator(*PSYCHOMETRIC_DATE_KEYS, mode="before")
    @classmethod
    def _dates(cls, value):
        return _iso_date_or_none(value)

    @field_validator("counsellor_remarks", "parent_discussion_notes", mode="before")
    @classmethod
    def _text(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError("must be text")
        return _clean_multiline_text(value)


# --- ENH-028: bulk data-entry CSV rows (docs/superpowers/specs/2026-10-01-enh-028-bulk-data-entry-design.md §6) ---
# Every value arrives as CSV text. Each bound below mirrors the target column's width, so a bad cell rejects its row instead
# of failing the whole batch at the database. Unknown columns are ignored (a `status` or owner column has no effect).

RESULT_MARKS_MAX = 9999.99  # Numeric(6, 2)


def _required_text(value, max_length: int) -> str:
    cleaned = _clean_text(value, max_length)
    if cleaned is None:
        raise ValueError("is required")
    return cleaned


def _marks(value) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("is required")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("must be a number") from None
    if not math.isfinite(number):
        raise ValueError("must be a number")
    return number


class BulkResultRow(BaseModel):
    model_config = {"extra": "ignore"}

    academic_year: str
    term: str
    subject: str
    max_marks: float
    marks_obtained: float
    grade: str | None = None
    teacher_remarks: str | None = None

    @field_validator("academic_year", mode="before")
    @classmethod
    def _year(cls, value):
        return _required_text(value, 20)

    @field_validator("term", mode="before")
    @classmethod
    def _term(cls, value):
        return _required_text(value, 40)

    @field_validator("subject", mode="before")
    @classmethod
    def _subject(cls, value):
        return _required_text(value, 80)

    @field_validator("max_marks", mode="before")
    @classmethod
    def _max_marks(cls, value):
        number = _marks(value)
        if not 0 < number <= RESULT_MARKS_MAX:
            raise ValueError(f"must be greater than 0 and at most {RESULT_MARKS_MAX}")
        return number

    @field_validator("marks_obtained", mode="before")
    @classmethod
    def _marks_obtained(cls, value, info):
        number = _marks(value)
        if not 0 <= number <= RESULT_MARKS_MAX:
            raise ValueError(f"must be between 0 and {RESULT_MARKS_MAX}")
        if "max_marks" in info.data and number > info.data["max_marks"]:
            raise ValueError("must not exceed max_marks")
        return number

    @field_validator("grade", mode="before")
    @classmethod
    def _grade(cls, value):
        return _clean_text(value, 10)

    @field_validator("teacher_remarks", mode="before")
    @classmethod
    def _remarks(cls, value):
        return clean_free_text(value, 2000)


class BulkPsychometricRow(PsychometricResultFields):
    """The single create's fields plus the ENH-027 result fields; list cells are `;`-separated."""

    model_config = {"extra": "ignore"}

    assessment_type: str
    report_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _split_list_cells(cls, data):
        if isinstance(data, dict):
            data = {**data, **{key: data[key].split(";") if data[key].strip() else None for key in PSYCHOMETRIC_LIST_KEYS if isinstance(data.get(key), str)}}
        return data

    @field_validator("assessment_type", mode="before")
    @classmethod
    def _assessment_type(cls, value):
        return _required_text(value, 120)

    @field_validator("report_url", mode="before")
    @classmethod
    def _report_url(cls, value):
        cleaned = _clean_text(value, 500)
        if cleaned is not None and not cleaned.lower().startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return cleaned


class BulkTestPrepRow(BaseModel):
    model_config = {"extra": "ignore"}

    test_type: str
    target_score: str | None = None

    @field_validator("test_type", mode="before")
    @classmethod
    def _test_type(cls, value):
        cleaned = _required_text(value, 10).lower()
        if cleaned not in ("ielts", "sat"):
            raise ValueError("must be one of ielts, sat")
        return cleaned

    @field_validator("target_score", mode="before")
    @classmethod
    def _target_score(cls, value):
        return _clean_text(value, 20)


class BulkLanguageRow(BaseModel):
    model_config = {"extra": "ignore"}

    language: str
    level: str | None = None

    @field_validator("language", mode="before")
    @classmethod
    def _language(cls, value):
        return _required_text(value, 60)

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, value):
        return _clean_text(value, 30)


# --- ENH-005: student school transfer (docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md) ---

FREE_TEXT_MAX = 500
_BIDI_CONTROLS = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
_STUDENT_CODE = re.compile(r"[0-9A-F]{8}")

TransferStatus = Literal["pending", "approved", "rejected", "cancelled"]
TransferStatusFilter = Literal["pending", "approved", "rejected", "cancelled", "all"]
TransferDirection = Literal["outgoing", "incoming"]


def clean_free_text(value: str | None, limit: int = FREE_TEXT_MAX) -> str | None:
    """Coordinator/admin free text (`reason`, `note`). Blank becomes None. A NUL byte would surface as a 500 from
    PostgreSQL text, and bidirectional overrides could visually reorder text shown to an admin (security review S7).
    Line breaks and tabs stay (it is a textarea); zero-width joiners stay (Indic scripts need them).
    ENH-011 reuses the same rule with its own length `limit`."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > limit:
        raise ValueError(f"must be {limit} characters or fewer")
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


# --- ENH-012: digital portfolio (docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md) ---


PORTFOLIO_SECTIONS: frozenset[str] = frozenset({
    "project", "internship", "competition", "sport", "leadership", "volunteering",
    "extracurricular", "award", "certification", "skill",
})


def _no_control_characters(value: str | None) -> str | None:
    # Same rule as PromotionItem.grade_or_class (line ~501 above): a NUL byte cannot be stored in
    # PostgreSQL text and would surface as a 500; other control characters have no place in text that
    # is later rendered. Kept for genuinely single-line fields only (title/organization) -- a newline
    # in either would be a data problem, not a feature.
    if value is not None and any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError("must not contain control characters")
    return value


def _clean_multiline_text(value: str | None) -> str | None:
    """Same bidi-override/control-character rule as `clean_free_text` (line ~591), reused here rather
    than duplicated ad hoc: it is the house precedent for any field that renders with line breaks
    (a <textarea> / `white-space: pre-wrap`), unlike the single-line `_no_control_characters` above.
    `description` and `personal_statement` both fit that shape -- pressing Enter in either must not be
    a 422. Length is enforced by each field's own `Field(max_length=...)`, not duplicated here (this
    lets `description` (2000) and `personal_statement` (4000) share one function with different caps)."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    for ch in value:
        if ch in _BIDI_CONTROLS or (unicodedata.category(ch) == "Cc" and ch not in "\n\t"):
            raise ValueError("must not contain control or bidirectional-override characters")
    return value


# Code-review simplification pass: PortfolioEntryCreate/Update's own model_validators AND
# portfolio.py's post-merge PATCH check all need the identical date-range rule -- declared once here
# (with the one user-facing message it raises) and imported by both, instead of the same condition and
# string being copied three times. No leading underscore: this is a deliberate cross-module export, not
# schemas.py-internal.
DATE_RANGE_ERROR = "End date must not be before start date"


def date_range_is_invalid(date_from: date | None, date_to: date | None) -> bool:
    return date_from is not None and date_to is not None and date_to < date_from


# --- ENH-021: internship tracking on the portfolio `internship` section (spec §3.2 I1-I4) ---
INTERNSHIP_FIELD_KEYS: tuple[str, ...] = ("mentor_name", "mentor_designation", "attendance_percent", "completion_status", "feedback", "skills_acquired")
CompletionStatus = Literal["not_started", "in_progress", "completed", "discontinued"]
INTERNSHIP_ONLY_ERROR = "internship fields are only accepted for the internship section"
INTERNSHIP_COMPANY_ERROR = "Company is required for an internship"
INTERNSHIP_END_DATE_ERROR = "An internship marked completed needs an end date"


def internship_rule_error(organization: str | None, completion_status: str | None, date_to: date | None) -> str | None:
    """The internship rules shared by create (schema layer) and update (post-merge, in the route)."""
    if not organization:
        return INTERNSHIP_COMPANY_ERROR
    if completion_status == "completed" and date_to is None:
        return INTERNSHIP_END_DATE_ERROR
    return None


class _InternshipFields(BaseModel):
    mentor_name: str | None = Field(default=None, max_length=200)
    mentor_designation: str | None = Field(default=None, max_length=200)
    attendance_percent: StrictInt | None = Field(default=None, ge=0, le=100)
    completion_status: CompletionStatus | None = None
    feedback: str | None = Field(default=None, max_length=2000)
    skills_acquired: list[str] | None = None

    @field_validator("mentor_name", "mentor_designation")
    @classmethod
    def _single_line(cls, value: str | None) -> str | None:
        return _no_control_characters(value)

    @field_validator("feedback")
    @classmethod
    def _feedback(cls, value: str | None) -> str | None:
        return _clean_multiline_text(value)

    @field_validator("skills_acquired", mode="before")
    @classmethod
    def _skills(cls, value):
        return _clean_list(value)


# --- ENH-024: Skill India certification (docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md §5) ---
# Declared once and shared by PortfolioEntryCreate and portfolio.py's post-merge PATCH check (the DATE_RANGE_ERROR precedent).
CertificationType = Literal["skill_india"]
CertificationStatus = Literal["enrolled", "in_progress", "certified"]
CERT_TYPE_SECTION_ERROR = "Only a certification can be marked as Skill India"
CERT_STATUS_REQUIRED_ERROR = "Choose a status for the Skill India certification"
CERT_FIELDS_UNTAGGED_ERROR = "Status, certificate number and issue date apply only to Skill India certifications"
CERT_CERTIFIED_ERROR = "A certified Skill India certification needs a certificate number and issue date"


def skill_india_error(certification_type: str | None, certification_status: str | None, certificate_number: str | None, issued_on: date | None) -> str | None:
    """Spec D3/D6 on a complete state (a create payload, or a PATCH merged onto the stored entry); None when valid. Explicit
    nulls on an untagged entry are valid -- only a non-null detail is refused."""
    if certification_type is None:
        has_detail = certification_status is not None or certificate_number is not None or issued_on is not None
        return CERT_FIELDS_UNTAGGED_ERROR if has_detail else None
    if certification_status is None:
        return CERT_STATUS_REQUIRED_ERROR
    if certification_status == "certified" and (certificate_number is None or issued_on is None):
        return CERT_CERTIFIED_ERROR
    return None


def _clean_certificate_number(value: str | None) -> str | None:
    # `str_strip_whitespace` has already trimmed it; blank means "not given". Single-line, like title/organization.
    return _no_control_characters(value) if value else None


CertificateNumber = Annotated[str | None, Field(max_length=100), AfterValidator(_clean_certificate_number)]  # create and update: one rule


class PortfolioEntryCreate(_InternshipFields):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}
    section: str
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    organization: str | None = Field(default=None, max_length=200)
    date_from: date | None = None
    date_to: date | None = None
    certification_type: CertificationType | None = None
    certification_status: CertificationStatus | None = None
    certificate_number: CertificateNumber = None
    issued_on: date | None = None

    @field_validator("section")
    @classmethod
    def _known_section(cls, value: str) -> str:
        if value not in PORTFOLIO_SECTIONS:
            raise ValueError(f"section must be one of {sorted(PORTFOLIO_SECTIONS)}")
        return value

    @field_validator("title", "organization")
    @classmethod
    def _clean_text(cls, value: str | None) -> str | None:
        return _no_control_characters(value)

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str | None) -> str | None:
        return _clean_multiline_text(value)

    @model_validator(mode="after")
    def _date_range_is_ordered(self):
        # ENH-012 QA-02: "date_to"/"date_from" are internal field names -- Pydantic's model_validator
        # error surfaces this text verbatim to the end user (via detailMessage() on the frontend), so it
        # must already be in plain language, not something a UI layer patches after the fact.
        if date_range_is_invalid(self.date_from, self.date_to):
            raise ValueError(DATE_RANGE_ERROR)
        return self

    @model_validator(mode="after")
    def _skill_india_rules(self):
        # ENH-024: the tag lives only on a certification entry; the rest of the rule is shared with the PATCH merge check.
        if self.certification_type is not None and self.section != "certification":
            raise ValueError(CERT_TYPE_SECTION_ERROR)
        error = skill_india_error(self.certification_type, self.certification_status, self.certificate_number, self.issued_on)
        if error:
            raise ValueError(error)
        return self

    @model_validator(mode="after")
    def _internship_rules(self):
        # ENH-021 I1/I4: tracking fields belong to the internship section only; an internship names its company.
        if self.section != "internship":
            if self.model_fields_set & set(INTERNSHIP_FIELD_KEYS):
                raise ValueError(INTERNSHIP_ONLY_ERROR)
            return self
        error = internship_rule_error(self.organization, self.completion_status, self.date_to)
        if error:
            raise ValueError(error)
        return self


class PortfolioEntryUpdate(_InternshipFields):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    organization: str | None = Field(default=None, max_length=200)
    date_from: date | None = None
    date_to: date | None = None
    # ENH-024: no `certification_type` -- the tag is set at creation only (D8), so sending it is an `extra="forbid"` 422.
    # Cross-field rules need the stored entry, so portfolio.py checks them after the merge.
    certification_status: CertificationStatus | None = None
    certificate_number: CertificateNumber = None
    issued_on: date | None = None

    @field_validator("title", "organization")
    @classmethod
    def _clean_text(cls, value: str | None) -> str | None:
        return _no_control_characters(value)

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str | None) -> str | None:
        return _clean_multiline_text(value)

    @model_validator(mode="after")
    def _date_range_is_ordered(self):
        if date_range_is_invalid(self.date_from, self.date_to):
            raise ValueError(DATE_RANGE_ERROR)
        return self

    @model_validator(mode="after")
    def _title_not_explicitly_nulled(self):
        # `title` is NOT NULL at the database level. The PATCH endpoint's field-presence-aware merge
        # (model_fields_set) otherwise treats an explicit `title: null` the same as clearing any other
        # optional field, and would only fail later as an unhandled IntegrityError on flush. Reject it
        # here instead, at the same validation layer as every other portfolio schema rule, so the
        # response is the same structured 422 shape as every other rejection on this endpoint (a router-
        # level HTTPException with a bare string, which this replaces, breaks that shape's contract with
        # the frontend's detailMessage() -- see apps/web/lib/apiErrors.ts's own comment on the two 4xx
        # payload shapes it expects).
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title must not be null")
        return self


class PortfolioEntryOut(BaseModel):
    model_config = {"from_attributes": True}  # fields map 1:1 onto PortfolioEntry -- serialize the ORM row directly
    id: UUID
    school_student_id: UUID
    section: str
    title: str
    description: str | None
    organization: str | None
    date_from: date | None
    date_to: date | None
    certification_type: str | None = None
    certification_status: str | None = None
    certificate_number: str | None = None
    issued_on: date | None = None
    created_by_user_id: UUID
    updated_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    # ENH-021: additive; null/false for every non-internship entry. The storage key itself is never serialized (S9).
    mentor_name: str | None = None
    mentor_designation: str | None = None
    attendance_percent: int | None = None
    completion_status: str | None = None
    feedback: str | None = None
    skills_acquired: list[str] | None = None
    has_certificate: bool = False
    certificate_content_type: str | None = None


class PersonalStatementUpdate(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}
    personal_statement: str | None = Field(default=None, max_length=4000)

    @field_validator("personal_statement")
    @classmethod
    def _clean_text(cls, value: str | None) -> str | None:
        return _clean_multiline_text(value)


class PersonalStatementOut(BaseModel):
    personal_statement: str | None
    updated_at: datetime


# --- ENH-013: Student 360° view (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §6) ---

CAREER_GOAL_MAX = 120
TAB_360_KEYS: tuple[str, ...] = (
    "overview", "personal_details", "academic_records", "attendance", "examination_results", "career_guidance",
    "psychometric_assessment", "skills", "foreign_languages", "english_testing", "activities", "certificates",
    "documents", "teacher_remarks", "parent_communication", "edusphere_programs",
)


class CareerGoalUpdate(BaseModel):
    # `extra="forbid"`: this PATCH writes one column; a client-supplied school_id/assigned_teacher is a loud 422 (spec §9).
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}
    career_goal: str | None = Field(...)

    @field_validator("career_goal")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        # clean_free_text: blank -> None, length cap, no bidi/NUL; _no_control_characters: single line (no \n/\t).
        return _no_control_characters(clean_free_text(value, CAREER_GOAL_MAX))


class CareerGoalOut(BaseModel):
    school_student_id: UUID
    career_goal: str | None
    updated_at: datetime


class Tab360(BaseModel):
    status: Literal["has_data", "empty", "restricted"]
    count: int | None
    not_tracked: list[str]
    data: dict


class Student360Header(BaseModel):
    id: UUID
    full_name: str
    school_name: str | None
    student_code: str | None
    grade_or_class: str | None
    date_of_birth: date | None
    assigned_teacher_name: str | None


class Student360Out(BaseModel):
    student: Student360Header
    career_goal: str | None
    can_edit_career_goal: bool
    tabs: dict[str, Tab360]


# --- ENH-011: school skills tracker (docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md §5) ---

SkillModule = Literal["soft_skills", "digital_skills"]
SkillBatchStatus = Literal["open", "closed"]
SkillEnrollmentStatus = Literal["enrolled", "completed", "certified", "withdrawn"]
# Shown to the counselor as written (browser QA-05): user-facing wording, not field names. Shared with the PATCH endpoint's check.
END_BEFORE_START = "The end date must be on or after the start date"


def _optional(limit: int):
    return lambda value: clean_free_text(value, limit)


def _required(limit: int):
    def check(value: str) -> str:
        cleaned = clean_free_text(value, limit)
        if cleaned is None:
            raise ValueError("must not be blank")
        return cleaned

    return check


SkillTitle = Annotated[str, AfterValidator(_required(160))]
SkillName = Annotated[str, AfterValidator(_required(120))]
SkillShortText = Annotated[str | None, AfterValidator(_optional(120))]
SkillSessionTopic = Annotated[str | None, AfterValidator(_optional(160))]
SkillRemarks = Annotated[str | None, AfterValidator(_optional(2000))]


def _unique_ids(ids: list[UUID]) -> list[UUID]:
    if len(set(ids)) != len(ids):
        raise ValueError("must not repeat an id")
    return ids


def _unique_enrollments(rows: list) -> list:
    _unique_ids([r.enrollment_id for r in rows])
    return rows


def _check_dates(start: date | None, end: date | None) -> None:
    if start and end and end < start:
        raise ValueError(END_BEFORE_START)


class SkillBatchCreate(BaseModel):
    # `extra="forbid"`: status, creator and ids are server-owned (spec §5.1).
    model_config = {"extra": "forbid"}
    school_id: UUID
    module_type: SkillModule
    title: SkillTitle
    topic: SkillShortText = None
    trainer_name: SkillShortText = None
    start_date: date
    end_date: date | None = None

    @model_validator(mode="after")
    def _dates(self):
        _check_dates(self.start_date, self.end_date)
        return self


class SkillBatchUpdate(BaseModel):
    # A batch never changes school or module: sending either is a loud 422. A date sent alone is checked against the
    # stored other date by the endpoint.
    model_config = {"extra": "forbid"}
    title: SkillTitle | None = None
    topic: SkillShortText = None
    trainer_name: SkillShortText = None
    start_date: date | None = None
    end_date: date | None = None
    status: SkillBatchStatus | None = None

    @model_validator(mode="after")
    def _dates(self):
        _check_dates(self.start_date, self.end_date)
        return self


class SkillEnrollCreate(BaseModel):
    model_config = {"extra": "forbid"}
    school_student_ids: Annotated[list[UUID], Field(min_length=1, max_length=100), AfterValidator(_unique_ids)]


class SkillEnrollmentUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    status: SkillEnrollmentStatus


class SkillSessionCreate(BaseModel):
    model_config = {"extra": "forbid"}
    session_date: date
    topic: SkillSessionTopic = None


class SkillAttendanceMark(BaseModel):
    model_config = {"extra": "forbid"}
    enrollment_id: UUID
    present: bool


class SkillAttendanceIn(BaseModel):
    model_config = {"extra": "forbid"}
    records: Annotated[list[SkillAttendanceMark], Field(min_length=1, max_length=200), AfterValidator(_unique_enrollments)]


# ENH-030 (DEC-SCOPE-041): a teacher's whole-class mark for one day, one call (spec §5.2, §11 A1/A2).
SchoolAttendanceStatus = Literal["present", "absent", "late", "excused"]


class SchoolAttendanceMark(BaseModel):
    model_config = {"extra": "forbid"}
    student_id: UUID
    status: SchoolAttendanceStatus


def _unique_students(rows: list) -> list:
    _unique_ids([r.student_id for r in rows])
    return rows


class SchoolAttendanceIn(BaseModel):
    model_config = {"extra": "forbid"}
    session_date: date
    records: Annotated[list[SchoolAttendanceMark], Field(min_length=1, max_length=500), AfterValidator(_unique_students)]  # IT AttendanceBulkIn's limit


class SchoolAttendanceRosterStudent(BaseModel):
    id: UUID
    full_name: str
    grade_or_class: str | None
    status: SchoolAttendanceStatus | None  # None = not marked (never absent)


class SchoolAttendanceRosterOut(BaseModel):
    session_date: date
    today: date  # the school calendar's today, so the UI never uses the browser clock
    students: list[SchoolAttendanceRosterStudent]


class SkillAssessmentCreate(BaseModel):
    model_config = {"extra": "forbid"}
    name: SkillName
    max_score: Annotated[Decimal, Field(gt=0, le=1000, max_digits=6, decimal_places=2)]


class SkillScoreIn(BaseModel):
    model_config = {"extra": "forbid"}
    enrollment_id: UUID
    score: Annotated[Decimal, Field(ge=0, max_digits=6, decimal_places=2)]
    remarks: SkillRemarks = None


class SkillScoresIn(BaseModel):
    model_config = {"extra": "forbid"}
    scores: Annotated[list[SkillScoreIn], Field(min_length=1, max_length=200), AfterValidator(_unique_enrollments)]


class SkillBatchOut(BaseModel):
    id: UUID
    school: SchoolRef
    module_type: SkillModule
    title: str
    topic: str | None
    trainer_name: str | None
    start_date: date
    end_date: date | None
    status: SkillBatchStatus
    enrolled_count: int
    created_at: datetime


class SkillBatchPage(BaseModel):
    items: list[SkillBatchOut]
    total: int
    limit: int
    offset: int


class SkillAttendanceSummary(BaseModel):
    present: int
    marked: int


class SkillScoreOut(BaseModel):
    assessment_id: UUID
    score: float
    remarks: str | None


class SkillEnrollmentOut(BaseModel):
    id: UUID
    batch_id: UUID
    school_student_id: UUID
    student_name: str
    status: SkillEnrollmentStatus
    frozen: bool
    completed_at: datetime | None
    certified_at: datetime | None
    created_at: datetime
    attendance: SkillAttendanceSummary
    scores: list[SkillScoreOut]


class SkillAttendanceOut(BaseModel):
    enrollment_id: UUID
    present: bool


class SkillSessionOut(BaseModel):
    id: UUID
    session_date: date
    topic: str | None
    attendance: list[SkillAttendanceOut]


class SkillAssessmentOut(BaseModel):
    id: UUID
    name: str
    max_score: float


class SkillAssessmentScoreOut(BaseModel):
    enrollment_id: UUID
    score: float
    remarks: str | None


class SkillAssessmentScoresOut(SkillAssessmentOut):
    scores: list[SkillAssessmentScoreOut]


class SkillBatchDetail(SkillBatchOut):
    enrollments: list[SkillEnrollmentOut]
    sessions: list[SkillSessionOut]
    assessments: list[SkillAssessmentOut]


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
    # ENH-023 D12: optional precondition -- the tier the caller last saw. A mismatch under the row lock is a 409, so a
    # stale preview can never turn into an unconfirmed downgrade. Omitted = no precondition (backward compatible).
    expected_tier: str | None = None
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


class TierChangeService(BaseModel):
    key: str
    label: str


class TierChangeOut(BaseModel):
    """ENH-023 -- a tier change's effect, from the tier PATCH (`tier_change`) and its preview."""

    direction: Literal["upgrade", "downgrade", "unchanged"]
    from_tier: str | None
    to_tier: str | None
    gained: list[TierChangeService]
    lost: list[TierChangeService]


class SchoolUpdateOut(SchoolOut):
    """`SchoolOut` plus the additive `tier_change` (null when the body carried no tier field)."""

    tier_change: TierChangeOut | None = None


# --- ENH-018: school activity feedback (docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md §5) ---
# Free text reuses the house `clean_free_text` rule (trim, blank -> None, no NUL/bidi overrides, newlines kept) through
# `_required`/`_optional`; `trainer_name` is single-line, so it also takes `_no_control_characters`.
FEEDBACK_TEXT_MAX = 5000
FeedbackScore = Annotated[int, Field(strict=True, ge=1, le=5)]
FeedbackStatusFilter = Literal["all", "awaiting", "submitted"]


class ActivityFeedbackCreate(BaseModel):
    model_config = {"extra": "forbid"}
    rating: FeedbackScore
    satisfaction: FeedbackScore
    feedback: Annotated[str, AfterValidator(_required(FEEDBACK_TEXT_MAX))]
    suggestions: Annotated[str | None, AfterValidator(_optional(FEEDBACK_TEXT_MAX))] = None
    trainer_name: Annotated[str | None, AfterValidator(_optional(200)), AfterValidator(_no_control_characters)] = None


class ActivityParticipation(BaseModel):
    present: int
    marked: int


class ActivityFeedbackOut(BaseModel):
    id: UUID
    activity_id: UUID
    trainer_name: str | None
    rating: int
    satisfaction: int
    feedback: str
    suggestions: str | None
    submitted_by_name: str
    submitted_at: datetime


class SchoolFeedbackActivity(BaseModel):
    activity_id: UUID
    title: str
    activity_type: str
    scheduled_at: datetime
    participation: ActivityParticipation
    feedback: ActivityFeedbackOut | None


class SchoolFeedbackPage(BaseModel):
    items: list[SchoolFeedbackActivity]
    total: int
    limit: int
    offset: int


class AdminActivityFeedbackOut(ActivityFeedbackOut):
    school_id: UUID
    school_name: str
    activity_title: str
    activity_type: str
    scheduled_at: datetime
    participation: ActivityParticipation


class AdminFeedbackPage(BaseModel):
    items: list[AdminActivityFeedbackOut]
    total: int
    limit: int
    offset: int


# --- ENH-016: analytics dashboards (docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md §7) ---
# Read-only response models. Grade keys are "8".."12", "other" (a grade outside 8-12) and "unspecified" (no grade).


class MetricCell(BaseModel):
    count: int
    pct: float | None  # null when the grade has no students


class GradeMetricRow(BaseModel):
    key: str
    label: str
    is_proxy: bool  # D5: an estimate from existing data; `definition` says how it is computed
    definition: str | None
    cells: dict[str, MetricCell]


class GradePerformanceOut(BaseModel):
    grades: list[str]
    students: dict[str, int]
    metrics: list[GradeMetricRow]


class Headcounts(BaseModel):
    students: int
    teachers: int
    parents: int


class ActivityProgressRow(BaseModel):
    key: str
    label: str
    completed: int
    pending: int  # D2: total students - completed


class AverageRow(BaseModel):
    key: str
    label: str
    average_pct: float | None
    count: int


class PerformerRow(BaseModel):
    school_student_id: UUID
    full_name: str
    grade: str
    average_pct: float
    result_count: int


class PerformerList(BaseModel):
    items: list[PerformerRow]  # capped; `total` is the full count
    total: int


class StudentDevelopmentOut(BaseModel):
    headcounts: Headcounts
    activities: list[ActivityProgressRow]
    by_grade: list[AverageRow]
    by_subject: list[AverageRow]
    by_term: list[AverageRow]
    at_risk: PerformerList
    top_performers: PerformerList
    at_risk_below: int
    top_from: int


# D3: completed / in progress / not started (service in the tier) / not in plan / no module yet.
ScorecardState = Literal["completed", "in_progress", "not_started", "not_in_plan", "not_tracked"]


class ScorecardArea(BaseModel):
    key: str
    label: str
    state: ScorecardState


class ScorecardOut(BaseModel):
    school_student_id: UUID
    full_name: str
    grade: str
    portfolio_completion_pct: int
    areas: list[ScorecardArea]


class ScorecardPage(BaseModel):
    items: list[ScorecardOut]
    total: int
    limit: int
    offset: int


class TrackedValue(BaseModel):
    value: int | None
    tracked: bool
    note: str | None = None


class SchoolCounts(BaseModel):
    total: int
    active: int
    new: int
    renewal_due: int


class StudentCounts(BaseModel):
    total: int
    by_grade: dict[str, int]
    career_guidance: int
    psychometric: int
    counselling: int
    global_education: int


class ServiceTotals(BaseModel):
    """§27 over the services a tier includes: delivered (used), pending (included, unused), not tracked (no module yet)."""

    services_included: int
    delivered: int
    pending: int
    not_tracked: int
    utilization_pct: float | None


class CrossSchoolSummaryOut(BaseModel):
    """§34 -- aggregates only: no student-level field (spec §12)."""

    schools: SchoolCounts
    students: StudentCounts
    services: ServiceTotals
    outcomes: dict[str, TrackedValue]


class SchoolUtilizationRow(ServiceTotals):
    school_id: UUID
    name: str
    tier: str | None
    tier_valid_until: date | None
    is_active: bool  # a tier that is set and not past its end date (ENH-022's rule)
    is_new: bool
    renewal_due: bool
    students: int
    student_participation: int
    pending_activities: int


class SchoolUtilizationPage(BaseModel):
    items: list[SchoolUtilizationRow]
    total: int
    limit: int
    offset: int


# --- ENH-017 (DEC-SCOPE-036): School-visible Global Education pipeline -- an allowlist; §19 keeps application detail out --------


class PipelineStage(BaseModel):
    key: str
    label: str
    count: int


class PipelineUntracked(BaseModel):
    key: str
    label: str
    note: str


class PipelineStudentRow(BaseModel):
    school_student_id: UUID
    full_name: str
    student_code: str
    grade: str
    furthest_stage: str
    furthest_stage_label: str
    visa_stage_label: str | None
    application_count: int


class PipelineStudentPage(BaseModel):
    items: list[PipelineStudentRow]
    total: int
    limit: int
    offset: int


class GlobalEducationPipelineOut(BaseModel):
    grade: int | None
    students_in_scope: int
    bridged_students: int
    funnel: list[PipelineStage]
    not_tracked: list[PipelineUntracked]
    students: PipelineStudentPage


# --- bdm-001 (DEC-SCOPE-055): BDM profile -------------------------------------------------------------------------------
BdmType = Literal["agent", "school", "college"]
_BDM_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _bdm_employee_id(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Employee ID is required")
    if len(value) > 40:
        raise ValueError("Employee ID must be at most 40 characters")
    if _BDM_CONTROL.search(value):
        raise ValueError("Employee ID contains invalid characters")
    return value


BDM_FIELD_LABELS = {
    "bdm_type": "Module", "employee_id": "Employee ID", "designation": "Designation", "department": "Department",
    "territory": "Territory", "reporting_manager_user_id": "Reporting manager",
}


def _bdm_plain_text(value: str | None, info: ValidationInfo) -> str | None:
    """The Employee ID's rule for every profile text (no control characters); blank becomes None, which clears the field."""
    if value is not None and _BDM_CONTROL.search(value):
        raise ValueError(f"{BDM_FIELD_LABELS.get(info.field_name, info.field_name)} contains invalid characters")
    return value or None


BdmEmployeeId = Annotated[str, AfterValidator(_bdm_employee_id)]
# The string branch is trimmed BEFORE its length is checked (a padded value that fits once trimmed is accepted); None stays None.
BdmText = Annotated[Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None, AfterValidator(_bdm_plain_text)]


class BdmProfileCreate(BaseModel):
    """spec §5.2: type, Employee ID and reporting manager are required (B8); the three texts are optional."""

    model_config = ConfigDict(extra="forbid")
    bdm_type: BdmType
    employee_id: BdmEmployeeId
    designation: BdmText = None
    department: BdmText = None
    territory: BdmText = None
    reporting_manager_user_id: UUID


class BdmProfileUpdate(BaseModel):
    """Omitted = unchanged. The optional texts accept null/"" (clears). The three required keys reject an explicit null: the default
    None is never validated, but a sent null is checked against the non-nullable type and fails."""

    model_config = ConfigDict(extra="forbid")
    bdm_type: BdmType = None
    employee_id: BdmEmployeeId = None
    designation: BdmText = None
    department: BdmText = None
    territory: BdmText = None
    reporting_manager_user_id: UUID = None


class BdmManagerRef(BaseModel):
    id: UUID
    full_name: str
    active: bool


class BdmProfileOut(BaseModel):
    bdm_type: str
    employee_id: str
    designation: str | None
    department: str | None
    territory: str | None
    reporting_manager: BdmManagerRef


class BdmMeOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    division: str
    bdm_profile: BdmProfileOut


class BdmTeamRow(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    bdm_type: str
    employee_id: str
    designation: str | None
    department: str | None
    territory: str | None


class BdmAdminRow(BdmTeamRow):
    reporting_manager: BdmManagerRef
    manager_active: bool


class BdmManagerOption(BaseModel):
    """QA-03 (owner, 2026-10-02): email is returned so the picker can tell same-name managers apart."""

    id: UUID
    full_name: str
    email: str


class BdmTeamPage(BaseModel):
    items: list[BdmTeamRow]
    total: int
    limit: int
    offset: int


class BdmAdminPage(BaseModel):
    items: list[BdmAdminRow]
    total: int
    limit: int
    offset: int


class BdmManagerPage(BaseModel):
    items: list[BdmManagerOption]
    total: int
    limit: int
    offset: int


# --- bdm-010: travel requests, approval, expenses (DEC-SCOPE-063; docs/superpowers/specs/2026-10-03-bdm-010-travel-design.md §5.1) ---

BdmTripMode = Literal["flight", "train", "bus", "car", "cab", "local"]
BdmExpenseCategory = Literal["travel", "stay", "food", "local", "other"]
BDM_TRIP_FIELD_LABELS = {
    "travel_date": "Travel date", "return_date": "Return date", "from_place": "From", "to_place": "To", "purpose": "Purpose",
    "mode": "Mode of travel", "estimated_cost": "Estimated cost", "remarks": "Remarks", "reason": "Reason", "category": "Category",
    "amount": "Amount", "expense_date": "Expense date", "note": "Note",
}
# S5: multi-line text keeps \t \n \r; every other control character is refused (the single-line fields use _BDM_CONTROL).
_BDM_MULTILINE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TRIP_AMOUNT_FORMAT = "Enter an amount in rupees with up to 2 decimals, for example 2500.50"
TRIP_AMOUNT_MAX = Decimal("10000000.00")


def _trip_text(pattern: re.Pattern, required: bool):
    def check(value: str | None, info: ValidationInfo) -> str | None:
        field = info.field_name or ""
        label = BDM_TRIP_FIELD_LABELS.get(field, field)
        if value is not None and pattern.search(value):
            raise ValueError(f"{label} contains invalid characters")
        if required and not value:
            raise ValueError(f"{label} is required")
        return value or None
    return check


def _trip_amount(positive: bool):
    def parse(value):
        try:
            amount = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise PydanticCustomError("trip_amount_format", TRIP_AMOUNT_FORMAT) from None
        exponent = amount.as_tuple().exponent  # an int once finite (NaN/Infinity carry 'n'/'N'/'F')
        if not amount.is_finite() or (isinstance(exponent, int) and exponent < -2):
            raise PydanticCustomError("trip_amount_format", TRIP_AMOUNT_FORMAT)
        if positive and amount <= 0:
            raise PydanticCustomError("trip_amount_positive", "The amount must be more than ₹0")
        if amount < 0:
            raise PydanticCustomError("trip_amount_negative", "The estimated cost can't be negative")
        if amount > TRIP_AMOUNT_MAX:
            raise PydanticCustomError("trip_amount_max", "The amount can be at most ₹1,00,00,000")
        return amount
    return parse


def _trimmed(max_length: int):
    return StringConstraints(strip_whitespace=True, max_length=max_length)


def _trip_date(label: str):
    """QA10-08: a calendar date as YYYY-MM-DD with a 4-digit year; anything else (Chrome lets a year run to 6 digits) gets plain
    words instead of the parser's text."""
    def parse(value):
        if isinstance(value, date):
            return value
        try:
            if isinstance(value, str) and _ISO_DATE.fullmatch(value.strip()):  # the module's YYYY-MM-DD (ENH-027)
                return date.fromisoformat(value.strip())
        except ValueError:
            pass
        raise PydanticCustomError("trip_date", f"Enter a valid {label}")
    return parse


TripTravelDate = Annotated[date, BeforeValidator(_trip_date("travel date"))]
TripReturnDate = Annotated[date, BeforeValidator(_trip_date("return date"))]
TripExpenseDate = Annotated[date, BeforeValidator(_trip_date("expense date"))]
TripPlace = Annotated[Annotated[str, _trimmed(120)], AfterValidator(_trip_text(_BDM_CONTROL, True))]
TripPurpose = Annotated[Annotated[str, _trimmed(1000)], AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, True))]
TripReason = TripPurpose  # the same rule: required, multi-line, at most 1000
TripRemarks = Annotated[Annotated[str, _trimmed(2000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False))]
TripNote = Annotated[Annotated[str, _trimmed(500)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False))]
TripEstimatedCost = Annotated[Decimal, BeforeValidator(_trip_amount(positive=False))]
TripExpenseAmount = Annotated[Decimal, BeforeValidator(_trip_amount(positive=True))]


class BdmTripCreate(BaseModel):
    """§3 fields. Code, owner, statuses and currency are server-owned (`extra="forbid"` → 422, AC13). Date rules (T14) need
    "today", so `services/bdm_travel.check_dates` applies them."""

    model_config = ConfigDict(extra="forbid")
    travel_date: TripTravelDate
    return_date: TripReturnDate
    from_place: TripPlace
    to_place: TripPlace
    purpose: TripPurpose
    mode: BdmTripMode
    accommodation_required: bool = False
    estimated_cost: TripEstimatedCost
    remarks: TripRemarks = None


class BdmTripUpdate(BaseModel):
    """Omitted = unchanged. A sent null on a required field fails its non-nullable type (bdm-001's idiom); remarks accept null.
    The `None` default is never validated, so it is deliberately typed as the non-nullable type (hence the type: ignore)."""

    model_config = ConfigDict(extra="forbid")
    travel_date: TripTravelDate = None  # type: ignore[assignment]
    return_date: TripReturnDate = None  # type: ignore[assignment]
    from_place: TripPlace = None  # type: ignore[assignment]
    to_place: TripPlace = None  # type: ignore[assignment]
    purpose: TripPurpose = None  # type: ignore[assignment]
    mode: BdmTripMode = None  # type: ignore[assignment]
    accommodation_required: bool = None  # type: ignore[assignment]
    estimated_cost: TripEstimatedCost = None  # type: ignore[assignment]
    remarks: TripRemarks = None


class BdmTripReject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: TripReason


class BdmTripExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: BdmExpenseCategory
    amount: TripExpenseAmount
    expense_date: TripExpenseDate
    note: TripNote = None


class BdmTripExpenseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: BdmExpenseCategory = None  # type: ignore[assignment]
    amount: TripExpenseAmount = None  # type: ignore[assignment]
    expense_date: TripExpenseDate = None  # type: ignore[assignment]
    note: TripNote = None


class BdmPersonRef(BaseModel):
    id: UUID
    full_name: str


class BdmTripExpenseOut(BaseModel):
    id: UUID
    category: str
    amount: Decimal
    expense_date: date
    note: str | None


class BdmTripRow(BaseModel):
    id: UUID
    code: str
    bdm: BdmPersonRef
    travel_date: date
    return_date: date
    from_place: str
    to_place: str
    mode: str
    accommodation_required: bool
    estimated_cost: Decimal
    actual_cost: Decimal
    currency: str
    approval_status: str
    travel_status: str
    submitted_at: datetime | None


class BdmTripOut(BdmTripRow):
    purpose: str
    remarks: str | None
    rejection_reason: str | None
    decided_by: BdmPersonRef | None
    decided_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    expenses: list[BdmTripExpenseOut]
    can_edit: bool
    can_submit: bool
    can_withdraw: bool
    can_start: bool
    can_complete: bool
    can_cancel: bool
    can_add_expense: bool
    can_decide: bool


class BdmTripPage(BaseModel):
    items: list[BdmTripRow]
    total: int
    limit: int
    offset: int


# --- bdm-002 (DEC-SCOPE-060): organization CRM core ------------------------------------------------------------------------
BdmOrgType = Literal["college", "university", "agent", "school", "corporate", "training_institute", "other"]
BdmContactRole = Literal["principal", "dean", "hod", "placement_officer", "counselor", "management", "owner", "other"]
BDM_ORG_LABELS = {
    "name": "Organization name",
    "city": "City",
    "state": "State",
    "phone": "Phone",
    "email": "Email",
    "website": "Website",
    "courses_interested": "Courses interested",
    "designation": "Designation",
}
BDM_ORG_FIELDS = ("org_type", "name", "city", "state", "phone", "email", "website", "existing_partner", "courses_interested", "student_count")
_BDM_PHONE = re.compile(r"[0-9+()\- ]+")
_BDM_WEBSITE = re.compile(r"https?://\S+", re.IGNORECASE)
_BDM_SCHEME = re.compile(r"[a-z][a-z0-9+.-]*:", re.IGNORECASE)  # "javascript:", "mailto:", "ftp:" ...
_BDM_BARE_SITE = re.compile(r"[^\s/:]+\.[^\s/:]+(/\S*)?")  # "stjoseph.edu", "www.mary.ac.in/admissions"
BDM_MAX_CONTACTS = 20


def _bdm_org_text(value: str | None, info: ValidationInfo) -> str | None:
    """bdm-001's text rule (no control characters, blank -> None) plus the per-field shape checks (spec §5.1, §12.3)."""
    label = BDM_ORG_LABELS.get(info.field_name, info.field_name)
    if value is not None and _BDM_CONTROL.search(value):
        raise ValueError(f"{label} contains invalid characters")
    if not value:
        return None
    if info.field_name == "email":
        if not _EMAIL_SHAPE.fullmatch(value):
            raise ValueError("Enter a valid email address")
        return value.lower()
    if info.field_name == "phone" and not _BDM_PHONE.fullmatch(value):
        raise ValueError("Phone may contain only digits, spaces and + - ( )")
    if info.field_name == "website" and not _BDM_WEBSITE.fullmatch(value):  # http(s) only: no javascript:/data: hrefs (spec §12.3)
        raise ValueError("Website must start with http:// or https://" if _BDM_SCHEME.match(value) else "Enter a website such as stjoseph.edu")
    return value


def _bdm_website_prefix(value):
    """Browser QA-05: a bare domain is what people type, so it becomes https://. This runs BEFORE the length check, so the 255 limit
    counts the stored form."""
    if isinstance(value, str) and _BDM_BARE_SITE.fullmatch(value.strip()):
        return f"https://{value.strip()}"
    return value


def _bdm_org_required(value: str, info: ValidationInfo) -> str:
    value = _bdm_org_text(value, info)
    if value is None:
        raise ValueError(f"{BDM_ORG_LABELS[info.field_name]} is required")
    return value


def _bdm_contact_name(value: str) -> str:
    if _BDM_CONTROL.search(value):
        raise ValueError("Contact name contains invalid characters")
    if not value:
        raise ValueError("Contact name is required")
    return value


def _bdm_org_optional(max_length: int):
    return Annotated[Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)] | None, AfterValidator(_bdm_org_text)]


def _bdm_org_mandatory(max_length: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length), AfterValidator(_bdm_org_required)]


BdmOrgName = _bdm_org_mandatory(200)
BdmOrgCity = _bdm_org_mandatory(120)
BdmOrgShort = _bdm_org_optional(120)
BdmOrgPhone = _bdm_org_optional(30)
BdmOrgLong = _bdm_org_optional(255)
BdmOrgCourses = _bdm_org_optional(1000)
BdmOrgWebsite = Annotated[_bdm_org_optional(255), BeforeValidator(_bdm_website_prefix)]
BdmContactName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200), AfterValidator(_bdm_contact_name)]


def _bdm_student_count(value, handler):
    """Browser QA-04: the strict whole-number rule stays; every way it fails reads as one plain sentence."""
    try:
        return handler(value)
    except ValidationError:
        raise ValueError("Number of students must be a whole number from 0 to 1,000,000") from None


BdmStudentCount = Annotated[Annotated[StrictInt, Field(ge=0, le=1_000_000)] | None, WrapValidator(_bdm_student_count)]


class BdmContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: BdmContactName
    designation: BdmOrgShort = None
    role: BdmContactRole | None = None
    phone: BdmOrgPhone = None
    email: BdmOrgLong = None
    is_primary: StrictBool = False


class BdmContactUpdate(BaseModel):
    """Omitted = unchanged; a sent null on `name`/`is_primary` fails the non-nullable type (bdm-001's PATCH idiom)."""

    model_config = ConfigDict(extra="forbid")
    name: BdmContactName = None
    designation: BdmOrgShort = None
    role: BdmContactRole | None = None
    phone: BdmOrgPhone = None
    email: BdmOrgLong = None
    is_primary: StrictBool = None


def _bdm_contacts(contacts: list[BdmContactIn]) -> list[BdmContactIn]:
    if not contacts:
        raise ValueError("Add at least one contact")
    if len(contacts) > BDM_MAX_CONTACTS:
        raise ValueError(f"An organization can have at most {BDM_MAX_CONTACTS} contacts")
    if sum(c.is_primary for c in contacts) > 1:
        raise ValueError("Only one contact can be primary")
    return contacts


class BdmOrganizationCreate(BaseModel):
    """spec §5.1 / C13: type, name, city and >=1 contact are required. Server-owned fields (code, bdm_type, assignee, archive) are
    unknown fields here, so a client can never set them (§12.3 mass assignment)."""

    model_config = ConfigDict(extra="forbid")
    org_type: BdmOrgType
    name: BdmOrgName
    city: BdmOrgCity
    state: BdmOrgShort = None
    phone: BdmOrgPhone = None
    email: BdmOrgLong = None
    website: BdmOrgWebsite = None
    existing_partner: StrictBool = False
    courses_interested: BdmOrgCourses = None
    student_count: BdmStudentCount = None
    contacts: Annotated[list[BdmContactIn], AfterValidator(_bdm_contacts)]
    confirm_duplicate: StrictBool = False


class BdmOrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    org_type: BdmOrgType = None
    name: BdmOrgName = None
    city: BdmOrgCity = None
    state: BdmOrgShort = None
    phone: BdmOrgPhone = None
    email: BdmOrgLong = None
    website: BdmOrgWebsite = None
    existing_partner: StrictBool = None
    courses_interested: BdmOrgCourses = None
    student_count: BdmStudentCount = None
    confirm_duplicate: StrictBool = False


class BdmOrganizationAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bdm_user_id: UUID


class BdmOrgPerson(BaseModel):
    id: UUID
    full_name: str
    active: bool


class BdmContactOut(BaseModel):
    id: UUID
    name: str
    designation: str | None
    role: str | None
    phone: str | None
    email: str | None
    is_primary: bool


class BdmOrgPrimaryContact(BaseModel):
    name: str
    designation: str | None
    phone: str | None
    email: str | None


class BdmOrgPermissions(BaseModel):
    can_edit: bool
    can_archive: bool
    can_restore: bool
    can_reassign: bool


class BdmOrganizationRow(BaseModel):
    id: UUID
    code: str
    name: str
    org_type: str
    bdm_type: str
    city: str
    state: str | None
    existing_partner: bool
    assigned_bdm: BdmOrgPerson
    primary_contact: BdmOrgPrimaryContact | None
    archived: bool
    last_meeting_at: datetime | None  # bdm-006 fills these; always null until then (AC6)
    next_meeting_at: datetime | None
    permissions: BdmOrgPermissions


class BdmOrganizationOut(BdmOrganizationRow):
    phone: str | None
    email: str | None
    website: str | None
    courses_interested: str | None
    student_count: int | None
    contacts: list[BdmContactOut]
    created_by_name: str
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BdmOrganizationPage(BaseModel):
    items: list[BdmOrganizationRow]
    total: int
    limit: int
    offset: int


class BdmOrganizationEnvelope(BaseModel):
    organization: BdmOrganizationOut

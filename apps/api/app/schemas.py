import math
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal
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
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    WrapValidator,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.models import (
    APPLICATION_STATUSES,
    APPOINTMENT_MODES,
    BDM_ACTIVITY_DIRECTIONAL,
    BDM_APPOINTMENT_ALL_OUTCOMES,
    BDM_APPOINTMENT_ALL_TYPES,
    BDM_APPOINTMENT_STATUSES,
    BDM_GRADE_MAX,
    BDM_GRADE_MIN,
    BDM_MEETING_REQUEST_TYPES,
    BDM_MOU_SETTABLE,
    BDM_MOU_STATUSES,
    BDM_STAFF_MAX,
    BDM_TARGET_MAX,
    CANDIDATE_SKILL_LEVELS,
    CANDIDATE_SKILL_SOURCES,
    CANDIDATE_SKILL_STATUSES,
    CANDIDATE_STATUSES,
    CONTACT_CHANNELS,
    COURSE_LEVELS,
    GENDERS,
    INSTITUTION_TYPES,
    JOB_EMPLOYMENT_TYPES,
    JOB_PRIORITIES,
    JOB_SHIFTS,
    JOB_STATUSES,
    JOB_WORK_MODES,
    LEAD_APPOINTMENT_TYPE_LABELS,
    LEAD_CALL_MAX_SECONDS,
    LEAD_CALL_OUTCOMES,
    LEAD_CALL_TYPES,
    LEAD_FOLLOW_UP_REASONS,
    LEAD_PRIORITIES,
    PARTNERSHIP_POTENTIALS,
    QUAL_MODES,
    QUAL_PASSPORT,
    QUAL_SKILL_LEVELS,
    QUAL_STUDY_LEVELS,
    RANKING_SYSTEMS,
    RECRUITER_CALL_DIRECTIONS,
    RECRUITER_CALL_MAX_SECONDS,
    RECRUITER_CALL_OUTCOMES,
    RECRUITER_FOLLOW_UP_REASONS,
    RECRUITER_MEETING_TYPES,
    RELATIONSHIP_STRENGTHS,
    TEL_TARGET_KPIS,
    UNIVERSITY_OWNERSHIP_TYPES,
    UNIVERSITY_PRIORITIES,
    UNIVERSITY_RELATIONSHIPS,
)
from app.notifications.phone import normalise_phone
from app.services.agent_visa import VISA_CASE_STAGES
from app.tel_content_kinds import ASSET_KINDS as TEL_ASSET_KINDS
from app.tel_sources import TEL_SOURCES


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


class PlacementPoolOptIn(BaseModel):
    """rec-010 (spec §4): the consent version the student read. There is no user id: a student only ever acts for themselves, so any
    other key is ignored."""

    consent_version: str = Field(min_length=1, max_length=20)


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


class OverseasApplicationCounselorAssign(BaseModel):
    """AGN-023 (DEC-SCOPE-090 H8): swap only -- a counselor is required; null or missing is a 422."""

    counselor_id: UUID


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


class CounselorAgencyVisaUpdate(BaseModel):
    """AGN-023 (DEC-SCOPE-090 H4, final review I2): an EduSphere counselor's change to an agency visa case (PATCH /overseas/visa/{id}),
    typed so a bad body is a 422 and never a stored string. The checklist has the agency's limits (`AgentVisaUpdate`); the reference
    has the VisaCase column's length. `decision` is refused by the route before this model (the agency records it); any other unknown
    key is a 422. As on the agency route an absent key is unchanged and an explicit null clears the appointment date."""

    model_config = {"extra": "forbid"}
    status: str | None = Field(default=None, max_length=50)
    checklist: list[AgentDocumentType] | None = Field(default=None, max_length=8)
    appointment_date: date | None = None
    tracking_reference: str | None = Field(default=None, max_length=120)

    @field_validator("checklist")
    @classmethod
    def _checklist(cls, value):
        return _visa_checklist(value)

    @field_validator("appointment_date")
    @classmethod
    def _appointment_date(cls, value):
        return _application_date(value)


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


# --- AGN-020 (DEC-SCOPE-067; spec §5.3): one column-driven shape for every report. Codes, slugs and names only -- no ids. ---


class AgentReportColumn(BaseModel):
    key: str
    label: str
    numeric: bool = False


class AgentReportOption(BaseModel):
    value: str  # a slug, a member code, an intake key or a status -- never an id
    label: str


class AgentReportOut(BaseModel):
    """`items/total/limit/offset` follow the codebase's `Page` convention; a summary returns every group (`limit = total`) and a
    `totals` row. Every item's keys are exactly the column keys."""

    kind: str
    title: str
    scope: Literal["agency", "own"]
    columns: list[AgentReportColumn]
    items: list[dict[str, str | int | None]]
    totals: dict[str, str | int | None] | None
    total: int
    limit: int
    offset: int
    options: dict[str, list[AgentReportOption]]
    as_of: datetime


class AgentFunnelOut(BaseModel):
    """AGN-019 (DEC-SCOPE-066 P3): distinct students who reached each stage or a later one, so the stages never increase."""

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
    source: Literal[TEL_SOURCES] = "website"  # tel-003 (DEC-SCOPE-077): one of the 13 EVID-019 §2 sources, else 422
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


class SchoolCreateIn(SchoolCreate):
    """The single create's body (SCH-003). bdm-018 (DEC-SCOPE-085 §5.5): optionally resolves a pending onboarding request in the same
    transaction. A subclass, so ENH-029's bulk template (`SchoolCreate.model_fields`) does not gain the column."""

    bdm_onboarding_request_id: UUID | None = None


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


class SchoolLinkedBdm(BaseModel):
    """bdm-018 (H1): the School's BDM, derived from the linked organization's assignee; admin routes only."""

    full_name: str
    active: bool
    organization_code: str


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
    linked_bdm: SchoolLinkedBdm | None = None


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


class BdmManagerRow(BdmManagerOption):
    """bdm-025: /admin/bdm-managers only (the telecaller picker keeps BdmManagerOption) -- BDMs reporting to this manager, active or
    not, for the BDM managers card."""

    bdm_count: int


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


class BdmManagerRowPage(BaseModel):
    items: list[BdmManagerRow]
    total: int
    limit: int
    offset: int


# --- bdm-025: deactivation, portfolio handover, manager deactivation (DEC-SCOPE-082; spec §5) ---


class BdmDeactivate(BaseModel):
    """AC1: deactivating a BDM always says who takes over -- another BDM (`reassign`) or nobody yet (`leave`, handed over later)."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["reassign", "leave"]
    reassign_to: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def _mode_given(cls, data):
        if isinstance(data, dict) and data.get("mode") is None:
            raise ValueError("Choose who takes over this BDM's open work")
        return data

    @model_validator(mode="after")
    def _target_matches_mode(self):
        if self.mode == "reassign" and self.reassign_to is None:
            raise ValueError("Choose the BDM who takes over")
        if self.mode == "leave" and self.reassign_to is not None:
            raise ValueError("Keeping the work with this BDM takes no target")
        return self


class BdmHandover(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reassign_to: UUID


class BdmManagerDeactivate(BaseModel):
    """`reassign_to` is required only while BDMs report to the manager (checked by the route, which knows the team)."""

    model_config = ConfigDict(extra="forbid")
    reassign_to: UUID | None = None


class BdmPortfolio(BaseModel):
    organizations: int
    appointments: int
    tasks: int
    trips: int


class BdmMoved(BaseModel):
    organizations: int
    appointments: int
    tasks: int


class BdmDeactivateOut(BaseModel):
    id: UUID
    active: bool
    mode: Literal["reassign", "leave"]
    moved: BdmMoved
    trips_cancelled: int


class BdmHandoverOut(BaseModel):
    id: UUID
    moved: BdmMoved


class BdmManagerDeactivateOut(BaseModel):
    id: UUID
    active: bool
    moved_bdms: int


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


def _trip_text(pattern: re.Pattern, required: bool, labels: dict[str, str] = BDM_TRIP_FIELD_LABELS):
    def check(value: str | None, info: ValidationInfo) -> str | None:
        field = info.field_name or ""
        label = labels.get(field, field)
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


class BdmTripOrgRef(BaseModel):
    id: UUID
    name: str


class BdmTripItineraryItem(BaseModel):
    """bdm-011: one linked appointment on the trip page (§4: time, organization, meeting, status)."""

    id: UUID
    code: str
    starts_at: datetime
    duration_minutes: int
    appointment_type: str
    status: str
    organization: BdmTripOrgRef
    expected_leads: int | None
    expected_revenue: Decimal | None


class BdmTripMetrics(BaseModel):
    """bdm-011 (College §F, DEC-SCOPE-092 L1/L3): null = nothing to compute from; `actual_revenue` is not tracked yet (D17)."""

    meetings_planned: int
    meetings_completed: int
    estimated_cost: Decimal
    actual_cost: Decimal
    cost_per_completed_meeting: Decimal | None
    expected_leads: int | None
    expected_revenue: Decimal | None
    actual_leads: int
    actual_revenue: Decimal | None


class BdmTripOut(BdmTripRow):
    itinerary: list[BdmTripItineraryItem]
    metrics: BdmTripMetrics
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
    "address": "Address",
    "country": "Country",
    "territory": "Territory",
    "affiliation": "University / affiliation",
    "courses": "Courses",
    "source": "Source",
    "staff_count": "Number of staff",
    "board": "Board",
    "school_type": "School type",
    "grade_from": "Lowest grade",
    "grade_to": "Highest grade",
    "college_type": "College type",
}
BDM_MULTILINE_FIELDS = frozenset({"address", "courses", "courses_interested"})  # bdm-003 P14: line breaks kept
BDM_ORG_FIELDS = ("org_type", "name", "city", "state", "address", "phone", "email", "website", "existing_partner", "courses_interested", "student_count")
_BDM_PHONE = re.compile(r"[0-9+()\- ]+")
_BDM_WEBSITE = re.compile(r"https?://\S+", re.IGNORECASE)
_BDM_SCHEME = re.compile(r"[a-z][a-z0-9+.-]*:", re.IGNORECASE)  # "javascript:", "mailto:", "ftp:" ...
_BDM_BARE_SITE = re.compile(r"[^\s/:]+\.[^\s/:]+(/\S*)?")  # "stjoseph.edu", "www.mary.ac.in/admissions"
_BDM_CONTROL_MULTILINE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")  # bdm-003 P14: like _BDM_CONTROL, but a line break (\n) is allowed
BDM_MAX_CONTACTS = 20


def _bdm_org_text(value: str | None, info: ValidationInfo) -> str | None:
    """bdm-001's text rule (no control characters, blank -> None) plus the per-field shape checks (spec §5.1, §12.3). A multi-line field
    (bdm-003 P14) also allows a line break."""
    label = BDM_ORG_LABELS.get(info.field_name, info.field_name)
    control = _BDM_CONTROL_MULTILINE if info.field_name in BDM_MULTILINE_FIELDS else _BDM_CONTROL
    if value is not None and control.search(value):
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


def _bdm_newlines(value):
    """Before the length check, so the limit counts the stored form (as _bdm_website_prefix)."""
    return value.replace("\r\n", "\n").replace("\r", "\n") if isinstance(value, str) else value


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


def _bdm_org_optional(max_length: int, *, multiline: bool = False):
    """`multiline` (bdm-003 P14): \\r\\n / \\r become \\n before the length check, so the limit counts the stored form. The field must
    also be in BDM_MULTILINE_FIELDS for _bdm_org_text to accept the line break."""
    text = Annotated[Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)] | None, AfterValidator(_bdm_org_text)]
    return Annotated[text, BeforeValidator(_bdm_newlines)] if multiline else text


def _bdm_org_mandatory(max_length: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length), AfterValidator(_bdm_org_required)]


BdmOrgName = _bdm_org_mandatory(200)
BdmOrgCity = _bdm_org_mandatory(120)
BdmOrgShort = _bdm_org_optional(120)
BdmOrgPhone = _bdm_org_optional(30)
BdmOrgLong = _bdm_org_optional(255)
BdmOrgMedium = _bdm_org_optional(200)
BdmOrgCourses = _bdm_org_optional(1000, multiline=True)  # courses_interested and the College `courses`
BdmOrgAddress = _bdm_org_optional(500, multiline=True)
BdmOrgWebsite = Annotated[_bdm_org_optional(255), BeforeValidator(_bdm_website_prefix)]
BdmContactName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200), AfterValidator(_bdm_contact_name)]


def _bdm_whole_number(message: str, low: int, high: int):
    """Browser QA-04: strict whole numbers; every way one fails reads as one plain sentence."""

    def wrap(value, handler):
        try:
            return handler(value)
        except ValidationError:
            raise ValueError(message) from None

    return Annotated[Annotated[StrictInt, Field(ge=low, le=high)] | None, WrapValidator(wrap)]


BdmStudentCount = _bdm_whole_number("Number of students must be a whole number from 0 to 1,000,000", 0, 1_000_000)
BdmStaffCount = _bdm_whole_number(f"Number of staff must be a whole number from 0 to {BDM_STAFF_MAX:,}", 0, BDM_STAFF_MAX)
BdmGrade = _bdm_whole_number("Grade must be Nursery, LKG, UKG or 1 to 12", BDM_GRADE_MIN, BDM_GRADE_MAX)
BdmOrgSource = Literal["referral", "website", "event", "cold_call", "walk_in", "other"]
BdmSchoolBoard = SchoolBoard  # ENH-009's values by construction: bdm-018 copies the board onto `schools.board`
BdmSchoolType = Literal["private", "government", "aided", "international", "other"]
BdmCollegeType = Literal["engineering", "arts_science", "management", "medical", "polytechnic", "other"]


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


class BdmOrgProfileIn(BaseModel):
    """bdm-003 (DEC-SCOPE-065, spec §5.1): the type-specific fields. Omitted = not sent; null = clear. Which keys an org_type accepts is
    checked by services.bdm_organizations.check_profile (it needs the effective type); unknown keys -- the live agent figures commission,
    students, applications, enrollments and master_login among them -- are refused here (AC4)."""

    model_config = ConfigDict(extra="forbid")
    country: BdmOrgShort = Field(None, description="Agent: country (free text).")
    territory: BdmOrgShort = Field(None, description="Agent: territory (free text).")
    source: BdmOrgSource | None = Field(None, description="Agent: how the agency was found.")
    staff_count: BdmStaffCount = Field(None, description="Agent: number of staff, entered by the BDM (0-100000).")
    board: BdmSchoolBoard | None = Field(None, description="School: board, ENH-009's values.")
    school_type: BdmSchoolType | None = Field(None, description="School: school type.")
    grade_from: BdmGrade = Field(None, description="School: lowest grade. -2 Nursery, -1 LKG, 0 UKG, then 1-12.")
    grade_to: BdmGrade = Field(None, description="School: highest grade, same codes; not below grade_from.")
    affiliation: BdmOrgMedium = Field(None, description="College/University: university or affiliation (free text).")
    college_type: BdmCollegeType | None = Field(None, description="College/University: college type.")
    courses: BdmOrgCourses = Field(None, description="College/University: courses the college teaches; line breaks allowed.")


class BdmOrganizationCreate(BaseModel):
    """spec §5.1 / C13: type, name, city and >=1 contact are required. Server-owned fields (code, bdm_type, assignee, archive) are
    unknown fields here, so a client can never set them (§12.3 mass assignment)."""

    model_config = ConfigDict(extra="forbid")
    org_type: BdmOrgType
    name: BdmOrgName
    city: BdmOrgCity
    state: BdmOrgShort = None
    address: BdmOrgAddress = None
    phone: BdmOrgPhone = None
    email: BdmOrgLong = None
    website: BdmOrgWebsite = None
    existing_partner: StrictBool = False
    courses_interested: BdmOrgCourses = None
    student_count: BdmStudentCount = None
    profile: BdmOrgProfileIn | None = None
    contacts: Annotated[list[BdmContactIn], AfterValidator(_bdm_contacts)]
    university_id: UUID | None = None  # upc-004 UD8: University organizations only
    confirm_duplicate: StrictBool = False


class BdmOrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    org_type: BdmOrgType = None
    name: BdmOrgName = None
    city: BdmOrgCity = None
    state: BdmOrgShort = None
    address: BdmOrgAddress = None
    phone: BdmOrgPhone = None
    email: BdmOrgLong = None
    website: BdmOrgWebsite = None
    existing_partner: StrictBool = None
    courses_interested: BdmOrgCourses = None
    student_count: BdmStudentCount = None
    profile: BdmOrgProfileIn = None  # omitted = unchanged; an explicit null is a 422 (bdm-001's PATCH idiom)
    university_id: UUID | None = None  # upc-004 UD9: omitted = unchanged; null unlinks
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


class BdmAgentProfileOut(BaseModel):
    kind: Literal["agent"]
    country: str | None
    territory: str | None
    source: str | None
    staff_count: int | None


class BdmSchoolProfileOut(BaseModel):
    kind: Literal["school"]
    board: str | None
    school_type: str | None
    grade_from: int | None
    grade_to: int | None


class BdmCollegeProfileOut(BaseModel):
    kind: Literal["college"]
    affiliation: str | None
    college_type: str | None
    courses: str | None


BdmOrgProfileOut = Annotated[BdmAgentProfileOut | BdmSchoolProfileOut | BdmCollegeProfileOut, Field(discriminator="kind")]


# --- bdm-004 (DEC-SCOPE-071, spec §6.1): the pipeline on the organization detail ------------------------------------------------
class BdmPipelineStepOut(BaseModel):
    key: str
    label: str
    kind: Literal["manual", "live", "volume"]
    state: Literal["done", "current", "upcoming", "awaiting_handover", "not_tracked"]
    count: int | None = None  # bdm-019 A4: a volume step's live count once an agency is linked


class BdmPipelineLost(BaseModel):
    at: datetime
    reason: str


class BdmOrgPipelineOut(BaseModel):
    stage: str
    stage_label: str
    lost: BdmPipelineLost | None
    agent_status: str | None  # S4: Agent organizations only
    steps: list[BdmPipelineStepOut]


# --- bdm-018 (DEC-SCOPE-085, spec §5.7): the onboarding handover on the organization detail -------------------------------------
class BdmOnboardingRequestRef(BaseModel):
    id: UUID
    status: Literal["pending", "completed", "rejected"]
    created_at: datetime
    resolved_at: datetime | None
    reject_reason: str | None


class BdmOnboardingSchoolRef(BaseModel):
    name: str
    school_code: str | None


class BdmOnboardingAgentCounts(BaseModel):
    students: int
    applications: int
    enrollments: int


class BdmOnboardingAgentRef(BaseModel):
    """bdm-019 A7: a linked agency as a BDM sees it -- aggregates only, never a member or student (AC4)."""

    name: str
    prefix: str
    status: str
    master_login: bool
    staff_count: int
    counts: BdmOnboardingAgentCounts


class BdmOrgOnboardingOut(BaseModel):
    request: BdmOnboardingRequestRef | None  # the latest request
    school: BdmOnboardingSchoolRef | None
    agent: BdmOnboardingAgentRef | None = None  # bdm-019: Agent organizations
    can_request: bool


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
    last_meeting_at: datetime | None  # bdm-006: computed from appointments (spec §5.6); null when none
    next_meeting_at: datetime | None
    permissions: BdmOrgPermissions


class BdmOrganizationOut(BdmOrganizationRow):
    phone: str | None
    email: str | None
    website: str | None
    address: str | None
    courses_interested: str | None
    student_count: int | None
    profile: BdmOrgProfileOut | None  # null for corporate / training_institute / other (spec §5.1)
    pipeline: BdmOrgPipelineOut  # bdm-004: detail only; list rows are unchanged
    onboarding: BdmOrgOnboardingOut | None = None  # bdm-018: School organizations; bdm-019: Agent organizations too
    contacts: list[BdmContactOut]
    university: "BdmOrgUniversityRef | None" = None  # upc-004 UD10: the linked master record, read-only
    created_by_name: str
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BdmOrgUniversityRef(BaseModel):
    id: UUID
    university_code: str
    name: str
    country_name: str
    city: str
    primary_manager_name: str | None


class BdmOrganizationPage(BaseModel):
    items: list[BdmOrganizationRow]
    total: int
    limit: int
    offset: int


class BdmOrganizationEnvelope(BaseModel):
    organization: BdmOrganizationOut


# --- bdm-004 (DEC-SCOPE-071, spec §6.1): stage moves, Lost / Revive, history and the pipeline view -------------------------------
BdmStageKey = Annotated[str, StringConstraints(pattern=r"^[a-z_]{1,40}$")]
# P14 / TripNote: trimmed, at most 500 after \r\n -> \n, line breaks and tabs allowed, other control characters refused, blank -> None.
BdmPipelineNote = Annotated[TripNote, BeforeValidator(_bdm_newlines)]
BdmPipelineReason = Annotated[
    Annotated[Annotated[str, _trimmed(500)], AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, True))], BeforeValidator(_bdm_newlines)
]


class BdmStageMove(BaseModel):
    """S6: `from_stage` is the stage the form was showing -- a different stored stage is 409 `stage_changed`."""

    model_config = ConfigDict(extra="forbid")
    from_stage: BdmStageKey
    to_stage: BdmStageKey
    note: BdmPipelineNote = None


class BdmLostIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmPipelineReason


class BdmReviveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmPipelineReason


class BdmStageEventOut(BaseModel):
    id: UUID
    kind: Literal["move", "lost", "revived"]
    from_stage: str
    from_label: str
    to_stage: str
    to_label: str
    note: str | None
    actor: BdmPersonRef
    created_at: datetime


class BdmStageEventPage(BaseModel):
    items: list[BdmStageEventOut]
    total: int
    limit: int
    offset: int


class BdmPipelineStageCount(BaseModel):
    key: str
    label: str
    kind: Literal["manual", "live", "volume"]
    count: int | None  # null for live / volume steps (S2, S3)


class BdmPipelineItem(BaseModel):
    id: UUID
    code: str
    name: str
    city: str
    org_type: str
    assigned_bdm: BdmOrgPerson
    stage: str
    stage_label: str
    lost: bool


class BdmPipelinePage(BaseModel):
    bdm_type: BdmType
    stages: list[BdmPipelineStageCount]
    lost_count: int
    items: list[BdmPipelineItem]
    total: int
    limit: int
    offset: int


# --- bdm-005 (DEC-SCOPE-078, spec §6.1): MoU tracking ----------------------------------------------------------------------------
MOU_FIELD_LABELS = {
    "reference": "Reference",
    "notes": "Notes",
    "proposal_sent_on": "Proposal sent date",
    "signed_on": "Signed date",
    "valid_from": "Valid-from date",
    "valid_until": "Valid-until date",
}
BdmMouStatusIn = Literal[BDM_MOU_SETTABLE]  # M2: `expired` is derived, never accepted
BdmMouStatus = Literal[BDM_MOU_STATUSES]


def _mou_date(label: str):
    """bdm-010's YYYY-MM-DD rule (plain words, a 4-digit year); blank or null clears the date."""
    parse = _trip_date(label)
    return lambda value: None if value is None or (isinstance(value, str) and not value.strip()) else parse(value)


BdmMouReference = Annotated[Annotated[str, _trimmed(100)] | None, AfterValidator(_trip_text(_BDM_CONTROL, False, MOU_FIELD_LABELS))]
BdmMouNotes = Annotated[
    Annotated[Annotated[str, _trimmed(2000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, MOU_FIELD_LABELS))],
    BeforeValidator(_bdm_newlines),
]
BdmMouProposalSentOn = Annotated[date | None, BeforeValidator(_mou_date("proposal sent date"))]
BdmMouSignedOn = Annotated[date | None, BeforeValidator(_mou_date("signed date"))]
BdmMouValidFrom = Annotated[date | None, BeforeValidator(_mou_date("valid-from date"))]
BdmMouValidUntil = Annotated[date | None, BeforeValidator(_mou_date("valid-until date"))]


class BdmMouCreate(BaseModel):
    """A first MoU or a renewal (M6). Owner, organization, current flag and document are server-owned (`extra="forbid"`); the date
    rules run in the service on the merged state."""

    model_config = ConfigDict(extra="forbid")
    status: BdmMouStatusIn = "prospect"
    proposal_sent_on: BdmMouProposalSentOn = None
    signed_on: BdmMouSignedOn = None
    valid_from: BdmMouValidFrom = None
    valid_until: BdmMouValidUntil = None
    reference: BdmMouReference = None
    notes: BdmMouNotes = None


class BdmMouUpdate(BaseModel):
    """Partial: an omitted field is unchanged, `null` clears it. A status change carries `from_status` -- the (effective) status the
    form was showing; a different one is 409 `mou_status_changed` (the bdm-004 `from_stage` rule)."""

    model_config = ConfigDict(extra="forbid")
    status: BdmMouStatusIn | None = None
    from_status: BdmMouStatus | None = Field(default=None, validate_default=True)
    expected_updated_at: datetime | None = None  # QA5-01: the version the form showed; a newer stored one is 409 `mou_changed`
    proposal_sent_on: BdmMouProposalSentOn = None
    signed_on: BdmMouSignedOn = None
    valid_from: BdmMouValidFrom = None
    valid_until: BdmMouValidUntil = None
    reference: BdmMouReference = None
    notes: BdmMouNotes = None

    @field_validator("status")
    @classmethod
    def _status_not_null(cls, value):  # runs only when sent: an explicit null is not "unchanged"
        if value is None:
            raise PydanticCustomError("mou_status", "Choose a status")
        return value

    @field_validator("from_status")
    @classmethod
    def _from_status_with_status(cls, value, info: ValidationInfo):
        if info.data.get("status") is not None and value is None:
            raise PydanticCustomError("mou_from_status", "Send the status the form was showing")
        return value


class BdmMouOrgRef(BaseModel):
    id: UUID
    code: str
    name: str
    bdm_type: BdmType


class BdmMouDocumentOut(BaseModel):
    name: str | None
    content_type: str
    uploaded_at: datetime


class BdmMouPermissions(BaseModel):
    can_edit: bool
    can_upload: bool
    can_renew: bool


class BdmMouStageRef(BaseModel):
    key: str
    label: str


class BdmMouRow(BaseModel):
    id: UUID
    organization: BdmMouOrgRef
    assigned_bdm: BdmPersonRef
    status: BdmMouStatus
    status_label: str
    status_changed_at: datetime
    signed_on: date | None
    valid_until: date | None
    reference: str | None
    has_document: bool
    is_current: bool


class BdmMouOut(BdmMouRow):
    proposal_sent_on: date | None
    valid_from: date | None
    notes: str | None
    document: BdmMouDocumentOut | None
    expired_on: date | None
    created_by: BdmPersonRef
    permissions: BdmMouPermissions
    pipeline_on_sign: BdmMouStageRef | None
    created_at: datetime
    updated_at: datetime


class BdmMouEnvelope(BaseModel):
    mou: BdmMouOut


class BdmOrgMouOut(BaseModel):
    current: BdmMouOut | None
    can_start: bool


class BdmMouPage(BaseModel):
    items: list[BdmMouRow]
    total: int
    limit: int
    offset: int


class BdmMouEventOut(BaseModel):
    id: UUID
    kind: Literal["created", "status", "updated", "document", "renewed"]
    from_status: BdmMouStatus | None
    from_label: str | None
    to_status: BdmMouStatus
    to_label: str
    changed: list[str]
    actor: BdmPersonRef
    created_at: datetime


class BdmMouEventPage(BaseModel):
    items: list[BdmMouEventOut]
    total: int
    limit: int
    offset: int


# --- bdm-006 (DEC-SCOPE-068, spec §5.1): appointments ----------------------------------------------------------------------------
BdmAppointmentType = Literal[BDM_APPOINTMENT_ALL_TYPES]
BdmAppointmentOutcome = Literal[BDM_APPOINTMENT_ALL_OUTCOMES]
BdmAppointmentStatus = Literal[BDM_APPOINTMENT_STATUSES]
BDM_APPOINTMENT_LABELS = {"location": "Location", "purpose": "Purpose", "remarks": "Remarks", "reason": "Reason"}
BDM_APPOINTMENT_OPTIONAL_FIELDS = ("location", "purpose", "remarks", "expected_leads", "expected_revenue")


def _bdm_appt_text(value: str | None, info: ValidationInfo) -> str | None:
    """bdm-001's text rule: no control characters; blank -> None."""
    if value is not None and _BDM_CONTROL.search(value):
        raise ValueError(f"{BDM_APPOINTMENT_LABELS.get(info.field_name, info.field_name)} contains invalid characters")
    return value or None


def _bdm_appt_optional(max_length: int):
    return Annotated[Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)] | None, AfterValidator(_bdm_appt_text)]


def _bdm_appt_minute(value: datetime) -> datetime:
    """R-A7: compare what the UI shows -- seconds and microseconds are dropped; stored in UTC."""
    return value.replace(second=0, microsecond=0).astimezone(UTC)


def _bdm_appt_reason(value: str, info: ValidationInfo) -> str:
    """The text rule above, then required."""
    if (value := _bdm_appt_text(value, info)) is None:
        raise ValueError("Reason is required")
    return value


BdmApptStart = Annotated[AwareDatetime, AfterValidator(_bdm_appt_minute)]
BdmApptDuration = Annotated[StrictInt, Field(ge=15, le=720)]
BdmApptLeads = Annotated[StrictInt, Field(ge=0, le=1_000_000)] | None
BdmApptRevenue = Annotated[Decimal, Field(ge=0, le=Decimal("9999999999.99"), max_digits=12, decimal_places=2)] | None
BdmApptLocation = _bdm_appt_optional(255)
BdmApptPurpose = _bdm_appt_optional(1000)
BdmApptRemarks = _bdm_appt_optional(2000)
BdmApptReason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(_bdm_appt_reason)]


class BdmAppointmentCreate(BaseModel):
    """spec §5.1: server-owned fields (code, owner, status, outcome, the contact snapshot) are unknown fields here (§12.3)."""

    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    contact_id: UUID
    starts_at: BdmApptStart
    duration_minutes: BdmApptDuration = 60
    appointment_type: BdmAppointmentType
    location: BdmApptLocation = None
    purpose: BdmApptPurpose = None
    remarks: BdmApptRemarks = None
    expected_leads: BdmApptLeads = None
    expected_revenue: BdmApptRevenue = None
    trip_id: UUID | None = None  # bdm-011: one of the caller's trips covering the date (services/bdm_travel.linkable_trip)
    confirm_overlap: StrictBool = False


class BdmAppointmentUpdate(BaseModel):
    """Omitted = unchanged; a sent null on `contact_id` / `duration_minutes` / `appointment_type` fails the non-nullable type. The time
    changes only through reschedule and the status only through the actions."""

    model_config = ConfigDict(extra="forbid")
    contact_id: UUID = None
    duration_minutes: BdmApptDuration = None
    appointment_type: BdmAppointmentType = None
    location: BdmApptLocation = None
    purpose: BdmApptPurpose = None
    remarks: BdmApptRemarks = None
    expected_leads: BdmApptLeads = None
    expected_revenue: BdmApptRevenue = None
    trip_id: UUID | None = None  # bdm-011: null unlinks
    confirm_overlap: StrictBool = False


class BdmAppointmentReschedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: BdmApptStart
    duration_minutes: BdmApptDuration | None = None
    reason: _bdm_appt_optional(500) = None
    confirm_overlap: StrictBool = False


class BdmAppointmentReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmApptReason


# --- bdm-007 (DEC-SCOPE-070, spec §5): the meeting report ----------------------------------------------------------------------
BDM_REPORT_TEXT_FIELDS = ("discussion", "requirements", "opportunity", "next_action", "responsible_person")
BDM_REPORT_LABELS = {
    "discussion": "Discussion", "requirements": "Requirements", "opportunity": "Opportunity", "next_action": "Next action",
    "responsible_person": "Responsible person",
}


# Trimmed, at most N; line breaks only where the field is multi-line; blank -> None (or "<Label> is required"). Written as plain
# Annotated aliases (the TripRemarks form) so type checkers accept them as types.
_REPORT_MULTILINE = AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, BDM_REPORT_LABELS))
BdmReportDiscussion = Annotated[str, _trimmed(4000), AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, True, BDM_REPORT_LABELS))]
BdmReportLongText = Annotated[Annotated[str, _trimmed(2000)] | None, _REPORT_MULTILINE]
BdmReportNextAction = Annotated[Annotated[str, _trimmed(1000)] | None, _REPORT_MULTILINE]
BdmReportPerson = Annotated[Annotated[str, _trimmed(200)] | None, AfterValidator(_trip_text(_BDM_CONTROL, False, BDM_REPORT_LABELS))]
BdmFollowUpDate = Annotated[date, BeforeValidator(_trip_date("follow-up date"))]


class BdmMeetingReportCreate(BaseModel):
    """§5.1: the body of `POST /bdm/appointments/{id}/complete` -- filing the report is what completes the appointment. Author,
    `legacy`, `submitted_at` and the status are server-owned (unknown fields here)."""

    model_config = ConfigDict(extra="forbid")
    outcome: BdmAppointmentOutcome
    discussion: BdmReportDiscussion
    requirements: BdmReportLongText = None
    opportunity: BdmReportLongText = None
    next_action: BdmReportNextAction = None
    responsible_person: BdmReportPerson = None
    next_follow_up_on: BdmFollowUpDate | None = None


class BdmMeetingReportUpdate(BaseModel):
    """§5.2: omitted = unchanged; a sent null on `outcome` / `discussion` fails the non-nullable type; `next_follow_up_on: null` clears it."""

    model_config = ConfigDict(extra="forbid")
    outcome: BdmAppointmentOutcome = None
    discussion: BdmReportDiscussion | None = None
    requirements: BdmReportLongText = None
    opportunity: BdmReportLongText = None
    next_action: BdmReportNextAction = None
    responsible_person: BdmReportPerson = None
    next_follow_up_on: BdmFollowUpDate | None = None

    @field_validator("discussion")
    @classmethod
    def _discussion_not_null(cls, value: str | None) -> str:
        """Omitted = unchanged (the default is not validated); a sent null is refused -- a report always has a discussion."""
        if value is None:
            raise ValueError("Discussion is required")
        return value


class BdmMeetingReportOut(BaseModel):
    discussion: str | None
    requirements: str | None
    opportunity: str | None
    next_action: str | None
    responsible_person: str | None
    legacy: bool
    author: BdmOrgPerson
    submitted_at: datetime
    updated_at: datetime


class BdmFollowUpOut(BaseModel):
    id: UUID
    due_on: date
    status: str


class BdmAppointmentPermissions(BaseModel):
    can_edit: bool
    can_confirm: bool
    can_reschedule: bool
    can_cancel: bool
    can_no_show: bool
    can_complete: bool
    can_edit_report: bool


class BdmAppointmentOrgRef(BaseModel):
    id: UUID
    code: str
    name: str
    archived: bool


class BdmAppointmentRow(BaseModel):
    id: UUID
    code: str
    starts_at: datetime
    duration_minutes: int
    appointment_type: str
    status: str
    organization: BdmAppointmentOrgRef
    contact_name: str
    bdm: BdmOrgPerson
    outcome_pending: bool


class BdmAppointmentEventOut(BaseModel):
    from_status: str | None
    to_status: str
    old_starts_at: datetime | None
    new_starts_at: datetime | None
    reason: str | None
    actor_name: str
    created_at: datetime


class BdmAppointmentTripRef(BaseModel):
    """bdm-011: the linked trip, enough to show and link to it."""

    id: UUID
    code: str
    from_place: str
    to_place: str
    travel_date: date
    return_date: date
    approval_status: str
    travel_status: str


class BdmAppointmentOut(BdmAppointmentRow):
    trip: BdmAppointmentTripRef | None
    contact_id: UUID | None
    contact_designation: str | None
    contact_phone: str | None
    contact_email: str | None
    location: str | None
    purpose: str | None
    remarks: str | None
    outcome: str | None
    next_follow_up_on: date | None
    report: BdmMeetingReportOut | None
    follow_up: BdmFollowUpOut | None
    expected_leads: int | None
    expected_revenue: Decimal | None
    events: list[BdmAppointmentEventOut]
    permissions: BdmAppointmentPermissions
    created_at: datetime
    updated_at: datetime


class BdmAppointmentPage(BaseModel):
    items: list[BdmAppointmentRow]
    total: int
    limit: int
    offset: int


class BdmAppointmentEnvelope(BaseModel):
    appointment: BdmAppointmentOut


# --- bdm-009: activity log (DEC-SCOPE-069; docs/superpowers/specs/2026-10-03-bdm-009-activity-log-design.md §5.1) ---

BdmActivityChannel = Literal["call", "whatsapp", "email", "visit", "meeting", "other"]
BdmActivityDirection = Literal["outbound", "inbound"]
ACTIVITY_DIRECTION_REQUIRED = "Choose outgoing or incoming for a call, WhatsApp or email"
ACTIVITY_DIRECTION_REFUSED = "Direction applies only to calls, WhatsApp and email"


def activity_direction_error(channel: str | None, direction: str | None) -> str | None:
    """V6, shared by the create schema and the service's PATCH check (which sees the merged row)."""
    if channel is None:
        return None  # the channel failed its own validation; one error is enough
    if channel in BDM_ACTIVITY_DIRECTIONAL and direction is None:
        return ACTIVITY_DIRECTION_REQUIRED
    if channel not in BDM_ACTIVITY_DIRECTIONAL and direction is not None:
        return ACTIVITY_DIRECTION_REFUSED
    return None


class BdmActivityCreate(BaseModel):
    """V1-V6. Owner, contact name and timestamps are server-owned (`extra="forbid"` → 422). Time rules need "now", so the service
    checks them (spec §4.2)."""

    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    channel: BdmActivityChannel
    direction: BdmActivityDirection | None = Field(default=None, validate_default=True)
    contact_id: UUID | None = None
    occurred_at: AwareDatetime
    note: TripNote = None

    @field_validator("direction")
    @classmethod
    def _direction_fits_channel(cls, value: str | None, info: ValidationInfo) -> str | None:
        error = activity_direction_error(info.data.get("channel"), value)
        if error:
            raise ValueError(error)
        return value


class BdmActivityUpdate(BaseModel):
    """Only the fields sent change (`model_fields_set`). The organization is fixed after create. `null` clears direction, contact and
    note; channel and When can't be cleared."""

    model_config = ConfigDict(extra="forbid")
    channel: BdmActivityChannel | None = None
    direction: BdmActivityDirection | None = None
    contact_id: UUID | None = None
    occurred_at: AwareDatetime | None = None
    note: TripNote = None

    @model_validator(mode="after")
    def _required_stay_set(self) -> "BdmActivityUpdate":
        for field, label in (("channel", "Channel"), ("occurred_at", "When")):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{label} can't be empty")
        return self


class BdmActivityOrganization(BaseModel):
    id: UUID
    code: str
    name: str
    org_type: str


class BdmActivityPermissions(BaseModel):
    can_change: bool


class BdmActivityOut(BaseModel):
    id: UUID
    organization: BdmActivityOrganization
    bdm: BdmPersonRef
    contact_id: UUID | None
    contact_name: str | None
    contact_removed: bool
    channel: BdmActivityChannel
    direction: BdmActivityDirection | None
    occurred_at: datetime
    note: str | None
    created_at: datetime
    updated_at: datetime
    permissions: BdmActivityPermissions


class BdmActivityPage(BaseModel):
    items: list[BdmActivityOut]
    total: int
    limit: int
    offset: int


class BdmActivityChannelCounts(BaseModel):
    call: int
    whatsapp: int
    email: int
    visit: int
    meeting: int
    other: int


class BdmActivityDayCounts(BaseModel):
    day: date
    by_channel: BdmActivityChannelCounts
    calls_made: int
    organizations_contacted: int


class BdmActivityDayPage(BdmActivityPage):
    counts: BdmActivityDayCounts


# bdm-017 (DEC-SCOPE-072, spec §4-§5): a student lead a BDM enters against an organization, and the admin's explicit conversion link.
# The text rules are bdm-001's (no control characters, blank -> None) with bdm-002's email and phone shapes; the lengths are the
# `enquiries` columns'. Source, division, status, attribution and conversion are server-owned: `extra="forbid"` answers 422.
BDM_LEAD_LABELS = {"name": "Student name", "email": "Email", "student_email": "Email", "phone": "Phone", "interest": "Interest", "note": "Note",
                   "whatsapp_number": "WhatsApp number", "city": "City", "state": "State",  # these three: tel-008's lead edit
                   "qualification": "Qualification", "institution": "College/University", "subject": "Enquiry subject", "message": "Notes",  # tel-005
                   "current_org": "Current college/company", "career_objective": "Career objective", "preferred_batch": "Preferred batch",
                   "budget_range": "Budget range", "preferred_course": "Preferred course", "intake": "Intake",
                   "english_test_status": "IELTS/PTE status"}  # tel-009


def _bdm_lead_text(pattern: re.Pattern, required: bool):
    def check(value: str | None, info: ValidationInfo) -> str | None:
        label = BDM_LEAD_LABELS[info.field_name or ""]
        if value is not None and pattern.search(value):
            raise ValueError(f"{label} contains invalid characters")
        if not value:
            if required:
                raise ValueError(f"{label} is required")
            return None
        if info.field_name in ("email", "student_email"):
            if not _EMAIL_SHAPE.fullmatch(value):
                raise ValueError("Enter a valid email address")
            return value.lower()
        if info.field_name in ("phone", "whatsapp_number") and not _BDM_PHONE.fullmatch(value):
            raise ValueError("Phone may contain only digits, spaces and + - ( )")
        return value
    return check


BdmLeadName = Annotated[Annotated[str, _trimmed(160)], AfterValidator(_bdm_lead_text(_BDM_CONTROL, True))]
BdmLeadEmail = Annotated[Annotated[str, _trimmed(255)], AfterValidator(_bdm_lead_text(_BDM_CONTROL, True))]
BdmLeadPhone = Annotated[Annotated[str, _trimmed(40)] | None, AfterValidator(_bdm_lead_text(_BDM_CONTROL, False))]
BdmLeadInterest = Annotated[Annotated[str, _trimmed(180)], AfterValidator(_bdm_lead_text(_BDM_CONTROL, True))]
BdmLeadNote = Annotated[Annotated[str, _trimmed(5000)] | None, AfterValidator(_bdm_lead_text(_BDM_MULTILINE_CONTROL, False))]


class BdmLeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: BdmLeadName
    email: BdmLeadEmail
    phone: BdmLeadPhone = None
    interest: BdmLeadInterest
    note: BdmLeadNote = None
    acknowledge_duplicate: StrictBool = Field(False, description="True saves even when the email is already a lead of this organization (409 possible_duplicate).")


class BdmLeadOut(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str | None
    interest: str
    status: str
    bdm: BdmPersonRef
    converted: bool
    created_at: datetime


class BdmLeadPage(BaseModel):
    items: list[BdmLeadOut]
    total: int
    limit: int
    offset: int


# bdm-021 (spec §4): a College organization's funnel and revenue -- aggregates only (AC3). An untracked stage or line is
# `tracked: false` with a null figure, never a 0 (AC2).
class BdmBusinessStage(BaseModel):
    key: str
    label: str
    definition: str
    tracked: bool
    count: int | None


class BdmRevenueLine(BaseModel):
    key: str
    label: str
    definition: str
    tracked: bool
    amount: Decimal | None


class BdmBusinessRevenue(BaseModel):
    lines: list[BdmRevenueLine]


class BdmBusinessOut(BaseModel):
    organization_id: UUID
    currency: Literal["INR"]
    funnel: list[BdmBusinessStage]
    revenue: BdmBusinessRevenue | None = Field(description="Null unless the caller is the assigned BDM, a manager or super_admin (B3).")


# bdm-022 (DEC-SCOPE-110): a linked Agent organization's performance -- the agency's own aggregates, never a student, member or money
# figure (AC4). An untracked step is `tracked: false` with a null count, never a 0.
class BdmAgentAgency(BaseModel):
    name: str
    prefix: str
    status: str


class BdmAgentStageCount(BaseModel):
    key: str
    label: str
    count: int


class BdmAgentPerformanceOut(BaseModel):
    organization_id: UUID
    linked: bool
    agency: BdmAgentAgency | None
    steps: list[BdmBusinessStage]
    applications_by_stage: list[BdmAgentStageCount]
    visa_applications: int | None
    as_of: datetime


class AdminLeadConversionIn(BaseModel):
    """The student account's email, typed by the admin and matched exactly (never inferred from the lead's own email)."""

    model_config = ConfigDict(extra="forbid")
    student_email: BdmLeadEmail


# --- tel-001 (DEC-SCOPE-073): telecaller profile ------------------------------------------------------------------------
TelecallerTeam = Literal["it", "overseas"]
TELECALLER_FIELD_LABELS = {"team": "Team", "employee_id": "Employee ID", "reporting_manager_user_id": "Reporting manager", "phone": "Phone"}


class TelecallerProfileCreate(BaseModel):
    """spec §5.2 / TL6: team, Employee ID and reporting manager, all required; nothing optional."""

    model_config = ConfigDict(extra="forbid")
    team: TelecallerTeam
    employee_id: BdmEmployeeId
    reporting_manager_user_id: UUID


class TelecallerProfileUpdate(BaseModel):
    """Omitted = unchanged. An explicit null for any key fails (all three are required on the row). `team` exists only so an equal
    value is a no-op; a different one is refused by services/telecaller.apply_profile_update (TL7)."""

    model_config = ConfigDict(extra="forbid")
    team: TelecallerTeam = None
    employee_id: BdmEmployeeId = None
    reporting_manager_user_id: UUID = None


class TelecallerSelfUpdate(BaseModel):
    """TL3: a telecaller may change only their phone. The key is required; null or "" clears it. bdm-017's lead phone rule
    (trimmed, max 40, digits/spaces/+-(), no control characters) is reused, not copied."""

    model_config = ConfigDict(extra="forbid")
    phone: BdmLeadPhone


class TelecallerProfileOut(BaseModel):
    team: str
    employee_id: str
    reporting_manager: BdmManagerRef


class TelecallerMeOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    division: str
    telecaller_profile: TelecallerProfileOut


class TelecallerTeamRow(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    team: str
    employee_id: str


class TelecallerAdminRow(TelecallerTeamRow):
    reporting_manager: BdmManagerRef
    manager_active: bool


class TelecallerTeamPage(BaseModel):
    items: list[TelecallerTeamRow]
    total: int
    limit: int
    offset: int


class TelecallerAdminPage(BaseModel):
    items: list[TelecallerAdminRow]
    total: int
    limit: int
    offset: int


# --- tel-002 (DEC-SCOPE-074): product/interest catalogue + campaigns --------------------------------------------------------
TelProductGroup = Literal["it", "overseas", "other"]
TelSource = Literal[TEL_SOURCES]
TelSortOrder = Annotated[StrictInt, Field(ge=0, le=9999)]
TEL_CATALOGUE_FIELD_LABELS = {
    "group": "Group", "name": "Name", "team": "Team", "program_id": "Course", "active": "Active", "sort_order": "Sort order",
    "source": "Source", "product_id": "Product", "start_date": "Start date", "end_date": "End date",
}


def _tel_name(max_length: int):
    """Trimmed, required, capped, no control characters; each failure names the field (services/telecaller._parse keeps a custom
    validator's own sentence)."""

    def check(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        if len(value) > max_length:
            raise ValueError(f"Name must be at most {max_length} characters")
        if _BDM_CONTROL.search(value):
            raise ValueError("Name contains invalid characters")
        return value

    return Annotated[str, AfterValidator(check)]


TelProductName, TelCampaignName = _tel_name(120), _tel_name(160)


class TelProductCreate(BaseModel):
    """P2: `team` may be omitted -- an IT/Overseas product takes its group's team, an Other product defaults to none (unassigned).
    `sort_order` may be omitted -- the product goes to the end of its group."""

    model_config = ConfigDict(extra="forbid")
    group: TelProductGroup
    name: TelProductName
    team: TelecallerTeam | None = None
    program_id: UUID | None = None
    sort_order: TelSortOrder = None  # omitted = after the group's last product


class TelProductUpdate(BaseModel):
    """Omitted = unchanged. An explicit null clears `team` (Other only) or `program_id`; on any other key it is a 422. `group` exists
    only so a change is refused with a sentence (it is fixed once created)."""

    model_config = ConfigDict(extra="forbid")
    group: TelProductGroup = None
    name: TelProductName = None
    team: TelecallerTeam | None = None
    program_id: UUID | None = None
    active: StrictBool = None
    sort_order: TelSortOrder = None


class TelCampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: TelCampaignName
    source: TelSource
    product_id: UUID
    start_date: date
    end_date: date | None = None


class TelCampaignUpdate(BaseModel):
    """Omitted = unchanged; null clears only `end_date`. The date order is checked on the merged row (services/telecaller_catalogue)."""

    model_config = ConfigDict(extra="forbid")
    name: TelCampaignName = None
    source: TelSource = None
    product_id: UUID = None
    start_date: date = None
    end_date: date | None = None
    active: StrictBool = None


class TelProgramRef(BaseModel):
    id: UUID
    title: str


class TelProductOut(BaseModel):
    id: UUID
    group: str
    name: str
    team: str | None
    program: TelProgramRef | None
    active: bool
    sort_order: int


class TelProductPage(BaseModel):
    items: list[TelProductOut]
    total: int
    limit: int
    offset: int


class TelCampaignProductRef(BaseModel):
    id: UUID
    name: str
    group: str
    active: bool


class TelCampaignOut(BaseModel):
    id: UUID
    name: str
    source: str
    product: TelCampaignProductRef
    start_date: date
    end_date: date | None
    active: bool


class TelCampaignPage(BaseModel):
    items: list[TelCampaignOut]
    total: int
    limit: int
    offset: int


# --- tel-012 (DEC-SCOPE-083): scripts, message templates, brochure assets --------------------------------------------------
TelChannel = Literal["whatsapp", "email"]
TelAssetKind = Literal[TEL_ASSET_KINDS]
TEL_CONTENT_FIELD_LABELS = {
    "name": "Name", "product_id": "Product", "steps": "Steps", "active": "Active", "channel": "Channel", "kind": "Kind",
    "asset_id": "Brochure", "subject": "Subject", "body": "Message",
}
_TEL_BODY_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # tabs and newlines are text in a message body
TelContentName = _tel_name(160)


class TelScriptStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    notes: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Every step needs a title")
        if len(value) > 120:
            raise ValueError("A step title must be at most 120 characters")
        if _BDM_CONTROL.search(value):
            raise ValueError("A step title contains invalid characters")
        return value

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        value = (value or "").strip() or None
        if value and len(value) > 1000:
            raise ValueError("Talking points must be at most 1000 characters")
        if value and _TEL_BODY_CONTROL.search(value):
            raise ValueError("Talking points contain invalid characters")
        return value


def _tel_steps(value: list[TelScriptStep]) -> list[TelScriptStep]:
    if not 1 <= len(value) <= 20:
        raise ValueError("Add between 1 and 20 steps")
    return value


TelScriptSteps = Annotated[list[TelScriptStep], AfterValidator(_tel_steps)]


def _tel_subject(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("Subject is required")
    if len(value) > 200:
        raise ValueError("Subject must be at most 200 characters")
    if _BDM_CONTROL.search(value):
        raise ValueError("Subject must be one line without control characters")
    return value


def _tel_body(value: str) -> str:
    """The per-channel length is checked on the merged row (services/telecaller_content); CRLF is stored as LF."""
    value = value.replace("\r\n", "\n").strip()
    if not value:
        raise ValueError("Message is required")
    if _TEL_BODY_CONTROL.search(value):
        raise ValueError("Message contains invalid characters")
    return value


TelSubject = Annotated[str | None, AfterValidator(_tel_subject)]
TelBody = Annotated[str, AfterValidator(_tel_body)]


class TelScriptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: UUID
    name: TelContentName
    steps: TelScriptSteps


class TelScriptUpdate(BaseModel):
    """Omitted = unchanged; null is a 422 on every key (nothing here is optional once set)."""

    model_config = ConfigDict(extra="forbid")
    product_id: UUID = None
    name: TelContentName = None
    steps: TelScriptSteps = None
    active: StrictBool = None


class TelTemplateCreate(BaseModel):
    """`kind` is a string checked against the channel's list in the service, so the 422 names the channel."""

    model_config = ConfigDict(extra="forbid")
    channel: TelChannel
    kind: str
    name: TelContentName
    product_id: UUID | None = None
    asset_id: UUID | None = None
    subject: TelSubject = None
    body: TelBody


class TelTemplateUpdate(BaseModel):
    """Omitted = unchanged; null clears `product_id`, `asset_id` and `subject` (an email then fails "Subject is required"). `channel`
    exists only so a change is refused with a sentence."""

    model_config = ConfigDict(extra="forbid")
    channel: TelChannel = None
    kind: str = None
    name: TelContentName = None
    product_id: UUID | None = None
    asset_id: UUID | None = None
    subject: TelSubject = None
    body: TelBody = None
    active: StrictBool = None


class TelAssetCreate(BaseModel):
    """The multipart form fields of an upload (the file itself is checked by services/telecaller_content.read_pdf)."""

    model_config = ConfigDict(extra="forbid")
    name: TelContentName
    kind: TelAssetKind
    product_id: UUID | None = None


class TelAssetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: TelContentName = None
    kind: TelAssetKind = None
    product_id: UUID | None = None
    active: StrictBool = None


class TelScriptOut(BaseModel):
    id: UUID
    product: TelCampaignProductRef
    name: str
    steps: list[TelScriptStep]
    active: bool


class TelScriptPage(BaseModel):
    items: list[TelScriptOut]
    total: int
    limit: int
    offset: int


class TelAssetRef(BaseModel):
    id: UUID
    name: str
    active: bool


class TelTemplateOut(BaseModel):
    id: UUID
    channel: str
    kind: str
    name: str
    product: TelCampaignProductRef | None
    asset: TelAssetRef | None
    subject: str | None
    body: str
    active: bool


class TelTemplatePage(BaseModel):
    items: list[TelTemplateOut]
    total: int
    limit: int
    offset: int


class TelAssetLink(BaseModel):
    url: str
    expires_at: datetime


class TelTemplatePreview(BaseModel):
    subject: str | None
    body: str
    brochure_link: TelAssetLink | None


class TelAssetOut(BaseModel):
    id: UUID
    name: str
    kind: str
    product: TelCampaignProductRef | None
    file_name: str
    size_bytes: int
    active: bool
    uploaded_at: datetime


class TelAssetPage(BaseModel):
    items: list[TelAssetOut]
    total: int
    limit: int
    offset: int


# --- bdm-008 (DEC-SCOPE-075, spec §6): follow-ups and tasks ---------------------------------------------------------------------
BDM_TASK_LABELS = {"title": "Title", "notes": "Notes"}
BdmTaskKind = Literal["follow_up", "task"]
BdmTaskBucket = Literal["today", "overdue", "upcoming", "open", "done", "cancelled"]
BdmTaskOrgType = BdmOrgType | Literal["none"]
BdmTaskTitle = Annotated[str, _trimmed(200), AfterValidator(_trip_text(_BDM_CONTROL, True, BDM_TASK_LABELS))]
BdmTaskNotes = Annotated[Annotated[str, _trimmed(2000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, BDM_TASK_LABELS))]
BdmTaskDue = Annotated[date, BeforeValidator(_trip_date("due date"))]


class BdmTaskCreate(BaseModel):
    """§6.2: a manual follow-up or task. Assignee, source, status and timestamps are server-owned (unknown fields here)."""

    model_config = ConfigDict(extra="forbid")
    kind: BdmTaskKind
    title: BdmTaskTitle
    due_on: BdmTaskDue
    organization_id: UUID | None = None
    notes: BdmTaskNotes = None


class BdmTaskUpdate(BaseModel):
    """§6.3: omitted = unchanged; `notes: null` clears; a sent null title or due date is refused (both are always set)."""

    model_config = ConfigDict(extra="forbid")
    title: BdmTaskTitle | None = None
    due_on: BdmTaskDue | None = None
    notes: BdmTaskNotes = None

    @field_validator("title", "due_on")
    @classmethod
    def _not_null(cls, value, info: ValidationInfo):
        """Omitted = unchanged (the default is not validated); a sent null is refused."""
        if value is None:
            raise ValueError(f"{'Title' if info.field_name == 'title' else 'Due date'} is required")
        return value


class BdmTaskOrgRef(BaseModel):
    id: UUID
    code: str
    name: str
    org_type: str
    archived: bool


class BdmTaskAppointmentRef(BaseModel):
    id: UUID
    code: str


class BdmTaskPermissions(BaseModel):
    can_edit: bool
    can_complete: bool
    can_cancel: bool


class BdmTaskOut(BaseModel):
    id: UUID
    kind: str
    title: str
    notes: str | None
    due_on: date
    status: str
    source: str
    overdue: bool
    organization: BdmTaskOrgRef | None
    appointment: BdmTaskAppointmentRef | None
    assignee: BdmOrgPerson
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime
    permissions: BdmTaskPermissions


class BdmTaskBucketCounts(BaseModel):
    today: int
    overdue: int
    upcoming: int
    done: int
    cancelled: int


class BdmTaskTypeCount(BaseModel):
    org_type: str | None
    count: int


class BdmTaskCounts(BaseModel):
    buckets: BdmTaskBucketCounts
    by_org_type: list[BdmTaskTypeCount]


class BdmTaskPage(BaseModel):
    items: list[BdmTaskOut]
    total: int
    limit: int
    offset: int
    today: date
    counts: BdmTaskCounts


# bdm-013 (DEC-SCOPE-079): the read-only calendar feed -- only what the calendar shows (no notes, contacts, purpose or costs).
class BdmCalendarAppointment(BaseModel):
    id: UUID
    code: str
    day: date  # the IST date of starts_at
    starts_at: datetime
    duration_minutes: int
    appointment_type: str
    status: str
    seminar: bool
    organization: BdmAppointmentOrgRef


class BdmCalendarTrip(BaseModel):
    id: UUID
    code: str
    travel_date: date
    return_date: date
    from_place: str
    to_place: str
    mode: str
    approval_status: str
    travel_status: str


class BdmCalendarTask(BaseModel):
    id: UUID
    kind: str
    title: str
    due_on: date
    status: str
    overdue: bool
    organization: BdmAppointmentOrgRef | None


class BdmCalendarOut(BaseModel):
    bdm: BdmManagerRef
    date_from: date
    date_to: date
    today: date
    truncated: bool
    appointments: list[BdmCalendarAppointment]
    trips: list[BdmCalendarTrip]
    tasks: list[BdmCalendarTask]


# --- bdm-014 (DEC-SCOPE-097): My Day ---------------------------------------------------------------------------------------------
class BdmMyDayOrgRef(BdmAppointmentOrgRef):
    org_type: str


class BdmMyDayAppointment(BaseModel):
    id: UUID
    code: str
    starts_at: datetime
    duration_minutes: int
    appointment_type: str
    status: str
    organization: BdmMyDayOrgRef


class BdmMyDayAppointments(BaseModel):
    count: int
    truncated: bool
    items: list[BdmMyDayAppointment]


class BdmMyDayTrip(BaseModel):
    id: UUID
    code: str
    travel_date: date
    return_date: date
    from_place: str
    to_place: str
    approval_status: str
    travel_status: str
    appointment_count: int


class BdmMyDayTrips(BaseModel):
    total: int
    items: list[BdmMyDayTrip]


class BdmMyDayFollowUpGroup(BaseModel):
    key: str  # an org_type, "mou" (source = mou) or "none" (no organization)
    count: int


class BdmMyDayFollowUps(BaseModel):
    total: int
    groups: list[BdmMyDayFollowUpGroup]


class BdmMyDayTile(BaseModel):
    key: str  # the Appendix B.2 ID, e.g. "T-A1"
    label: str
    tracked: bool
    value: int | None  # null when not tracked -- never a fabricated 0
    note: str | None


class BdmMyDayOut(BaseModel):
    today: date
    bdm_type: str
    appointments: BdmMyDayAppointments
    trips: BdmMyDayTrips
    follow_ups: BdmMyDayFollowUps
    tiles: list[BdmMyDayTile]


# --- bdm-023 (DEC-SCOPE-108): the management dashboard -- Appendix B.4 tiles and alerts ----------------------------------------------
class BdmDashboardTile(BaseModel):
    key: str  # T-M01 ... T-M08
    label: str
    definition: str
    value: int


class BdmDashboardAlertItem(BaseModel):
    id: UUID  # the record's id (a BDM's user id for a missing daily report)
    title: str
    bdm: BdmPersonRef
    at: datetime | date  # the item's time: start, travel date, due date, waiting since, completed at or report date
    organization_id: UUID | None


class BdmDashboardAlert(BaseModel):
    key: str  # AL-1 ... AL-7
    label: str
    tone: Literal["danger", "warning", "success"]
    record: Literal["appointment", "trip", "task", "mou", "daily_report"]
    count: int
    items: list[BdmDashboardAlertItem]  # the first 10 (R8)


class BdmManagerDashboardOut(BaseModel):
    today: date
    month: date
    manager: BdmPersonRef | None  # the super_admin's chosen manager; null for a manager's own team or all teams
    tiles: list[BdmDashboardTile]
    alerts: list[BdmDashboardAlert]


# --- bdm-024 (DEC-SCOPE-113): performance by BDM type (Appendix B.6 P-rows) + drill-down, and the master view (V-chains) --------------
BdmTypeName = Literal["agent", "school", "college"]


class BdmPerformanceFigures(BaseModel):
    meetings: int
    trips: int | None  # null on an organization row: trips belong to the BDM
    new_organizations: int
    mous: int
    leads: int
    students: int
    revenue: Decimal | None  # INR; null = not tracked (Agent / School, D17)


class BdmPerformanceCell(BaseModel):
    type: BdmTypeName
    tracked: bool
    value: int | Decimal | None  # Decimal = INR revenue; null when not tracked
    definition: str


class BdmPerformanceRow(BaseModel):
    key: str  # P-01 ... P-08
    label: str
    cells: list[BdmPerformanceCell]


class BdmPerformanceBdm(BaseModel):
    id: UUID
    full_name: str
    active: bool
    figures: BdmPerformanceFigures


class BdmPerformanceOut(BaseModel):
    from_: date = Field(serialization_alias="from")
    to: date
    manager: BdmPersonRef | None
    type: BdmTypeName | None
    rows: list[BdmPerformanceRow]
    bdms: list[BdmPerformanceBdm]  # the BDMs of `type`, by name; empty without `type`


class BdmPerformanceBdmRef(BaseModel):
    id: UUID
    full_name: str
    active: bool
    bdm_type: BdmTypeName


class BdmPerformanceOrganization(BaseModel):
    id: UUID
    code: str
    name: str
    figures: BdmPerformanceFigures


class BdmPerformanceTrip(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    from_place: str
    to_place: str
    travel_date: date
    approval_status: str
    travel_status: str


class BdmPerformanceBdmOut(BaseModel):
    from_: date = Field(serialization_alias="from")
    to: date
    bdm: BdmPerformanceBdmRef
    totals: BdmPerformanceFigures
    organizations: list[BdmPerformanceOrganization]
    trips: list[BdmPerformanceTrip]


ChainCount = int | Decimal | None  # Decimal = INR revenue; null = a step that is not tracked


class BdmChainStep(BaseModel):
    key: str
    label: str
    definition: str
    tracked: bool


class BdmHierarchyOrganization(BaseModel):
    id: UUID
    code: str
    name: str
    counts: list[ChainCount]  # one per chain step, in chain order


class BdmHierarchyBdm(BaseModel):
    id: UUID
    full_name: str
    active: bool
    organization_count: int  # linked organizations (listed)
    not_linked: int  # Agent / School organizations not onboarded yet (counted, not listed)
    totals: list[ChainCount]
    organizations: list[BdmHierarchyOrganization]


class BdmHierarchyType(BaseModel):
    type: BdmTypeName
    label: str
    chain: list[BdmChainStep]
    bdm_count: int  # active BDMs
    organization_count: int
    not_linked: int
    totals: list[ChainCount]
    bdms: list[BdmHierarchyBdm]


class BdmHierarchyOut(BaseModel):
    manager: BdmPersonRef | None
    as_of: datetime
    types: list[BdmHierarchyType]


# --- tel-022 (DEC-SCOPE-080): daily + monthly targets ------------------------------------------------------------------------
TelTargetPeriod = Literal["daily", "monthly"]
TelTargetKpi = Literal[TEL_TARGET_KPIS]
TEL_TARGET_KPI_LABELS = dict(zip(TEL_TARGET_KPIS, ("Calls", "Connected calls", "Qualified leads", "Follow-ups", "Counselling appointments", "Conversions"), strict=True))
TEL_TARGET_MAX = 100_000
TEL_TARGET_FIELD_LABELS = {"scope": "Scope", "team": "Team", "user_id": "Telecaller", "period": "Period", "effective_from": "Starts", "values": "Values"}


def _target_values(values: dict) -> dict:
    """Each sentence names its KPI (services/telecaller._parse keeps a value_error's own text). None = remove the override."""
    if not values:
        raise ValueError("Values: enter at least one target")
    for kpi, value in values.items():
        label = TEL_TARGET_KPI_LABELS.get(kpi)
        if label is None:
            raise ValueError(f"Values: unknown KPI {kpi}")
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Values: {label} must be a whole number")
        if value < 0:
            raise ValueError(f"Values: {label} must be 0 or more")
        if value > TEL_TARGET_MAX:
            raise ValueError(f"Values: {label} must be {TEL_TARGET_MAX} or less")
    return values


class TelTargetSet(BaseModel):
    """The scope shape (team xor user) and the date rules are checked in services/telecaller_targets, each with its own sentence."""

    model_config = ConfigDict(extra="forbid")
    scope: Literal["team", "user"]
    team: TelecallerTeam | None = None
    user_id: UUID | None = None
    period: TelTargetPeriod
    effective_from: date | None = None  # omitted = the earliest allowed date
    values: Annotated[dict[str, Any], AfterValidator(_target_values)]


class TelTargetPerson(BaseModel):
    id: UUID
    full_name: str


class TelTargetSetOut(BaseModel):
    scope: str
    team: str | None
    user: TelTargetPerson | None
    period: str
    effective_from: date
    values: dict[str, int | None]


class TelTargetOut(BaseModel):
    id: UUID
    scope: str
    team: str | None
    user: TelTargetPerson | None
    period: str
    kpi: str
    value: int | None
    effective_from: date
    set_by: TelTargetPerson
    updated_at: datetime


class TelTargetPage(BaseModel):
    items: list[TelTargetOut]
    total: int
    limit: int
    offset: int


class TelTargetValue(BaseModel):
    kpi: str
    value: int | None
    source: Literal["user", "team"] | None


class TelTargetEffectiveOut(BaseModel):
    date: date
    month: date
    team: str
    user: TelTargetPerson | None
    daily: list[TelTargetValue]
    monthly: list[TelTargetValue]


# tel-020 (DEC-SCOPE-111 AL1, AL11; API §12AE): a team's alert thresholds, whole hours 1-168 (a string or a fraction is refused).
TEL_SETTING_FIELD_LABELS = {"not_contacted_hours": "Lead not contacted after (hours)", "hot_pending_hours": "Hot lead pending after (hours)"}
TelSettingHours = Annotated[StrictInt, Field(ge=1, le=168)]


class TelSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    not_contacted_hours: TelSettingHours
    hot_pending_hours: TelSettingHours


class TelSettingsOut(BaseModel):
    team: str
    team_label: str
    not_contacted_hours: int
    hot_pending_hours: int
    updated_at: datetime
    updated_by: TelTargetPerson | None


class TelSettingsPage(BaseModel):
    items: list[TelSettingsOut]


# tel-004 (DEC-SCOPE-081, spec §5): a person's lead stage move. The reason reuses bdm-004's note rules (trimmed, at most 500,
# blank -> None); the service decides when it is required.
class LeadStageMove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_stage: BdmStageKey
    reason: BdmPipelineNote = None


class LeadStageOut(BaseModel):
    id: UUID
    status: str
    status_label: str
    stage_changed_at: datetime


class LeadStageActor(BaseModel):
    id: UUID
    full_name: str


class LeadStageHistoryRow(BaseModel):
    id: UUID
    from_stage: str
    from_label: str
    to_stage: str
    to_label: str
    event: str
    actor: LeadStageActor | None
    reason: str | None
    created_at: datetime


class LeadStageHistoryPage(BaseModel):
    items: list[LeadStageHistoryRow]
    total: int
    limit: int
    offset: int


# --- bdm-018 (DEC-SCOPE-085, spec §5): the school onboarding handover --------------------------------------------------------------
_ONBOARDING_LABELS = {"note": "Note", "reason": "Reason", "school_code": "School ID", "agent_code": "Agent code"}
BdmOnboardingNote = Annotated[
    Annotated[Annotated[str, _trimmed(1000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, _ONBOARDING_LABELS))],
    BeforeValidator(_bdm_newlines),
]
BdmOnboardingReason = Annotated[
    Annotated[Annotated[str, _trimmed(500)], AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, True, _ONBOARDING_LABELS))], BeforeValidator(_bdm_newlines)
]
BdmOnboardingSchoolCode = Annotated[Annotated[str, _trimmed(8)], AfterValidator(_trip_text(_BDM_CONTROL, True, _ONBOARDING_LABELS))]
BdmOnboardingStatus = Literal["pending", "completed", "rejected"]
BdmOnboardingKind = Literal["school", "agent"]  # bdm-019


class BdmOnboardingRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: BdmOnboardingNote = None


class BdmOnboardingRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmOnboardingReason


class BdmOnboardingLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    school_code: BdmOnboardingSchoolCode


class BdmOnboardingLinkAgentIn(BaseModel):
    """bdm-019 A1: the Agent Organization's code (`agent_orgs.prefix`), matched case-insensitively."""

    model_config = ConfigDict(extra="forbid")
    agent_code: BdmOnboardingSchoolCode  # the same 1-8 character, control-free text as a School ID


class BdmOnboardingOrgPrefill(BaseModel):
    """The organization's details the admin creates the School from (spec §5.2): read live, never snapshotted."""

    id: UUID
    code: str
    name: str
    city: str
    state: str | None
    address: str | None
    phone: str | None
    email: str | None
    website: str | None
    board: str | None
    grade_from: int | None
    grade_to: int | None


class BdmOnboardingContact(BaseModel):
    name: str
    email: str | None
    phone: str | None


class BdmOnboardingMou(BaseModel):
    reference: str | None
    signed_on: date | None


class BdmOnboardingSchool(BaseModel):
    id: UUID
    name: str
    school_code: str | None


class BdmOnboardingAgentOrg(BaseModel):
    id: UUID
    name: str
    prefix: str
    status: str


class BdmOnboardingItem(BaseModel):
    id: UUID
    status: BdmOnboardingStatus
    note: str | None
    created_at: datetime
    resolved_at: datetime | None
    resolution: Literal["created", "linked"] | None
    reject_reason: str | None
    requested_by: BdmPersonRef
    assigned_bdm: BdmOrgPerson
    organization: BdmOnboardingOrgPrefill
    primary_contact: BdmOnboardingContact | None
    mou: BdmOnboardingMou | None
    school: BdmOnboardingSchool | None
    kind: BdmOnboardingKind  # bdm-019
    agent_org: BdmOnboardingAgentOrg | None  # bdm-019: the linked agency (agent requests only)


class BdmOnboardingPage(BaseModel):
    items: list[BdmOnboardingItem]
    total: int
    limit: int
    offset: int


# bdm-020 (DEC-SCOPE-089): a linked School's student development counts -- aggregates only, never a student (AC3).
class BdmSchoolActivityMetric(BaseModel):
    key: str
    label: str
    tracked: bool
    completed: int | None  # None when not tracked (A2)
    pending: int | None


class BdmSchoolActivityOut(BaseModel):
    linked: bool
    school: BdmOnboardingSchoolRef | None
    total_students: int | None
    metrics: list[BdmSchoolActivityMetric]


# tel-008 (DEC-SCOPE-084 D2): what a telecaller or manager may change on a lead -- the §2 contact fields, the product and the priority.
# Owner, telecaller, stage, source, campaign and the qualification fields are not editable here: `extra="forbid"` answers 422. Text
# follows bdm-017's lead rules (trimmed, no control characters, blank -> None; email lower-cased, phone shape).
LeadPlace = Annotated[Annotated[str, _trimmed(120)] | None, AfterValidator(_bdm_lead_text(_BDM_CONTROL, False))]


class TelecallerLeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: BdmLeadName = None
    email: BdmLeadEmail = None
    phone: BdmLeadPhone = None
    whatsapp_number: BdmLeadPhone = None
    city: LeadPlace = None
    state: LeadPlace = None
    product_id: UUID | None = None
    priority: Literal[LEAD_PRIORITIES] = None


def _mobile(value: str) -> str:
    if normalise_phone(value) is None:
        raise ValueError("Enter a valid mobile number")
    return value


# tel-005 (DEC-SCOPE-088; I1, R5, R6): a lead a telecaller or manager enters. The mobile is required and must be a number the duplicate check
# can match on; email is optional (I1). Owner, telecaller and stage are never sent (`extra="forbid"`): the creator and the pipeline decide.
LeadMobile = Annotated[Annotated[str, _trimmed(40)], AfterValidator(_bdm_lead_text(_BDM_CONTROL, True)), AfterValidator(_mobile)]
LeadOptionalEmail = Annotated[Annotated[str, _trimmed(255)] | None, AfterValidator(_bdm_lead_text(_BDM_CONTROL, False))]
LeadInstitution = Annotated[Annotated[str, _trimmed(200)] | None, AfterValidator(_bdm_lead_text(_BDM_CONTROL, False))]
LeadSubject = Annotated[Annotated[str, _trimmed(180)] | None, AfterValidator(_bdm_lead_text(_BDM_CONTROL, False))]


class TelecallerLeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: BdmLeadName
    phone: LeadMobile
    email: LeadOptionalEmail = None
    whatsapp_number: BdmLeadPhone = None
    city: LeadPlace = None
    state: LeadPlace = None
    qualification: LeadPlace = None
    passing_year: int | None = Field(default=None, ge=1950, le=2100)
    institution: LeadInstitution = None
    product_id: UUID
    campaign_id: UUID | None = None
    source: Literal[TEL_SOURCES]
    priority: Literal[LEAD_PRIORITIES] = "warm"
    division: Literal["it", "overseas"] | None = None
    subject: LeadSubject = None
    message: BdmLeadNote = None


class LeadEnquiryCreate(BaseModel):
    """tel-005 (I5): "Add enquiry to this lead" -- the new enquiry's subject, notes, source and optional campaign."""

    model_config = ConfigDict(extra="forbid")
    subject: BdmLeadInterest
    message: BdmLeadNote = None
    source: Literal[TEL_SOURCES]
    campaign_id: UUID | None = None



def _qual_text(max_length: int):
    return Annotated[Annotated[str, _trimmed(max_length)] | None, AfterValidator(_bdm_lead_text(_BDM_CONTROL, False))]


class LeadQualificationIn(BaseModel):
    """tel-009 (DEC-SCOPE-093, QD2): the PUT body -- every field optional. Which fields apply depends on the lead's product group, which
    only the service knows; an applicable field left out is cleared. Ranges are the table's CHECKs (QF2)."""

    model_config = ConfigDict(extra="forbid")
    qualification: LeadPlace = None
    passing_year: int | None = Field(default=None, ge=1950, le=2100)
    city: LeadPlace = None
    state: LeadPlace = None
    current_org: _qual_text(200) = None
    work_experience_years: int | None = Field(default=None, ge=0, le=50)
    it_skill_level: Literal[QUAL_SKILL_LEVELS] | None = None
    career_objective: _qual_text(500) = None
    preferred_batch: _qual_text(120) = None
    budget_range: _qual_text(120) = None
    preferred_mode: Literal[QUAL_MODES] | None = None
    study_level: Literal[QUAL_STUDY_LEVELS] | None = None
    preferred_course: _qual_text(200) = None
    intake: _qual_text(40) = None
    academic_percentage: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    english_test_status: _qual_text(120) = None
    passport_status: Literal[QUAL_PASSPORT] | None = None


class LeadImportRow(BaseModel):
    """tel-006 (IM1): one CSV row -- tel-005's lead fields; the campaign gives the source, product and team."""

    model_config = ConfigDict(extra="forbid")
    name: BdmLeadName
    phone: LeadMobile
    email: LeadOptionalEmail = None
    whatsapp_number: BdmLeadPhone = None
    city: LeadPlace = None
    state: LeadPlace = None
    qualification: LeadPlace = None
    passing_year: int | None = Field(default=None, ge=1950, le=2100)
    institution: LeadInstitution = None
    priority: Literal[LEAD_PRIORITIES] = "warm"
    subject: LeadSubject = None
    message: BdmLeadNote = None


class LeadTimelineRow(BaseModel):
    """tel-015 (DEC-SCOPE-114 D3/D5): `id` is the source row's id, so a follow-up's scheduled / done / cancelled entries share it (`event`
    tells them apart). The optional fields are null where they do not apply."""

    id: UUID
    kind: Literal["created", "enquiry", "stage", "priority", "assignment", "handover", "student_link", "call", "message", "follow_up",
                  "appointment", "milestone"]
    at: datetime
    actor: LeadStageActor | None
    from_value: str
    from_label: str
    to_value: str
    to_label: str
    reason: str | None
    event: str | None = None  # tel-018: the stage row's pipeline event; tel-015: the sub-kind (method, linked, scheduled, type...)
    subject: str | None = None
    status: str | None = None
    duration_seconds: int | None = None
    scheduled_for: datetime | None = None


class LeadTimelinePage(BaseModel):
    items: list[LeadTimelineRow]
    total: int
    limit: int
    offset: int


# --- tel-007 (DEC-SCOPE-087, spec §5): distribution rules, the unassigned queue and manual (re)assignment ---------------------------
class TelDistributionRuleCreate(BaseModel):
    """The service checks the shape (a product rule names a product, a city rule a city), the product and the telecaller."""
    model_config = ConfigDict(extra="forbid")
    team: Literal["it", "overseas"]
    kind: Literal["product", "city"]
    product_id: UUID | None = None
    city: BdmOrgShort = None
    telecaller_user_id: UUID


class TelDistributionRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    telecaller_user_id: UUID


class TelRuleProduct(BaseModel):
    id: UUID
    name: str
    active: bool


class TelRuleTelecaller(BaseModel):
    id: UUID
    full_name: str
    active: bool


class TelDistributionRuleOut(BaseModel):
    id: UUID
    team: str
    kind: str
    product: TelRuleProduct | None
    city: str | None
    telecaller: TelRuleTelecaller
    editable: bool


class TelDistributionRulePage(BaseModel):
    items: list[TelDistributionRuleOut]
    total: int
    limit: int
    offset: int


class TelQueueProduct(BaseModel):
    id: UUID
    name: str


class TelQueueLead(BaseModel):
    id: UUID
    lead_code: str
    name: str
    division: str
    city: str | None
    product: TelQueueProduct | None
    source: str
    status: str
    status_label: str
    telecaller: TelRuleTelecaller | None
    created_at: datetime


class TelQueueLeadPage(BaseModel):
    items: list[TelQueueLead]
    total: int
    limit: int
    offset: int


class TelLeadAssign(BaseModel):
    """D3: 1-100 distinct leads to one telecaller, all or nothing."""
    model_config = ConfigDict(extra="forbid")
    lead_ids: list[UUID] = Field(min_length=1, max_length=100)
    telecaller_user_id: UUID

    @field_validator("lead_ids")
    @classmethod
    def _distinct(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Each lead can be chosen once")
        return value


class TelLeadAssignOut(BaseModel):
    assigned: int
    unchanged: int


# --- tel-016 (DEC-SCOPE-095, spec §3): lead counselling appointments ---------------------------------------------------------------------
def _lead_appt_link(value: str | None) -> str | None:
    """AP7 / spec §5: a meeting link is an http(s) URL -- never `javascript:` or another scheme that would run when clicked."""
    if value is not None and not value.lower().startswith(("http://", "https://")):
        raise ValueError("Meeting link must start with http:// or https://")
    return value


LeadApptLink = Annotated[_bdm_appt_optional(500), AfterValidator(_lead_appt_link)]


class LeadAppointmentCreate(BaseModel):
    """The type must fit the lead's division and the counselor must be one of its active counselors -- checked in the service (AP4).
    Server-owned fields (code, status, duration, booked_by) are unknown fields here."""

    model_config = ConfigDict(extra="forbid")
    appointment_type: Literal[tuple(LEAD_APPOINTMENT_TYPE_LABELS)]
    counselor_id: UUID
    scheduled_at: BdmApptStart
    mode: Literal[APPOINTMENT_MODES]
    meeting_link: LeadApptLink = None
    location: _bdm_appt_optional(200) = None
    purpose: _bdm_appt_optional(500) = None
    remarks: _bdm_appt_optional(1000) = None


class LeadAppointmentReschedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduled_at: BdmApptStart
    reason: _bdm_appt_optional(500) = None


class LeadAppointmentCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmApptReason
# --- tel-011 (DEC-SCOPE-094, spec §3): follow-ups on a lead ---------------------------------------------------------------------
LEAD_FOLLOW_UP_LABELS = {"notes": "Notes", "next_action": "Next action"}
LeadFollowUpReason = Literal[LEAD_FOLLOW_UP_REASONS]
LeadFollowUpNotes = Annotated[Annotated[str, _trimmed(2000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, LEAD_FOLLOW_UP_LABELS))]
LeadFollowUpAction = Annotated[Annotated[str, _trimmed(200)] | None, AfterValidator(_trip_text(_BDM_CONTROL, False, LEAD_FOLLOW_UP_LABELS))]


class LeadFollowUpCreate(BaseModel):
    """F5/F6: the due instant (with its offset; the web sends IST), the §7 reason, notes and next action, and the optional move of the
    lead to Follow-up. Creator, status and timestamps are server-owned (unknown fields here)."""

    model_config = ConfigDict(extra="forbid")
    due_at: AwareDatetime
    reason: LeadFollowUpReason
    notes: LeadFollowUpNotes = None
    next_action: LeadFollowUpAction = None
    move_to_follow_up: bool = False


class LeadFollowUpUpdate(BaseModel):
    """Reschedule / edit an open follow-up: only the keys sent are considered (due time and reason can't be cleared)."""

    model_config = ConfigDict(extra="forbid")
    due_at: AwareDatetime | None = None
    reason: LeadFollowUpReason | None = None
    notes: LeadFollowUpNotes = None
    next_action: LeadFollowUpAction = None

    @model_validator(mode="after")
    def _required_stay_set(self):
        for key, label in (("due_at", "Due time"), ("reason", "Reason")):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{label} can't be removed")
        return self


# bdm-015 (DEC-SCOPE-099, spec §5): the daily activity report.
BDM_DAILY_REPORT_LABELS = {"note": "Note", "comment": "Comment"}
DailyReportNote = Annotated[Annotated[str, _trimmed(2000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, BDM_DAILY_REPORT_LABELS))]
DailyReportComment = Annotated[Annotated[str, _trimmed(1000)], AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, True, BDM_DAILY_REPORT_LABELS))]


class BdmDailyReportSubmit(BaseModel):
    """R4: the optional end-of-day note. Counts, owner and times are server-owned (unknown fields → 422)."""

    model_config = ConfigDict(extra="forbid")
    note: DailyReportNote = None


class BdmDailyReportCommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: DailyReportComment


class BdmDailyReportCount(BaseModel):
    key: str
    label: str
    definition: str
    tracked: bool
    count: int | None


class BdmDailyReportManagerComment(BaseModel):
    text: str
    by: BdmPersonRef
    at: datetime


class BdmDailyReportOut(BaseModel):
    """`status` draft = a live preview (nothing stored); submitted = the snapshot taken at `submitted_at`."""

    report_date: date
    bdm: BdmPersonRef
    bdm_type: Literal["agent", "school", "college"]
    status: Literal["draft", "submitted"]
    submitted_at: datetime | None
    note: str | None
    counts: list[BdmDailyReportCount]
    can_submit: bool
    submit_window_days: int
    manager_comment: BdmDailyReportManagerComment | None


class BdmDailyReportDay(BaseModel):
    report_date: date
    status: Literal["submitted", "missing", "not_started"]
    submitted_at: datetime | None


class BdmDailyReportTeamRow(BaseModel):
    bdm: BdmPersonRef
    bdm_type: Literal["agent", "school", "college"]
    days: list[BdmDailyReportDay]


class BdmDailyReportGrid(BaseModel):
    dates: list[date]
    items: list[BdmDailyReportTeamRow]
    total: int
    limit: int
    offset: int


# bdm-016 (DEC-SCOPE-103, spec §5): monthly targets. The month is `YYYY-MM` (IST); the setter and times are server-owned.
BDM_TARGET_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
BdmTargetMonth = Annotated[str, StringConstraints(pattern=BDM_TARGET_MONTH_PATTERN)]
BDM_TARGET_BATCH_MAX = 200


class BdmTargetItem(BaseModel):
    """R4: a whole number 0-100000, or null to clear the target. The KPI is checked against the BDM's catalogue in the service."""

    model_config = ConfigDict(extra="forbid")
    bdm_user_id: UUID
    kpi_key: str = Field(min_length=1, max_length=40)
    target: Annotated[StrictInt, Field(ge=0, le=BDM_TARGET_MAX)] | None


class BdmTargetsPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: BdmTargetMonth
    items: list[BdmTargetItem] = Field(min_length=1, max_length=BDM_TARGET_BATCH_MAX)

    @model_validator(mode="after")
    def _one_value_per_kpi(self):
        pairs = [(i.bdm_user_id, i.kpi_key) for i in self.items]
        if len(set(pairs)) != len(pairs):
            raise ValueError("Each BDM's KPI can appear only once")
        return self


class BdmTargetsCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: BdmTargetMonth


class BdmTargetKpi(BaseModel):
    """`achieved` is null when not tracked or the month hasn't started; `percent` also when no target or a target of 0 (R5)."""

    key: str
    label: str
    definition: str
    tracked: bool
    target: int | None
    achieved: int | None
    percent: int | None


class BdmTargetSheet(BaseModel):
    month: str
    month_status: Literal["past", "current", "future"]
    editable: bool
    bdm: BdmPersonRef
    bdm_type: Literal["agent", "school", "college"]
    kpis: list[BdmTargetKpi]


class BdmTargetTeamRow(BaseModel):
    bdm: BdmPersonRef
    bdm_type: Literal["agent", "school", "college"]
    targets_set: int
    kpi_count: int


class BdmTargetTeam(BaseModel):
    month: str
    month_status: Literal["past", "current", "future"]
    editable: bool
    items: list[BdmTargetTeamRow]
    total: int
    limit: int
    offset: int


class BdmTargetsSaved(BaseModel):
    month: str
    changed: int


class BdmTargetsCopied(BaseModel):
    month: str
    copied: int


# tel-010 (DEC-SCOPE-096): a call on a lead. The caller, lead and timestamps are server-owned (unknown fields here); the outcome rules that
# need the lead (closed, follow-up required, duplicate remarks) are the service's.
LeadCallType = Literal[LEAD_CALL_TYPES]
LeadCallOutcome = Literal[LEAD_CALL_OUTCOMES]
LeadCallDuration = Annotated[int, Field(ge=0, le=LEAD_CALL_MAX_SECONDS)]
LeadCallRemarks = Annotated[Annotated[str, _trimmed(2000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, {"remarks": "Remarks"}))]


class LeadCallCreate(BaseModel):
    """D6: `occurred_at` defaults to now. D5: `next_follow_up` is tel-011's create body."""

    model_config = ConfigDict(extra="forbid")
    occurred_at: AwareDatetime | None = None
    duration_seconds: LeadCallDuration
    call_type: LeadCallType
    outcome: LeadCallOutcome
    remarks: LeadCallRemarks = None
    next_follow_up: LeadFollowUpCreate | None = None


class LeadWhatsAppCreate(BaseModel):
    """tel-013: WA4 the template is optional; WA1 the text as sent (tel-012's limit)."""

    model_config = ConfigDict(extra="forbid")
    channel: Literal["whatsapp"]
    template_id: UUID | None = None
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


def _one_line(value):
    """tel-014 E6: a subject is one header line -- CR/LF become spaces (header injection)."""
    return re.sub(r"[\r\n]+", " ", value) if isinstance(value, str) else value


class LeadEmailCreate(BaseModel):
    """tel-014 (DEC-SCOPE-106): EM4 the template is optional; E6 tel-012's email limits. The recipient is always the lead's address (E7),
    never the caller's."""

    model_config = ConfigDict(extra="forbid")
    channel: Literal["email"]
    template_id: UUID | None = None
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), BeforeValidator(_one_line)]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


LeadMessageCreate = Annotated[LeadWhatsAppCreate | LeadEmailCreate, Field(discriminator="channel")]


class LeadCallUpdate(BaseModel):
    """CL4: same-day details only -- the outcome is locked (an unknown field here). Time, duration and type can't be cleared."""

    model_config = ConfigDict(extra="forbid")
    occurred_at: AwareDatetime | None = None
    duration_seconds: LeadCallDuration | None = None
    call_type: LeadCallType | None = None
    remarks: LeadCallRemarks = None

    @model_validator(mode="after")
    def _required_stay_set(self):
        for key, label in (("occurred_at", "Call time"), ("duration_seconds", "Duration"), ("call_type", "Call type")):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{label} can't be removed")
        return self


# --- tel-019 (DEC-SCOPE-098, spec §3): BDM meeting requests ----------------------------------------------------------------------------
MEETING_REQUEST_LABELS = {
    "organization_name": "Organization", "person_name": "Person", "contact_phone": "Phone", "contact_email": "Email", "location": "Location",
    "purpose": "Purpose", "remarks": "Remarks",
}
_MEETING_PHONE = re.compile(r"^\+?[0-9 ()-]{7,30}$")
_MEETING_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")  # LoginRequest's rule: `.local` demo addresses stay valid


def _meeting_text(max_length: int, required: bool, multiline: bool = False):
    pattern = _BDM_MULTILINE_CONTROL if multiline else _BDM_CONTROL
    text = Annotated[str, _trimmed(max_length)] if required else Annotated[str, _trimmed(max_length)] | None
    return Annotated[text, AfterValidator(_trip_text(pattern, required, MEETING_REQUEST_LABELS))]


def _meeting_phone(value: str) -> str:
    if not _MEETING_PHONE.fullmatch(value):
        raise ValueError("Phone must be 7 to 30 characters: digits, spaces and + - ( )")
    return value


def _meeting_email(value: str | None) -> str | None:
    if value and not _MEETING_EMAIL.fullmatch(value):
        raise ValueError("Enter a valid email address")
    return value or None


class MeetingRequestCreate(BaseModel):
    """MR7: what the telecaller knows. The BDM type follows from the request type (MR5); a named BDM is checked in the service (MR8).
    Server-owned fields (code, status, the deciding BDM, the appointment) are unknown fields here."""

    model_config = ConfigDict(extra="forbid")
    request_type: Literal[BDM_MEETING_REQUEST_TYPES]
    bdm_user_id: UUID | None = None
    organization_name: _meeting_text(200, True)
    person_name: _meeting_text(200, True)
    contact_phone: Annotated[str, _trimmed(30), AfterValidator(_meeting_phone)]
    contact_email: Annotated[Annotated[str, _trimmed(255)] | None, AfterValidator(_meeting_email)] = None
    proposed_at: BdmApptStart
    mode: Literal[APPOINTMENT_MODES]
    location: _meeting_text(255, False) = None
    purpose: _meeting_text(1000, True, multiline=True)
    remarks: _meeting_text(2000, False, multiline=True) = None


class MeetingRequestDecline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmApptReason

# --- tel-018 (DEC-SCOPE-101, spec §3.3): handover, return and the counselor's student link ----------------------------------------
class LeadHandoverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    counselor_id: UUID


class LeadReturnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmApptReason


class LeadStudentLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: UUID


# --- tel-025 (DEC-SCOPE-104, spec §2): telecaller deactivation, team move, handover and manager deactivation --------------------------

TelecallerReassignTarget = Literal["telecaller", "queue"]


class TelecallerReassign(BaseModel):
    """LC3: who takes over the open leads -- an active telecaller of the same team, or the team's unassigned queue. Whether a target is
    required at all depends on the open work, which only the route knows (AC3)."""

    model_config = ConfigDict(extra="forbid")
    target: TelecallerReassignTarget | None = None
    reassign_to: UUID | None = None

    @model_validator(mode="after")
    def _target_matches(self):
        if self.target == "telecaller" and self.reassign_to is None:
            raise ValueError("Choose the telecaller who takes over")
        if self.target != "telecaller" and self.reassign_to is not None:
            raise ValueError("Only a telecaller target takes reassign_to")
        return self


class TelecallerTeamMove(TelecallerReassign):
    team: Literal["it", "overseas"]
    reporting_manager_user_id: UUID | None = None


class TelecallerOpenWork(BaseModel):
    leads: int
    follow_ups: int
    appointments: int


class TelecallerHandoverOut(BaseModel):
    id: UUID
    target: TelecallerReassignTarget | None
    moved: TelecallerOpenWork


class TelecallerDeactivateOut(TelecallerHandoverOut):
    active: bool
    rules_removed: int


class TelecallerTeamMoveOut(TelecallerHandoverOut):
    team: str
    rules_removed: int


class TelecallerManagerDeactivate(BaseModel):
    """D4: `reassign_to` is required only while telecallers report to the manager (checked by the route)."""

    model_config = ConfigDict(extra="forbid")
    reassign_to: UUID | None = None


class TelecallerManagerRow(BdmManagerOption):
    """The reporting-manager picker and the Telecaller managers card: every telecaller reporting to this manager, active or not (D4)."""

    telecaller_count: int


class TelecallerManagerPage(BaseModel):
    items: list[TelecallerManagerRow]
    total: int
    limit: int
    offset: int


class TelecallerManagerDeactivateOut(BaseModel):
    id: UUID
    active: bool
    moved_telecallers: int


# --- rec-001 (DEC-SCOPE-116): recruiter profile -------------------------------------------------------------------------------
RECRUITER_FIELD_LABELS = {"employee_id": "Employee ID", "reporting_manager_user_id": "Reporting manager"}


class RecruiterProfileCreate(BaseModel):
    """spec §4: the Recruiter Staff page sends both, required. The generic Users form sends no profile (an empty one is created)."""

    model_config = ConfigDict(extra="forbid")
    employee_id: BdmEmployeeId
    reporting_manager_user_id: UUID


class RecruiterProfileUpdate(BaseModel):
    """Omitted = unchanged; an explicit null fails (a value, once set, is never cleared here)."""

    model_config = ConfigDict(extra="forbid")
    employee_id: BdmEmployeeId = None
    reporting_manager_user_id: UUID = None


class RecruiterProfileOut(BaseModel):
    employee_id: str | None
    reporting_manager: BdmManagerRef | None


class RecruiterMeOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    division: str
    recruiter_profile: RecruiterProfileOut


class RecruiterTeamRow(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    employee_id: str | None


class RecruiterAdminRow(RecruiterTeamRow):
    reporting_manager: BdmManagerRef | None


class RecruiterTeamPage(BaseModel):
    items: list[RecruiterTeamRow]
    total: int
    limit: int
    offset: int


class RecruiterAdminPage(BaseModel):
    items: list[RecruiterAdminRow]
    total: int
    limit: int
    offset: int


class PlacementManagerRow(BdmManagerOption):
    """The reporting-manager picker: every recruiter reporting to this manager, active or not."""

    recruiter_count: int


class PlacementManagerPage(BaseModel):
    items: list[PlacementManagerRow]
    total: int
    limit: int
    offset: int


# --- rec-002 (DEC-SCOPE-117): recruiter managed lists and campaigns -----------------------------------------------------------------
REC_CATALOGUE_FIELD_LABELS = {
    "name": "Name", "active": "Active", "lead_source_id": "Lead source", "start_date": "Start date", "end_date": "End date",
}


class RecValueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: TelProductName


class RecValueUpdate(BaseModel):
    """Omitted = unchanged; null is a 422 on either key."""

    model_config = ConfigDict(extra="forbid")
    name: TelProductName = None
    active: StrictBool = None


class RecValueOut(BaseModel):
    id: UUID
    name: str
    active: bool
    sort_order: int


class RecValuePage(BaseModel):
    items: list[RecValueOut]
    total: int
    limit: int
    offset: int


class RecCampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: TelCampaignName
    lead_source_id: UUID
    start_date: date
    end_date: date | None = None


class RecCampaignUpdate(BaseModel):
    """Omitted = unchanged; null clears only `end_date`. The date order is checked on the merged row."""

    model_config = ConfigDict(extra="forbid")
    name: TelCampaignName = None
    lead_source_id: UUID = None
    start_date: date = None
    end_date: date | None = None
    active: StrictBool = None


class RecLeadSourceRef(BaseModel):
    id: UUID
    name: str
    active: bool


class RecCampaignOut(BaseModel):
    id: UUID
    name: str
    lead_source: RecLeadSourceRef
    start_date: date
    end_date: date | None
    active: bool


class RecCampaignPage(BaseModel):
    items: list[RecCampaignOut]
    total: int
    limit: int
    offset: int


# --- upc-001 (DEC-SCOPE-118): partnership manager profile ---------------------------------------------------------------------
PARTNERSHIP_FIELD_LABELS = {"employee_id": "Employee ID", "reporting_head_user_id": "Reporting head", "phone": "Phone"}


class PartnershipProfileCreate(BaseModel):
    """spec §5 / PU6: Employee ID and reporting head, both required; nothing optional."""

    model_config = ConfigDict(extra="forbid")
    employee_id: BdmEmployeeId
    reporting_head_user_id: UUID


class PartnershipProfileUpdate(BaseModel):
    """Omitted = unchanged. An explicit null fails (both are required on the row). `user_id` is not a field, so a profile never moves."""

    model_config = ConfigDict(extra="forbid")
    employee_id: BdmEmployeeId = None
    reporting_head_user_id: UUID = None


class PartnershipProfileOut(BaseModel):
    employee_id: str
    reporting_head: BdmManagerRef


class PartnershipMeOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    division: str
    partnership_profile: PartnershipProfileOut


class PartnershipTeamRow(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    employee_id: str


class PartnershipAdminRow(PartnershipTeamRow):
    reporting_head: BdmManagerRef
    head_active: bool


class PartnershipTeamPage(BaseModel):
    items: list[PartnershipTeamRow]
    total: int
    limit: int
    offset: int


class PartnershipAdminPage(BaseModel):
    items: list[PartnershipAdminRow]
    total: int
    limit: int
    offset: int


class PartnershipHeadPage(BaseModel):
    items: list[BdmManagerOption]
    total: int
    limit: int
    offset: int


# --- upc-003 Global University Master (DEC-SCOPE-120, spec §3) --------------------------------------------------------------
UNIVERSITY_FIELD_LABELS = {
    "name": "University name", "city": "City", "state_region": "State / region", "website": "Website", "international_office": "International office",
    "overview": "Overview", "eligibility": "Eligibility", "other_name": "Ranking name", "rank": "Rank",
    # upc-006 contacts
    "designation": "Designation", "department": "Department", "email": "Email", "phone": "Phone", "whatsapp": "WhatsApp", "linkedin": "LinkedIn",
    "notes": "Notes",
}
UNIVERSITY_MAX_RANKINGS = 10
UNIVERSITY_MAX_PROGRAMS = 20


def _university_text(multiline: bool, required: bool):
    """bdm-001's text rule (no control characters; blank -> None) with this item's labels; the website must be http(s)."""

    def check(value: str | None, info: ValidationInfo) -> str | None:
        label = UNIVERSITY_FIELD_LABELS.get(info.field_name or "", info.field_name)
        control = _BDM_CONTROL_MULTILINE if multiline else _BDM_CONTROL
        if value is not None and control.search(value):
            raise ValueError(f"{label} contains invalid characters")
        if not value:
            if required:
                raise ValueError(f"{label} is required")
            return None
        if info.field_name in ("website", "linkedin") and not _BDM_WEBSITE.fullmatch(value):  # http(s) only: no javascript:/data: hrefs
            example = "a link such as linkedin.com/in/name" if info.field_name == "linkedin" else "a website such as abc.ac.uk"
            raise ValueError(f"{label} must start with http:// or https://" if _BDM_SCHEME.match(value) else f"Enter {example}")
        if info.field_name == "email":  # upc-006
            if not _EMAIL_SHAPE.fullmatch(value):
                raise ValueError("Enter a valid email address")
            return value.lower()
        if info.field_name in ("phone", "whatsapp") and not _BDM_PHONE.fullmatch(value):
            raise ValueError(f"{label} may contain only digits, spaces and + - ( )")
        return value

    return check


def _university_str(max_length: int, *, required: bool = False, multiline: bool = False):
    trimmed = Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)]
    text = Annotated[trimmed if required else trimmed | None, AfterValidator(_university_text(multiline, required))]
    return Annotated[text, BeforeValidator(_bdm_newlines)] if multiline else text


def _university_body(value: str, info: ValidationInfo) -> str:
    """Catalogue text (overview, eligibility) sits in NOT NULL columns, so blank stays "" rather than None."""
    return _university_text(True, False)(value, info) or ""


UniversityName = _university_str(200, required=True)
UniversityCity = _university_str(120, required=True)
UniversityShort = _university_str(120)
UniversityWebsite = Annotated[_university_str(300), BeforeValidator(_bdm_website_prefix)]
UniversityOffice = _university_str(1000, multiline=True)
UniversityBody = Annotated[str, BeforeValidator(_bdm_newlines), StringConstraints(strip_whitespace=True, max_length=5000), AfterValidator(_university_body)]
InstitutionType = Literal[INSTITUTION_TYPES]
UniversityOwnership = Literal[UNIVERSITY_OWNERSHIP_TYPES]
UniversityRelationship = Literal[UNIVERSITY_RELATIONSHIPS]
UniversityPriority = Literal[UNIVERSITY_PRIORITIES]
PartnershipPotential = Literal[PARTNERSHIP_POTENTIALS]
RelationshipStrength = Literal[RELATIONSHIP_STRENGTHS]  # upc-006 CT4: §11 exactly


def _program(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 80 or _BDM_CONTROL.search(value):
        raise ValueError("Each programme area must be 1 to 80 plain characters")
    return value


def _distinct(values: list) -> list:
    if len({v.casefold() for v in values}) != len(values):
        raise ValueError("List each value once")
    return values


class UniversityRankingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: Literal[RANKING_SYSTEMS]
    other_name: _university_str(80) = None
    year: Annotated[StrictInt, Field(ge=1900, le=2100)]
    rank: _university_str(20, required=True)

    @model_validator(mode="after")
    def _other_name(self):
        if (self.system == "Other") != (self.other_name is not None):
            raise ValueError("Name the ranking system for an Other ranking, and only then")
        return self


def _rankings(values: list[UniversityRankingIn]) -> list[UniversityRankingIn]:
    keys = [(r.system, (r.other_name or "").casefold(), r.year) for r in values]
    if len(set(keys)) != len(keys):
        raise ValueError("Each ranking system and year may appear once")
    return values


UniversityRankings = Annotated[list[UniversityRankingIn], Field(max_length=UNIVERSITY_MAX_RANKINGS), AfterValidator(_rankings)]
CourseLevels = Annotated[list[Literal[COURSE_LEVELS]], Field(max_length=len(COURSE_LEVELS)), AfterValidator(_distinct)]
PopularPrograms = Annotated[list[Annotated[str, AfterValidator(_program)]], Field(max_length=UNIVERSITY_MAX_PROGRAMS), AfterValidator(_distinct)]


# upc-004 UD2: why a head / super_admin adds a university that matches an existing one (audited; ignored when nothing matches).
DuplicateReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=500)] | None


class UniversityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: UniversityName
    country_id: UUID
    city: UniversityCity
    institution_type: InstitutionType = "university"
    ownership_type: UniversityOwnership | None = None
    state_region: UniversityShort = None
    website: UniversityWebsite = None
    course_levels: CourseLevels = []
    popular_programs: PopularPrograms = []
    international_office: UniversityOffice = None
    existing_relationship: UniversityRelationship | None = None
    priority: UniversityPriority | None = None
    partnership_potential: PartnershipPotential | None = None
    relationship_strength: RelationshipStrength | None = None
    overview: UniversityBody = ""
    eligibility: UniversityBody = ""
    rankings: UniversityRankings = []
    duplicate_reason: DuplicateReason = None


class UniversityUpdate(BaseModel):
    """PATCH: omitted = unchanged; an explicit null on a required field fails its non-nullable type (bdm-001's idiom). The code, slug,
    owners, visibility and active flag are server-owned, so sending them is a 422 (extra="forbid")."""

    model_config = ConfigDict(extra="forbid")
    name: UniversityName = None
    country_id: UUID = None
    city: UniversityCity = None
    institution_type: InstitutionType = None
    ownership_type: UniversityOwnership | None = None
    state_region: UniversityShort = None
    website: UniversityWebsite = None
    course_levels: CourseLevels = None
    popular_programs: PopularPrograms = None
    international_office: UniversityOffice = None
    existing_relationship: UniversityRelationship | None = None
    priority: UniversityPriority | None = None
    partnership_potential: PartnershipPotential | None = None
    relationship_strength: RelationshipStrength | None = None
    overview: UniversityBody = None
    eligibility: UniversityBody = None
    rankings: UniversityRankings = None
    duplicate_reason: DuplicateReason = None


class UniversityAssign(BaseModel):
    """The whole ownership, both slots: a missing or null slot is cleared."""

    model_config = ConfigDict(extra="forbid")
    primary_manager_user_id: UUID | None = None
    backup_manager_user_id: UUID | None = None

    @model_validator(mode="after")
    def _slots(self):
        if self.backup_manager_user_id is not None and self.primary_manager_user_id is None:
            raise ValueError("Choose a primary manager before a backup")
        if self.backup_manager_user_id is not None and self.backup_manager_user_id == self.primary_manager_user_id:
            raise ValueError("The backup manager must be a different person")
        return self


class UniversityDeactivate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: StrictBool = False


class UniversityCountryRef(BaseModel):
    id: UUID
    name: str
    iso2: str | None
    region: str | None
    catalogue_visible: bool


class UniversityRankingOut(BaseModel):
    system: str
    other_name: str | None
    year: int
    rank: str


class UniversityPermissions(BaseModel):
    can_edit: bool
    can_assign: bool
    can_publish: bool
    can_deactivate: bool
    can_move_stage: bool  # upc-007 PS5
    can_reopen: bool  # upc-007 PS6
    can_edit_contacts: bool  # upc-006 CT5


class UniversityRow(BaseModel):
    id: UUID
    university_code: str
    slug: str
    name: str
    institution_type: str
    country: UniversityCountryRef
    city: str
    priority: str | None
    partnership_potential: str | None
    relationship_strength: str | None
    primary_manager: BdmManagerRef | None
    backup_manager: BdmManagerRef | None
    catalogue_visible: bool
    active: bool
    stage: str
    stage_label: str
    lost: bool
    permissions: UniversityPermissions


class UniversityStageRef(BaseModel):
    key: str
    label: str
    column: str


class UniversityLostOut(BaseModel):
    at: datetime
    reason: str


class UniversityPipelineOut(BaseModel):
    """upc-007: the stored stage, its Kanban column, the Lost flag and the catalogue (labels come from the API, not the client)."""

    stage: str
    stage_label: str
    column: str
    column_label: str
    changed_at: datetime
    lost: UniversityLostOut | None
    stages: list[UniversityStageRef]


class UniversityDetail(UniversityRow):
    ownership_type: str | None
    state_region: str | None
    website: str | None
    course_levels: list[str]
    popular_programs: list[str]
    international_office: str | None
    existing_relationship: str | None
    overview: str
    eligibility: str
    rankings: list[UniversityRankingOut]
    application_count: int
    linked_bdm_organizations: list["LinkedBdmOrganization"]  # upc-004 UD11
    created_at: datetime
    updated_at: datetime
    pipeline: UniversityPipelineOut
    follow_up: "UniversityFollowUpOut"  # upc-020 TK14/TK15


class LinkedBdmOrganization(BaseModel):
    id: UUID
    code: str
    name: str
    city: str
    bdm_type: str
    assigned_bdm_name: str
    archived: bool


class UniversityMatchCountry(BaseModel):
    id: UUID
    name: str


class UniversityMatch(BaseModel):
    """upc-004 UD5: the duplicate panel's fields (no commission, for every role that sees it)."""

    id: UUID
    university_code: str
    name: str
    country: UniversityMatchCountry
    city: str
    active: bool
    catalogue_visible: bool
    existing_relationship: str | None
    primary_manager: BdmManagerRef | None
    backup_manager: BdmManagerRef | None


class UniversityMatchPage(BaseModel):
    items: list[UniversityMatch]
    total: int


class UniversityEnvelope(BaseModel):
    university: UniversityDetail


class UniversityPage(BaseModel):
    items: list[UniversityRow]
    total: int
    limit: int
    offset: int


# --- upc-007 (DEC-SCOPE-126, spec §3): stage moves, Lost / Reopen, stage history and the Kanban board -------------------------------
class UniversityStageMove(BaseModel):
    """PS4: `from_stage` is the stage the form was showing -- a different stored stage is 409 `stage_changed`."""

    model_config = ConfigDict(extra="forbid")
    from_stage: BdmStageKey
    to_stage: BdmStageKey
    note: BdmPipelineNote = None


class UniversityStageReason(BaseModel):
    """PS7: Lost and Reopen each need a reason."""

    model_config = ConfigDict(extra="forbid")
    reason: BdmPipelineReason


class UniversityStageEventOut(BaseModel):
    id: UUID
    kind: Literal["move", "lost", "reopened"]
    from_stage: str
    from_label: str
    to_stage: str
    to_label: str
    note: str | None
    actor: BdmPersonRef
    created_at: datetime


class UniversityStageEventPage(BaseModel):
    items: list[UniversityStageEventOut]
    total: int
    limit: int
    offset: int


class UniversityPipelineColumn(BaseModel):
    key: str
    label: str
    stages: list[str]
    count: int


class UniversityPipelineItem(BaseModel):
    id: UUID
    university_code: str
    name: str
    city: str
    country_name: str
    stage: str
    stage_label: str
    column: str
    lost: bool
    primary_manager: BdmManagerRef | None


class UniversityPipelinePage(BaseModel):
    columns: list[UniversityPipelineColumn]
    lost_count: int
    items: list[UniversityPipelineItem]
    total: int
    limit: int
    offset: int


# --- upc-006 University contacts (DEC-SCOPE-123, spec §3) --------------------------------------------------------------------
UNIVERSITY_MAX_CONTACTS = 50
ContactName = _university_str(200, required=True)
ContactShort = _university_str(120)
ContactPhone = _university_str(30)
ContactEmail = _university_str(255)
ContactLinkedIn = Annotated[_university_str(300), BeforeValidator(_bdm_website_prefix)]
ContactNotes = _university_str(2000, multiline=True)
ContactChannel = Literal[CONTACT_CHANNELS]
ContactRoleCode = Annotated[str, StringConstraints(max_length=40)]  # checked against the catalogue by the service (422)


class UniversityContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ContactName
    designation: ContactShort = None
    department: ContactShort = None
    role_code: ContactRoleCode | None = None
    email: ContactEmail = None
    phone: ContactPhone = None
    whatsapp: ContactPhone = None
    linkedin: ContactLinkedIn = None
    preferred_channel: ContactChannel | None = None
    relationship_strength: RelationshipStrength | None = None
    notes: ContactNotes = None
    is_primary: StrictBool = False
    shareable: StrictBool = False


class UniversityContactUpdate(BaseModel):
    """PATCH: omitted = unchanged; null clears an optional field and fails `name`/`is_primary`/`shareable`. `is_primary: false` is refused
    by the route (CT6: make another contact primary instead)."""

    model_config = ConfigDict(extra="forbid")
    name: ContactName = None
    designation: ContactShort = None
    department: ContactShort = None
    role_code: ContactRoleCode | None = None
    email: ContactEmail = None
    phone: ContactPhone = None
    whatsapp: ContactPhone = None
    linkedin: ContactLinkedIn = None
    preferred_channel: ContactChannel | None = None
    relationship_strength: RelationshipStrength | None = None
    notes: ContactNotes = None
    is_primary: StrictBool = None
    shareable: StrictBool = None


class UniversityContactRoleOut(BaseModel):
    code: str
    label: str


class UniversityContactRolePage(BaseModel):
    items: list[UniversityContactRoleOut]


class UniversityContactOut(BaseModel):
    id: UUID
    university_id: UUID
    name: str
    designation: str | None
    department: str | None
    role: UniversityContactRoleOut | None
    email: str | None
    phone: str | None
    whatsapp: str | None
    linkedin: str | None
    preferred_channel: str | None
    relationship_strength: str | None
    notes: str | None  # null in the shareable slice (CT14)
    is_primary: bool
    shareable: bool
    created_at: datetime
    updated_at: datetime


class UniversityContactEnvelope(BaseModel):
    contact: UniversityContactOut


class UniversityContactPage(BaseModel):
    items: list[UniversityContactOut]
    total: int
    limit: int
    offset: int


# --- upc-010 (DEC-SCOPE-130): university visits (§8). Limits per VS18; participants and contacts per VS11/VS12 ------------------------
VISIT_MAX_PARTICIPANTS = 10
VISIT_MAX_CONTACTS = 20
VisitPurpose = _university_str(1000, required=True, multiline=True)
VisitLong = _university_str(2000, multiline=True)
VisitNotes = _university_str(1000, multiline=True)
VisitCity = _university_str(120)
VisitReason = _university_str(1000, required=True, multiline=True)
VisitStatus = Literal["planned", "approved", "travel_booked", "visit_completed", "follow_up", "closed"]  # = UNIVERSITY_VISIT_STATUSES (§8)


def _unique_ids(values: list[UUID] | None) -> list[UUID] | None:
    """A repeated pick is one pick (order kept)."""
    return None if values is None else list(dict.fromkeys(values))


VisitParticipants = Annotated[list[UUID], Field(max_length=VISIT_MAX_PARTICIPANTS), AfterValidator(_unique_ids)]
VisitContacts = Annotated[list[UUID], Field(max_length=VISIT_MAX_CONTACTS), AfterValidator(_unique_ids)]


class UniversityVisitIn(BaseModel):
    """`lead_user_id` defaults to the caller; `city` to the university's city (VS1)."""

    model_config = ConfigDict(extra="forbid")
    university_id: UUID
    lead_user_id: UUID | None = None
    city: VisitCity = None
    purpose: VisitPurpose
    proposed_date: date
    confirmed_date: date | None = None
    travel_required: StrictBool = False
    travel_notes: VisitNotes = None
    hotel_required: StrictBool = False
    hotel_notes: VisitNotes = None
    agenda: VisitLong = None
    expected_outcome: VisitLong = None
    participant_user_ids: VisitParticipants = []
    contact_ids: VisitContacts = []


class UniversityVisitUpdate(BaseModel):
    """PATCH: omitted = unchanged; null clears an optional field and fails a required one. The university never changes (create a new
    visit); which fields may change depends on the status (VS9, decided by the service)."""

    model_config = ConfigDict(extra="forbid")
    lead_user_id: UUID = None
    city: UniversityCity = None
    purpose: VisitPurpose = None
    proposed_date: date = None
    confirmed_date: date | None = None
    travel_required: StrictBool = None
    travel_notes: VisitNotes = None
    hotel_required: StrictBool = None
    hotel_notes: VisitNotes = None
    agenda: VisitLong = None
    expected_outcome: VisitLong = None
    follow_up_date: date | None = None
    participant_user_ids: VisitParticipants = None
    contact_ids: VisitContacts = None


class UniversityVisitComplete(BaseModel):
    """AC3: completing a visit asks for the follow-up date."""

    model_config = ConfigDict(extra="forbid")
    follow_up_date: date


class UniversityVisitReject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: VisitReason


class UniversityVisitClose(BaseModel):
    """VS5: the reason is required when a visit is closed before it happened (checked by the service)."""

    model_config = ConfigDict(extra="forbid")
    reason: VisitNotes = None


class VisitPerson(BaseModel):
    id: UUID
    full_name: str
    active: bool


class VisitCountryRef(BaseModel):
    id: UUID
    name: str


class VisitUniversityRef(BaseModel):
    id: UUID
    name: str
    university_code: str
    city: str
    country: VisitCountryRef


class VisitContactRef(BaseModel):
    id: UUID
    name: str
    designation: str | None


class VisitEventOut(BaseModel):
    action: str
    from_status: str | None
    to_status: str | None
    actor: VisitPerson
    reason: str | None
    created_at: datetime


class VisitPermissions(BaseModel):
    can_edit: bool
    can_submit: bool
    can_decide: bool
    can_book: bool
    can_complete: bool
    can_follow_up: bool
    can_close: bool


class UniversityVisitRow(BaseModel):
    id: UUID
    code: str
    university: VisitUniversityRef
    city: str
    lead: VisitPerson
    proposed_date: date
    confirmed_date: date | None
    status: str
    approval_state: Literal["draft", "waiting", "returned"] | None  # only while planned (VS2)
    submitted_at: datetime | None


class UniversityVisitOut(UniversityVisitRow):
    purpose: str
    created_by: VisitPerson
    travel_required: bool
    travel_notes: str | None
    hotel_required: bool
    hotel_notes: str | None
    agenda: str | None
    expected_outcome: str | None
    follow_up_date: date | None
    rejection_reason: str | None
    decided_by: VisitPerson | None
    decided_at: datetime | None
    close_reason: str | None
    participants: list[VisitPerson]
    contacts: list[VisitContactRef]
    events: list[VisitEventOut]
    permissions: VisitPermissions
    editable_fields: list[str]
    created_at: datetime
    updated_at: datetime


class UniversityVisitEnvelope(BaseModel):
    visit: UniversityVisitOut


class UniversityVisitPage(BaseModel):
    items: list[UniversityVisitRow]
    total: int
    limit: int
    offset: int


class VisitOption(BaseModel):
    id: UUID
    label: str
    detail: str | None


class VisitOptionPage(BaseModel):
    items: list[VisitOption]
    total: int


# --- upc-020 (DEC-SCOPE-139, spec §3): partnership tasks and follow-ups ----------------------------------------------------------
PartnershipTaskKind = Literal["follow_up", "task"]  # = partnership_task_rules.KINDS
PartnershipTaskPriority = Literal["high", "medium", "low"]  # = partnership_task_rules.PRIORITIES
PartnershipTaskBand = Literal["overdue", "today", "tomorrow", "upcoming", "open", "done", "cancelled"]  # TK13 (+ every open item)
PartnershipTaskTitle = _university_str(200, required=True)
PartnershipTaskNotes = _university_str(2000, multiline=True)
PartnershipTaskReason = _university_str(500, required=True, multiline=True)


class PartnershipTaskIn(BaseModel):
    """TK9/TK10: the assignee defaults to the caller. Source, status and timestamps are server-owned (unknown fields here)."""

    model_config = ConfigDict(extra="forbid")
    university_id: UUID
    kind: PartnershipTaskKind
    title: PartnershipTaskTitle
    due_on: date
    priority: PartnershipTaskPriority = "medium"
    assignee_user_id: UUID | None = None
    notes: PartnershipTaskNotes = None


class PartnershipTaskUpdate(BaseModel):
    """TK12: omitted = unchanged; `notes: null` clears; a sent null title, priority or assignee is refused. The due date changes only
    through `reschedule`."""

    model_config = ConfigDict(extra="forbid")
    title: PartnershipTaskTitle = None
    priority: PartnershipTaskPriority = None
    assignee_user_id: UUID = None
    notes: PartnershipTaskNotes = None


class PartnershipTaskReschedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    due_on: date


class PartnershipTaskCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: PartnershipTaskReason


class PartnershipTaskUniversity(BaseModel):
    id: UUID
    university_code: str
    name: str


class PartnershipTaskPermissions(BaseModel):
    can_edit: bool
    can_reschedule: bool
    can_complete: bool
    can_cancel: bool


class PartnershipTaskOut(BaseModel):
    id: UUID
    university: PartnershipTaskUniversity
    kind: str
    title: str
    notes: str | None
    due_on: date
    priority: str
    status: str
    band: str
    overdue: bool
    source: str
    assignee: BdmManagerRef
    created_by: BdmManagerRef
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime
    permissions: PartnershipTaskPermissions


class PartnershipTaskEnvelope(BaseModel):
    task: PartnershipTaskOut


class PartnershipTaskCounts(BaseModel):
    overdue: int
    today: int
    tomorrow: int
    upcoming: int
    done: int
    cancelled: int


class PartnershipTaskPage(BaseModel):
    items: list[PartnershipTaskOut]
    total: int
    limit: int
    offset: int
    today: date
    counts: PartnershipTaskCounts


class PartnershipTaskCatalogue(BaseModel):
    titles: list[str]


class UniversityNextAction(BaseModel):
    """TK14: the earliest open follow-up (§20 "Next Action + Next Action Date", Owner, Priority)."""

    id: UUID
    title: str
    due_on: date
    priority: str
    band: str
    assignee: BdmManagerRef


class UniversityLastAction(BaseModel):
    """TK15: the later of the latest completed task and the latest stage move."""

    title: str
    at: datetime


class UniversityFollowUpOut(BaseModel):
    next_action: UniversityNextAction | None
    last_action: UniversityLastAction | None


# --- rec-006 (DEC-SCOPE-119): the recruiter Skills Master ------------------------------------------------------------------------
SKILL_FIELD_LABELS = {
    "name": "Name", "alias": "Alias", "active": "Active", "category_id": "Category", "tag_category_ids": "Other categories", "skill_id": "Related skill",
    "into_skill_id": "Merge into",
}
_SPACES = re.compile(r" +")


def _skill_term(label: str, max_length: int = 80):
    """Trimmed with inner spaces collapsed (services/skills.normalise, so the lower() indexes decide duplicates), required, capped, no
    control characters; each failure names the field."""

    def check(value: str) -> str:
        value = _SPACES.sub(" ", value.strip())
        if not value:
            raise ValueError(f"{label} is required")
        if len(value) > max_length:
            raise ValueError(f"{label} must be at most {max_length} characters")
        if _BDM_CONTROL.search(value):
            raise ValueError(f"{label} contains invalid characters")
        return value

    return Annotated[str, AfterValidator(check)]


def _pick(noun: str):
    """A UUID chosen from a list; a malformed one reads as a sentence, not a pydantic error."""

    def check(value):
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except ValueError:
            raise ValueError(f"Choose {noun} from the list") from None

    return Annotated[UUID, BeforeValidator(check)]


RecSkillName, SkillAliasText = _skill_term("Name"), _skill_term("Alias")
SkillCategoryPick, SkillPick = _pick("a category"), _pick("a skill")


def _distinct_tags(value: list[UUID]) -> list[UUID]:
    if len(set(value)) != len(value):
        raise ValueError("Other categories must not repeat")
    if len(value) > 10:
        raise ValueError("Choose at most 10 other categories")
    return value


SkillTags = Annotated[list[SkillCategoryPick], AfterValidator(_distinct_tags)]


class SkillCategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: RecSkillName


class SkillCategoryUpdate(BaseModel):
    """Omitted = unchanged; an explicit null is a 422 (both are required on the row)."""

    model_config = ConfigDict(extra="forbid")
    name: RecSkillName = None
    active: StrictBool = None


class SkillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: RecSkillName
    category_id: SkillCategoryPick
    tag_category_ids: SkillTags = []


class SkillUpdate(BaseModel):
    """Omitted = unchanged; `tag_category_ids` replaces the whole set ([] clears it)."""

    model_config = ConfigDict(extra="forbid")
    name: RecSkillName = None
    category_id: SkillCategoryPick = None
    tag_category_ids: SkillTags = None
    active: StrictBool = None


class SkillAliasCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: SkillAliasText


class SkillRelatedCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: SkillPick


class SkillMerge(BaseModel):
    """rec-011 SK7: merge this skill into another (the kept one)."""

    model_config = ConfigDict(extra="forbid")
    into_skill_id: SkillPick


class SkillCategoryOut(BaseModel):
    id: UUID
    name: str
    active: bool
    sort_order: int


class SkillCategoryPage(BaseModel):
    items: list[SkillCategoryOut]
    total: int
    limit: int
    offset: int


class SkillRef(BaseModel):
    id: UUID
    name: str
    active: bool


class SkillAliasOut(BaseModel):
    id: UUID
    alias: str


class SkillOut(BaseModel):
    id: UUID
    name: str
    active: bool
    category: SkillRef
    tags: list[SkillRef]
    aliases: list[SkillAliasOut]
    related: list[SkillRef]


class SkillPage(BaseModel):
    items: list[SkillOut]
    total: int
    limit: int
    offset: int


# --- rec-003 (DEC-SCOPE-121): the company master ----------------------------------------------------------------------------------
REC_COMPANY_LABELS = {
    "name": "Company name", "website": "Website", "linkedin_url": "LinkedIn", "city": "City", "state": "State", "country": "Country",
    "head_office": "Head office", "branches": "Branches", "description": "Company description",
}
REC_COMPANY_MULTILINE = frozenset({"branches", "description"})
REC_COMPANY_URLS = frozenset({"website", "linkedin_url"})
REC_COMPANY_FIELDS = (  # the columns a create or edit may write; everything else on `companies` is server-owned
    "name", "website", "linkedin_url", "industry_id", "company_size_id", "employee_count", "city", "state", "country", "head_office",
    "branches", "description", "lead_source_id", "campaign_id", "priority", "assigned_bdm_user_id",
)


def _rec_company_text(value: str | None, info: ValidationInfo) -> str | None:
    """bdm-002's rules with this module's labels: no control characters (a line break only in a multi-line field), blank -> None, and
    http(s) links only, so a stored value can never become a javascript:/data: href."""
    label = REC_COMPANY_LABELS[info.field_name]
    control = _BDM_CONTROL_MULTILINE if info.field_name in REC_COMPANY_MULTILINE else _BDM_CONTROL
    if value is not None and control.search(value):
        raise ValueError(f"{label} contains invalid characters")
    if not value:
        return None
    if info.field_name in REC_COMPANY_URLS and not _BDM_WEBSITE.fullmatch(value):
        raise ValueError(f"{label} must start with http:// or https://" if _BDM_SCHEME.match(value) else f"Enter a {label} link such as example.com")
    return value


def _rec_company_name(value: str, info: ValidationInfo) -> str:
    value = _rec_company_text(value, info)
    if value is None:
        raise ValueError("Company name is required")
    return value


def _rec_company_optional(max_length: int, *, multiline: bool = False, url: bool = False):
    text = Annotated[Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)] | None, AfterValidator(_rec_company_text)]
    if multiline:
        text = Annotated[text, BeforeValidator(_bdm_newlines)]
    return Annotated[text, BeforeValidator(_bdm_website_prefix)] if url else text


RecCompanyName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=180), AfterValidator(_rec_company_name)]
RecCompanyShort = _rec_company_optional(120)
RecCompanyUrl = _rec_company_optional(300, url=True)
RecCompanyPlace = _rec_company_optional(300)
RecCompanyBranches = _rec_company_optional(1000, multiline=True)
RecCompanyDescription = _rec_company_optional(2000, multiline=True)
RecEmployeeCount = _bdm_whole_number("Number of employees must be a whole number from 0 to 10,000,000", 0, 10_000_000)
RecCompanyPriority = Literal["hot", "warm", "cold"]


# --- rec-004 (DEC-SCOPE-125): company contacts ------------------------------------------------------------------------------------
REC_CONTACT_LABELS = {
    "designation": "Designation", "department": "Department", "mobile": "Mobile", "email": "Email", "linkedin_url": "LinkedIn", "notes": "Notes",
}
REC_CONTACT_MAX = 50  # C4: active and inactive together; bounds the unpaginated list


def _rec_contact_text(value: str | None, info: ValidationInfo) -> str | None:
    """bdm-002's rules with this module's labels: no control characters (a line break only in notes), blank -> None, a mobile the
    duplicate/call lookups can match (normalise_phone), a lower-cased email, and http(s) LinkedIn links only."""
    field = info.field_name
    label = REC_CONTACT_LABELS[field]
    control = _BDM_CONTROL_MULTILINE if field == "notes" else _BDM_CONTROL
    if value is not None and control.search(value):
        raise ValueError(f"{label} contains invalid characters")
    if not value:
        return None
    if field == "email":
        if not _EMAIL_SHAPE.fullmatch(value):
            raise ValueError("Enter a valid email address")
        return value.lower()
    if field == "mobile" and (not _BDM_PHONE.fullmatch(value) or normalise_phone(value) is None):
        raise ValueError("Enter a valid mobile number")
    if field == "linkedin_url" and not _BDM_WEBSITE.fullmatch(value):
        raise ValueError("LinkedIn must start with http:// or https://" if _BDM_SCHEME.match(value) else "Enter a LinkedIn link such as linkedin.com/in/name")
    return value


def _rec_contact_optional(max_length: int, *, before=None):
    text = Annotated[Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)] | None, AfterValidator(_rec_contact_text)]
    return Annotated[text, BeforeValidator(before)] if before else text


RecContactShort = _rec_contact_optional(120)
RecContactMobile = _rec_contact_optional(40)
RecContactEmail = _rec_contact_optional(255)
RecContactLinkedIn = _rec_contact_optional(300, before=_bdm_website_prefix)
RecContactNotes = _rec_contact_optional(2000, before=_bdm_newlines)
RecContactChannel = Literal["call", "whatsapp", "email"]


class RecContactUpdate(BaseModel):
    """PATCH: omitted = unchanged, null = clear; a sent null on name / is_primary / active fails the non-nullable type. `is_primary: true`
    makes this the primary (false is refused: choose another); `active` deactivates or reactivates (C2)."""

    model_config = ConfigDict(extra="forbid")
    name: BdmContactName = None
    designation: RecContactShort = None
    department: RecContactShort = None
    role_id: UUID | None = None
    mobile: RecContactMobile = None
    email: RecContactEmail = None
    linkedin_url: RecContactLinkedIn = None
    preferred_channel: RecContactChannel | None = None
    notes: RecContactNotes = None
    is_primary: StrictBool = None
    active: StrictBool = None


class RecContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: BdmContactName
    designation: RecContactShort = None
    department: RecContactShort = None
    role_id: UUID | None = None
    mobile: RecContactMobile = None
    email: RecContactEmail = None
    linkedin_url: RecContactLinkedIn = None
    preferred_channel: RecContactChannel | None = None
    notes: RecContactNotes = None
    is_primary: StrictBool = False


REC_CONTACT_FIELDS = ("name", "designation", "department", "role_id", "mobile", "email", "linkedin_url", "preferred_channel", "notes")


class RecCompanyUpdate(BaseModel):
    """PATCH: omitted = unchanged, null = clear (a null name fails its type). Server-owned fields (code, assignee, archive, creator) are
    unknown fields, so a client can never set them; the recruiter changes only through /assign."""

    model_config = ConfigDict(extra="forbid")
    name: RecCompanyName = None
    website: RecCompanyUrl = None
    linkedin_url: RecCompanyUrl = None
    industry_id: UUID | None = None
    company_size_id: UUID | None = None
    employee_count: RecEmployeeCount = None
    city: RecCompanyShort = None
    state: RecCompanyShort = None
    country: RecCompanyShort = None
    head_office: RecCompanyPlace = None
    branches: RecCompanyBranches = None
    description: RecCompanyDescription = None
    lead_source_id: UUID | None = None
    campaign_id: UUID | None = None
    priority: RecCompanyPriority | None = None
    assigned_bdm_user_id: UUID | None = None
    confirm_duplicate: StrictBool = False


class RecCompanyCreate(RecCompanyUpdate):
    name: RecCompanyName
    assigned_recruiter_user_id: UUID | None = None  # managers and super_admin only (services/recruiter_companies)
    contact: RecContactIn | None = None  # rec-004 C7 "+ Add Recruiter": the first contact, created as primary in the same transaction


class RecCompanyAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recruiter_user_id: UUID


class RecPersonRef(BaseModel):
    id: UUID
    full_name: str
    active: bool


class RecCatalogueRef(BaseModel):
    id: UUID
    name: str
    active: bool


class RecCompanyPermissions(BaseModel):
    can_edit: bool
    can_archive: bool
    can_restore: bool
    can_reassign: bool


class RecCompanyRow(BaseModel):
    id: UUID
    code: str
    name: str
    city: str | None
    priority: str | None
    industry: RecCatalogueRef | None
    lead_source: RecCatalogueRef | None
    assigned_recruiter: RecPersonRef | None
    archived: bool
    permissions: RecCompanyPermissions
    stage: str
    stage_label: str
    lost: bool
    next_follow_up_at: datetime | None = None  # rec-024 FU9: the earliest open follow-up (derived)


class RecCompanyPage(BaseModel):
    items: list[RecCompanyRow]
    total: int
    limit: int
    offset: int


class RecAssignmentOut(BaseModel):
    from_user: RecPersonRef | None
    to_user: RecPersonRef
    changed_by: RecPersonRef
    created_at: datetime


# --- rec-005 (DEC-SCOPE-127, spec §4): the company pipeline ---------------------------------------------------------------------
RecStageKey = Annotated[str, StringConstraints(pattern=r"^[a-z_]{1,30}$")]


class RecPipelineStep(BaseModel):
    key: str
    label: str
    kind: Literal["start", "manual", "driven"]
    state: Literal["done", "current", "upcoming"]


class RecLostOut(BaseModel):
    at: datetime
    reason: str


class RecPipelineOut(BaseModel):
    stage: str
    stage_label: str
    stage_changed_at: datetime
    lost: RecLostOut | None
    can_move: bool
    can_reopen: bool
    steps: list[RecPipelineStep]


class RecStageMove(BaseModel):
    """`from_stage` is the stage the form was showing -- a different stored stage is 409 `stage_changed`."""

    model_config = ConfigDict(extra="forbid")
    from_stage: RecStageKey
    to_stage: RecStageKey
    reason: BdmPipelineNote = None


class RecStageReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmPipelineReason


class RecActorRef(BaseModel):
    id: UUID
    full_name: str


class RecStageEventOut(BaseModel):
    id: UUID
    event: str
    from_stage: str
    from_label: str
    to_stage: str
    to_label: str
    reason: str | None
    actor: RecActorRef | None
    created_at: datetime


class RecStageEventPage(BaseModel):
    items: list[RecStageEventOut]
    total: int
    limit: int
    offset: int


class RecBoardStage(BaseModel):
    key: str
    label: str
    kind: Literal["start", "manual", "driven"]
    count: int


class RecBoardItem(BaseModel):
    id: UUID
    code: str
    name: str
    city: str | None
    priority: str | None
    assigned_recruiter: RecPersonRef | None
    stage: str
    stage_label: str
    lost: bool


class RecBoardOut(BaseModel):
    stages: list[RecBoardStage]
    lost_count: int
    items: list[RecBoardItem]
    total: int
    limit: int
    offset: int


class RecCompanyOut(RecCompanyRow):
    website: str | None
    linkedin_url: str | None
    company_size: RecCatalogueRef | None
    employee_count: int | None
    state: str | None
    country: str | None
    head_office: str | None
    branches: str | None
    description: str | None
    campaign: RecCatalogueRef | None
    assigned_bdm: RecPersonRef | None
    owner_type: str
    created_by: RecPersonRef | None
    assignment_history: list[RecAssignmentOut]
    pipeline: RecPipelineOut
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RecCompanyEnvelope(BaseModel):
    company: RecCompanyOut


class RecContactOut(BaseModel):
    id: UUID
    name: str
    designation: str | None
    department: str | None
    role: RecCatalogueRef | None
    mobile: str | None
    email: str | None
    linkedin_url: str | None
    preferred_channel: str | None
    notes: str | None
    is_primary: bool
    active: bool
    last_contacted_at: datetime | None  # C6: the latest call (rec-025) or message (rec-026 MS10); meetings join with rec-028
    next_follow_up_at: datetime | None = None  # rec-024 FU9: the earliest open follow-up about this contact
    whatsapp_to: str | None = None  # rec-026 MS6: the wa.me number (E.164 digits), None when the mobile is unusable
    created_at: datetime
    updated_at: datetime


class RecContactList(BaseModel):
    items: list[RecContactOut]
    can_edit: bool


class RecBdmOption(BaseModel):
    id: UUID
    full_name: str


class RecBdmOptionPage(BaseModel):
    items: list[RecBdmOption]
    total: int


# --- rec-009 (DEC-SCOPE-122, spec §3/§5): the candidate master ------------------------------------------------------------------
CandidateStatus = Literal[CANDIDATE_STATUSES]
CANDIDATE_FIELD_LABELS = {
    "name": "Name", "mobile": "Mobile", "email": "Email", "location": "Location", "qualification": "Qualification", "college": "College",
    "passing_year": "Passing year", "experience_months": "Total experience (months)", "current_company": "Current company",
    "current_salary": "Current salary", "expected_salary": "Expected salary", "notice_days": "Notice period (days)",
    "preferred_locations": "Preferred locations", "preferred_role": "Preferred role", "linkedin": "LinkedIn", "source_id": "Source",
    "source_detail": "Source detail", "status": "Status",
}
NO_CONTACT = "Enter a mobile number or an email"
_LINKEDIN = re.compile(r"https?://\S+", re.IGNORECASE)


def _candidate_text(label: str, max_length: int):
    """Optional text: trimmed, blank = null, capped, no control characters; the error names the field."""

    def check(value: str | None) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        if len(value) > max_length:
            raise ValueError(f"{label} must be at most {max_length} characters")
        if _BDM_CONTROL.search(value):
            raise ValueError(f"{label} contains invalid characters")
        return value

    return Annotated[str | None, AfterValidator(check)]


def _candidate_mobile(value: str | None) -> str | None:
    if value is not None and normalise_phone(value) is None:
        raise ValueError("Enter a valid mobile number (10 digits, or + and the country code)")
    return value


_EMAIL = TypeAdapter(EmailStr)


def _candidate_email(value: str | None) -> str | None:
    """Blank = null; otherwise a valid address, stored lower-cased (Q-07 matches emails case-insensitively)."""
    value = (value or "").strip()
    if not value:
        return None
    if len(value) > 255:
        raise ValueError("Email must be at most 255 characters")
    try:
        return _EMAIL.validate_python(value).lower()
    except ValidationError:
        raise ValueError("Enter a valid email address") from None


def _linkedin(value: str | None) -> str | None:
    """http(s) only, so the profile link can never be a javascript: URL."""
    if value is not None and not _LINKEDIN.fullmatch(value):
        raise ValueError("LinkedIn must be a link starting with https://")
    return value


def _places(value: list[str]) -> list[str]:
    """Up to 10 places, each 1-80 characters; blanks dropped and repeats (any case) removed, first spelling kept."""
    out: list[str] = []
    for raw in value:
        place = raw.strip()
        if not place or place.lower() in {p.lower() for p in out}:
            continue
        if len(place) > 80 or _BDM_CONTROL.search(place):
            raise ValueError("Each preferred location must be at most 80 characters")
        out.append(place)
    if len(out) > 10:
        raise ValueError("Enter at most 10 preferred locations")
    return out


def _whole(label: str, low: int, high: int):
    """A whole number in range; the error is one plain sentence (browser QA-02), not pydantic's wording."""

    def check(value: int | None) -> int | None:
        if value is not None and not low <= value <= high:
            raise ValueError(f"{label} must be between {low} and {high}")
        return value

    return Annotated[StrictInt | None, AfterValidator(check)]


def _salary(label: str):
    """A yearly amount: finite, 0 to 9,999,999,999.99, at most 2 decimal places (numeric(12,2))."""

    def check(value: Decimal | None) -> Decimal | None:
        if value is not None and (not value.is_finite() or value < 0 or value > Decimal("9999999999.99") or value.as_tuple().exponent < -2):
            raise ValueError(f"{label} must be a positive amount (at most 2 decimal places)")
        return value

    return Annotated[Decimal | None, AfterValidator(check)]


CandidateName = _tel_name(160)
CandidateMobile = Annotated[_candidate_text("Mobile", 40), AfterValidator(_candidate_mobile)]
CandidateEmail = Annotated[str | None, AfterValidator(_candidate_email)]
CandidateLinkedin = Annotated[_candidate_text("LinkedIn", 300), AfterValidator(_linkedin)]


class _CandidateFields(BaseModel):
    """The optional §8 fields, shared by create and edit; null or blank clears one."""

    model_config = ConfigDict(extra="forbid")
    mobile: CandidateMobile = None
    email: CandidateEmail = None
    location: _candidate_text("Location", 120) = None
    qualification: _candidate_text("Qualification", 120) = None
    college: _candidate_text("College", 200) = None
    passing_year: _whole("Passing year", 1950, 2100) = None
    experience_months: _whole("Total experience (months)", 0, 600) = None
    current_company: _candidate_text("Current company", 200) = None
    current_salary: _salary("Current salary") = None
    expected_salary: _salary("Expected salary") = None
    notice_days: _whole("Notice period (days)", 0, 365) = None
    preferred_locations: Annotated[list[str], AfterValidator(_places)] = Field(default_factory=list)
    preferred_role: _candidate_text("Preferred role", 120) = None
    linkedin: CandidateLinkedin = None
    source_detail: _candidate_text("Source detail", 200) = None


class CandidateCreate(_CandidateFields):
    name: CandidateName
    source_id: UUID
    status: CandidateStatus = "available"

    @model_validator(mode="after")
    def _contact(self):
        if self.mobile is None and self.email is None:
            raise ValueError(NO_CONTACT)
        return self


class CandidateUpdate(_CandidateFields):
    """PATCH: omitted = unchanged (model_dump(exclude_unset=True)); name, source and status cannot be null. The service checks that the
    merged row still has a mobile or an email."""

    name: CandidateName = None
    source_id: UUID = None
    status: CandidateStatus = None
    preferred_locations: Annotated[list[str], AfterValidator(_places)] = None


class CandidateResumeOut(BaseModel):
    version: int
    file_name: str | None
    content_type: str
    size_bytes: int
    uploaded_by: BdmPersonRef | None
    created_at: datetime


class CandidateItem(BaseModel):
    id: UUID
    candidate_code: str
    name: str
    location: str | None
    experience_months: int | None
    preferred_role: str | None
    source: RecLeadSourceRef
    source_detail: str | None
    status: CandidateStatus
    archived: bool
    created_at: datetime


class CandidatePage(BaseModel):
    items: list[CandidateItem]
    total: int
    limit: int
    offset: int


class CandidateDetail(CandidateItem):
    mobile: str | None
    email: str | None
    qualification: str | None
    college: str | None
    passing_year: int | None
    current_company: str | None
    current_salary: Decimal | None
    expected_salary: Decimal | None
    notice_days: int | None
    preferred_locations: list[str]
    linkedin: str | None
    archived_at: datetime | None
    created_by: BdmPersonRef | None
    updated_by: BdmPersonRef | None
    updated_at: datetime
    resumes: list[CandidateResumeOut]
    can_edit: bool
    whatsapp_to: str | None = None  # rec-026 MS6: the wa.me number (E.164 digits), None when the mobile is unusable


# --- rec-007 (DEC-SCOPE-129): the Job Requirement ----------------------------------------------------------------------------------
REC_REQUIREMENT_LABELS = {
    "title": "Job title", "location": "Job location", "description": "Job description", "department": "Department",
    "qualification": "Qualification", "joining_requirement": "Joining requirement", "note": "Note",
    # rec-008's JD (the same text rules)
    "role": "Job role", "experience": "Experience", "skills": "Skills", "salary": "Salary", "responsibilities": "Responsibilities",
    "requirements": "Requirements",
}
REC_REQUIREMENT_MULTILINE = frozenset({"description", "note", "skills", "responsibilities", "requirements"})
REC_REQUIREMENT_FIELDS = (  # the `jobs` columns a create or edit may write; code, status, assignee and creator are server-owned
    "title", "location", "description", "department", "job_category_id", "vacancies", "qualification", "experience_min_months",
    "experience_max_months", "salary_min", "salary_max", "work_mode", "shift", "employment_type", "joining_requirement", "closes_on",
    "requirement_date", "priority",
)


def _rec_requirement_text(value: str | None, info: ValidationInfo) -> str | None:
    """bdm-002's rule: no control characters (a line break only in a multi-line field); blank -> None."""
    label = REC_REQUIREMENT_LABELS.get(info.field_name, "Skill")
    control = _BDM_CONTROL_MULTILINE if info.field_name in REC_REQUIREMENT_MULTILINE else _BDM_CONTROL
    if value is not None and control.search(value):
        raise ValueError(f"{label} contains invalid characters")
    return value or None


def _rec_requirement_text_type(max_length: int, *, multiline: bool = False):
    text = Annotated[Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)] | None, AfterValidator(_rec_requirement_text)]
    return Annotated[text, BeforeValidator(_bdm_newlines)] if multiline else text


def _rec_required_text(value: str | None, info: ValidationInfo) -> str:
    if value is None:
        raise ValueError(f"{REC_REQUIREMENT_LABELS[info.field_name]} is required")
    return value


RecRequirementTitle = Annotated[_rec_requirement_text_type(180), AfterValidator(_rec_required_text)]
RecRequirementLocation = Annotated[_rec_requirement_text_type(120), AfterValidator(_rec_required_text)]
RecSkillName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
RecMonths = Annotated[int | None, Field(ge=0, le=600)]
RecMoney = Annotated[Decimal | None, Field(ge=0, max_digits=12, decimal_places=2)]


class RecRequirementUpdate(BaseModel):
    """PATCH: omitted = unchanged, null = clear (title and location cannot be cleared). Sending `required_skills` / `preferred_skills`
    replaces that list; each name resolves through the Skills Master (J7). Min > max is a 422 here when both are sent, and in the
    service against the stored values."""

    model_config = ConfigDict(extra="forbid")
    title: RecRequirementTitle = None
    location: RecRequirementLocation = None
    description: _rec_requirement_text_type(10000, multiline=True) = None
    department: _rec_requirement_text_type(120) = None
    job_category_id: UUID | None = None
    vacancies: Annotated[int | None, Field(ge=1, le=10000)] = None
    qualification: _rec_requirement_text_type(300) = None
    experience_min_months: RecMonths = None
    experience_max_months: RecMonths = None
    salary_min: RecMoney = None
    salary_max: RecMoney = None
    work_mode: Literal[JOB_WORK_MODES] | None = None
    shift: Literal[JOB_SHIFTS] | None = None
    employment_type: Literal[JOB_EMPLOYMENT_TYPES] | None = None
    joining_requirement: _rec_requirement_text_type(300) = None
    closes_on: date | None = None
    requirement_date: date | None = None
    priority: Literal[JOB_PRIORITIES] | None = None
    required_skills: list[RecSkillName] | None = Field(default=None, max_length=30)
    preferred_skills: list[RecSkillName] | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def _ranges(self):
        for low, high, label in (("experience_min_months", "experience_max_months", "experience"), ("salary_min", "salary_max", "salary")):
            a, b = getattr(self, low), getattr(self, high)
            if a is not None and b is not None and a > b:
                raise ValueError(f"Minimum {label} cannot be more than the maximum")
        return self


class RecRequirementCreate(RecRequirementUpdate):
    company_id: UUID
    title: RecRequirementTitle
    location: RecRequirementLocation
    assigned_recruiter_user_id: UUID | None = None  # managers and super_admin only (services/recruiter_requirements)


class RecRequirementStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[JOB_STATUSES]
    note: _rec_requirement_text_type(500, multiline=True) = None


class RecRequirementAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recruiter_user_id: UUID


# --- rec-008 (DEC-SCOPE-132 JD3): a JD version's fields; the company, number and version are server-owned ---------------------------
REC_JD_FIELDS = (
    "role", "experience", "qualification", "skills", "salary", "location", "description", "responsibilities", "requirements", "openings",
    "contact_id", "closing_date",
)


class RecJdCreate(BaseModel):
    """POST /recruiter/requirements/{id}/jd: the whole version (a new current one); omitted = empty."""

    model_config = ConfigDict(extra="forbid")
    role: Annotated[_rec_requirement_text_type(180), AfterValidator(_rec_required_text)]
    experience: _rec_requirement_text_type(120) = None
    qualification: _rec_requirement_text_type(300) = None
    skills: _rec_requirement_text_type(1000, multiline=True) = None
    salary: _rec_requirement_text_type(120) = None
    location: _rec_requirement_text_type(120) = None
    description: _rec_requirement_text_type(10000, multiline=True) = None
    responsibilities: _rec_requirement_text_type(5000, multiline=True) = None
    requirements: _rec_requirement_text_type(5000, multiline=True) = None
    openings: Annotated[int | None, Field(ge=1, le=10000)] = None
    contact_id: UUID | None = None
    closing_date: date | None = None

# --- rec-024 (DEC-SCOPE-131, spec §3): recruiter follow-ups ----------------------------------------------------------------------
REC_FOLLOW_UP_LABELS = {"notes": "Notes", "outcome": "Outcome"}
RecFollowUpReason = Literal[RECRUITER_FOLLOW_UP_REASONS]
RecFollowUpNotes = Annotated[Annotated[str, _trimmed(2000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, REC_FOLLOW_UP_LABELS))]
RecFollowUpOutcome = Annotated[Annotated[str, _trimmed(500)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, REC_FOLLOW_UP_LABELS))]


class RecFollowUpCreate(BaseModel):
    """FU5/FU6/FU10: the due instant (with its offset; the web sends IST), the §18 reason, optional links and notes. Creator, status and
    timestamps are server-owned (unknown fields here)."""

    model_config = ConfigDict(extra="forbid")
    due_at: AwareDatetime
    reason: RecFollowUpReason
    contact_id: UUID | None = None
    job_id: UUID | None = None
    application_id: UUID | None = None
    notes: RecFollowUpNotes = None


class RecFollowUpUpdate(BaseModel):
    """Reschedule (`due_at`) or edit an open follow-up: only the keys sent are considered; null clears a link or the notes, never the due
    time or the reason."""

    model_config = ConfigDict(extra="forbid")
    due_at: AwareDatetime | None = None
    reason: RecFollowUpReason | None = None
    contact_id: UUID | None = None
    job_id: UUID | None = None
    application_id: UUID | None = None
    notes: RecFollowUpNotes = None

    @model_validator(mode="after")
    def _required_stay_set(self):
        for key, label in (("due_at", "Due time"), ("reason", "Reason")):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{label} can't be removed")
        return self


class RecFollowUpComplete(BaseModel):
    """FU7: what came of it (optional)."""

    model_config = ConfigDict(extra="forbid")
    outcome: RecFollowUpOutcome = None


# --- rec-025 (DEC-SCOPE-133, spec §3): recruiter calls -----------------------------------------------------------------------------
RecCallNotes = Annotated[Annotated[str, _trimmed(2000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, {"notes": "Notes"}))]
RecCallDuration = Annotated[int, Field(ge=0, le=RECRUITER_CALL_MAX_SECONDS)]


class RecCallFollowUp(BaseModel):
    """CA6: rec-024's create body without the links (the call's contact is the link)."""

    model_config = ConfigDict(extra="forbid")
    due_at: AwareDatetime
    reason: RecFollowUpReason
    notes: RecFollowUpNotes = None


class RecCallCreate(BaseModel):
    """CA2: exactly one party. CA5: `occurred_at` defaults to now. CA6: `next_follow_up` only on a contact call (checked in the service,
    so the 422 names the field). Caller and timestamps are server-owned (unknown fields here)."""

    model_config = ConfigDict(extra="forbid")
    contact_id: UUID | None = None
    candidate_id: UUID | None = None
    occurred_at: AwareDatetime | None = None
    duration_seconds: RecCallDuration | None = None
    direction: Literal[RECRUITER_CALL_DIRECTIONS] = "outgoing"
    outcome: Literal[RECRUITER_CALL_OUTCOMES]
    notes: RecCallNotes = None
    next_follow_up: RecCallFollowUp | None = None


class RecCallUpdate(BaseModel):
    """CA4: same-day details only -- the outcome and the party are locked (unknown fields here). Time and direction can't be cleared; a
    null duration or notes clears them."""

    model_config = ConfigDict(extra="forbid")
    occurred_at: AwareDatetime | None = None
    duration_seconds: RecCallDuration | None = None
    direction: Literal[RECRUITER_CALL_DIRECTIONS] | None = None
    notes: RecCallNotes = None

    @model_validator(mode="after")
    def _required_stay_set(self):
        for key, label in (("occurred_at", "Call time"), ("direction", "Direction")):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{label} can't be removed")
        return self

# --- rec-028 (DEC-SCOPE-134, spec §3): company meetings ----------------------------------------------------------------------------
REC_MEETING_LABELS = {"outcome": "Outcome", "next_action": "Next action", "purpose": "Purpose"}
RecMeetingType = Literal[RECRUITER_MEETING_TYPES]
RecMeetingMode = Literal[APPOINTMENT_MODES]
RecMeetingPurpose = Annotated[Annotated[str, _trimmed(1000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, REC_MEETING_LABELS))]
RecMeetingOutcomeText = Annotated[str, _trimmed(2000), AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, True, REC_MEETING_LABELS))]
RecMeetingNextAction = Annotated[Annotated[str, _trimmed(500)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, REC_MEETING_LABELS))]
RecMeetingPeople = Annotated[list[UUID], Field(max_length=20)]


class RecMeetingCreate(BaseModel):
    """MT1-MT5: the §20 fields. Code, status, creator and timestamps are server-owned (unknown fields here). The primary contact is always
    stored as a participant; contacts and recruiters are checked in the service (MT5)."""

    model_config = ConfigDict(extra="forbid")
    meeting_type: RecMeetingType
    starts_at: BdmApptStart
    mode: RecMeetingMode
    location: _bdm_appt_optional(200) = None
    meeting_url: LeadApptLink = None
    purpose: RecMeetingPurpose = None
    contact_id: UUID | None = None
    participant_contact_ids: RecMeetingPeople = []
    participant_user_ids: RecMeetingPeople = []


class RecMeetingUpdate(BaseModel):
    """Edit a scheduled meeting: only the keys sent are considered. A changed `starts_at` is a reschedule (MT6). Null clears an optional
    field, never the type, start or mode."""

    model_config = ConfigDict(extra="forbid")
    meeting_type: RecMeetingType | None = None
    starts_at: BdmApptStart | None = None
    mode: RecMeetingMode | None = None
    location: _bdm_appt_optional(200) = None
    meeting_url: LeadApptLink = None
    purpose: RecMeetingPurpose = None
    contact_id: UUID | None = None
    participant_contact_ids: RecMeetingPeople | None = None
    participant_user_ids: RecMeetingPeople | None = None
    reschedule_reason: _bdm_appt_optional(500) = None

    @model_validator(mode="after")
    def _required_stay_set(self):
        for key in ("meeting_type", "starts_at", "mode", "participant_contact_ids", "participant_user_ids"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key.replace('_', ' ').capitalize()} can't be removed")
        return self


class RecMeetingOutcome(BaseModel):
    """MT7: the outcome, and optionally a next action that becomes a rec-024 follow-up (due time and reason checked in the service, so
    each missing one is placed on its own field)."""

    model_config = ConfigDict(extra="forbid")
    outcome: RecMeetingOutcomeText
    next_action: RecMeetingNextAction = None
    next_action_due_at: AwareDatetime | None = None
    next_action_reason: RecFollowUpReason | None = None


# --- rec-026 (DEC-SCOPE-135): recruiter message templates, WhatsApp and email --------------------------------------------------------
class RecTemplateCreate(BaseModel):
    """MS3. `kind` is a string checked against the channel's list in the service, so the 422 names the channel (tel-012's shape)."""

    model_config = ConfigDict(extra="forbid")
    channel: TelChannel
    kind: str
    name: TelContentName
    subject: TelSubject = None
    body: TelBody


class RecTemplateUpdate(BaseModel):
    """Omitted = unchanged. `channel` exists only so a change is refused with a sentence."""

    model_config = ConfigDict(extra="forbid")
    channel: TelChannel = None
    kind: str = None
    name: TelContentName = None
    subject: TelSubject = None
    body: TelBody = None
    active: StrictBool = None


class RecMessageParty(BaseModel):
    """MS4: exactly one recipient -- a company contact or a candidate. The recipient's address is never a request field (MS7)."""

    model_config = ConfigDict(extra="forbid")
    contact_id: UUID | None = None
    candidate_id: UUID | None = None
    template_id: UUID | None = None

    @model_validator(mode="after")
    def _one_party(self):
        if (self.contact_id is None) == (self.candidate_id is None):
            raise ValueError("Choose a contact or a candidate")
        return self


class RecWhatsAppCreate(RecMessageParty):
    channel: Literal["whatsapp"]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class RecEmailCreate(RecMessageParty):
    channel: Literal["email"]
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), BeforeValidator(_one_line)]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


RecMessageCreate = Annotated[RecWhatsAppCreate | RecEmailCreate, Field(discriminator="channel")]

# --- rec-017 (DEC-SCOPE-136): a candidate on a requirement and its status (services/applications) -----------------------------------
class RecApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: UUID
    status: Literal["sourced", "screened", "shortlisted"] = "sourced"  # applications.INITIAL
    note: _rec_requirement_text_type(500, multiline=True) = None


class RecApplicationStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[APPLICATION_STATUSES]
    note: _rec_requirement_text_type(500, multiline=True) = None


# --- rec-011 (DEC-SCOPE-137, spec §1/§4): a candidate's skills -------------------------------------------------------------------
CANDIDATE_SKILL_LABELS = {"skill": "Skill", "level": "Level", "experience_months": "Experience (months)", "last_used_year": "Last used", "source": "Source", "status": "Status"}


def _last_used(value: int | None) -> int | None:
    """SK2: a year from 1950 to this year -- a skill cannot be last used in the future."""
    this_year = datetime.now(UTC).year
    if value is not None and not 1950 <= value <= this_year:
        raise ValueError(f"Last used must be a year between 1950 and {this_year}")
    return value


class CandidateSkillUpdate(BaseModel):
    """PATCH: omitted = unchanged; a null experience or last-used year clears it, level and source cannot be cleared (null is "required").
    The skill and the status are unknown fields here: a different skill is a remove and an add, and the status has its own route (SK4)."""

    model_config = ConfigDict(extra="forbid")
    level: Literal[CANDIDATE_SKILL_LEVELS] = None
    experience_months: _whole("Experience (months)", 0, 600) = None
    last_used_year: Annotated[StrictInt | None, AfterValidator(_last_used)] = None
    source: Literal[CANDIDATE_SKILL_SOURCES] = None


class CandidateSkillCreate(CandidateSkillUpdate):
    """SK5: `skill` is text resolved through the Skills Master (a name or an alias). A new row is always `claimed` (SK4)."""

    skill: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    level: Literal[CANDIDATE_SKILL_LEVELS]
    source: Literal[CANDIDATE_SKILL_SOURCES] = "resume"


class CandidateSkillStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[CANDIDATE_SKILL_STATUSES]

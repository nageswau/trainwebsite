"""ENH-017 (`DEC-SCOPE-036`; spec docs/superpowers/specs/2026-09-29-enh-017-global-education-pipeline-design.md): the
`School CRM.md` §17 Global Education funnel for a school's bridged (SCH-010) students, high-level stage only (§19). Read-only:
it selects named columns, never an `OverseasApplication`/`VisaCase` row, so application detail cannot reach the response."""

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.school_analytics import grade_key, students_in
from app.api.school_feedback import _require_school_reader
from app.api.schools import OFFER_ONWARD_STATUSES, _own_school_id, _stage_at_or_after
from app.api.workflows import VISA_CASE_STAGES
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import OverseasApplication, SchoolStudent, User, VisaCase
from app.schemas import GlobalEducationPipelineOut, PipelineStage, PipelineStudentPage, PipelineStudentRow, PipelineUntracked

router = APIRouter(prefix="/school", tags=["school-global-education"])
logger = get_logger("app.school.global_education")

# Spec §5.1, in funnel order. A student reaches a stage on any of their bridged applications (D3).
FUNNEL = (
    ("pathway", "Global education pathway"),
    ("profile_evaluation", "Profile evaluation"),
    ("shortlisted", "University shortlisted"),
    ("offer", "Offer received"),
    ("visa", "Visa"),
    ("admitted", "Admitted"),
)

FUNNEL_LABELS = dict(FUNNEL)
# Spec §5.2 (D1): §17/§19 stages with no data source yet -- shown as not tracked, never as a fabricated 0.
NOT_TRACKED = (
    ("applications_started", "Applications started", "Application status does not distinguish started from submitted."),
    ("applications_submitted", "Applications submitted", "Application status does not distinguish started from submitted."),
    ("deposit", "Deposit", "No deposit stage is recorded."),
    ("scholarship", "Scholarships", "No school-student scholarship link exists yet."),
    ("top_100", "Top 100 universities", "Universities carry no ranking yet."),
    ("alumni", "Alumni", "Alumni tracking is not built yet."),
)
VISA_STAGE_LABELS = {"checklist": "Checklist", "documentation": "Documentation", "interview_prep": "Interview preparation", "tracking": "Tracking", "decision": "Decision"}
VISA_UNKNOWN_LABEL = "In progress"
ROSTER_COLUMNS = (SchoolStudent.id, SchoolStudent.full_name, SchoolStudent.student_code, SchoolStudent.grade_level, SchoolStudent.grade_or_class)


def application_stages(status: str, has_offer_letter: bool) -> set[str]:
    """The funnel stages one application has reached (spec §5.1). Visa is added from `VisaCase` rows (D10)."""
    reached = {"pathway"}
    if _stage_at_or_after(status, "eligibility_evaluation"):
        reached.add("profile_evaluation")
    if _stage_at_or_after(status, "university_selection"):
        reached.add("shortlisted")
    if status in OFFER_ONWARD_STATUSES or has_offer_letter:
        reached.add("offer")
    if status == "enrolled":
        reached.add("admitted")
    return reached


def furthest_stage(reached: set[str]) -> str:
    return next(key for key, _ in reversed(FUNNEL) if key in reached)


def visa_stage_label(statuses: list[str]) -> str | None:
    """The most advanced modelled visa stage across a student's cases; "In progress" when none is a modelled stage."""
    if not statuses:
        return None
    known = [s for s in statuses if s in VISA_STAGE_LABELS]
    return VISA_STAGE_LABELS[max(known, key=VISA_CASE_STAGES.index)] if known else VISA_UNKNOWN_LABEL


@router.get("/global-education/pipeline", response_model=GlobalEducationPipelineOut)
async def global_education_pipeline(user: User = Depends(_require_school_reader), db: AsyncSession = Depends(get_db)):
    school_id = _own_school_id(user)
    roster = (await db.execute(select(*ROSTER_COLUMNS).where(SchoolStudent.school_id == school_id).order_by(SchoolStudent.full_name, SchoolStudent.id))).all()
    scope = students_in([school_id])
    reached: dict = defaultdict(set)
    application_count: dict = defaultdict(int)
    # The offer letter is reduced to a boolean in SQL; "" is not an offer (matches the dashboard's truthiness test).
    has_offer_letter = and_(OverseasApplication.offer_letter_url.is_not(None), OverseasApplication.offer_letter_url != "")
    applications = select(OverseasApplication.school_student_id, OverseasApplication.status, has_offer_letter).where(OverseasApplication.school_student_id.in_(scope))
    for sid, status, offer in (await db.execute(applications)).tuples():
        reached[sid] |= application_stages(status, bool(offer))
        application_count[sid] += 1
    visa_statuses: dict = defaultdict(list)
    visas = select(OverseasApplication.school_student_id, VisaCase.status).join(VisaCase, VisaCase.application_id == OverseasApplication.id).where(OverseasApplication.school_student_id.in_(scope))
    for sid, status in (await db.execute(visas)).tuples():
        reached[sid].add("visa")
        visa_statuses[sid].append(status)

    bridged = [s for s in roster if s.id in reached]
    rows = [
        PipelineStudentRow(
            school_student_id=s.id, full_name=s.full_name, student_code=s.student_code, grade=grade_key(s.grade_level, s.grade_or_class),
            furthest_stage=(stage := furthest_stage(reached[s.id])), furthest_stage_label=FUNNEL_LABELS[stage],
            visa_stage_label=visa_stage_label(visa_statuses[s.id]), application_count=application_count[s.id],
        )
        for s in bridged
    ]
    return GlobalEducationPipelineOut(
        grade=None, students_in_scope=len(roster), bridged_students=len(bridged),
        funnel=[PipelineStage(key=key, label=label, count=sum(1 for s in bridged if key in reached[s.id])) for key, label in FUNNEL],
        not_tracked=[PipelineUntracked(key=key, label=label, note=note) for key, label, note in NOT_TRACKED],
        students=PipelineStudentPage(items=rows, total=len(bridged), limit=25, offset=0),
    )

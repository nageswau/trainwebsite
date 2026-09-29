"""ENH-017 (`DEC-SCOPE-036`; spec docs/superpowers/specs/2026-09-29-enh-017-global-education-pipeline-design.md): the
`School CRM.md` §17 Global Education funnel for a school's bridged (SCH-010) students, high-level stage only (§19). Read-only:
it selects named columns, never an `OverseasApplication`/`VisaCase` row, so application detail cannot reach the response."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.school_feedback import _require_school_reader
from app.api.schools import _own_school_id
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import User
from app.schemas import GlobalEducationPipelineOut, PipelineStage, PipelineStudentPage

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


@router.get("/global-education/pipeline", response_model=GlobalEducationPipelineOut)
async def global_education_pipeline(user: User = Depends(_require_school_reader), db: AsyncSession = Depends(get_db)):
    _own_school_id(user)
    return GlobalEducationPipelineOut(
        grade=None, students_in_scope=0, bridged_students=0,
        funnel=[PipelineStage(key=key, label=label, count=0) for key, label in FUNNEL],
        not_tracked=[], students=PipelineStudentPage(items=[], total=0, limit=25, offset=0),
    )

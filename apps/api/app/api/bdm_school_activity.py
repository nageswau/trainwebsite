"""bdm-020 (DEC-SCOPE-086, spec §2): a linked School's student development counts on the BDM side.

The organization resolves through `services.bdm_organizations.load_scoped` (out of scope = 404, other roles 403). The counts are the
School module's own (`school_analytics.DEVELOPMENT_ROWS` over `student_indicators`, imported unchanged), so they equal the School's
Student development section (AC1). Aggregates only: no student id, name or row ever leaves here (AC3). Read-only."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.school_analytics import DEVELOPMENT_ROWS, student_indicators, students_in
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import School, SchoolStudent, User
from app.schemas import BdmSchoolActivityOut
from app.services import bdm_organizations as org_svc

router = APIRouter(prefix="/bdm/organizations", tags=["bdm-school-activity"])
logger = get_logger("app.bdm.school_activity")

NOT_SCHOOL = "School activity is only for School organizations"
UNTRACKED = [("student_profile_completion", "Student Profile Completion")]  # D24 / A2: no School-module figure exists


@router.get("/{org_id}/school-activity", response_model=BdmSchoolActivityOut)
async def school_activity(org_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await org_svc.load_scoped(db, user, org_id)
    if org.bdm_type != "school":
        raise HTTPException(404, NOT_SCHOOL)
    if org.school_id is None:
        return {"linked": False, "school": None, "total_students": None, "metrics": []}
    school = await db.get_one(School, org.school_id)
    total = await db.scalar(select(func.count()).select_from(SchoolStudent).where(SchoolStudent.school_id == school.id)) or 0
    indicators = await student_indicators(db, students_in([school.id]))
    completed = {key: len(rule(indicators)) for key, _label, rule in DEVELOPMENT_ROWS}
    metrics = [{"key": key, "label": label, "tracked": True, "completed": completed[key], "pending": total - completed[key]} for key, label, _rule in DEVELOPMENT_ROWS]  # D2
    metrics += [{"key": key, "label": label, "tracked": False, "completed": None, "pending": None} for key, label in UNTRACKED]
    logger.info("bdm_school_activity_viewed", extra={"extra_fields": {"actor_id": str(user.id), "org_id": str(org.id), "school_id": str(school.id)}})
    return {"linked": True, "school": {"name": school.name, "school_code": school.school_code}, "total_students": total, "metrics": metrics}

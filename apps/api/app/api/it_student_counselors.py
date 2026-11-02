"""itc-003 (DEC-SCOPE-337) -- the IT student -> counselor link: the IT counselor's own students (list and one; anything else is 404) and
the IT Admin's reassignment (csc-005 / ccrm-033 rules). API_CONTRACT.md §12II; RBAC_MATRIX.md §2.239."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import User
from app.schemas import OverseasApplicationCounselorAssign
from app.services import it_student_counselors as links

logger = logging.getLogger("app.it_student_counselors")
router = APIRouter(prefix="/counselor/it/students", tags=["it-student-counselors"])
admin_router = APIRouter(prefix="/admin/it/students", tags=["it-student-counselors"])


@router.get("")
async def my_students(q: str | None = Query(None, max_length=100), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                      user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    links.require_it_counselor(user)
    return await links.page(db, user, limit, offset, like_pattern(q))


@router.get("/{student_id}")
async def my_student(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    links.require_it_counselor(user)
    return await links.one(db, user, student_id)


@admin_router.put("/{student_id}/counselor")
async def assign_counselor(student_id: UUID, payload: OverseasApplicationCounselorAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-023's assign body (swap only; a reason when a counselor is replaced); the same counselor is `changed: false`."""
    result = await links.assign(db, user, student_id, payload.counselor_id, payload.reason)
    if result["changed"]:
        await db.commit()
        logger.info("it_student_counselor_assigned", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student_id), "counselor_id": str(result["counselor_id"])}})
    return result

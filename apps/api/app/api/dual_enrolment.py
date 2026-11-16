"""ENH-033 (DEC-SCOPE-441) -- a target-division counselor or telecaller adds that division to an existing student (IT -> Overseas or
Overseas -> IT). API_CONTRACT.md §12MH; RBAC_MATRIX.md §2.331."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import dual_enrolment

logger = logging.getLogger("app.dual_enrolment")
router = APIRouter(prefix="/workflows", tags=["dual-enrolment"])

Division = Literal["it", "overseas"]


class DualEnrolmentIn(BaseModel):
    student_id: UUID
    counselor_id: UUID
    student_requested: bool = False


@router.get("/{division}/dual-enrolment/lookup")
async def lookup(division: Division, ref: str = Query(..., min_length=1, max_length=320), user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):  # fmt: skip
    return await dual_enrolment.lookup(db, user, division, ref)


@router.post("/{division}/dual-enrolment", status_code=201)
async def enrol(division: Division, payload: DualEnrolmentIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await dual_enrolment.enrol(db, user, division, payload.student_id, payload.counselor_id, payload.student_requested)
    await db.commit()
    logger.info("student_dual_enrolled", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(payload.student_id), "division": division}})
    return result

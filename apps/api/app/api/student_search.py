"""nehn-041 (DEC-SCOPE-291; API §12GP): GET /search/students?q= -- the unified student search, each kind in the caller's existing
scope. A role with no student list 403; a search under 3 or over 100 characters 422; over 30 a minute 429."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import User
from app.services import counselor_search, student_search

router = APIRouter(prefix="/search", tags=["student-search"])


@router.get("/students")
async def search_students(
    q: str = Query(..., max_length=200),
    kind: Literal["it_student", "overseas_student", "agency_student", "school_student"] | None = Query(None, alias="type"),
    division: Literal["it", "overseas", "school"] | None = None,
    program: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    kinds = student_search.caller_kinds(user)
    text = counselor_search.term(q)
    # S5: the filters narrow the caller's kinds; one outside them leaves no group (never a wider scope)
    wanted = {kind} if kind else set(student_search.KINDS)
    if division:
        wanted &= student_search.DIVISION_KINDS[division]
    if program:
        wanted &= {"it_student"}
    kinds = tuple(k for k in kinds if k in wanted)
    return await student_search.search(db, user, text, like_pattern(text), kinds=kinds, program=program)

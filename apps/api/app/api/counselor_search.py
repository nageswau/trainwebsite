"""ccrm-012 (DEC-SCOPE-246; API §12EY): GET /counselor/search?q= -- the overseas counselor's quick search over their own leads, students
and applications. Anyone else 403; a search under 3 or over 100 characters 422; over 30 a minute 429."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import User
from app.services import counselor_search

router = APIRouter(prefix="/counselor", tags=["counselor-search"])


@router.get("/search")
async def search(q: str = Query(..., max_length=200), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "counselor" or user.division != "overseas":  # QS1: an IT counselor works leads only (tel-017)
        raise HTTPException(403, counselor_search.OVERSEAS_COUNSELOR_ONLY)
    text = counselor_search.term(q)
    return await counselor_search.search(db, user, text, like_pattern(text))

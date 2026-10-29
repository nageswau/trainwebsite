"""nehn-033 (DEC-SCOPE-332) -- the overseas student's own Progress page: GET /overseas/me/progress. Read-only; the student's own rows
only (nothing in the request names a record); any other role is 403. API_CONTRACT.md §12ID; RBAC_MATRIX.md §2.235."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import overseas_progress
from app.services.student_profiles import require_student

me_router = APIRouter(prefix="/overseas/me", tags=["overseas-progress"])


@me_router.get("/progress")
async def my_progress(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await overseas_progress.build(db, require_student(user).id)

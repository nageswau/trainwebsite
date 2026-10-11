"""rec-032 (DEC-SCOPE-177, API §12CR): the recruiter dashboard -- the fourteen §1 tiles, every figure computed by
`services/recruiter_metrics.py`. Read-only and never cached; one request for the page that shows it.

Scope (DB1-DB3): a recruiter reads their own figures (another recruiter id → 403); a placement manager their team + the unassigned
queue, or one direct report; super_admin everything, or any one recruiter (an id out of scope → 404). Every other role → 403."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import recruiter_metrics as metrics
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/recruiter", tags=["recruiter-dashboard"])


@router.get("/dashboard")
async def dashboard(response: Response, recruiter: UUID | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§1: D1-D14 (Appendix B) for the caller's scope, optionally narrowed to one recruiter."""
    response.headers.update(NO_STORE)
    return await metrics.dashboard(db, user, recruiter, await db_now(db))

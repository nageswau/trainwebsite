"""rec-027 (spec §1, TL1-TL3): a company's and a candidate's timeline, newest first. Read only -- no audit, no log (TL9)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import RecTimelinePage
from app.services import candidates
from app.services import recruiter_companies as companies
from app.services import recruiter_timeline as svc

router = APIRouter(prefix="/recruiter", tags=["recruiter-timeline"])


@router.get("/companies/{company_id}/timeline", response_model=RecTimelinePage)
async def company_timeline(company_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Whoever has the company in scope (the recruiter, their manager, super_admin, the assigned BDM); out of scope = 404."""
    company = await companies.load_scoped(db, user, company_id)
    return await svc.company_page(db, company.id, limit, offset)


@router.get("/candidates/{candidate_id}/timeline", response_model=RecTimelinePage)
async def candidate_timeline(candidate_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every candidate reader, every pool candidate (R11) -- the rule of the candidate's calls and applications."""
    candidates.require_reader(user)
    candidate = await candidates.load(db, candidate_id)
    return await svc.candidate_page(db, candidate.id, limit, offset)

"""pob-017 (DEC-SCOPE-429): a requirement's sourcing plan and source funnel. Mounted on the pob-016 checklist router (S12), so it shares its
`/recruiter` prefix. Every route resolves the requirement through `load_scoped` (out of scope = 404); a save is one transaction: scope, row
lock, role (403), state (409), change, audit, one commit here."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Job, User
from app.schemas import RecSourcingPlanIn
from app.services import candidates
from app.services import recruiter_requirements as requirements
from app.services import requirement_sourcing as svc

router = APIRouter()


async def _out(db: AsyncSession, user: User, job: Job) -> dict:
    """The plan, the funnel and what this caller may do; the web renders from these flags."""
    return {**await svc.view(db, user, job), "can_edit": requirements.permissions(user, job)["can_edit"], "can_link_searches": user.role in candidates.READERS}


@router.get("/requirements/{requirement_id}/sourcing")
async def get_sourcing(requirement_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id, officers=True)
    return await _out(db, user, job)


@router.put("/requirements/{requirement_id}/sourcing")
async def put_sourcing(requirement_id: UUID, payload: RecSourcingPlanIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1: the whole plan; the same plan again changes and audits nothing."""
    job = await requirements.load_scoped(db, user, requirement_id, lock=True, officers=True)
    requirements.require(user, job, "can_edit", "sourcing_plan")
    changed = await svc.save(db, user, job, payload)
    await db.commit()
    if changed:
        requirements.log("recruiter_requirement_sourcing_plan_saved", user, job.id)
    return await _out(db, user, job)

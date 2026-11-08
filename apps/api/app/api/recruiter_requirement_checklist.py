"""pob-016 (DEC-SCOPE-419): the requirement validation checklist. Every requirement route resolves through `load_scoped` (out of scope = 404) and every write is one
transaction: scope, row lock, change, audit, one commit here."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Job, User
from app.schemas import RecChecklistCompanyRule, RecChecklistGlobalRule, RecChecklistItemSet, RecRequirementReject
from app.services import recruiter_companies as companies
from app.services import recruiter_requirements as requirements
from app.services import requirement_checklist as svc

router = APIRouter(prefix="/recruiter", tags=["recruiter-requirements"])


async def _out(db: AsyncSession, user: User, job: Job) -> dict:
    """The checklist and what this caller may do with it; the web renders from these flags (C12)."""
    body = await svc.view(db, job)
    manages = user.role in svc.MANAGERS
    return {
        **{k: v for k, v in body.items() if k != "overridable"},
        "company_id": job.company_id,
        "can_edit": requirements.permissions(user, job)["can_edit"],
        "can_override": manages and body["overridable"],
        "can_set_company_rule": manages,
        "can_set_global_rule": user.role == "super_admin",
    }


@router.get("/requirements/{requirement_id}/checklist")
async def get_checklist(requirement_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id, officers=True)
    return await _out(db, user, job)


@router.put("/requirements/{requirement_id}/checklist/items/{item_key}")
async def set_checklist_item(requirement_id: UUID, item_key: Literal[svc.KEYS], payload: RecChecklistItemSet, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):  # fmt: skip
    """C2-C5: an answer and its follow-up; the same answer again changes nothing. C13: `jobs.updated_at` stays, so an open Edit form is not told it is stale."""
    job = await requirements.load_scoped(db, user, requirement_id, lock=True, officers=True)
    requirements.require(user, job, "can_edit", "checklist_item")
    changed = await svc.set_item(db, user, job, item_key, payload.status)
    await db.commit()
    if changed:
        requirements.log("recruiter_requirement_checklist_item", user, job.id, item=item_key, status=payload.status)
    return await _out(db, user, job)


@router.post("/requirements/{requirement_id}/checklist/override")
async def override_checklist(requirement_id: UUID, payload: RecRequirementReject, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """C11/AC3: scope (404) -> a Team Lead (403) -> something is being blocked (409). The reason is audited, never logged."""
    job = await requirements.load_scoped(db, user, requirement_id, lock=True, officers=True)
    if user.role not in svc.MANAGERS:
        raise HTTPException(403, svc.NO_OVERRIDE)
    await svc.override(db, user, job, payload.reason)
    await db.commit()
    requirements.log("recruiter_requirement_checklist_overridden", user, job.id)
    return await _out(db, user, job)


@router.put("/companies/{company_id}/checklist-rule")
async def set_company_rule(company_id: UUID, payload: RecChecklistCompanyRule, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """C6/C12: the role first (403), then the manager's company scope (404). Null means "use the global rule"."""
    if user.role not in svc.MANAGERS:
        raise HTTPException(403, svc.NO_COMPANY_RULE)
    company = await companies.load_scoped(db, user, company_id, lock=True)
    svc.set_company_rule(db, user, company, payload.block_sourcing)
    await db.commit()
    return {"block_sourcing": payload.block_sourcing}


@router.put("/requirement-checklist/settings")
async def set_global_rule(payload: RecChecklistGlobalRule, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """C6/C12: super_admin only, as hrc-007's approval settings. Turning it on never stops a requirement already started (C9)."""
    if user.role != "super_admin":
        raise HTTPException(403, svc.NO_GLOBAL_RULE)
    await svc.set_global_rule(db, user, payload.block_sourcing)
    await db.commit()
    return {"block_sourcing": payload.block_sourcing}


# pob-017 (DEC-SCOPE-429 S12): the sourcing plan and funnel share this router, so main.py is unchanged
from app.api.recruiter_requirement_sourcing import router as _sourcing_router  # noqa: E402

router.include_router(_sourcing_router)

"""tel-018 (DEC-SCOPE-101, spec §3.3; API §12V): the counselor handover, the counselor's leads, the return and the student link.

- POST /telecaller/leads/{id}/handover: the lead's telecaller (tel-004 scope; 403 once handed over), their manager or super_admin.
- /counselor/leads/...: the assigned counselor only -- the list, the detail (milestones, permissions), the timeline, the return, the
  link suggestions and the student link / unlink.

Scope always comes from the session; an id outside it is 404, a role that may not act 403, a rule conflict 409, invalid input 422."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import Enquiry, User
from app.schemas import LeadHandoverIn, LeadReturnIn, LeadStudentLinkIn, LeadTimelinePage
from app.services import bdm_leads, lead_handover, lead_pipeline, telecaller_leads
from app.services.lead_timeline import page as timeline_page

telecaller_router = APIRouter(prefix="/telecaller/leads", tags=["lead-handover"])
counselor_router = APIRouter(prefix="/counselor/leads", tags=["lead-handover"])


@telecaller_router.post("/{lead_id}/handover")
async def handover(lead_id: UUID, payload: LeadHandoverIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """HO4, in this order so each refusal is one rule: scope 404, handed over 403, closed / past the link 409, counselor 422, same 409."""
    _, filters = lead_pipeline.scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *filters)
    telecaller_leads.require_writable(user, lead)
    await lead_handover.handover(db, user, lead, payload.counselor_id)
    await db.commit()
    return await telecaller_leads.detail(db, user, lead_id, filters)


@counselor_router.get("")
async def my_leads(limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await lead_handover.page(db, lead_handover.counselor_scope(user), limit, offset)


@counselor_router.get("/{lead_id}")
async def lead_detail(lead_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await lead_handover.detail(db, lead_id, lead_handover.counselor_scope(user))


@counselor_router.get("/{lead_id}/timeline", response_model=LeadTimelinePage)
async def lead_timeline(lead_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    filters = lead_handover.counselor_scope(user)
    if await db.scalar(select(Enquiry.id).where(Enquiry.id == lead_id, *filters)) is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    return await timeline_page(db, lead_id, limit, offset)


@counselor_router.post("/{lead_id}/return")
async def return_lead(lead_id: UUID, payload: LeadReturnIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """T19 / AC2. The answer is the lead as it now is (it has left the counselor's scope, so it is read without it)."""
    lead = await lead_pipeline.locked_lead(db, lead_id, *lead_handover.counselor_scope(user))
    await lead_handover.return_lead(db, user, lead, payload.reason)
    await db.commit()
    return await lead_handover.detail(db, lead_id, [])


@counselor_router.get("/{lead_id}/link-suggestions")
async def link_suggestions(lead_id: UUID, q: str | None = Query(None, min_length=3, max_length=200), user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    lead = await db.scalar(select(Enquiry).where(Enquiry.id == lead_id, *lead_handover.counselor_scope(user)))
    if lead is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    return await lead_handover.suggestions(db, lead, like_pattern(q))


@counselor_router.post("/{lead_id}/student-link")
async def link_student(lead_id: UUID, payload: LeadStudentLinkIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """T20 / AC3-AC4: the counselor confirms a student; the admin route's rules (spec §3.2)."""
    filters = lead_handover.counselor_scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *filters)
    await lead_handover.link_student(db, user, lead, User.id == payload.student_id)
    await lead_handover.commit_link(db, user, lead_id)
    return await lead_handover.detail(db, lead_id, filters)


@counselor_router.delete("/{lead_id}/student-link")
async def unlink_student(lead_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    filters = lead_handover.counselor_scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *filters)
    await lead_handover.unlink_student(db, user, lead, admin=False)
    await db.commit()
    bdm_leads.log("lead_unconverted", user, lead_id)
    return await lead_handover.detail(db, lead_id, filters)


"""tel-018 (DEC-SCOPE-101, spec §3.3; API §12V): the counselor handover, the counselor's leads, the return and the student link.

- POST /telecaller/leads/{id}/handover: the lead's telecaller (tel-004 scope; 403 once handed over), their manager or super_admin.
- /counselor/leads/...: the assigned counselor only -- the list, the detail (milestones, permissions), the timeline, the return, the
  link suggestions and the student link / unlink; ccrm-003 the stage move and the next action (its follow-ups are in
  `api/telecaller_follow_ups.py`); ccrm-008 the one-step conversion to a new overseas student (API §12FE).

Scope always comes from the session; an id outside it is 404, a role that may not act 403, a rule conflict 409, invalid input 422."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.lead_stages import CLOSED
from app.models import Enquiry, User
from app.schemas import (
    CounselorLeadStageMove,
    CounselorStudentCreate,
    LeadHandoverIn,
    LeadNextActionIn,
    LeadNoteIn,
    LeadNoteOut,
    LeadNotePage,
    LeadReturnIn,
    LeadStudentLinkIn,
    LeadTimelinePage,
)
from app.services import bdm_leads, counselor_students, lead_conversion, lead_handover, lead_notes, lead_pipeline, telecaller_leads
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
async def my_leads(
    limit: int = LIMIT,
    offset: int = OFFSET,
    stage: str | None = None,
    priority: str | None = None,
    created_from: str | None = Query(None, alias="from"),
    created_to: str | None = Query(None, alias="to"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ccrm-012 (DEC-SCOPE-246 QS7): optional stage / priority / lead-date filters, inside the counselor's scope."""
    scope = lead_handover.counselor_scope(user)
    return await lead_handover.page(db, [*scope, *lead_handover.list_filters(stage, priority, created_from, created_to)], limit, offset)


@counselor_router.get("/{lead_id}")
async def lead_detail(lead_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await lead_handover.detail(db, lead_id, lead_handover.counselor_scope(user))


async def _counselor_lead(db: AsyncSession, user: User, lead_id: UUID) -> None:
    if await db.scalar(select(Enquiry.id).where(Enquiry.id == lead_id, *lead_handover.counselor_scope(user))) is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)


@counselor_router.get("/{lead_id}/timeline", response_model=LeadTimelinePage)
async def lead_timeline(lead_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _counselor_lead(db, user, lead_id)
    return await timeline_page(db, lead_id, limit, offset)


@counselor_router.get("/{lead_id}/notes", response_model=LeadNotePage)
async def lead_notes_list(lead_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-002 (DEC-SCOPE-242): the notes of a lead handed to this counselor (owner + division), newest first."""
    await _counselor_lead(db, user, lead_id)
    return await lead_notes.page(db, lead_id, limit, offset)


@counselor_router.post("/{lead_id}/notes", response_model=LeadNoteOut, status_code=201)
async def lead_note_add(lead_id: UUID, payload: LeadNoteIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-002: a note on a closed lead is allowed (history); another counselor's lead is 404."""
    await _counselor_lead(db, user, lead_id)
    return await lead_notes.add(db, user, lead_id, payload.body)


@counselor_router.post("/{lead_id}/stage")
async def change_stage(lead_id: UUID, payload: CounselorLeadStageMove, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-003 (DEC-SCOPE-243, CC8 / A1, A2): the counselor's stage move on a lead handed to them. Any next action sent is applied first,
    then tel-004's engine with the counselor's list; an open target with no next action stored is 422 and nothing is kept."""
    lead = await lead_pipeline.locked_lead(db, lead_id, *lead_handover.counselor_scope(user))
    await lead_handover.set_next_action(db, user, lead, payload.next_action, payload.next_action_due)
    await lead_pipeline.person_move(db, lead, user, "counselor", payload.to_stage, payload.reason)
    out = {**lead_pipeline.stage_out(lead), "next_action": lead.next_action, "next_action_due": lead.next_action_due}
    await db.commit()
    return out


@counselor_router.put("/{lead_id}/next-action")
async def set_next_action(lead_id: UUID, payload: LeadNextActionIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-003 A3: both fields; a closed lead needs none (409). The answer is the lead detail."""
    filters = lead_handover.counselor_scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *filters)
    if lead.status in CLOSED:
        raise HTTPException(409, lead_handover.NEXT_ACTION_CLOSED)
    await lead_handover.set_next_action(db, user, lead, payload.next_action, payload.next_action_due)
    await db.commit()
    return await lead_handover.detail(db, lead_id, filters)


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


@counselor_router.post("/{lead_id}/convert", status_code=201)
async def convert_to_student(lead_id: UUID, payload: CounselorStudentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-008 (DEC-SCOPE-252): an overseas counselor only (403), on a lead handed to them (404); the rules are `lead_conversion.convert`.
    The set-password link is mailed after the commit and its token is never returned."""
    counselor_students.require_overseas_counselor(user, lead_conversion.COUNSELOR_ONLY)
    filters = lead_handover.counselor_scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *filters)
    student, issued = await lead_conversion.convert(db, user, lead, payload)
    out = counselor_students.student_out(student, "pending_setup")
    await lead_handover.commit_link(db, user, lead_id)
    delivery = await counselor_students.deliver_link(student, issued, user)
    return {"student": out, "lead": await lead_handover.detail(db, lead_id, filters), **delivery}


@counselor_router.delete("/{lead_id}/student-link")
async def unlink_student(lead_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    filters = lead_handover.counselor_scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *filters)
    await lead_handover.unlink_student(db, user, lead, admin=False)
    await db.commit()
    bdm_leads.log("lead_unconverted", user, lead_id)
    return await lead_handover.detail(db, lead_id, filters)


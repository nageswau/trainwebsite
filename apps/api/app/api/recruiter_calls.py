"""rec-025 (DEC-SCOPE-132, spec §3): recruiter calls -- log a call on a company contact or a candidate (with an optional next follow-up),
a company's and a candidate's call lists, and the same-day edit and delete.

A contact call's scope is its company's (rec-003 `load_scoped` / `can_edit`); a candidate call's is the pool's (rec-009, R11). Every write
is one transaction -- the party lock and rights, the call lock, the rules, the change, audit, one commit here, then the log."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import RecruiterCall, User
from app.schemas import RecCallCreate, RecCallUpdate
from app.services import candidates
from app.services import recruiter_calls as svc
from app.services import recruiter_companies as companies
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/recruiter", tags=["recruiter-calls"])


@router.post("/calls", status_code=201)
async def log_call(payload: RecCallCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry logs a second call; the daily cap bounds it). Returns the call and the id of the follow-up it created."""
    now = await db_now(db)
    call, follow_up_id = await svc.create(db, user, payload, now)
    await db.commit()
    svc.log("recruiter_call_logged", user, call.id, outcome=payload.outcome, kind="contact" if payload.contact_id else "candidate", follow_up=follow_up_id is not None)
    return {"call": await svc.one(db, user, call.id, now), "follow_up_id": follow_up_id}


@router.get("/companies/{company_id}/calls")
async def company_calls(company_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every contact call of the company, newest first -- whoever has the company in scope (a manager and the assigned BDM read)."""
    await companies.load_scoped(db, user, company_id)
    return await svc.page(db, user, RecruiterCall.company_id == company_id, await db_now(db), limit, offset)


@router.get("/candidates/{candidate_id}/calls")
async def candidate_calls(candidate_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    candidates.require_reader(user)
    await candidates.load(db, candidate_id)
    return await svc.page(db, user, RecruiterCall.candidate_id == candidate_id, await db_now(db), limit, offset)


@router.patch("/calls/{call_id}")
async def update_call(call_id: UUID, payload: RecCallUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CA4: same IST day, by the caller; the outcome and the party are locked."""
    now = await db_now(db)
    call = await svc.load_for_write(db, user, call_id, "call_update", now)
    changed = svc.apply_update(db, user, call, payload.model_dump(exclude_unset=True), now)
    await db.commit()
    if changed:
        svc.log("recruiter_call_updated", user, call_id, fields=changed)
    return await svc.one(db, user, call_id, now)


@router.delete("/calls/{call_id}", status_code=204)
async def delete_call(call_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CA4/CA6: a follow-up the call created stays."""
    call = await svc.load_for_write(db, user, call_id, "call_delete", await db_now(db))
    svc.audit(db, user, "delete", call.id, {"outcome": call.outcome})
    await db.delete(call)
    await db.commit()
    svc.log("recruiter_call_deleted", user, call_id)
    return Response(status_code=204)

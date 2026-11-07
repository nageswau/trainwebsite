"""pob-008 (DEC-SCOPE-423 B5/B6/B9): the outreach cadence library (every recruiter-CRM role reads it; the Team Lead and super_admin write)
and a contact's run of a cadence, started and stopped on an outreach message. Each write is one transaction: checks, change, audit, commit."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Company, User
from app.schemas import RecCadenceCreate, RecCadenceStart, RecCadenceUpdate
from app.services import recruiter_cadences as svc
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/recruiter", tags=["recruiter-cadences"])


@router.get("/cadences")
async def list_cadences(include_inactive: bool = False, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_reader(db, user)
    return await svc.list_out(db, user, include_inactive)


@router.post("/cadences", status_code=201)
async def create_cadence(payload: RecCadenceCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent: a retry with the same name is 409."""
    cadence = await svc.create(db, user, payload)
    await db.commit()
    svc.log("recruiter_cadence_created", user, cadence.id, steps=len(payload.steps))
    return await svc.one_out(db, user, cadence)


@router.patch("/cadences/{cadence_id}")
async def update_cadence(cadence_id: UUID, payload: RecCadenceUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    cadence = await svc.update(db, user, cadence_id, payload)
    await db.commit()
    svc.log("recruiter_cadence_updated", user, cadence.id)
    return await svc.one_out(db, user, cadence)


@router.post("/messages/{message_id}/cadence", status_code=201)
async def start_cadence(message_id: UUID, payload: RecCadenceStart, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """B6: the message (outreach to a contact) is step 1. A second start on the contact is 409."""
    run = await svc.start(db, user, message_id, payload.cadence_id)
    await db.commit()
    svc.log("recruiter_cadence_started", user, run.id, message_id=str(message_id))
    return await svc.one_message(db, user, await db.get(Company, run.company_id), message_id)


@router.post("/messages/{message_id}/cadence/stop")
async def stop_cadence(message_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    run = await svc.stop(db, user, message_id, await db_now(db))
    await db.commit()
    svc.log("recruiter_cadence_stopped", user, run.id, message_id=str(message_id))
    return await svc.one_message(db, user, await db.get(Company, run.company_id), message_id)

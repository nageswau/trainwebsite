"""upc-011 (DEC-SCOPE-152, spec §3): partnership events -- add, read, edit and cancel.

Every write is one transaction: the event row lock, the actor check, the change and the audit row, one commit here, then a structured
log (ids only). There is no list: the calendar (`/partnership/calendar`) is the list."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import PartnershipEventCancel, PartnershipEventEnvelope, PartnershipEventIn, PartnershipEventUpdate
from app.services import partnership_calendar as calendar
from app.services import partnership_events as svc

router = APIRouter(prefix="/partnership/events", tags=["partnership-events"])


@router.post("", status_code=201, response_model=PartnershipEventEnvelope)
async def add_event(payload: PartnershipEventIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_creator(db, user)
    e = await svc.create(db, user, payload)
    await db.commit()
    svc.log("partnership_event_created", user, e.id, kind=e.kind)
    return {"event": await svc.detail_out(db, user, e.id)}


@router.get("/{event_id}", response_model=PartnershipEventEnvelope)
async def get_event(event_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await calendar.require_reader(db, user)
    return {"event": await svc.detail_out(db, user, event_id)}


@router.patch("/{event_id}", response_model=PartnershipEventEnvelope)
async def edit_event(event_id: UUID, payload: PartnershipEventUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    e = await svc.load_for_write(db, user, event_id, "edit")
    changed = await svc.update(db, user, e, payload)
    await db.commit()
    if changed:
        svc.log("partnership_event_edited", user, e.id, fields=changed)
    return {"event": await svc.detail_out(db, user, e.id)}


@router.post("/{event_id}/cancel", response_model=PartnershipEventEnvelope)
async def cancel_event(event_id: UUID, payload: PartnershipEventCancel, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    e = await svc.load_for_write(db, user, event_id, "cancel")
    svc.cancel(db, user, e, payload.reason, datetime.now(UTC))
    await db.commit()
    svc.log("partnership_event_cancelled", user, e.id)
    return {"event": await svc.detail_out(db, user, e.id)}

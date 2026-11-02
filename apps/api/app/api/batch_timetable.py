"""itc-020 (DEC-SCOPE-344) -- the batch timetable: weekly slots (IT Admin), single-class cancellation (IT Admin) and the calendar of
dated classes (every IT role, scoped). API_CONTRACT.md §12IP; RBAC_MATRIX.md §2.244."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import TimetableCancelIn, TimetableSlotIn
from app.services import batch_timetable as timetable

router = APIRouter(prefix="/it", tags=["batch-timetable"])


@router.get("/batches/{batch_id}/timetable")
async def list_slots(batch_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    timetable.require_editor(user)
    batch = await timetable.batch_or_404(db, batch_id, lock=False)
    return {"batch_id": batch_id, "items": [timetable.slot_out(s) for s in await timetable.slots_of(db, batch)]}


@router.post("/batches/{batch_id}/timetable", status_code=201)
async def create_slot(batch_id: UUID, payload: TimetableSlotIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    timetable.require_editor(user)
    slot = await timetable.create_slot(db, user, await timetable.batch_or_404(db, batch_id), payload)
    await db.commit()
    return timetable.slot_out(slot)


@router.put("/batches/{batch_id}/timetable/{slot_id}")
async def update_slot(batch_id: UUID, slot_id: UUID, payload: TimetableSlotIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    timetable.require_editor(user)
    slot = await timetable.update_slot(db, user, await timetable.batch_or_404(db, batch_id), slot_id, payload)
    out = timetable.slot_out(slot)
    await db.commit()
    return out


@router.delete("/batches/{batch_id}/timetable/{slot_id}", status_code=204)
async def delete_slot(batch_id: UUID, slot_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    timetable.require_editor(user)
    await timetable.delete_slot(db, user, await timetable.batch_or_404(db, batch_id), slot_id)
    await db.commit()
    return Response(status_code=204)


@router.post("/batches/{batch_id}/timetable/{slot_id}/cancellations", status_code=201)
async def cancel_class(batch_id: UUID, slot_id: UUID, payload: TimetableCancelIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    timetable.require_editor(user)
    row = await timetable.cancel_class(db, user, await timetable.batch_or_404(db, batch_id), slot_id, payload)
    await db.commit()
    return {"slot_id": row.slot_id, "occurs_on": row.occurs_on, "reason": row.reason}


@router.get("/timetable")
async def calendar(start: date | None = Query(None, alias="from"), end: date | None = Query(None, alias="to"), batch_id: UUID | None = None,
                   user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    return await timetable.occurrences(db, user, start, end, batch_id)

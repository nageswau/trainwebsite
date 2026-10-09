"""upc-009 (DEC-SCOPE-145, spec §3): university meetings -- the four lists, schedule, read, edit/reschedule, complete and cancel.

Every write is one transaction: the row locks (university then meeting, services.university_meetings.load_for_write), the actor check,
the change, the history and audit rows, the stage advance and upc-020 follow-ups, one commit here, then a structured log (ids only). The
pickers are upc-010's (`/partnership/visits/*-options`, the same roles and scope)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import (
    UniversityMeetingCancel,
    UniversityMeetingComplete,
    UniversityMeetingEnvelope,
    UniversityMeetingIn,
    UniversityMeetingPage,
    UniversityMeetingUpdate,
    UniversityMeetingView,
)
from app.services import university_meetings as svc

router = APIRouter(prefix="/partnership/meetings", tags=["partnership-meetings"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("", response_model=UniversityMeetingPage)
async def list_meetings(
    view: UniversityMeetingView | None = None,
    university_id: UUID | None = None,
    mine: bool = False,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """MG14/MG16: every partnership reader reads every meeting; `mine` = responsible, scheduled by or joining as an employee."""
    await svc.require_reader(db, user)
    return await svc.page(db, svc.list_filters(user, university_id, mine), view, _now(), limit, offset)


@router.post("", status_code=201, response_model=UniversityMeetingEnvelope)
async def schedule_meeting(payload: UniversityMeetingIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_creator(db, user)
    uni = await svc.university_for(db, user, payload.university_id)
    now = _now()
    m = await svc.create(db, user, uni, payload, now)
    await db.commit()
    svc.log("university_meeting_created", user, m.id, university_id=str(uni.id), stage=uni.stage)
    return {"meeting": await svc.detail_out(db, user, m.id, now)}


@router.get("/{meeting_id}", response_model=UniversityMeetingEnvelope)
async def get_meeting(meeting_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_reader(db, user)
    return {"meeting": await svc.detail_out(db, user, meeting_id, _now())}


@router.patch("/{meeting_id}", response_model=UniversityMeetingEnvelope)
async def edit_meeting(meeting_id: UUID, payload: UniversityMeetingUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MG9: a scheduled meeting only; a changed `starts_at` is a reschedule."""
    m = await svc.load_for_write(db, user, meeting_id, "edit")
    now = _now()
    changed = await svc.update(db, user, m, payload, now)
    await db.commit()
    if changed:
        svc.log("university_meeting_edited", user, m.id, fields=changed)
    return {"meeting": await svc.detail_out(db, user, m.id, now)}


@router.post("/{meeting_id}/complete", response_model=UniversityMeetingEnvelope)
async def complete_meeting(meeting_id: UUID, payload: UniversityMeetingComplete, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MG10-MG13 (AC2, AC3): the outcome, the follow-ups and the stage advance in one transaction."""
    uni = await svc.university_of(db, user, meeting_id)
    m = await svc.load_for_write(db, user, meeting_id, "complete")
    now = _now()
    await svc.complete(db, user, m, uni, payload, now)
    await db.commit()
    svc.log("university_meeting_completed", user, m.id, university_id=str(uni.id), stage=uni.stage)
    return {"meeting": await svc.detail_out(db, user, m.id, now)}


@router.post("/{meeting_id}/cancel", response_model=UniversityMeetingEnvelope)
async def cancel_meeting(meeting_id: UUID, payload: UniversityMeetingCancel, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    m = await svc.load_for_write(db, user, meeting_id, "cancel")
    now = _now()
    svc.cancel(db, user, m, payload.reason, now)
    await db.commit()
    svc.log("university_meeting_cancelled", user, m.id)
    return {"meeting": await svc.detail_out(db, user, m.id, now)}

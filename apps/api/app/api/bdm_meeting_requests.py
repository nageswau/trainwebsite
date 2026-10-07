"""tel-019 (DEC-SCOPE-097, spec §3; API §12S): BDM meeting requests.

- /telecaller/meeting-requests: a telecaller files a request and lists their own (MR12).
- /bdm/meeting-requests: the BDM inbox (a BDM, a BDM manager, super_admin read; only a BDM accepts or declines).

Scope always comes from the session; an id outside it is 404, a role that may not act 403. Every write is one transaction: the request row
lock, the change, the audit, one commit. Accept books through bdm-006's own `book_appointment` (every bdm-006 rule applies, MR9), so the
lock order is request -> organization -> appointment, and a refusal there rolls the whole accept back (the request stays pending). Create
is not idempotent (as bdm-006 R-A5): the form disables its button while a submit is in flight."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.bdm_appointments import book_appointment
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BDM_MEETING_REQUEST_BDM_TYPE, BDM_MEETING_REQUEST_STATUSES, BdmMeetingRequest, User
from app.schemas import BdmAppointmentCreate, MeetingRequestCreate, MeetingRequestDecline
from app.services import bdm_appointments as appt_svc
from app.services import bdm_meeting_requests as svc
from app.services.bdm import bdm_context
from app.services.telecaller import telecaller_context

telecaller_router = APIRouter(prefix="/telecaller/meeting-requests", tags=["bdm-meeting-requests"])
router = APIRouter(prefix="/bdm/meeting-requests", tags=["bdm-meeting-requests"])
Status = Literal[BDM_MEETING_REQUEST_STATUSES]


@telecaller_router.get("/options")
async def request_options(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await telecaller_context(db, user)
    return await svc.options(db)


@telecaller_router.post("", status_code=201)
async def file_request(payload: MeetingRequestCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """In this order so each refusal is exactly one rule: 403 role; 422 fields (schema), time, named BDM (MR8)."""
    await telecaller_context(db, user)
    svc.require_proposable(payload.proposed_at, await svc.db_now(db))
    bdm_type = BDM_MEETING_REQUEST_BDM_TYPE[payload.request_type]
    if payload.bdm_user_id is not None:
        await svc.require_target(db, payload.bdm_user_id, bdm_type)
    request = BdmMeetingRequest(code=await svc.next_code(db), requester_user_id=user.id, bdm_type=bdm_type, status="pending",
                                **payload.model_dump())
    db.add(request)
    await db.flush()
    svc.audit(db, user, "create", request, {"bdm_type": bdm_type, "named": payload.bdm_user_id is not None})
    await db.commit()
    svc.log("bdm_meeting_request_filed", user, request, bdm_type=bdm_type)
    return (await svc.outs(db, user, [await svc.fresh(db, request)]))[0]


@telecaller_router.get("")
async def my_requests(status: Status | None = None, limit: int = LIMIT, offset: int = OFFSET,
                      user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The telecaller's own requests, newest first."""
    await telecaller_context(db, user)
    filters = [BdmMeetingRequest.requester_user_id == user.id]
    if status is not None:
        filters.append(BdmMeetingRequest.status == status)
    return await svc.page(db, user, filters, (BdmMeetingRequest.created_at.desc(), BdmMeetingRequest.id), limit, offset)


@router.get("")
async def inbox(status: Status | None = None, limit: int = LIMIT, offset: int = OFFSET,
                user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    filters = await svc.scope_filters(db, user)
    if status is not None:
        filters.append(BdmMeetingRequest.status == status)
    return await svc.page(db, user, filters, svc.inbox_order(), limit, offset)


@router.get("/{request_id}")
async def get_request(request_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return (await svc.outs(db, user, [await svc.load_scoped(db, user, request_id)]))[0]


async def _deciding(db: AsyncSession, user: User, request_id: UUID) -> BdmMeetingRequest:
    """Role (403), scope under the row lock (404), then state (409) -- the order accept and decline share."""
    await bdm_context(db, user)
    request = await svc.load_scoped(db, user, request_id, lock=True)
    svc.require_pending(request)
    return request


@router.post("/{request_id}/accept")
async def accept_request(request_id: UUID, payload: BdmAppointmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC2: exactly one appointment -- the row lock and the pending check serialise two accepts; the unique bdm_appointment_id is the
    backstop."""
    request = await _deciding(db, user, request_id)
    appt, overridden = await book_appointment(db, user, payload)
    request.status, request.bdm_user_id, request.bdm_appointment_id, request.decided_at = "accepted", user.id, appt.id, await svc.db_now(db)
    svc.audit(db, user, "accept", request, {"appointment_id": str(appt.id), "organization_id": str(appt.organization_id)})
    await db.commit()
    appt_svc.log("bdm_appt_created", user, appt.id, organization_id=str(appt.organization_id), overlap_override=overridden)
    svc.log("bdm_meeting_request_accepted", user, request, appointment_id=str(appt.id))
    return {
        "appointment": await appt_svc.appointment_out(db, user, appt),
        "meeting_request": (await svc.outs(db, user, [await svc.fresh(db, request)]))[0],
    }


@router.post("/{request_id}/decline")
async def decline_request(request_id: UUID, payload: MeetingRequestDecline, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC3 / MR2: a reason is required and the decline is final."""
    request = await _deciding(db, user, request_id)
    request.status, request.bdm_user_id, request.decline_reason, request.decided_at = "declined", user.id, payload.reason, await svc.db_now(db)
    svc.audit(db, user, "decline", request)
    await db.commit()
    svc.log("bdm_meeting_request_declined", user, request)
    return (await svc.outs(db, user, [await svc.fresh(db, request)]))[0]

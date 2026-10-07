"""tel-019 (DEC-SCOPE-097, spec §3): BDM meeting requests -- who sees which request (MR1, MR3, MR11), the named target (MR8), the code
(MR6) and the output.

Functions only; nothing here commits -- the route owns the transaction. Every BDM-side route resolves a request through `load_scoped`, so
an id outside the caller's scope is the same 404 as a missing one. Logs and audit rows carry ids, types and statuses, never the person,
their contact details or free text."""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    APPOINTMENT_MODES,
    BDM_MEETING_REQUEST_BDM_TYPE,
    BDM_MEETING_REQUEST_CODE_SEQ,
    BDM_MEETING_REQUEST_TYPES,
    AuditLog,
    BdmAppointment,
    BdmMeetingRequest,
    BdmProfile,
    User,
)
from app.services.bdm import BDM_TYPES, bdm_context

logger = logging.getLogger("app.bdm")

NOT_FOUND = "Meeting request not found"
TYPE_LABEL = {"college": "College meeting", "agent": "Agent meeting", "school": "School meeting", "corporate": "Corporate meeting"}
BDM_TYPE_LABEL = {"college": "College", "agent": "Agent", "school": "School"}
HORIZON = timedelta(days=366)  # tel-016 AP8


def invalid(field: str, msg: str, value=None) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


async def db_now(db: AsyncSession) -> datetime:
    return await db.scalar(select(func.now()))


def require_proposable(start: datetime, now: datetime) -> None:
    if start <= now:
        raise invalid("proposed_at", "Choose a time in the future", start.isoformat())
    if start > now + HORIZON:
        raise invalid("proposed_at", "Choose a time within the next year", start.isoformat())


def _active_bdms(bdm_type: str | None = None):
    stmt = (select(User, BdmProfile.bdm_type).join(BdmProfile, BdmProfile.user_id == User.id)
            .where(User.role == "bdm", User.active.is_(True)))
    return stmt if bdm_type is None else stmt.where(BdmProfile.bdm_type == bdm_type)


async def options(db: AsyncSession) -> dict:
    bdms: dict[str, list[dict]] = {t: [] for t in BDM_TYPES}
    for user, bdm_type in (await db.execute(_active_bdms().order_by(User.full_name, User.id))).all():
        bdms[bdm_type].append({"id": user.id, "full_name": user.full_name})
    return {
        "types": [{"key": k, "label": TYPE_LABEL[k], "bdm_type": BDM_MEETING_REQUEST_BDM_TYPE[k]} for k in BDM_MEETING_REQUEST_TYPES],
        "bdms": bdms,
        "modes": list(APPOINTMENT_MODES),
    }


async def require_target(db: AsyncSession, bdm_user_id: UUID, bdm_type: str) -> User:
    """MR8: an active BDM of the request's type. FOR SHARE: a deactivation of that user waits for this request's commit."""
    row = (await db.execute(_active_bdms(bdm_type).where(User.id == bdm_user_id).with_for_update(of=User, read=True))).first()
    if row is None:
        raise invalid("bdm_user_id", f"Choose an active {BDM_TYPE_LABEL[bdm_type]} BDM, or leave it for any of them", str(bdm_user_id))
    return row[0]


async def next_code(db: AsyncSession) -> str:
    """MR6: a sequence never repeats a value; gaps after a rollback are accepted. uq_bdm_meeting_requests_code is the backstop."""
    return f"MRQ-{await db.scalar(select(BDM_MEETING_REQUEST_CODE_SEQ.next_value())):06d}"


def _pool():
    """MR1: the unassigned requests -- always pending (ck_bdm_meeting_requests_decided)."""
    return BdmMeetingRequest.bdm_user_id.is_(None)


async def scope_filters(db: AsyncSession, user: User) -> list:
    """MR11 / MR3: a BDM their type's pool plus what is theirs; a manager their team's plus the whole pool (sub-select, so a row lock
    never touches bdm_profiles); super_admin all; any other role 403."""
    if user.role == "bdm":
        profile = await bdm_context(db, user)
        return [BdmMeetingRequest.bdm_type == profile.bdm_type, or_(BdmMeetingRequest.bdm_user_id == user.id, _pool())]
    if user.role == "bdm_manager":
        team = select(BdmProfile.user_id).where(BdmProfile.reporting_manager_user_id == user.id)
        return [or_(BdmMeetingRequest.bdm_user_id.in_(team), _pool())]
    if user.role == "super_admin":
        return []
    raise HTTPException(403, "BDM role required")


async def load_scoped(db: AsyncSession, user: User, request_id: UUID, *, lock: bool = False) -> BdmMeetingRequest:
    """With `lock`, the scope is evaluated under the row lock: a pool request another BDM took while this one waited reads as missing."""
    stmt = select(BdmMeetingRequest).where(BdmMeetingRequest.id == request_id, *await scope_filters(db, user))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    request = await db.scalar(stmt)
    if request is None:
        raise HTTPException(404, NOT_FOUND)
    return request


def require_pending(request: BdmMeetingRequest) -> None:
    if request.status != "pending":
        raise HTTPException(409, f"This request is already {request.status}")


def inbox_order(user: User) -> tuple:
    """Pending first -- those named for the caller ahead of the pool (QA-02), then soonest proposed first; then decided ones, latest
    decision first."""
    pending = BdmMeetingRequest.status == "pending"
    named_for_me = and_(pending, BdmMeetingRequest.bdm_user_id == user.id)
    return (case((pending, 0), else_=1), case((named_for_me, 0), else_=1), case((pending, BdmMeetingRequest.proposed_at)),
            BdmMeetingRequest.decided_at.desc(), BdmMeetingRequest.id)


def permissions(user: User, request: BdmMeetingRequest) -> dict[str, bool]:
    """Only a BDM decides, and only a pending request in their scope (anything they can read is in scope)."""
    can = user.role == "bdm" and request.status == "pending" and request.bdm_user_id in (None, user.id)
    return {"can_accept": can, "can_decline": can}


def _person(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name} if user else None


async def outs(db: AsyncSession, user: User, requests: list[BdmMeetingRequest]) -> list[dict]:
    """The shape every route returns (spec §3), batched: one query for the people, one for the appointments."""
    if not requests:
        return []
    people_ids = {r.requester_user_id for r in requests} | {r.bdm_user_id for r in requests if r.bdm_user_id}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(people_ids)))).all()}
    appt_ids = {r.bdm_appointment_id for r in requests if r.bdm_appointment_id}
    appts = {a.id: a for a in (await db.scalars(select(BdmAppointment).where(BdmAppointment.id.in_(appt_ids)))).all()} if appt_ids else {}
    result = []
    for r in requests:
        appt = appts.get(r.bdm_appointment_id)
        result.append({
            "id": r.id, "code": r.code, "request_type": r.request_type, "type_label": TYPE_LABEL[r.request_type], "bdm_type": r.bdm_type,
            "organization_name": r.organization_name, "person_name": r.person_name, "contact_phone": r.contact_phone,
            "contact_email": r.contact_email, "proposed_at": r.proposed_at, "mode": r.mode, "location": r.location, "purpose": r.purpose,
            "remarks": r.remarks, "status": r.status, "requester": _person(people.get(r.requester_user_id)),
            "bdm": _person(people.get(r.bdm_user_id)),
            "appointment": {"id": appt.id, "code": appt.code, "starts_at": appt.starts_at, "status": appt.status} if appt else None,
            "decline_reason": r.decline_reason, "decided_at": r.decided_at, "created_at": r.created_at, "permissions": permissions(user, r),
        })
    return result


async def page(db: AsyncSession, user: User, filters: list, order: tuple, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(BdmMeetingRequest).where(*filters))
    rows = (await db.scalars(select(BdmMeetingRequest).where(*filters).order_by(*order).limit(limit).offset(offset))).all()
    return {"items": await outs(db, user, list(rows)), "total": total or 0, "limit": limit, "offset": offset}


async def fresh(db: AsyncSession, request: BdmMeetingRequest) -> BdmMeetingRequest:
    """Server defaults (timestamps) are expired after a flush/commit."""
    await db.refresh(request)
    return request


def audit(db: AsyncSession, user: User, action: str, request: BdmMeetingRequest, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, types and statuses only."""
    db.add(AuditLog(user_id=user.id, action=f"bdm_meeting_request.{action}", entity_type="bdm_meeting_request", entity_id=str(request.id),
                    metadata_json={"code": request.code, "request_type": request.request_type, "status": request.status, **(metadata or {})}))


def log(event: str, user: User, request: BdmMeetingRequest, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "meeting_request_id": str(request.id), "status": request.status, **extra}})

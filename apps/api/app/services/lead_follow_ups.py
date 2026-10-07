"""tel-011 (DEC-SCOPE-094, spec §3): follow-ups on a lead -- rules, the day / overdue / per-lead lists and the output.

A follow-up belongs to its lead (F3): every read and write goes through the lead's scope (`lead_pipeline.scope`), so another
telecaller's follow-up is the same 404 as a missing one and a reassigned lead's follow-ups move with it. Only the lead's telecaller
writes (F2). Writes lock the lead, then the follow-up -- the order of a closing stage move, which cancels the open ones (F4). Functions
only; nothing here commits. Logs and audit carry ids, the reason key and field names -- never notes, next action or cancel reasons."""

import logging
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.lead_stages import CLOSED
from app.lead_stages import label as stage_label
from app.models import AuditLog, Enquiry, LeadFollowUp, TelProduct, User
from app.schemas import LeadFollowUpCreate
from app.services import lead_pipeline, telecaller_leads
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import today_ist

logger = logging.getLogger("app.leads")

NOT_FOUND = "Follow-up not found"
TELECALLER_ONLY = "Only the lead's telecaller can change its follow-ups"
LEAD_CLOSED = "This lead is closed. A manager can reopen it before a follow-up is added"
DUE_PAST = "Choose a due time in the future"
DUE_FAR = "Choose a due time within the next 12 months"
STATE_REFUSALS = {"done": "This follow-up is already done", "cancelled": "This follow-up was cancelled"}
HORIZON = timedelta(days=366)
OPEN_CAP = 20  # F10: an abuse bound per lead, far above real use
OPEN_CAP_REACHED = f"This lead already has {OPEN_CAP} open follow-ups"

Caller, Creator, Completer = aliased(User), aliased(User), aliased(User)
IS_OPEN = LeadFollowUp.status == "open"


def _rows():
    """One query: the follow-up, its lead, the lead's product and telecaller, the creator and completer -- no N+1."""
    return (
        select(LeadFollowUp, Enquiry, TelProduct, Caller, Creator, Completer)
        .join(Enquiry, Enquiry.id == LeadFollowUp.lead_id)
        .outerjoin(TelProduct, TelProduct.id == Enquiry.product_id)
        .outerjoin(Caller, Caller.id == Enquiry.telecaller_user_id)
        .join(Creator, Creator.id == LeadFollowUp.created_by_user_id)
        .outerjoin(Completer, Completer.id == LeadFollowUp.completed_by_user_id)
    )


def _person(user: User | None) -> dict | None:
    return None if user is None else {"id": user.id, "full_name": user.full_name}


def can_change(user: User, lead: Enquiry, fu: LeadFollowUp) -> bool:
    return user.role == "telecaller" and not telecaller_leads.read_only(user, lead) and fu.status == "open"


def _out(user: User, now: datetime, fu: LeadFollowUp, lead: Enquiry, product: TelProduct | None, caller, creator, completer) -> dict:
    return {
        "id": fu.id, "due_at": fu.due_at, "reason": fu.reason, "notes": fu.notes, "next_action": fu.next_action, "status": fu.status,
        "overdue": fu.status == "open" and fu.due_at < now,  # F1
        "lead": {
            "id": lead.id, "lead_code": lead.lead_code, "name": lead.name, "priority": lead.priority, "status": lead.status,
            "status_label": stage_label(lead.status), "product": None if product is None else {"id": product.id, "name": product.name},
            "telecaller": _person(caller),
        },
        "created_by": _person(creator), "created_at": fu.created_at, "completed_at": fu.completed_at, "completed_by": _person(completer),
        "cancelled_at": fu.cancelled_at, "cancel_reason": fu.cancel_reason, "can_change": can_change(user, lead, fu),
    }


async def _page(db: AsyncSession, user: User, now: datetime, where: list, order: tuple, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(LeadFollowUp).join(Enquiry, Enquiry.id == LeadFollowUp.lead_id).where(*where))
    rows = (await db.execute(_rows().where(*where).order_by(*order).limit(limit).offset(offset))).tuples().all()
    return {"items": [_out(user, now, *row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


def in_day(day: date):
    start, end = day_range(day)
    return IS_OPEN & (LeadFollowUp.due_at >= start) & (LeadFollowUp.due_at < end)


def overdue(now: datetime):
    return IS_OPEN & (LeadFollowUp.due_at < now)


async def list_page(db: AsyncSession, user: User, scope: list, view: str, day: date, now: datetime, limit: int, offset: int) -> dict:
    """AC1 / AC2 / F1: `day` = the open follow-ups due in that IST day; `overdue` = every open one past its due time. Both oldest due
    first; the counts are the two views' totals, so the tabs agree with the lists."""
    chosen = in_day(day) if view == "day" else overdue(now)
    out = await _page(db, user, now, [*scope, chosen], (LeadFollowUp.due_at, LeadFollowUp.id), limit, offset)
    counts = (await db.execute(
        select(func.count().filter(in_day(day)), func.count().filter(overdue(now)))
        .select_from(LeadFollowUp).join(Enquiry, Enquiry.id == LeadFollowUp.lead_id).where(*scope)
    )).one()
    return {**out, "day": day, "counts": {"day": counts[0] or 0, "overdue": counts[1] or 0}}


async def lead_page(db: AsyncSession, user: User, lead_id: UUID, now: datetime, limit: int, offset: int) -> dict:
    """The lead's follow-ups: open ones by due time, then done / cancelled newest first."""
    order = (
        case((IS_OPEN, 0), else_=1), case((IS_OPEN, LeadFollowUp.due_at)).asc(),
        func.coalesce(LeadFollowUp.completed_at, LeadFollowUp.cancelled_at).desc(), LeadFollowUp.id,
    )
    return await _page(db, user, now, [LeadFollowUp.lead_id == lead_id], order, limit, offset)


async def one(db: AsyncSession, user: User, fu_id: UUID, now: datetime) -> dict:
    row = (await db.execute(_rows().where(LeadFollowUp.id == fu_id).execution_options(populate_existing=True))).tuples().one()
    return _out(user, now, *row)


def due_filter(kind: str, now: datetime):
    """F9: My Leads' "Due follow-up" -- the lead has an open follow-up due in today's IST window, or one past its due time."""
    condition = in_day(today_ist(now)) if kind == "today" else overdue(now)
    return exists().where(LeadFollowUp.lead_id == Enquiry.id, condition)


def require_telecaller(user: User) -> None:
    if user.role != "telecaller":
        raise HTTPException(403, TELECALLER_ONLY)


def check_due(due_at: datetime, now: datetime) -> None:
    """F6 / AC3. A 422 on the field (the validation-error shape), so the form can place it."""
    if due_at <= now or due_at > now + HORIZON:
        msg = DUE_PAST if due_at <= now else DUE_FAR
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "due_at"), "msg": msg, "input": due_at.isoformat()}])


async def create(db: AsyncSession, user: User, lead: Enquiry, payload: LeadFollowUpCreate, now: datetime) -> LeadFollowUp:
    """The caller locked the lead and checked role and handover. F4 closed -> 409; F6 time; F10 cap (counted under the lead lock, so
    exact); F5 the optional move (tel-004's rules, so a lead past the counselor is 422 and nothing is created)."""
    if lead.status in CLOSED:
        raise HTTPException(409, LEAD_CLOSED)
    check_due(payload.due_at, now)
    if (await db.scalar(select(func.count()).select_from(LeadFollowUp).where(LeadFollowUp.lead_id == lead.id, IS_OPEN)) or 0) >= OPEN_CAP:
        raise HTTPException(409, OPEN_CAP_REACHED)
    if payload.move_to_follow_up and lead.status != "follow_up":
        await lead_pipeline.person_move(db, lead, user, "telecaller", "follow_up", None)
    fu = LeadFollowUp(lead_id=lead.id, due_at=payload.due_at, reason=payload.reason, notes=payload.notes, next_action=payload.next_action,
                      created_by_user_id=user.id)
    db.add(fu)
    await db.flush()
    audit(db, user, "create", fu.id, {"lead_id": str(lead.id), "reason": fu.reason, "moved_stage": payload.move_to_follow_up})
    return fu


async def load_for_write(db: AsyncSession, user: User, fu_id: UUID, scope: list) -> LeadFollowUp:
    """In scope (404) -> lead lock (still in scope: a lead reassigned meanwhile is 404) -> telecaller (403) -> handover (403) ->
    follow-up lock -> open (409)."""
    lead_id = await db.scalar(select(LeadFollowUp.lead_id).join(Enquiry, Enquiry.id == LeadFollowUp.lead_id).where(LeadFollowUp.id == fu_id, *scope))
    if lead_id is None:
        raise HTTPException(404, NOT_FOUND)
    lead = await lead_pipeline.locked_lead(db, lead_id, *scope)
    require_telecaller(user)
    telecaller_leads.require_writable(user, lead)
    fu = await db.scalar(select(LeadFollowUp).where(LeadFollowUp.id == fu_id).with_for_update().execution_options(populate_existing=True))
    if fu is None:  # never in practice (follow-ups are not deleted); narrows the type without an assert
        raise HTTPException(404, NOT_FOUND)
    if fu.status != "open":
        raise HTTPException(409, STATE_REFUSALS[fu.status])
    return fu


def audit(db: AsyncSession, user: User, action: str, fu_id, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"lead_follow_up.{action}", entity_type="lead_follow_up", entity_id=str(fu_id), metadata_json=metadata or {}))


def log(event: str, user: User, fu_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "follow_up_id": str(fu_id), **extra}})

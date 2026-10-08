"""rec-025 (DEC-SCOPE-132, spec §1-§3): calls logged on a company contact or a candidate -- the party rules, the lists, the same-day
edit/delete gate, the next follow-up and the contact's Last contacted.

A contact call belongs to its company (CA3): reads and writes go through rec-003's company scope (`load_scoped`) and `can_edit`, so a
call on another recruiter's company is the same 404 as a missing one. A candidate call follows R11 (`candidates.WRITERS` log, readers
read). Every write locks the party row first (the company or the candidate), then the call. Only the caller changes a call, on its IST
day (CA4). Functions only; nothing here commits. Logs and audit carry ids, the outcome and field names -- never notes."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RECRUITER_CALL_OUTCOMES, AuditLog, Candidate, Company, CompanyContact, RecruiterCall, User
from app.schemas import RecCallCreate, RecFollowUpCreate
from app.services import candidates
from app.services import recruiter_companies as companies
from app.services import recruiter_follow_ups as follow_ups
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import today_ist
from app.services.lead_calls import check_time

logger = logging.getLogger("app.recruiter")

# CA1 (UNVERIFIED: the source names no outcomes), in the order the form offers them.
OUTCOMES = dict(zip(RECRUITER_CALL_OUTCOMES, ("Connected", "Call back requested", "Busy", "No answer", "Switched off", "Wrong number"), strict=True))
CONNECTED = frozenset({"connected", "call_back_requested"})
DAILY_CAP = 300  # CA9: an abuse bound, far above real use

NOT_FOUND = "Call not found"
CONTACT_NOT_FOUND = "Contact not found"
ONE_PARTY = "Choose a contact or a candidate -- one, not both"
CONTACT_INACTIVE = "This contact is inactive. Reactivate them before logging a call"
FOLLOW_UP_CANDIDATE = "Follow-ups belong to a company: add one from a contact call"
CALLER_ONLY = "Only the person who logged this call can change it"
NOT_TODAY = "Only today's calls can be changed"
MOVE_TODAY = "A call can only be moved within today"
CAP_REACHED = f"You've logged {DAILY_CAP} calls for this day"

Call = RecruiterCall


def _invalid(field: str, msg: str, value) -> RequestValidationError:
    """On the field (the validation-error shape), so the form can place it."""
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def editable(call: Call, now: datetime) -> bool:
    return today_ist(call.occurred_at) == today_ist(now)


def _writable(user: User, company: Company | None, candidate: Candidate | None) -> bool:
    if company is not None:
        return companies.permissions(user, company)["can_edit"]
    return user.role in candidates.WRITERS and candidate is not None and candidate.archived_at is None


def _rows():
    """One query: the call, its caller and its party (contact + company, or candidate) -- no N+1."""
    return (
        select(Call, User, CompanyContact, Company, Candidate)
        .join(User, User.id == Call.caller_user_id)
        .outerjoin(CompanyContact, CompanyContact.id == Call.contact_id)
        .outerjoin(Company, Company.id == Call.company_id)
        .outerjoin(Candidate, Candidate.id == Call.candidate_id)
    )


def _out(user: User, now: datetime, call: Call, caller: User, contact, company, candidate) -> dict:
    return {
        "id": call.id, "kind": "contact" if contact is not None else "candidate", "company_id": call.company_id,
        "contact": None if contact is None else {"id": contact.id, "name": contact.name},
        "candidate": None if candidate is None else {"id": candidate.id, "name": candidate.name, "code": candidate.candidate_code},
        "occurred_at": call.occurred_at, "duration_seconds": call.duration_seconds, "direction": call.direction, "outcome": call.outcome,
        "outcome_label": OUTCOMES[call.outcome], "connected": call.outcome in CONNECTED, "notes": call.notes,
        "caller": {"id": caller.id, "full_name": caller.full_name}, "created_at": call.created_at,
        "can_change": call.caller_user_id == user.id and editable(call, now) and _writable(user, company, candidate),
    }


async def page(db: AsyncSession, user: User, where, now: datetime, limit: int, offset: int) -> dict:
    """A company's or a candidate's calls, newest first."""
    total = await db.scalar(select(func.count()).select_from(Call).where(where))
    rows = (await db.execute(_rows().where(where).order_by(Call.occurred_at.desc(), Call.created_at.desc()).limit(limit).offset(offset))).tuples().all()
    return {"items": [_out(user, now, *row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


async def one(db: AsyncSession, user: User, call_id: UUID, now: datetime) -> dict:
    row = (await db.execute(_rows().where(Call.id == call_id).execution_options(populate_existing=True))).tuples().one()
    return _out(user, now, *row)


async def _locked_company(db: AsyncSession, user: User, company_id: UUID, route: str, missing: str) -> Company:
    """The company locked and in scope (404 as `missing`), then `can_edit` (403, then 409 when archived)."""
    try:
        company = await companies.load_scoped(db, user, company_id, lock=True)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, missing) from None
        raise
    companies.require(user, company, "can_edit", route)
    return company


async def _locked_candidate(db: AsyncSession, user: User, candidate_id: UUID, missing: str = candidates.NOT_FOUND) -> Candidate:
    """A writer (403), the candidate locked in the pool (404 as `missing`), not archived (409)."""
    candidates.require_writer(user)
    try:
        candidate = await candidates.load(db, candidate_id, lock=True)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, missing) from None
        raise
    if candidate.archived_at is not None:
        raise HTTPException(409, candidates.ARCHIVED)
    return candidate


async def create(db: AsyncSession, user: User, payload: RecCallCreate, now: datetime) -> tuple[Call, UUID | None]:
    """CA2 one party (422); the party locked and writable (403 / 404 / 409); CA5 the time; CA9 the cap; the call; CA6 the next follow-up
    through rec-024's rules, so a refusal there rolls the whole call back."""
    if (payload.contact_id is None) == (payload.candidate_id is None):
        raise _invalid("contact_id", ONE_PARTY, None)
    company = None
    if payload.contact_id is not None:
        company_id = await db.scalar(select(CompanyContact.company_id).where(CompanyContact.id == payload.contact_id))
        if company_id is None:
            raise HTTPException(404, CONTACT_NOT_FOUND)
        company = await _locked_company(db, user, company_id, "call_create", CONTACT_NOT_FOUND)
        contact = await db.scalar(select(CompanyContact).where(CompanyContact.id == payload.contact_id).execution_options(populate_existing=True))
        if not contact.active:
            raise HTTPException(409, CONTACT_INACTIVE)
    else:
        if payload.next_follow_up is not None:
            raise _invalid("next_follow_up", FOLLOW_UP_CANDIDATE, None)
        await _locked_candidate(db, user, payload.candidate_id)
    occurred_at = check_time(payload.occurred_at or now, now)
    start, end = day_range(today_ist(occurred_at))
    count = await db.scalar(select(func.count()).select_from(Call).where(Call.caller_user_id == user.id, Call.occurred_at >= start, Call.occurred_at < end))
    if (count or 0) >= DAILY_CAP:
        raise HTTPException(409, CAP_REACHED)
    call = Call(
        company_id=company.id if company else None, contact_id=payload.contact_id, candidate_id=payload.candidate_id, caller_user_id=user.id,
        occurred_at=occurred_at, duration_seconds=payload.duration_seconds, direction=payload.direction, outcome=payload.outcome, notes=payload.notes,
    )
    db.add(call)
    await db.flush()
    follow_up = None
    if payload.next_follow_up is not None:
        body = RecFollowUpCreate(**payload.next_follow_up.model_dump(), contact_id=payload.contact_id)
        follow_up = await follow_ups.create(db, user, company, body, now)
    party = {"contact_id": str(call.contact_id)} if company else {"candidate_id": str(call.candidate_id)}
    audit(db, user, "create", call.id, {**party, "outcome": call.outcome, "follow_up_id": str(follow_up.id) if follow_up else None})
    return call, follow_up.id if follow_up else None


async def load_for_write(db: AsyncSession, user: User, call_id: UUID, route: str, now: datetime) -> Call:
    """The party locked and writable (as on create; a party out of scope is this call's 404) -> the call locked -> the caller (403) ->
    its IST day (409)."""
    party = (await db.execute(select(Call.company_id, Call.candidate_id).where(Call.id == call_id))).first()
    if party is None:
        raise HTTPException(404, NOT_FOUND)
    if party.company_id is not None:
        await _locked_company(db, user, party.company_id, route, NOT_FOUND)
    else:
        await _locked_candidate(db, user, party.candidate_id, NOT_FOUND)
    call = await db.scalar(select(Call).where(Call.id == call_id).with_for_update().execution_options(populate_existing=True))
    if call is None:  # deleted while we waited for the party lock
        raise HTTPException(404, NOT_FOUND)
    if call.caller_user_id != user.id:
        raise HTTPException(403, CALLER_ONLY)
    if not editable(call, now):
        raise HTTPException(409, NOT_TODAY)
    return call


def apply_update(db: AsyncSession, user: User, call: Call, changes: dict, now: datetime) -> list[str]:
    """CA4: only values that differ are written; a moved time stays in today. Returns the changed fields."""
    changed = sorted(key for key, value in changes.items() if getattr(call, key) != value)
    if "occurred_at" in changed:
        changes["occurred_at"] = check_time(changes["occurred_at"], now)
        if today_ist(changes["occurred_at"]) != today_ist(now):
            raise _invalid("occurred_at", MOVE_TODAY, changes["occurred_at"].isoformat())
    for key in changed:
        setattr(call, key, changes[key])
    if changed:
        audit(db, user, "update", call.id, {"fields": changed})
    return changed


async def contact_last(db: AsyncSession, company_id: UUID) -> dict[UUID, datetime]:
    """CA7: each contact's latest call -- one query for the company's contact list."""
    rows = await db.execute(select(Call.contact_id, func.max(Call.occurred_at)).where(Call.company_id == company_id).group_by(Call.contact_id))
    return dict(rows.tuples().all())


def audit(db: AsyncSession, user: User, action: str, call_id, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"recruiter_call.{action}", entity_type="recruiter_call", entity_id=str(call_id), metadata_json=metadata or {}))


def log(event: str, user: User, call_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "call_id": str(call_id), **extra}})


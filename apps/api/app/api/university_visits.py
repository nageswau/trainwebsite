"""upc-010 (DEC-SCOPE-124, spec §3): university visits -- list, approval queue, option pickers, plan, edit and the §8 commands.

Every write is one transaction: the visit row lock (FOR UPDATE), the actor or approver check, the change, the history and audit rows,
the in-app notices (`channels=[]`, VS15), one commit here, then a structured log (ids only). Lists are {items, total, limit, offset}."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.workflows import _notify_user
from app.core.database import get_db
from app.models import Country, University, UniversityVisit, UniversityVisitParticipant, User
from app.schemas import (
    UniversityVisitClose,
    UniversityVisitComplete,
    UniversityVisitEnvelope,
    UniversityVisitIn,
    UniversityVisitPage,
    UniversityVisitReject,
    UniversityVisitUpdate,
    VisitOptionPage,
    VisitStatus,
)
from app.services import university_visits as svc
from app.services.bdm_travel import india_today
from app.services.partnership_universities import search_filters

router = APIRouter(prefix="/partnership/visits", tags=["partnership-visits"])
OPTION_LIMIT = Query(20, ge=1, le=100)
NEWEST = (UniversityVisit.proposed_date.desc(), UniversityVisit.code.desc())


def _line(v: UniversityVisit, uni_name: str) -> str:
    return f"{v.code}: {uni_name}, {v.proposed_date:%d %b %Y}"


@router.get("", response_model=UniversityVisitPage)
async def list_visits(
    status: VisitStatus | None = None,
    university_id: UUID | None = None,
    mine: bool = False,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every partnership role reads every visit (VS7); `mine` = the caller leads, planned or joins it."""
    await svc.require_reader(db, user)
    filters = []
    if status is not None:
        filters.append(UniversityVisit.status == status)
    if university_id is not None:
        filters.append(UniversityVisit.university_id == university_id)
    if mine:
        joined = exists().where(UniversityVisitParticipant.visit_id == UniversityVisit.id, UniversityVisitParticipant.user_id == user.id)
        filters.append(or_(UniversityVisit.lead_user_id == user.id, UniversityVisit.created_by_user_id == user.id, joined))
    return await svc.page(db, filters, limit, offset, NEWEST)


@router.get("/approvals", response_model=UniversityVisitPage)
async def approvals(limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Waiting visits this caller may decide, oldest submission first (VS4)."""
    if user.role not in ("partnership_head", "super_admin"):
        raise HTTPException(403, "Only a partnership head or a super admin approves visits")
    return await svc.page(db, svc.approvals_filter(user), limit, offset, (UniversityVisit.submitted_at, UniversityVisit.code))


@router.get("/university-options", response_model=VisitOptionPage)
async def university_options(q: str | None = SEARCH, limit: int = OPTION_LIMIT, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_creator(db, user)
    filters = [*await svc.university_scope(db, user), *search_filters(like_pattern(q))]
    base = select(University, Country).join(Country, Country.id == University.country_id).where(*filters)
    rows = (await db.execute(base.order_by(University.name, University.id).limit(limit + 1))).all()
    items = [{"id": u.id, "label": u.name, "detail": f"{u.university_code} · {u.city}, {c.name}"} for u, c in rows[:limit]]
    return {"items": items, "total": len(rows)}


async def _people(db: AsyncSession, filters: list, q: str | None, limit: int) -> dict:
    stmt = select(User).where(*filters, *_matching(like_pattern(q), User.full_name, User.email)).order_by(User.full_name, User.id).limit(limit + 1)
    rows = (await db.scalars(stmt)).all()
    return {"items": [{"id": u.id, "label": u.full_name, "detail": u.email} for u in rows[:limit]], "total": len(rows)}


@router.get("/lead-options", response_model=VisitOptionPage)
async def lead_options(q: str | None = SEARCH, limit: int = OPTION_LIMIT, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """VS6: a manager leads their own visits; a head picks themselves or an active direct report."""
    await svc.require_creator(db, user)
    return await _people(db, svc.lead_filter(user), q, limit)


@router.get("/employee-options", response_model=VisitOptionPage)
async def employee_options(q: str | None = SEARCH, limit: int = OPTION_LIMIT, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """VS11: other EduSphere employees are active partnership managers and heads."""
    await svc.require_reader(db, user)
    return await _people(db, [User.active.is_(True), User.role.in_(svc.STAFF_ROLES)], q, limit)


@router.post("", status_code=201, response_model=UniversityVisitEnvelope)
async def plan_visit(payload: UniversityVisitIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_creator(db, user)
    uni = await svc.university_for(db, user, payload.university_id)
    lead_id = payload.lead_user_id or user.id
    await svc.check_lead(db, user, lead_id)
    await svc.check_participants(db, payload.participant_user_ids, lead_id)
    await svc.check_contacts(db, payload.contact_ids, uni.id)
    svc.check_future(payload.proposed_date, "The proposed visit date")
    svc.check_future(payload.confirmed_date, "The confirmed visit date")
    values = payload.model_dump(exclude={"university_id", "lead_user_id", "city", "participant_user_ids", "contact_ids"})
    v = UniversityVisit(code=await svc.next_code(db), university_id=uni.id, lead_user_id=lead_id, created_by_user_id=user.id, city=payload.city or uni.city, status="planned", **values)
    db.add(v)
    await db.flush()
    await svc.replace_links(db, v, payload.participant_user_ids, payload.contact_ids)
    svc.record(db, user, v, "create", None, fields=sorted(k for k, val in payload.model_dump().items() if val not in (None, "", [], False)))
    await db.commit()
    svc.log("university_visit_created", user, v)
    return {"visit": await svc.detail_out(db, user, v)}


@router.get("/{visit_id}", response_model=UniversityVisitEnvelope)
async def get_visit(visit_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_reader(db, user)
    return {"visit": await svc.detail_out(db, user, await svc.load(db, visit_id))}


async def _locked(db: AsyncSession, user: User, visit_id: UUID, action: str) -> UniversityVisit:
    await svc.require_reader(db, user)
    v = await svc.load(db, visit_id, lock=True)
    svc.require_actor(user, v, action)
    return v


@router.patch("/{visit_id}", response_model=UniversityVisitEnvelope)
async def edit_visit(visit_id: UUID, payload: UniversityVisitUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Only the fields sent; an equal value is not a change (no history row). Which fields may change follows the status (VS9)."""
    v = await _locked(db, user, visit_id, "edit")
    changes = payload.model_dump(exclude_unset=True)
    current = {"participant_user_ids": await svc.participant_ids(db, v.id), "contact_ids": await svc.contact_ids_of(db, v.id)}
    changed = sorted(k for k, value in changes.items() if (set(value or []) != current[k] if k in current else getattr(v, k) != value))
    if not changed:
        return {"visit": await svc.detail_out(db, user, v)}
    if not set(changed) <= svc.editable_fields(v):
        if not svc.RULES["edit"](v):
            raise svc.refusal(v, "edit")
        frozen = "Only the follow-up date can change after the visit" if v.status in ("visit_completed", "follow_up") else "An approved visit's plan can't be changed"
        raise HTTPException(409, frozen if v.status != "planned" else "The follow-up date is set when the visit is completed")
    lead_id = changes.get("lead_user_id", v.lead_user_id)
    if "lead_user_id" in changed:
        await svc.check_lead(db, user, lead_id)
    if {"lead_user_id", "participant_user_ids"} & set(changed):
        await svc.check_participants(db, changes.get("participant_user_ids", sorted(current["participant_user_ids"])), lead_id)
    if "contact_ids" in changed:
        await svc.check_contacts(db, changes["contact_ids"], v.university_id)
    for key, label in (("proposed_date", "The proposed visit date"), ("confirmed_date", "The confirmed visit date"), ("follow_up_date", "The follow-up date")):
        if key in changed:
            svc.check_future(changes[key], label)
    for key in changed:
        if key not in current:
            setattr(v, key, changes[key])
    await svc.replace_links(db, v, changes.get("participant_user_ids") if "participant_user_ids" in changed else None, changes.get("contact_ids") if "contact_ids" in changed else None)
    svc.record(db, user, v, "edit", v.status, fields=changed)
    await db.commit()
    svc.log("university_visit_edited", user, v, fields=changed)
    return {"visit": await svc.detail_out(db, user, v)}


async def _transition(db: AsyncSession, user: User, visit_id: UUID, action: str, apply, *, reason: str | None = None) -> dict:
    """The lead's or creator's commands: lock, actor, the transition table, the change, history + audit, one commit."""
    v = await _locked(db, user, visit_id, action)
    if not svc.RULES[action](v):
        svc.log("university_visit_refused", user, v, action=action, status=409)
        raise svc.refusal(v, action)
    before = v.status
    apply(v)
    await db.flush()
    svc.record(db, user, v, action, before, reason=reason)
    if action == "submit":
        uni = await db.get_one(University, v.university_id)
        for recipient in await svc.approvers(db, v):
            await _notify_user(db, recipient, "Visit approval needed", _line(v, uni.name), "/partnership/visits/approvals", channels=[])
    await db.commit()
    svc.log(f"university_visit_{action}", user, v)
    return {"visit": await svc.detail_out(db, user, v)}


def _submit(v: UniversityVisit) -> None:
    v.submitted_at, v.rejection_reason = svc.now(), None


@router.post("/{visit_id}/submit", response_model=UniversityVisitEnvelope)
async def submit(visit_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _transition(db, user, visit_id, "submit", _submit)


@router.post("/{visit_id}/book", response_model=UniversityVisitEnvelope)
async def book(visit_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC2: Travel Booked only after Approved, and once the visit date is confirmed."""

    def apply(v: UniversityVisit) -> None:
        if v.confirmed_date is None:
            raise HTTPException(422, "Set the confirmed visit date before booking travel")
        v.status = "travel_booked"

    return await _transition(db, user, visit_id, "book", apply)


@router.post("/{visit_id}/complete", response_model=UniversityVisitEnvelope)
async def complete(visit_id: UUID, body: UniversityVisitComplete, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC3 + N1: on or after the confirmed date, with the follow-up date."""

    def apply(v: UniversityVisit) -> None:
        if v.confirmed_date is not None and india_today() < v.confirmed_date:
            raise HTTPException(422, f"The visit can be completed on or after its confirmed date, {v.confirmed_date:%d %b %Y}")
        svc.check_future(body.follow_up_date, "The follow-up date")
        v.status, v.follow_up_date = "visit_completed", body.follow_up_date

    return await _transition(db, user, visit_id, "complete", apply)


@router.post("/{visit_id}/follow-up", response_model=UniversityVisitEnvelope)
async def follow_up(visit_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _transition(db, user, visit_id, "follow_up", lambda v: setattr(v, "status", "follow_up"))


@router.post("/{visit_id}/close", response_model=UniversityVisitEnvelope)
async def close(visit_id: UUID, body: UniversityVisitClose | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """VS5: closing before the visit happened (called off) needs a reason; after the follow-up it is optional."""
    reason = body.reason if body else None

    def apply(v: UniversityVisit) -> None:
        if v.status in svc.EARLY_CLOSE and not reason:
            raise HTTPException(422, "Give a reason for closing a visit that has not happened")
        v.status, v.close_reason = "closed", reason

    return await _transition(db, user, visit_id, "close", apply, reason=reason)


async def _decide(db: AsyncSession, user: User, visit_id: UUID, approve: bool, reason: str | None = None) -> dict:
    """VS4 + AC1/AC5 under locks: the visit FOR UPDATE, then the lead's profile and head FOR SHARE (in `can_decide`)."""
    await svc.require_reader(db, user)
    v = await svc.load(db, visit_id, lock=True)
    if user.role == "partnership_manager" or not await svc.can_decide(db, user, v, lock=True):
        svc.log("university_visit_refused", user, v, action="decide", status=403)
        raise HTTPException(403, "Only the reporting partnership head approves this visit (a super admin when the head can't)")
    if not svc.RULES["decide"](v):
        raise svc.refusal(v, "decide")
    before = v.status
    if approve:
        v.status = "approved"
    else:
        v.submitted_at, v.rejection_reason = None, reason
    v.decided_by_user_id, v.decided_at = user.id, svc.now()
    await db.flush()
    svc.record(db, user, v, "approve" if approve else "reject", before, reason=reason)
    uni = await db.get_one(University, v.university_id)
    for recipient_id in dict.fromkeys((v.lead_user_id, v.created_by_user_id)):
        recipient = await db.get_one(User, recipient_id)
        await _notify_user(db, recipient, "Visit approved" if approve else "Visit returned", _line(v, uni.name), f"/partnership/visits/{v.id}", channels=[])
    await db.commit()
    svc.log("university_visit_decided", user, v, outcome="approved" if approve else "returned", fallback=user.role == "super_admin")
    return {"visit": await svc.detail_out(db, user, v)}


@router.post("/{visit_id}/approve", response_model=UniversityVisitEnvelope)
async def approve(visit_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _decide(db, user, visit_id, True)


@router.post("/{visit_id}/reject", response_model=UniversityVisitEnvelope)
async def reject(visit_id: UUID, body: UniversityVisitReject, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _decide(db, user, visit_id, False, body.reason)

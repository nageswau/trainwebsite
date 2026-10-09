"""upc-014 (DEC-SCOPE-142, spec §3): MoU / agreement management -- a university's agreements, the menu list, create, edit, the status
commands (approve, sign) and renewal.

Every write: the read gate (403), then the university row FOR UPDATE (serialises numbers, overlap checks and renewals per university)
and the agreement FOR UPDATE, the write permission (403 role/team, 409 inactive), the state and value checks, the change, the history
and audit rows, one commit here, then a structured log (ids only). Lists are {items, total, limit, offset}."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import UNIVERSITY_AGREEMENT_TYPES, OverseasCourse, University, UniversityAgreement, UniversityDocument, User
from app.schemas import UniversityAgreementIn, UniversityAgreementMove, UniversityAgreementRenew, UniversityAgreementUpdate
from app.services import partnership_universities as unis
from app.services import university_agreements as svc
from app.services.bdm_travel import india_today

router = APIRouter(prefix="/partnership", tags=["partnership-agreements"])
AgreementType = Literal[UNIVERSITY_AGREEMENT_TYPES]
EffectiveStatus = Literal[svc.EFFECTIVE_STATUSES]
PAGE = Query(50, ge=1, le=50)
ROLE_LABELS = {"partnership_manager": "Partnership manager", "partnership_head": "Partnership head", "super_admin": "Super admin"}
LIST_FIELDS = ("course_ids", "country_ids")


def _stored(values: dict) -> dict:
    """JSON columns hold ids as text."""
    return {k: [str(i) for i in v] if k in LIST_FIELDS else v for k, v in values.items()}


async def _page(db: AsyncSession, user: User, filters: list, order: tuple, limit: int, offset: int, *, events: bool) -> dict:
    base = select(UniversityAgreement, University).join(University, University.id == UniversityAgreement.university_id).where(*filters)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = [(a, u) for a, u in (await db.execute(base.order_by(*order).limit(limit).offset(offset))).tuples().all()]
    return {"items": await svc.agreements_out(db, user, rows, events=events), "total": total or 0, "limit": limit, "offset": offset}


async def _locked(db: AsyncSession, user: User, agreement_id: UUID, action: str, route: str) -> tuple[UniversityAgreement, University]:
    """The read gate, the agreement (404), then university -> agreement row locks and the write permission."""
    await svc.require_reader(db, user)
    university_id = (await svc.load(db, agreement_id)).university_id
    uni = await unis.load(db, university_id, lock=True)
    unis.require(user, uni, await unis.team_of(db, user), action, route)
    return await svc.load(db, agreement_id, lock=True), uni


@router.get("/universities/{university_id}/agreements")
async def list_agreements(university_id: UUID, limit: int = PAGE, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Newest first, each with its history, links and the moves the caller may make (AG13)."""
    await svc.require_reader(db, user)
    await unis.load(db, university_id)
    order = (UniversityAgreement.created_at.desc(), UniversityAgreement.mou_number.desc())
    return await _page(db, user, [UniversityAgreement.university_id == university_id], order, limit, offset, events=True)


@router.get("/universities/{university_id}/agreement-options")
async def agreement_options(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """What a manager may pick: this university's courses and its agreement-kind documents (the form filters by type)."""
    await svc.require_reader(db, user)
    uni = await unis.load(db, university_id)
    unis.require(user, uni, await unis.team_of(db, user), "can_manage_agreements", "agreement_options")
    courses = (await db.scalars(select(OverseasCourse).where(OverseasCourse.university_id == uni.id).order_by(OverseasCourse.title, OverseasCourse.id))).all()
    documents = (
        await db.scalars(
            select(UniversityDocument)
            .where(UniversityDocument.university_id == uni.id, UniversityDocument.kind.in_(UNIVERSITY_AGREEMENT_TYPES))
            .order_by(func.lower(UniversityDocument.title), UniversityDocument.id)
        )
    ).all()
    return {
        "courses": [{"id": c.id, "title": c.title, "level": c.level} for c in courses],
        "documents": [{"id": d.id, "kind": d.kind, "title": d.title, "current_version": d.current_version} for d in documents],
    }


@router.get("/agreement-signatories")
async def signatory_options(q: str | None = SEARCH, limit: int = Query(20, ge=1, le=50), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Who may sign for EduSphere (AG7): active partnership managers, heads and super admins, by name or email -- the lookup shape the
    searchable picker reads."""
    await svc.require_reader(db, user)
    filters = [User.active.is_(True), User.role.in_(svc.SIGNATORY_ROLES), *_matching(like_pattern(q), User.full_name, User.email)]
    rows = (await db.scalars(select(User).where(*filters).order_by(User.full_name, User.id).limit(limit + 1))).all()
    return {"items": [{"id": u.id, "label": u.full_name, "detail": ROLE_LABELS[u.role]} for u in rows[:limit]], "truncated": len(rows) > limit}


@router.get("/agreements")
async def menu_agreements(
    status: EffectiveStatus | None = None,
    agreement_type: AgreementType | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = PAGE,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AG18: every agreement, soonest expiry first; `status` is the effective one (Expiring / Expired included); `q` matches the MoU
    number or the university's name or code."""
    await svc.require_reader(db, user)
    filters = []
    if status is not None:
        filters.append(svc.effective_status_sql(india_today()) == status)
    if agreement_type is not None:
        filters.append(UniversityAgreement.agreement_type == agreement_type)
    if (pattern := like_pattern(q)) is not None:
        filters.append(or_(*(c.ilike(pattern, escape="\\") for c in (UniversityAgreement.mou_number, University.name, University.university_code))))
    return await _page(db, user, filters, (UniversityAgreement.expiry_date, UniversityAgreement.mou_number), limit, offset, events=False)


@router.get("/agreements/{agreement_id}")
async def get_agreement(agreement_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_reader(db, user)
    return {"agreement": await svc.agreement_out(db, user, await svc.load(db, agreement_id))}


@router.post("/universities/{university_id}/agreements", status_code=201)
async def create_agreement(university_id: UUID, payload: UniversityAgreementIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A draft with a new MoU number (AG1)."""
    await svc.require_reader(db, user)
    uni = await unis.load(db, university_id, lock=True)
    unis.require(user, uni, await unis.team_of(db, user), "can_manage_agreements", "agreement_create")
    values = payload.model_dump()
    svc.check_dates(values)
    await svc.check_values(db, uni.id, payload.agreement_type, values)
    a = UniversityAgreement(mou_number=await svc.next_number(db), university_id=uni.id, status="draft", created_by_user_id=user.id, **_stored(values))
    db.add(a)
    await db.flush()
    svc.record(db, user, a, "create", None, changed=sorted(k for k, v in values.items() if v not in (None, "", [], False)))
    await db.commit()
    svc.log("university_agreement_created", user, a)
    return {"agreement": await svc.agreement_out(db, user, a)}


@router.patch("/agreements/{agreement_id}")
async def update_agreement(agreement_id: UUID, payload: UniversityAgreementUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Only the fields sent; an equal value is not a change (no history row). Terms change before approval, the signing fields until
    signed (AG11)."""
    a, uni = await _locked(db, user, agreement_id, "can_manage_agreements", "agreement_update")
    changes = _stored(payload.model_dump(exclude_unset=True))
    changed = sorted(k for k, v in changes.items() if getattr(a, k) != v)
    if changed:
        svc.check_editable(a, set(changed))
        state = {k: getattr(a, k) for k in ("start_date", "expiry_date", "renewal_date")} | {k: changes[k] for k in changed}
        if None in (state["start_date"], state["expiry_date"]):
            raise HTTPException(422, "The start and expiry dates are required")
        svc.check_dates(state)
        merged = {"all_courses": a.all_courses, "course_ids": a.course_ids} | {k: changes[k] for k in changed}
        await svc.check_values(db, uni.id, a.agreement_type, merged)
        for key in changed:
            setattr(a, key, changes[key])
        svc.record(db, user, a, "update", a.status, changed=changed)
        await db.commit()
        svc.log("university_agreement_updated", user, a, fields=changed)
    return {"agreement": await svc.agreement_out(db, user, a)}


@router.post("/agreements/{agreement_id}/status")
async def move_agreement(agreement_id: UUID, payload: UniversityAgreementMove, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AG5: one step of the flow. Approval is the head's (AG6); signing checks AC2, the overlap and moves the university's stage."""
    action = "can_approve_agreements" if payload.to_status == "approved" else "can_manage_agreements"
    a, uni = await _locked(db, user, agreement_id, action, f"agreement_{payload.to_status}")
    svc.check_move(a, payload.from_status, payload.to_status)
    if payload.to_status == "signed":
        await svc.sign(db, user, a, uni)
    before = a.status
    a.status, a.status_changed_at = payload.to_status, datetime.now(UTC)
    svc.record(db, user, a, "status", before, note=payload.note)
    await db.commit()
    svc.log("university_agreement_moved", user, a, from_status=before)
    return {"agreement": await svc.agreement_out(db, user, a)}


@router.post("/agreements/{agreement_id}/renew", status_code=201)
async def renew_agreement(agreement_id: UUID, payload: UniversityAgreementRenew, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AG8: a new draft copying the terms, linked to this one; this one becomes Renewed when the new one is signed."""
    a, uni = await _locked(db, user, agreement_id, "can_manage_agreements", "agreement_renew")
    if a.status not in svc.IN_FORCE:
        raise HTTPException(409, "Only a signed or active agreement can be renewed")
    if await svc.successor(db, a.id) is not None:
        raise HTTPException(409, "This agreement already has a renewal")
    dates = payload.model_dump()
    svc.check_dates(dates)
    renewal = UniversityAgreement(
        mou_number=await svc.next_number(db), university_id=uni.id, status="draft", previous_agreement_id=a.id, created_by_user_id=user.id,
        **{k: getattr(a, k) for k in svc.COPIED_ON_RENEWAL}, **dates,
    )  # fmt: skip
    db.add(renewal)
    await db.flush()
    svc.record(db, user, renewal, "renew", None, note=f"Renewal of {a.mou_number}")
    await db.commit()
    svc.log("university_agreement_renewed", user, renewal, previous_id=str(a.id))
    return {"agreement": await svc.agreement_out(db, user, renewal)}

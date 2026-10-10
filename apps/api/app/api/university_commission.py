"""upc-016 (DEC-SCOPE-144, spec §3): §15 commission terms of an agreement -- RESTRICTED to the commission roles (U2). An agreement's terms,
add, edit, remove, and the "Commercial Terms" menu list.

Every write: the read gate (403), the agreement (404), the university row FOR UPDATE then the agreement FOR UPDATE (upc-014's order), the
write permission (403 role/team, 409 inactive), the freeze rule (409 once approved, CM9), the term (404), the value checks (422), the
change and an audit row, one commit here, then a structured log (ids only). Lists are {items, total, limit, offset}."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import OFFSET
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import (
    COMMISSION_CURRENCIES,
    COMMISSION_TRIGGERS,
    University,
    UniversityAgreement,
    UniversityCommissionReceipt,
    UniversityCommissionTerm,
    User,
)
from app.schemas import CommissionReceiptIn, CommissionTermIn, CommissionTermUpdate
from app.services import partnership_universities as unis
from app.services import university_agreements as agreements
from app.services import university_commission as svc
from app.services.bdm_travel import india_today

router = APIRouter(prefix="/partnership", tags=["partnership-commission"])
PAGE = Query(50, ge=1, le=50)
Trigger = Literal[COMMISSION_TRIGGERS]
Currency = Literal[COMMISSION_CURRENCIES]


async def _editable(db: AsyncSession, user: User, pairs: list[tuple[UniversityAgreement, University]]) -> set[UUID]:
    """The agreements whose terms this caller may change now: may manage the university's agreements, and the terms are not frozen."""
    team = await unis.team_of(db, user)
    return {a.id for a, uni in pairs if agreements.terms_editable(unis.permissions(user, uni, team), a)}


async def _locked(db: AsyncSession, user: User, agreement_id: UUID, route: str) -> tuple[UniversityAgreement, University]:
    await svc.require_reader(db, user)
    university_id = (await agreements.load(db, agreement_id)).university_id
    uni = await unis.load(db, university_id, lock=True)
    unis.require(user, uni, await unis.team_of(db, user), "can_manage_agreements", route)
    a = await agreements.load(db, agreement_id, lock=True)
    if a.status not in agreements.TERM_STATUSES:
        raise HTTPException(409, svc.FROZEN)
    return a, uni


async def _one(db: AsyncSession, user: User, term: UniversityCommissionTerm, a: UniversityAgreement, uni: University) -> dict:
    await db.refresh(term)  # server defaults (timestamps) are expired after a flush
    return {"term": (await svc.terms_out(db, [term], await _editable(db, user, [(a, uni)])))[0]}


@router.get("/agreements/{agreement_id}/commission-terms")
async def list_terms(agreement_id: UUID, limit: int = PAGE, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Oldest first (CM7: every commission role reads every agreement's terms)."""
    await svc.require_reader(db, user)
    a = await agreements.load(db, agreement_id)
    uni = await unis.load(db, a.university_id)
    base = select(UniversityCommissionTerm).where(UniversityCommissionTerm.agreement_id == a.id)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.scalars(base.order_by(*svc.ORDER).limit(limit).offset(offset))).all()
    return {"items": await svc.terms_out(db, list(rows), await _editable(db, user, [(a, uni)])), "total": total or 0, "limit": limit, "offset": offset}


@router.post("/agreements/{agreement_id}/commission-terms", status_code=201)
async def create_term(agreement_id: UUID, payload: CommissionTermIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    a, uni = await _locked(db, user, agreement_id, "commission_term_create")
    values = payload.model_dump()
    await svc.check_values(db, uni.id, values)
    await svc.check_room(db, a.id)
    term = UniversityCommissionTerm(agreement_id=a.id, created_by_user_id=user.id, updated_by_user_id=user.id, **svc.stored(values))
    db.add(term)
    await db.flush()
    svc.record(db, user, term, a, "create", changed=sorted(k for k, v in values.items() if v not in (None, "", [])))
    await db.commit()
    svc.log("university_commission_term_created", user, term)
    return await _one(db, user, term, a, uni)


@router.patch("/agreements/{agreement_id}/commission-terms/{term_id}")
async def update_term(agreement_id: UUID, term_id: UUID, payload: CommissionTermUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Only the fields sent; an equal value is not a change. Switching between % and fixed sends the other one as null."""
    a, uni = await _locked(db, user, agreement_id, "commission_term_update")
    term = await svc.load(db, a.id, term_id)
    changes = svc.stored(payload.model_dump(exclude_unset=True))
    changed = sorted(k for k, v in changes.items() if getattr(term, k) != v)
    if changed:
        await svc.check_values(db, uni.id, {k: getattr(term, k) for k in svc.FIELDS} | {k: changes[k] for k in changed})
        for key in changed:
            setattr(term, key, changes[key])
        term.updated_by_user_id = user.id
        svc.record(db, user, term, a, "update", changed=changed)
        await db.commit()
        svc.log("university_commission_term_updated", user, term, fields=changed)
    return await _one(db, user, term, a, uni)


@router.delete("/agreements/{agreement_id}/commission-terms/{term_id}", status_code=204)
async def delete_term(agreement_id: UUID, term_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CM11: a mistaken row comes out while the terms are still negotiable; the audit row keeps the trace."""
    a, _ = await _locked(db, user, agreement_id, "commission_term_delete")
    term = await svc.load(db, a.id, term_id)
    svc.record(db, user, term, a, "delete")
    await db.delete(term)
    await db.commit()
    svc.log("university_commission_term_deleted", user, term)
    return Response(status_code=204)


@router.get("/commission-terms")
async def menu_terms(
    trigger: Trigger | None = None,
    currency: Currency | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = PAGE,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CM14: every term, newest first, with its agreement and university; `q` matches the MoU number or the university's name or code."""
    await svc.require_reader(db, user)
    filters = []
    if trigger is not None:
        filters.append(UniversityCommissionTerm.trigger == trigger)
    if currency is not None:
        filters.append(UniversityCommissionTerm.currency == currency)
    if (pattern := like_pattern(q)) is not None:
        filters.append(or_(*(c.ilike(pattern, escape="\\") for c in (UniversityAgreement.mou_number, University.name, University.university_code))))
    base = (
        select(UniversityCommissionTerm, UniversityAgreement, University)
        .join(UniversityAgreement, UniversityAgreement.id == UniversityCommissionTerm.agreement_id)
        .join(University, University.id == UniversityAgreement.university_id)
        .where(*filters)
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    order = (UniversityCommissionTerm.created_at.desc(), UniversityCommissionTerm.id)
    rows = (await db.execute(base.order_by(*order).limit(limit).offset(offset))).all()
    terms = await svc.terms_out(db, [t for t, _, _ in rows], await _editable(db, user, [(a, u) for _, a, u in rows]))
    today = india_today()
    items = []
    for item, (_, a, uni) in zip(terms, rows, strict=True):
        state = agreements.effective_status(a, today)
        item["agreement"] = {
            "id": a.id, "mou_number": a.mou_number, "agreement_type": a.agreement_type, "type_label": agreements.TYPE_LABELS[a.agreement_type],
            "status": a.status, "effective_status": state, "status_label": agreements.STATUS_LABELS[state],
        }  # fmt: skip
        item["university"] = {"id": uni.id, "name": uni.name, "university_code": uni.university_code}
        items.append(item)
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


# --- upc-019 (DEC-SCOPE-161, spec §3): the commission ledger of one university -- Expected (computed), Received (recorded), Outstanding --
LISTED = 200  # applications and receipts shown; the totals are over all of them


@router.get("/universities/{university_id}/commission")
async def ledger(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CL11: totals per currency (no FX); every commission role reads every university (as CM7)."""
    await svc.require_reader(db, user)
    uni = await unis.load(db, university_id)
    rows = (await svc.expected_rows(db, [uni.id])).get(uni.id, [])
    expected, received = svc.currency_sums(rows), (await svc.received_sums(db, [uni.id])).get(uni.id, {})
    zero = Decimal(0)
    totals = [
        {"currency": c, "expected": svc.money_str(expected.get(c, zero)), "received": svc.money_str(received.get(c, zero)), "outstanding": svc.money_str(expected.get(c, zero) - received.get(c, zero))}
        for c in sorted(expected.keys() | received.keys())
    ]
    R = UniversityCommissionReceipt
    receipts_total = await db.scalar(select(func.count()).select_from(R).where(R.university_id == uni.id))
    receipts = (await db.scalars(select(R).where(R.university_id == uni.id).order_by(R.received_on.desc(), R.created_at.desc(), R.id).limit(LISTED))).all()
    applications = [r | {"amount": svc.money_str(r["amount"])} for r in rows[:LISTED]]
    return {
        "university": {"id": uni.id, "name": uni.name, "university_code": uni.university_code}, "totals": totals,
        "applications": applications, "applications_total": len(rows), "receipts": await svc.receipts_out(db, list(receipts)),
        "receipts_total": receipts_total or 0, "permissions": {"can_record": svc.can_record(user)},
    }  # fmt: skip


@router.post("/universities/{university_id}/commission/receipts", status_code=201)
async def record_receipt(university_id: UUID, payload: CommissionReceiptIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CL10: one lump sum, under the university lock so two concurrent saves of one reference can't both pass."""
    await svc.require_reader(db, user)
    svc.require_recorder(user)
    uni = await unis.load(db, university_id, lock=True)
    await svc.check_receipt(db, uni.id, payload.received_on, payload.reference, payload.application_ids)
    receipt = UniversityCommissionReceipt(university_id=uni.id, created_by_user_id=user.id, **payload.model_dump() | {"application_ids": [str(i) for i in payload.application_ids]})
    db.add(receipt)
    await db.flush()
    svc.record_receipt(db, user, receipt, "create")
    try:
        await db.commit()
    except IntegrityError as e:  # the per-university reference index (a race the lock did not see)
        await db.rollback()
        raise HTTPException(409, svc.DUPLICATE_REFERENCE) from e
    svc.log_receipt("university_commission_receipt_created", user, receipt)
    await db.refresh(receipt)
    return {"receipt": (await svc.receipts_out(db, [receipt]))[0]}


@router.delete("/universities/{university_id}/commission/receipts/{receipt_id}", status_code=204)
async def remove_receipt(university_id: UUID, receipt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CL12: a mistaken receipt comes out (audited) and is re-entered; receipts are never edited."""
    await svc.require_reader(db, user)
    svc.require_recorder(user)
    uni = await unis.load(db, university_id, lock=True)
    R = UniversityCommissionReceipt
    receipt = await db.scalar(select(R).where(R.id == receipt_id, R.university_id == uni.id).with_for_update())
    if receipt is None:
        raise HTTPException(404, svc.RECEIPT_NOT_FOUND)
    svc.record_receipt(db, user, receipt, "delete")
    await db.delete(receipt)
    await db.commit()
    svc.log_receipt("university_commission_receipt_deleted", user, receipt)
    return Response(status_code=204)

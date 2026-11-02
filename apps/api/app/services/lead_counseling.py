"""itc-010 (DEC-SCOPE-343): the IT counseling record -- one row per session (C1) on a lead handed to an IT counselor. The route has applied
its scope and, for a write, locked the lead; this module never decides who may read. Each save writes one audit row
(`lead_counseling.create` / `.update`, ids, the outcome and itc-001's field diff with notes as "changed") that the lead timeline reads (C10).
Logs carry ids and field names only; the notes are never logged (C11)."""

import logging
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED
from app.models import AuditLog, Enquiry, LeadCounselingObjection, LeadCounselingRecord, LeadCounselingRecordObjection, TelProduct, User
from app.schemas import LeadCounselingIn
from app.services.audit_changes import audit_change
from app.services.bdm_appointments import db_now, today_ist
from app.services.lead_pipeline import invalid

logger = logging.getLogger("app.leads")

CREATE, UPDATE = "lead_counseling.create", "lead_counseling.update"
IT_ONLY = "Only an IT counselor can record counseling"
LEAD_CLOSED = "This lead is closed, so its counseling can't be changed"
NOT_FOUND = "Counseling record not found"
PRODUCT = "Choose an active IT course"
OBJECTIONS = "Choose objections from the active list"
PAST = "The date can't be before today"
TEXT = ("objection_notes", "notes")  # blank is none
FIELDS = ("recommended_product_id", "objection_notes", "fee_quoted", "expected_joining_date", "decision_maker", "outcome", "next_follow_up", "notes")


async def _objection_ids(db: AsyncSession, record_id: UUID) -> list[UUID]:
    return list(await db.scalars(select(LeadCounselingRecordObjection.objection_id).where(LeadCounselingRecordObjection.record_id == record_id)))


async def _check(db: AsyncSession, sent: dict, before: dict) -> None:
    """C9 on the values that change: an active IT course, active objections, dates today (IST) or later -- so a stored value that has
    since gone inactive or past still saves (AC3 is at creation)."""
    changed = {f for f, v in sent.items() if v != before.get(f)}
    product_id = sent.get("recommended_product_id")
    if "recommended_product_id" in changed and product_id is not None:
        course = await db.get(TelProduct, product_id)
        if course is None or not course.active or course.product_group != "it":
            raise invalid("recommended_product_id", PRODUCT, str(product_id))
    added = set(sent.get("objection_ids") or []) - set(before.get("objection_ids") or [])
    if "objection_ids" in changed and added:
        active = set(await db.scalars(select(LeadCounselingObjection.id).where(LeadCounselingObjection.id.in_(added), LeadCounselingObjection.active.is_(True))))
        if active != added:
            raise invalid("objection_ids", OBJECTIONS, [str(i) for i in added - active])
    today = today_ist(await db_now(db))
    for field in ("expected_joining_date", "next_follow_up"):
        value: date | None = sent.get(field)
        if field in changed and value is not None and value < today:
            raise invalid(field, PAST, value.isoformat())


def _clean(sent: dict) -> dict:
    return {f: (v or None) if f in TEXT else v for f, v in sent.items()}


def _require_open(lead: Enquiry) -> None:
    if lead.status in CLOSED:
        raise HTTPException(409, LEAD_CLOSED)


async def _set_objections(db: AsyncSession, record_id: UUID, ids: list[UUID]) -> None:
    await db.execute(delete(LeadCounselingRecordObjection).where(LeadCounselingRecordObjection.record_id == record_id))
    db.add_all(LeadCounselingRecordObjection(record_id=record_id, objection_id=i) for i in dict.fromkeys(ids))


def _audited(values: dict) -> dict:
    """The objection set as sorted id strings, so a reorder is no change and the audit value is plain JSON."""
    return values | {"objection_ids": sorted(str(i) for i in values["objection_ids"])}


def _log(event: str, user: User, lead: Enquiry, record_id: UUID, fields: list[str]) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "lead_id": str(lead.id), "record_id": str(record_id), "fields": fields}})


async def create(db: AsyncSession, user: User, lead: Enquiry, payload: LeadCounselingIn) -> UUID:
    """On a locked lead: closed -> 409; C9; the row, its objections and the audit row. Commits."""
    _require_open(lead)
    sent = _clean(payload.model_dump())
    await _check(db, sent, {})
    record = LeadCounselingRecord(lead_id=lead.id, author_user_id=user.id, updated_by_user_id=user.id, **{f: sent[f] for f in FIELDS})
    db.add(record)
    await db.flush()
    await _set_objections(db, record.id, sent["objection_ids"])
    db.add(AuditLog(user_id=user.id, action=CREATE, entity_type="enquiry", entity_id=str(lead.id), metadata_json={"record_id": str(record.id), "outcome": record.outcome}))
    await db.commit()
    _log("lead_counseling_created", user, lead, record.id, sorted(f for f in sent if sent[f] not in (None, [])))
    return record.id


async def update(db: AsyncSession, user: User, lead: Enquiry, record_id: UUID, sent: dict) -> None:
    """On a locked lead: a record of another lead is 404; closed -> 409; C9 on the changed values; one itc-001 diff row. Commits."""
    record = await db.scalar(select(LeadCounselingRecord).where(LeadCounselingRecord.id == record_id, LeadCounselingRecord.lead_id == lead.id).with_for_update())
    if record is None:
        raise HTTPException(404, NOT_FOUND)
    _require_open(lead)
    sent = _clean(sent)
    if "objection_ids" in sent:
        sent["objection_ids"] = sent["objection_ids"] or []
    before = {f: getattr(record, f) for f in FIELDS} | {"objection_ids": await _objection_ids(db, record.id)}
    await _check(db, sent, before)
    for field in FIELDS:
        if field in sent:
            setattr(record, field, sent[field])
    if "objection_ids" in sent and set(sent["objection_ids"]) != set(before["objection_ids"]):
        await _set_objections(db, record.id, sent["objection_ids"])
    after = before | sent
    diff = audit_change(db, user, UPDATE, "enquiry", lead.id, _audited(before), _audited(after), metadata={"record_id": str(record.id), "outcome": after["outcome"]})
    if diff is not None:
        record.updated_by_user_id, record.updated_at = user.id, await db_now(db)
    await db.commit()
    if diff is not None:
        _log("lead_counseling_updated", user, lead, record.id, sorted(diff.metadata_json["changes"]))


async def page(db: AsyncSession, lead_id: UUID, limit: int, offset: int, record_id: UUID | None = None) -> dict:
    """Newest session first (`id` breaks a tie); the course, objections and people are read in three batched queries."""
    where = [LeadCounselingRecord.lead_id == lead_id, *([LeadCounselingRecord.id == record_id] if record_id else [])]
    total = await db.scalar(select(func.count()).select_from(LeadCounselingRecord).where(*where))
    records = list(
        await db.scalars(
            select(LeadCounselingRecord)
            .where(*where)
            .order_by(LeadCounselingRecord.created_at.desc(), LeadCounselingRecord.id.desc())
            .limit(limit)
            .offset(offset)
            .execution_options(populate_existing=True)
        )
    )
    ids = [r.id for r in records]
    objections: dict[UUID, list[dict]] = {i: [] for i in ids}
    rows = await db.execute(
        select(LeadCounselingRecordObjection.record_id, LeadCounselingObjection.id, LeadCounselingObjection.name)
        .join(LeadCounselingObjection, LeadCounselingObjection.id == LeadCounselingRecordObjection.objection_id)
        .where(LeadCounselingRecordObjection.record_id.in_(ids))
        .order_by(LeadCounselingObjection.sort_order, func.lower(LeadCounselingObjection.name))
    )
    for record_ref, oid, name in rows.all():
        objections[record_ref].append({"id": oid, "name": name})
    product_ids = {r.recommended_product_id for r in records if r.recommended_product_id}
    products: dict[UUID | None, dict] = {p.id: {"id": p.id, "name": p.name} for p in await db.scalars(select(TelProduct).where(TelProduct.id.in_(product_ids)))}
    user_ids = {r.author_user_id for r in records} | {r.updated_by_user_id for r in records}
    people = {u.id: {"id": u.id, "full_name": u.full_name} for u in await db.scalars(select(User).where(User.id.in_(user_ids)))}
    items = [
        {
            "id": r.id,
            **{f: getattr(r, f) for f in FIELDS if f != "recommended_product_id"},
            "recommended_product": products.get(r.recommended_product_id),
            "objections": objections[r.id],
            "author": people[r.author_user_id],
            "updated_by": people[r.updated_by_user_id],
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in records
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


async def one(db: AsyncSession, lead_id: UUID, record_id: UUID) -> dict:
    return (await page(db, lead_id, 1, 0, record_id))["items"][0]

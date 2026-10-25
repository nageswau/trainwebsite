"""ccrm-040 (DEC-SCOPE-275, CN1-CN5) -- the overseas student's data-processing and document-sharing consents. Each kind's current
agreement is the latest active overseas `Agreement` of that kind (a newer version asks again); acceptance is a `ConsentRecord`
(STU-009's insert-only row with the version and IP). Only the student consents; staff read the result on the 360."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agreement, AuditLog, ConsentRecord, User

KINDS = ("data_processing", "document_sharing")
ACCEPTED = "overseas_consent.accept"
NOT_FOUND = "Consent not found"


async def current(db: AsyncSession) -> list[Agreement]:
    """The current agreement of each kind, in KINDS order; a kind with no active agreement is left out."""
    rows = (
        await db.scalars(select(Agreement).where(Agreement.division == "overseas", Agreement.kind.in_(KINDS), Agreement.active.is_(True)).order_by(Agreement.created_at.desc(), Agreement.id))
    ).all()
    latest: dict[str, Agreement] = {}
    for row in rows:
        latest.setdefault(row.kind, row)
    return [latest[k] for k in KINDS if k in latest]


async def status(db: AsyncSession, student_id: UUID) -> list[dict]:
    agreements = await current(db)
    given = {
        r.agreement_id: r.created_at for r in (await db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == student_id, ConsentRecord.agreement_id.in_([a.id for a in agreements])))).all()
    }
    return [{"id": a.id, "kind": a.kind, "title": a.title, "body": a.body, "version": a.version, "accepted_at": given.get(a.id)} for a in agreements]


def staff_view(items: list[dict]) -> list[dict]:
    """CN4: the 360 shows what was given, not the wording."""
    return [{"kind": i["kind"], "label": i["title"], "version": i["version"], "accepted_at": i["accepted_at"]} for i in items]


async def accept(db: AsyncSession, student: User, agreement_id: UUID, ip_address: str | None) -> tuple[dict, bool]:
    """No commit. CN3: once per agreement; a repeat returns the first acceptance. Only a current overseas consent is accepted (404)."""
    agreement = next((a for a in await current(db) if a.id == agreement_id), None)
    if agreement is None:
        raise HTTPException(404, NOT_FOUND)
    record = await db.scalar(select(ConsentRecord).where(ConsentRecord.user_id == student.id, ConsentRecord.agreement_id == agreement.id))
    created = record is None
    if created:
        record = ConsentRecord(user_id=student.id, agreement_id=agreement.id, version=agreement.version, ip_address=ip_address)
        db.add(record)
        db.add(AuditLog(user_id=student.id, action=ACCEPTED, entity_type="user", entity_id=str(student.id), outcome="accepted", metadata_json={"kind": agreement.kind, "version": agreement.version}))
        await db.flush()
        await db.refresh(record)
    return {"id": agreement.id, "kind": agreement.kind, "version": agreement.version, "accepted_at": record.created_at}, created

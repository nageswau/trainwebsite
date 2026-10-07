"""tel-008 (DEC-SCOPE-084, spec §2): the telecaller lead workspace -- the scoped list and detail, the contact/priority edit and the lead
timeline (W1; tel-015 moved the reader to `services/lead_timeline.py`).

Scope is tel-004's `lead_pipeline.scope`; a lead outside it reads as missing (404). Functions only; nothing here commits -- the route
owns the transaction. Logs and audit rows carry ids, field names and priority keys -- never the lead's name, email or phone."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Enquiry, User
from app.notifications.phone import normalise_phone
from app.services import bdm_leads, lead_handover, lead_pipeline
from app.services.telecaller_catalogue import locked_active_product

logger = logging.getLogger("app.leads")

HANDED_OVER = "This lead is with the counselor; you can view it but not change it"
PRIORITY_CHANGE = "lead.priority_change"
PRIORITY_LABEL = {"hot": "Hot", "warm": "Warm", "cold": "Cold"}
SEARCHED = (Enquiry.lead_code, Enquiry.name, Enquiry.email, Enquiry.phone, Enquiry.whatsapp_number)


def read_only(user: User, lead: Enquiry) -> bool:
    """D1 / T19: once a counselor is assigned (`owner_id`), the telecaller keeps read access only; a manager still acts."""
    return user.role == "telecaller" and lead.owner_id is not None


def require_writable(user: User, lead: Enquiry) -> None:
    if read_only(user, lead):
        logger.warning("lead_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "lead_id": str(lead.id), "status": 403}})
        raise HTTPException(403, HANDED_OVER)


def whatsapp_to(lead: Enquiry) -> str | None:
    """tel-013 D1 / AC1: the wa.me number -- the WhatsApp number, else the mobile, as E.164 digits without the `+` (ENH-014's +91 default);
    an unusable WhatsApp number falls back to the mobile. None when neither is usable (AC3)."""
    number = normalise_phone(lead.whatsapp_number) or normalise_phone(lead.phone)
    return number.lstrip("+") if number else None


def row_out(user: User, row) -> dict:
    return {**bdm_leads.admin_out(row), "read_only": read_only(user, row[0])}


async def page(db: AsyncSession, user: User, filters: list, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(Enquiry).where(*filters))
    rows = (await db.execute(bdm_leads.admin_rows().where(*filters).order_by(*bdm_leads.NEWEST).limit(limit).offset(offset))).all()
    return {"items": [row_out(user, row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


async def detail(db: AsyncSession, user: User, lead_id: UUID, filters: list) -> dict:
    """tel-018: a lead that has just converted moves first, and the linked student's milestones come along (read only, T4)."""
    await lead_handover.observe_conversion(db, lead_id)
    row = (await db.execute(bdm_leads.admin_rows().where(Enquiry.id == lead_id, *filters).execution_options(populate_existing=True))).one_or_none()
    if row is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    return {**row_out(user, row), "message": row[0].message, "whatsapp_to": whatsapp_to(row[0]),
            "milestones": await lead_handover.milestones(db, row[0])}


async def apply_update(db: AsyncSession, user: User, lead: Enquiry, changes: dict) -> None:
    """D2: only values that differ are written. A priority change is its own audit row `{from, to}` (W1, the timeline reads it); the
    other fields share one `lead.contact_update` row naming the fields. Nothing changed -> no audit."""
    changes = {key: value for key, value in changes.items() if getattr(lead, key) != value}
    if changes.get("product_id") is not None:
        await locked_active_product(db, changes["product_id"])
    if "priority" in changes:
        db.add(AuditLog(user_id=user.id, action=PRIORITY_CHANGE, entity_type="enquiry", entity_id=str(lead.id),
                        metadata_json={"from": lead.priority, "to": changes["priority"]}))
    fields = sorted(key for key in changes if key != "priority")
    if fields:
        db.add(AuditLog(user_id=user.id, action="lead.contact_update", entity_type="enquiry", entity_id=str(lead.id), metadata_json={"fields": fields}))
    for key, value in changes.items():
        setattr(lead, key, value)
    if changes:
        logger.info("lead_updated", extra={"extra_fields": {"actor_id": str(user.id), "lead_id": str(lead.id), "fields": sorted(changes)}})


"""tel-009 (DEC-SCOPE-093, spec §3): the lead qualification form -- basic answers always, the IT or overseas requirement by the lead's
product group (QD2). The shared answers live on `enquiries` (QD1); the rest in `lead_qualifications`. A PUT replaces only the fields that
apply, so the other group's stored values are kept (AC3).

Functions only; nothing here commits -- the route owns the transaction and has already locked the lead. Logs and the audit row carry
ids and field names, never values."""

import logging

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Enquiry, LeadQualification, TelProduct, User
from app.services.telecaller_leads import read_only

logger = logging.getLogger("app.leads")

AUDIT = "lead.qualification_update"
SHARED = ("qualification", "passing_year", "city", "state")  # QD1: the lead's own columns
BASIC = (*SHARED, "current_org", "work_experience_years")
IT = ("it_skill_level", "career_objective", "preferred_batch", "budget_range", "preferred_mode")
OVERSEAS = ("study_level", "preferred_course", "intake", "academic_percentage", "english_test_status", "passport_status", "budget_range")
STORED = tuple(dict.fromkeys(f for f in (*BASIC, *IT, *OVERSEAS) if f not in SHARED))
APPLIES = {"it": (*BASIC, *IT), "overseas": (*BASIC, *OVERSEAS)}  # any other group (`other`, no product): basic only


async def _product(db: AsyncSession, lead: Enquiry) -> TelProduct | None:
    return await db.get(TelProduct, lead.product_id) if lead.product_id else None


async def _row(db: AsyncSession, lead: Enquiry) -> LeadQualification | None:
    stmt = select(LeadQualification).where(LeadQualification.lead_id == lead.id).execution_options(populate_existing=True)
    return await db.scalar(stmt)


async def read(db: AsyncSession, user: User, lead: Enquiry) -> dict:
    product, row = await _product(db, lead), await _row(db, lead)
    editor = await db.get(User, row.updated_by_user_id) if row else None
    stored = {field: getattr(row, field) if row else None for field in STORED}
    if stored["academic_percentage"] is not None:
        stored["academic_percentage"] = float(stored["academic_percentage"])
    return {
        "lead_id": lead.id,
        "product": {"id": product.id, "name": product.name, "group": product.product_group} if product else None,
        "product_group": product.product_group if product else None,
        **{field: getattr(lead, field) for field in SHARED},
        **stored,
        "read_only": read_only(user, lead),
        "updated_by": {"id": editor.id, "full_name": editor.full_name} if editor else None,
        "updated_at": row.updated_at if row else None,
    }


async def replace(db: AsyncSession, user: User, lead: Enquiry, sent: dict) -> None:
    """QD2: the fields that apply are replaced (left out = cleared); a field that doesn't apply is 422, which also catches a product
    changed while the form was open. QD3: only changed values are written, with one names-only audit row; the stage never moves."""
    product = await _product(db, lead)
    applies = APPLIES.get(product.product_group if product else None, BASIC)
    stray = sorted(set(sent) - set(applies))
    if stray:
        raise HTTPException(422, f"These fields don't apply to this lead's product: {', '.join(stray)}")
    row = await _row(db, lead)
    changed = [f for f in applies if (getattr(lead, f) if f in SHARED else getattr(row, f, None)) != sent.get(f)]
    if not changed:
        return
    if row is None:
        row = LeadQualification(lead_id=lead.id, updated_by_user_id=user.id)
        db.add(row)
    for field in changed:
        setattr(lead if field in SHARED else row, field, sent.get(field))
    row.updated_by_user_id, row.updated_at = user.id, await db.scalar(select(func.now()))
    db.add(AuditLog(user_id=user.id, action=AUDIT, entity_type="enquiry", entity_id=str(lead.id), metadata_json={"fields": sorted(changed)}))
    logger.info("lead_qualification_updated", extra={"extra_fields": {"actor_id": str(user.id), "lead_id": str(lead.id), "fields": sorted(changed)}})

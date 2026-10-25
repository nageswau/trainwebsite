"""tel-009 (DEC-SCOPE-093, spec §3): the lead qualification form -- basic answers always, the IT or overseas requirement by the lead's
product group (QD2). The shared answers live on `enquiries` (QD1); the rest in `lead_qualifications`. A PUT replaces only the fields that
apply, so the other group's stored values are kept (AC3).
ccrm-005 (DEC-SCOPE-259, LF1/LF3): the overseas group adds the spec §3 study and academic answers and the English tests -- a list kept in
`lead_english_tests`, replaced whole like any other applicable field. The counselor uses this service on the leads handed to them (LF7).

Functions only; nothing here commits -- the route owns the transaction and has already locked the lead. Logs and the audit row carry
ids and field names, never values."""

import logging

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Country, Enquiry, LeadEnglishTest, LeadQualification, TelProduct, User
from app.services.bdm_appointments import db_now, today_ist
from app.services.lead_pipeline import invalid
from app.services.telecaller_leads import read_only

logger = logging.getLogger("app.leads")

AUDIT = "lead.qualification_update"
COUNTRY_UNKNOWN = "Choose a country from the list"
SHARED = ("qualification", "passing_year", "city", "state")  # QD1: the lead's own columns
TESTS = "english_tests"  # ccrm-005 LF3: rows of `lead_english_tests`
TEST_FIELDS = ("test_type", "status", "overall_score", "test_date", "valid_until", "remarks")
BASIC = (*SHARED, "current_org", "work_experience_years")
IT = ("it_skill_level", "career_objective", "preferred_batch", "budget_range", "preferred_mode")
OVERSEAS = ("study_level", "preferred_course", "intake", "academic_percentage", "english_test_status", "passport_status", "budget_range",
            "preferred_country_id", "study_mode", "preferred_campus", "academic_cgpa", "backlogs", TESTS)
STORED = tuple(dict.fromkeys(f for f in (*BASIC, *IT, *OVERSEAS) if f not in (*SHARED, TESTS)))
APPLIES = {"it": (*BASIC, *IT), "overseas": (*BASIC, *OVERSEAS)}  # any other group (`other`, no product): basic only
NUMBERS = ("academic_percentage", "academic_cgpa")


async def _product(db: AsyncSession, lead: Enquiry) -> TelProduct | None:
    return await db.get(TelProduct, lead.product_id) if lead.product_id else None


async def _row(db: AsyncSession, lead: Enquiry) -> LeadQualification | None:
    stmt = select(LeadQualification).where(LeadQualification.lead_id == lead.id).execution_options(populate_existing=True)
    return await db.scalar(stmt)


async def english_tests(db: AsyncSession, lead: Enquiry) -> list[dict]:
    """The lead's English tests as stored, in order -- also what ccrm-008's conversion copies (LF8)."""
    rows = await db.scalars(select(LeadEnglishTest).where(LeadEnglishTest.lead_id == lead.id).order_by(LeadEnglishTest.position))
    return [{field: getattr(t, field) for field in TEST_FIELDS} for t in rows]


async def read(db: AsyncSession, user: User, lead: Enquiry) -> dict:
    product, row = await _product(db, lead), await _row(db, lead)
    editor = await db.get(User, row.updated_by_user_id) if row else None
    stored = {field: getattr(row, field) if row else None for field in STORED}
    for field in NUMBERS:
        if stored[field] is not None:
            stored[field] = float(stored[field])
    country = await db.get(Country, stored["preferred_country_id"]) if stored["preferred_country_id"] else None
    today = today_ist(await db_now(db))
    tests = [t | {"overall_score": None if t["overall_score"] is None else float(t["overall_score"]),
                  "expired": t["valid_until"] is not None and t["valid_until"] < today} for t in await english_tests(db, lead)]
    return {
        "lead_id": lead.id,
        "product": {"id": product.id, "name": product.name, "group": product.product_group} if product else None,
        "product_group": product.product_group if product else None,
        **{field: getattr(lead, field) for field in SHARED},
        **stored,
        "preferred_country": {"id": country.id, "name": country.name} if country else None,
        TESTS: tests,
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
    sent = sent | ({TESTS: sent.get(TESTS) or []} if TESTS in applies else {})  # a list left out (or null) is empty

    async def current(field: str):
        if field == TESTS:
            return await english_tests(db, lead)
        return getattr(lead, field) if field in SHARED else getattr(row, field, None)

    changed = [f for f in applies if await current(f) != sent.get(f)]
    if not changed:
        return
    country_id = sent.get("preferred_country_id")
    if "preferred_country_id" in changed and country_id and await db.get(Country, country_id) is None:
        raise invalid("preferred_country_id", COUNTRY_UNKNOWN, str(country_id))
    if row is None:
        row = LeadQualification(lead_id=lead.id, updated_by_user_id=user.id)
        db.add(row)
    for field in changed:
        if field == TESTS:
            await db.execute(delete(LeadEnglishTest).where(LeadEnglishTest.lead_id == lead.id))
            db.add_all(LeadEnglishTest(lead_id=lead.id, position=i, **t) for i, t in enumerate(sent[TESTS]))
        else:
            setattr(lead if field in SHARED else row, field, sent.get(field))
    row.updated_by_user_id, row.updated_at = user.id, await db.scalar(select(func.now()))
    db.add(AuditLog(user_id=user.id, action=AUDIT, entity_type="enquiry", entity_id=str(lead.id), metadata_json={"fields": sorted(changed)}))
    logger.info("lead_qualification_updated", extra={"extra_fields": {"actor_id": str(user.id), "lead_id": str(lead.id), "fields": sorted(changed)}})

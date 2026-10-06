"""tel-005 (DEC-SCOPE-087, spec §3): lead intake -- the duplicate match (T12), manual lead creation, "Add enquiry to this lead" and the
website enquiry that attaches to a person who is already a lead. tel-006's CSV import joins here.

A person is their normalised mobile OR their lower-cased email, matched across every lead (closed ones too, R1). Each intake path takes
the person's advisory locks before it matches (R7), so two intakes of one person serialise and the second sees the first. Functions only;
nothing here commits -- the route owns the transaction. Logs and audit rows carry ids, never a name, email or phone."""

import logging
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import label as stage_label
from app.models import AuditLog, Enquiry, LeadEnquiry, TelCampaign, User
from app.notifications.phone import normalise_phone
from app.schemas import EnquiryIn, LeadEnquiryCreate, TelecallerLeadCreate
from app.services import lead_pipeline
from app.services.telecaller_catalogue import locked_active_product

logger = logging.getLogger("app.leads")

DUPLICATE = "Lead already exists."
MATCH_LIMIT = 5  # R2
ENQUIRY_LIMIT = 5
TEAM_LABEL = {"it": "IT", "overseas": "Overseas"}


def identity(phone: str | None, email: str | None) -> tuple[str | None, str | None]:
    """The match keys: the E.164 mobile (None when unparseable) and the trimmed, lower-cased email."""
    return normalise_phone(phone), (email.strip().lower() or None) if email else None


async def lock_identity(db: AsyncSession, phone_key: str | None, email_key: str | None) -> None:
    """R7: transaction-scoped locks on the person's keys, taken in sorted order so two intakes never deadlock."""
    keys = sorted(key for key in (phone_key and f"lead:phone:{phone_key}", email_key and f"lead:email:{email_key}") if key)
    for key in keys:
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})


async def matching_leads(db: AsyncSession, phone_key: str | None, email_key: str | None, limit: int = MATCH_LIMIT) -> list[Enquiry]:
    """Every lead with the mobile or the email (both indexed), newest first."""
    conditions = []
    if phone_key:
        conditions.append(Enquiry.phone_normalized == phone_key)
    if email_key:
        conditions.append(func.lower(Enquiry.email) == email_key)
    if not conditions:
        return []
    stmt = select(Enquiry).where(or_(*conditions)).order_by(Enquiry.created_at.desc(), Enquiry.id.desc()).limit(limit)
    return list((await db.scalars(stmt)).all())


async def panel(db: AsyncSession, user: User, leads: list[Enquiry], phone_key: str | None, email_key: str | None) -> list[dict]:
    """The EVID-019 §18 panel (R2, R3): who has each matching lead and where it stands -- never its phone, email or messages."""
    if not leads:
        return []
    ids = [lead.id for lead in leads]
    _, filters = lead_pipeline.scope(user)
    in_scope = set((await db.scalars(select(Enquiry.id).where(Enquiry.id.in_(ids), *filters))).all())
    people = {lead.telecaller_user_id for lead in leads} | {lead.owner_id for lead in leads}
    names = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(people - {None})))).all())
    later = (await db.scalars(select(LeadEnquiry).where(LeadEnquiry.lead_id.in_(ids)).order_by(LeadEnquiry.created_at.desc()))).all()

    def person(user_id):
        return {"id": user_id, "full_name": names.get(user_id)} if user_id else None

    def enquiries(lead: Enquiry) -> list[dict]:
        rows = [{"subject": e.subject, "source": e.source, "at": e.created_at} for e in later if e.lead_id == lead.id]
        rows.append({"subject": lead.subject, "source": lead.source, "at": lead.created_at})  # the lead's own, first enquiry
        return sorted(rows, key=lambda row: row["at"], reverse=True)[:ENQUIRY_LIMIT]

    return [
        {
            "id": lead.id, "lead_code": lead.lead_code, "name": lead.name, "status": lead.status, "status_label": stage_label(lead.status),
            "telecaller": person(lead.telecaller_user_id), "counselor": person(lead.owner_id),
            "last_contact_at": None,  # R3: tel-010 (calls) / tel-013 (messages) fill this
            "matched_on": [key for key, hit in (("phone", phone_key and lead.phone_normalized == phone_key),
                                                ("email", email_key and (lead.email or "").lower() == email_key)) if hit],
            "enquiries": enquiries(lead), "in_scope": lead.id in in_scope,
        }
        for lead in leads
    ]


async def _campaign(db: AsyncSession, campaign_id: UUID) -> TelCampaign:
    campaign = await db.get(TelCampaign, campaign_id)
    if not campaign or not campaign.active:
        raise HTTPException(422, "Choose an active campaign")
    return campaign


async def create_lead(db: AsyncSession, user: User, payload: TelecallerLeadCreate) -> Enquiry:
    """I2 / R5 / R6: validate the catalogue choices, block a known person (409 with the panel), insert. A telecaller's lead is theirs
    (`assigned` event); a manager's waits unassigned in its team's queue for tel-007's distribution."""
    product = await locked_active_product(db, payload.product_id)
    if product.team and payload.division and payload.division != product.team:
        raise HTTPException(422, f"{product.name} belongs to the {TEAM_LABEL[product.team]} team")
    division = product.team or payload.division
    if division is None:
        raise HTTPException(422, "Choose the division (IT or Overseas) for this product")
    if payload.campaign_id:
        campaign = await _campaign(db, payload.campaign_id)
        if campaign.product_id != product.id:
            raise HTTPException(422, "This campaign is for another product")
        if campaign.source != payload.source:
            raise HTTPException(422, "This campaign belongs to another lead source")

    phone_key, email_key = identity(payload.phone, payload.email)
    await lock_identity(db, phone_key, email_key)
    matches = await matching_leads(db, phone_key, email_key)
    if matches:
        logger.info("lead_duplicate_blocked", extra={"extra_fields": {"actor_id": str(user.id), "lead_ids": [str(m.id) for m in matches]}})
        detail = {"message": DUPLICATE, "code": "duplicate_lead", "matches": await panel(db, user, matches, phone_key, email_key)}
        raise HTTPException(409, jsonable_encoder(detail))  # an exception's detail is serialised as is: ids and dates become text

    fields = payload.model_dump(include={"name", "phone", "email", "whatsapp_number", "city", "state", "qualification", "passing_year",
                                         "institution", "product_id", "campaign_id", "source", "priority"})
    assigned = user.role == "telecaller"
    lead = Enquiry(**fields, division=division, subject=payload.subject or product.name, message=payload.message or "",
                   telecaller_user_id=user.id if assigned else None)
    db.add(lead)
    await db.flush()
    if assigned:
        await lead_pipeline.apply_event(db, lead, "assigned", user)
    db.add(AuditLog(user_id=user.id, action="lead.create", entity_type="enquiry", entity_id=str(lead.id),
                    metadata_json={"source": lead.source, "product_id": str(product.id), "assigned": assigned}))
    logger.info("lead_created", extra={"extra_fields": {"actor_id": str(user.id), "lead_id": str(lead.id), "assigned": assigned}})
    return lead


async def add_enquiry(db: AsyncSession, user: User, lead_id: UUID, payload: LeadEnquiryCreate) -> dict:
    """I5: append an enquiry to any lead -- it doesn't move the stage (a closed lead stays closed until a manager reopens it, T13)."""
    lead = await db.get(Enquiry, lead_id)
    if lead is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    if payload.campaign_id:
        await _campaign(db, payload.campaign_id)
    row = LeadEnquiry(lead_id=lead.id, subject=payload.subject, message=payload.message or "", source=payload.source,
                      campaign_id=payload.campaign_id, created_by_user_id=user.id)
    db.add(row)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="lead.enquiry_add", entity_type="enquiry", entity_id=str(lead.id),
                    metadata_json={"lead_enquiry_id": str(row.id), "source": row.source}))
    logger.info("lead_enquiry_added", extra={"extra_fields": {"actor_id": str(user.id), "lead_id": str(lead.id)}})
    return {"id": row.id, "lead_id": lead.id, "lead_code": lead.lead_code, "subject": row.subject, "source": row.source, "created_at": row.created_at}


async def website_intake(db: AsyncSession, payload: EnquiryIn) -> tuple[Enquiry, bool]:
    """T12 / R4 / R9: a known person's enquiry attaches to their newest lead; anyone else is a new lead exactly as before.
    Returns the lead and whether the enquiry attached."""
    phone_key, email_key = identity(payload.phone, payload.email)
    await lock_identity(db, phone_key, email_key)
    known = await matching_leads(db, phone_key, email_key, limit=1)
    if known:
        db.add(LeadEnquiry(lead_id=known[0].id, subject=payload.subject, message=payload.message, source=payload.source,
                           metadata_json=payload.metadata))
        logger.info("website_enquiry_attached", extra={"extra_fields": {"lead_id": str(known[0].id)}})
        return known[0], True
    lead = Enquiry(division=payload.division, name=payload.name, email=payload.email, phone=payload.phone, subject=payload.subject,
                   message=payload.message, source=payload.source, metadata_json=payload.metadata, crm_sync_status="pending")
    db.add(lead)
    return lead, False

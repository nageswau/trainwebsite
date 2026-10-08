"""rec-004 (DEC-SCOPE-125, spec §1-§3): a company's contacts -- the primary rule, the role check and the output.

Functions only; nothing here commits -- the route owns the transaction. Scope and write rights are the company's (rec-003's
`load_scoped` and `can_edit`, C1), so a contact of a company outside the caller's scope is the same 404 as a missing one. Every write
first locks the company row, which serialises primary changes; the partial unique index is the backstop."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, CompanyContact, RecContactRole, User
from app.notifications.phone import wa_number
from app.schemas import REC_CONTACT_FIELDS, REC_CONTACT_MAX, RecContactIn
from app.services import recruiter_calls, recruiter_messages
from app.services import recruiter_companies as companies
from app.services.recruiter_follow_ups import contact_next

CONTACT_NOT_FOUND = "Contact not found"


async def contacts_of(db: AsyncSession, company_id: UUID) -> list[CompanyContact]:
    """Insertion order; fresh from the database (another request may have changed the primary since this session loaded them)."""
    stmt = select(CompanyContact).where(CompanyContact.company_id == company_id).order_by(CompanyContact.position)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


async def load_for_write(db: AsyncSession, user: User, contact_id: UUID, route: str) -> tuple[Company, CompanyContact]:
    """The contact's company, locked and checked for scope (404) and write rights (403, then 409 when archived)."""
    company_id = await db.scalar(select(CompanyContact.company_id).where(CompanyContact.id == contact_id))
    if company_id is None:
        raise HTTPException(404, CONTACT_NOT_FOUND)
    try:
        company = await companies.load_scoped(db, user, company_id, lock=True)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, CONTACT_NOT_FOUND) from None
        raise
    companies.require(user, company, "can_edit", route)
    contact = await db.scalar(select(CompanyContact).where(CompanyContact.id == contact_id).execution_options(populate_existing=True))
    return company, contact


async def check_role(db: AsyncSession, role_id: UUID | None, stored: UUID | None = None) -> None:
    """A role must be active when it is set or changed (FOR SHARE: a concurrent deactivation waits); keeping a since-deactivated one is
    allowed (rec-003's catalogue rule)."""
    if role_id is None or role_id == stored:
        return
    role = await db.scalar(select(RecContactRole).where(RecContactRole.id == role_id).with_for_update(read=True))
    if role is None or not role.active:
        raise HTTPException(422, "Choose an active contact role")


async def set_primary(db: AsyncSession, contacts: list[CompanyContact], target: CompanyContact) -> None:
    """Clear first and flush, so the partial unique index never sees two primaries in one statement batch (bdm-002)."""
    for contact in contacts:
        if contact is not target and contact.is_primary:
            contact.is_primary = False
    await db.flush()
    target.is_primary = True
    await db.flush()


async def add(db: AsyncSession, user: User, company: Company, payload: RecContactIn) -> CompanyContact:
    """C2/C4: a new contact is primary when asked, or when the company has no primary yet. The caller holds the company lock."""
    contacts = await contacts_of(db, company.id)
    if len(contacts) >= REC_CONTACT_MAX:
        raise HTTPException(409, f"A company can have at most {REC_CONTACT_MAX} contacts")
    await check_role(db, payload.role_id)
    contact = CompanyContact(company_id=company.id, created_by_user_id=user.id, **payload.model_dump(include=set(REC_CONTACT_FIELDS)))
    db.add(contact)
    await db.flush()
    if payload.is_primary or not any(c.is_primary for c in contacts):
        await set_primary(db, contacts, contact)
    fields = sorted(k for k in REC_CONTACT_FIELDS if getattr(contact, k) is not None)
    companies.audit(db, user, "contact_create", company.id, {"contact_id": str(contact.id), "fields": fields})
    return contact


async def update(db: AsyncSession, user: User, company: Company, contact: CompanyContact, changes: dict) -> list[str]:
    """PATCH semantics (spec §1 C2): field changes, then active, then primary. Returns the changed field names (empty = nothing to do)."""
    primary = changes.pop("is_primary", None)
    active = changes.pop("active", None)
    if primary is False and contact.is_primary:
        raise HTTPException(422, "Choose another primary contact instead")
    await check_role(db, changes.get("role_id"), contact.role_id)
    changed = sorted(k for k, v in changes.items() if getattr(contact, k) != v)
    for key in changed:
        setattr(contact, key, changes[key])
    contacts = await contacts_of(db, company.id)
    others_active = any(c.active for c in contacts if c.id != contact.id)
    if active is False and contact.active:
        if contact.is_primary and others_active:
            raise HTTPException(409, "Make another contact primary first")
        contact.is_primary = False  # the last active contact: it stops being primary
        contact.active = False
        changed.append("active")
    elif active is True and not contact.active:
        contact.active = True
        changed.append("active")
        if not any(c.is_primary for c in contacts if c.id != contact.id):
            primary = True
    if primary and not contact.is_primary:
        if not contact.active:
            raise HTTPException(409, "Reactivate this contact first")
        await set_primary(db, contacts, contact)
        changed.append("is_primary")
    if changed:
        await db.flush()
        companies.audit(db, user, "contact_update", company.id, {"contact_id": str(contact.id), "fields": sorted(changed)})
    return sorted(changed)


async def list_out(db: AsyncSession, user: User, company: Company) -> dict:
    """Primary first, then active, then inactive, each in insertion order. One query for the roles (no N+1)."""
    contacts = await contacts_of(db, company.id)
    role_ids = {c.role_id for c in contacts} - {None}
    roles = {r.id: r for r in (await db.scalars(select(RecContactRole).where(RecContactRole.id.in_(role_ids)))).all()} if role_ids else {}
    contacts.sort(key=lambda c: (not c.is_primary, not c.active, c.position))
    next_due = await contact_next(db, company.id)
    last_call = await recruiter_calls.contact_last(db, company.id)
    last_message = await recruiter_messages.contact_last(db, company.id)
    items = [
        {
            **{
                k: getattr(c, k)
                for k in ("id", "name", "designation", "department", "mobile", "email", "linkedin_url", "preferred_channel", "notes", "is_primary", "active", "created_at", "updated_at")
            },
            "role": companies.ref(roles.get(c.role_id)),
            # C6: the latest call (rec-025 CA7) or message (rec-026 MS10); rec-028 adds meetings
            "last_contacted_at": max((t for t in (last_call.get(c.id), last_message.get(c.id)) if t), default=None),
            "next_follow_up_at": next_due.get(c.id),  # rec-024 FU9
            "whatsapp_to": wa_number(c.mobile),  # rec-026 MS6
        }
        for c in contacts
    ]
    return {"items": items, "can_edit": companies.permissions(user, company)["can_edit"]}

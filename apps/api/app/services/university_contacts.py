"""upc-006 (DEC-SCOPE-121, spec §3): university contacts -- who sees which contacts, the primary rule, and output.

Functions only; nothing here commits -- the route owns the transaction. Access reuses the University Master's (upc-003):
- the partnership roles and super_admin (CONTACT_ROLES) read every contact in full and write within the master's edit scope;
- overseas_admin reads the `shareable` slice only, without notes (CT5, CT14); counselors get the same slice in upc-030.
Contacts are PII: the audit and the logs carry ids and field names only.
"""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, UniversityContact, UniversityContactRole, User
from app.services.partnership_universities import CONTACT_ROLES

logger = logging.getLogger("app.partnership")

NOT_FOUND = "Contact not found"
FIELDS = ("name", "designation", "department", "role_code", "email", "phone", "whatsapp", "linkedin", "preferred_channel", "relationship_strength", "notes", "is_primary", "shareable")


def full_view(user: User) -> bool:
    return user.role in CONTACT_ROLES


def visible(user: User, university_id: UUID) -> list:
    filters = [UniversityContact.university_id == university_id]
    if not full_view(user):
        filters.append(UniversityContact.shareable.is_(True))
    return filters


ORDER = (UniversityContact.is_primary.desc(), func.lower(UniversityContact.name), UniversityContact.id)


async def university_of(db: AsyncSession, contact_id: UUID) -> UUID:
    university_id = await db.scalar(select(UniversityContact.university_id).where(UniversityContact.id == contact_id))
    if university_id is None:
        raise HTTPException(404, NOT_FOUND)
    return university_id


async def load(db: AsyncSession, contact_id: UUID) -> UniversityContact:
    """Under the university's lock (taken by the caller), so a delete in between is a 404 rather than a stale row."""
    stmt = select(UniversityContact).where(UniversityContact.id == contact_id).with_for_update().execution_options(populate_existing=True)
    contact = await db.scalar(stmt)
    if contact is None:
        raise HTTPException(404, NOT_FOUND)
    return contact


async def check_role(db: AsyncSession, code: str | None) -> None:
    if code is not None and await db.get(UniversityContactRole, code) is None:
        raise HTTPException(422, "Choose a contact role from the list")


async def check_email_free(db: AsyncSession, university_id: UUID, email: str | None, contact_id: UUID | None = None) -> None:
    """CT8: one email once per university (the university lock serialises this check; uq_university_contacts_email is the backstop)."""
    if email is None:
        return
    stmt = select(UniversityContact.id).where(UniversityContact.university_id == university_id, func.lower(UniversityContact.email) == email.lower())
    if contact_id is not None:
        stmt = stmt.where(UniversityContact.id != contact_id)
    if await db.scalar(stmt.limit(1)):
        raise HTTPException(409, "Another contact at this university already has this email")


async def count(db: AsyncSession, university_id: UUID) -> int:
    return await db.scalar(select(func.count()).select_from(UniversityContact).where(UniversityContact.university_id == university_id)) or 0


async def clear_primary(db: AsyncSession, university_id: UUID) -> None:
    """Before setting a new primary, flushed first, so the partial unique index never sees two primaries in one statement batch."""
    for other in (await db.scalars(select(UniversityContact).where(UniversityContact.university_id == university_id, UniversityContact.is_primary))).all():
        other.is_primary = False
    await db.flush()


def contact_out(user: User, contact: UniversityContact, role: UniversityContactRole | None) -> dict:
    return {
        **{k: getattr(contact, k) for k in ("id", "university_id", *FIELDS, "created_at", "updated_at") if k != "role_code"},
        "role": {"code": role.code, "label": role.label} if role else None,
        "notes": contact.notes if full_view(user) else None,
    }


async def detail_out(db: AsyncSession, user: User, contact: UniversityContact) -> dict:
    await db.refresh(contact)  # server defaults (timestamps) are expired after a flush
    role = await db.get(UniversityContactRole, contact.role_code) if contact.role_code else None
    return contact_out(user, contact, role)


def audit(db: AsyncSession, user: User, action: str, contact_id: UUID, university_id: UUID, fields: list[str] | None = None) -> None:
    metadata = {"university_id": str(university_id), **({"fields": fields} if fields is not None else {})}
    db.add(AuditLog(user_id=user.id, action=f"university_contact.{action}", entity_type="university_contact", entity_id=str(contact_id), metadata_json=metadata))


def log(event: str, user: User, contact_id: UUID, university_id: UUID, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "contact_id": str(contact_id), "university_id": str(university_id), **extra}})

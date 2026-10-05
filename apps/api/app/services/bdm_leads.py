"""bdm-017 (DEC-SCOPE-070, spec §4): BDM-entered student leads -- `enquiries` rows attributed to an organization and a BDM.

Functions only; nothing here commits -- the route owns the transaction. Organizations resolve through
`bdm_organizations.load_scoped`, so a lead list of an organization the caller can't read is the same 404 as a missing one. Logs and
audit rows carry ids, route, status and counts -- never the student's name, email, phone, interest or note.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AuditLog, BdmOrganization, Enquiry, User
from app.services.bdm_activities import day_range, india_date

logger = logging.getLogger("app.bdm")

DAILY_CAP = 200  # an abuse bound far above real use (bdm-009 V10's figure)
MAX_DUPLICATE_MATCHES = 10
NOT_ASSIGNED = "Only the organization's assigned BDM can add leads"
ARCHIVED = "This organization is archived"
DUPLICATE = "This student is already a lead of this organization"
NEWEST = (Enquiry.created_at.desc(), Enquiry.id.desc())


def not_assigned(user: User, org_id: UUID) -> HTTPException:
    """The 403 for a BDM who isn't the organization's assignee, visible in the logs with ids only (bdm-009's
    `bdm_activity_write_refused`). Returns the exception for the caller to raise."""
    logger.warning("bdm_lead_write_refused", extra={"extra_fields": {
        "actor_id": str(user.id), "route": "lead_create", "status": 403, "organization_id": str(org_id)}})
    return HTTPException(403, NOT_ASSIGNED)


async def check_daily_cap(db: AsyncSession, bdm_user_id: UUID, now: datetime) -> None:
    """A soft bound on the BDM's IST day: two concurrent saves on different organizations may pass it by one or two."""
    start, end = day_range(india_date(now))
    count = await db.scalar(select(func.count()).select_from(Enquiry).where(
        Enquiry.bdm_user_id == bdm_user_id, Enquiry.created_at >= start, Enquiry.created_at < end))
    if (count or 0) >= DAILY_CAP:
        raise HTTPException(409, f"You've added {DAILY_CAP} leads today")


async def check_duplicates(db: AsyncSession, org_id: UUID, email: str) -> None:
    """L8: the same email (any case) already a lead of this organization -> 409 in bdm-002's `possible_duplicate` shape. Runs under the
    organization row lock, so two concurrent adds of one student can't both pass it. Other organizations are never compared."""
    conditions = [Enquiry.bdm_organization_id == org_id, func.lower(Enquiry.email) == email]
    total = await db.scalar(select(func.count()).select_from(Enquiry).where(*conditions))
    if not total:
        return
    rows = (await db.scalars(select(Enquiry).where(*conditions).order_by(Enquiry.created_at, Enquiry.id).limit(MAX_DUPLICATE_MATCHES))).all()
    matches = [{"id": str(e.id), "name": e.name, "created_at": e.created_at.isoformat()} for e in rows]
    raise HTTPException(409, {"message": DUPLICATE, "code": "possible_duplicate", "matches": matches, "total": total})


def _rows(filters: list) -> Select[Enquiry, str]:
    return select(Enquiry, User.full_name).join(User, User.id == Enquiry.bdm_user_id).where(*filters)


def _out(lead: Enquiry, bdm_name: str) -> dict:
    return {
        "id": lead.id, "name": lead.name, "email": lead.email, "phone": lead.phone, "interest": lead.subject, "status": lead.status,
        "bdm": {"id": lead.bdm_user_id, "full_name": bdm_name}, "converted": lead.converted_user_id is not None, "created_at": lead.created_at,
    }


async def page(db: AsyncSession, org_id: UUID, limit: int, offset: int) -> dict:
    """AC4: `total` is the exact count of the organization's leads (`ix_enquiries_bdm_org_created`)."""
    filters = [Enquiry.bdm_organization_id == org_id]
    total = await db.scalar(select(func.count()).select_from(Enquiry).where(*filters))
    result = (await db.execute(_rows(filters).order_by(*NEWEST).limit(limit).offset(offset))).all()
    return {"items": [_out(lead, name) for lead, name in result], "total": total or 0, "limit": limit, "offset": offset}


async def one(db: AsyncSession, lead_id: UUID) -> dict:
    lead, name = (await db.execute(_rows([Enquiry.id == lead_id]).execution_options(populate_existing=True))).one()
    return _out(lead, name)


def audit(db: AsyncSession, user: User, lead: Enquiry) -> None:
    """Same transaction as the insert (fail closed); ids only."""
    db.add(AuditLog(user_id=user.id, action="bdm_lead.created", entity_type="enquiry", entity_id=str(lead.id),
                    metadata_json={"bdm_organization_id": str(lead.bdm_organization_id)}))


def log(event: str, user: User, lead_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "lead_id": str(lead_id), **extra}})


# --- admin side (spec §5): the lead list's attribution and the explicit conversion link (L1, L2, L9) -------------------------------

LEAD_NOT_FOUND = "Lead not found"
WRONG_DIVISION = "Wrong division"  # update_lead's wording
ALREADY_LINKED = "Unlink the current student first"
NOT_LINKED = "This lead is not linked to a student"
STUDENT_TAKEN = "This student is already linked to another lead"
INVALID_STUDENT = "Enter the email of an active student account in this lead's division"
Attributor = aliased(User)
Converted = aliased(User)


def admin_rows():
    """Every lead with its organization, attributing BDM and linked student -- outer joins, so website rows come back with NULLs."""
    return (
        select(Enquiry, BdmOrganization.code, BdmOrganization.name, Attributor.full_name, Converted.full_name, Converted.email)
        .outerjoin(BdmOrganization, BdmOrganization.id == Enquiry.bdm_organization_id)
        .outerjoin(Attributor, Attributor.id == Enquiry.bdm_user_id)
        .outerjoin(Converted, Converted.id == Enquiry.converted_user_id)
    )


def admin_out(row) -> dict:
    """ADM-002's row (keys unchanged) plus the three bdm-017 objects, each null when absent."""
    x, org_code, org_name, bdm_name, student_name, student_email = row
    return {
        "id": x.id, "name": x.name, "email": x.email, "phone": x.phone, "division": x.division, "subject": x.subject, "status": x.status,
        "source": x.source, "crm_sync_status": x.crm_sync_status,
        "organization": {"id": x.bdm_organization_id, "code": org_code, "name": org_name} if x.bdm_organization_id else None,
        "bdm": {"id": x.bdm_user_id, "full_name": bdm_name} if x.bdm_user_id else None,
        "converted_user": {"id": x.converted_user_id, "full_name": student_name, "email": student_email} if x.converted_user_id else None,
    }


async def admin_one(db: AsyncSession, lead_id: UUID) -> dict:
    return admin_out((await db.execute(admin_rows().where(Enquiry.id == lead_id).execution_options(populate_existing=True))).one())


async def locked_for_admin(db: AsyncSession, user: User, lead_id: UUID) -> Enquiry:
    """The lead row locked FOR UPDATE: a second conversion of the same lead waits for this one. Division as update_lead (403)."""
    lead = await db.scalar(select(Enquiry).where(Enquiry.id == lead_id).with_for_update().execution_options(populate_existing=True))
    if lead is None:
        raise HTTPException(404, LEAD_NOT_FOUND)
    if user.role != "super_admin" and lead.division != user.division:
        raise HTTPException(403, WRONG_DIVISION)
    return lead


async def locked_student(db: AsyncSession, lead: Enquiry, email: str) -> User:
    """L2: an active `<division>_student` of the lead's division, FOR SHARE so a deactivation in the same instant waits for this commit.
    One message for every invalid target, so the route can't be used to probe accounts."""
    student = await db.scalar(select(User).where(func.lower(User.email) == email).with_for_update(read=True))
    if student is None or not student.active or student.role != f"{lead.division}_student" or student.division != lead.division:
        raise HTTPException(422, INVALID_STUDENT)
    return student


async def check_student_free(db: AsyncSession, student: User) -> None:
    """L9 read check; `uq_enquiries_converted_user` is the backstop when two admins link one student at the same instant."""
    if await db.scalar(select(Enquiry.id).where(Enquiry.converted_user_id == student.id).limit(1)):
        raise HTTPException(409, STUDENT_TAKEN)


def audit_conversion(db: AsyncSession, user: User, lead: Enquiry, action: str, student_id: UUID) -> None:
    db.add(AuditLog(user_id=user.id, action=action, entity_type="enquiry", entity_id=str(lead.id),
                    metadata_json={"converted_user_id": str(student_id)}))

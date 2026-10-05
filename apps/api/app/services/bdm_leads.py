"""bdm-017 (DEC-SCOPE-070, spec §4): BDM-entered student leads -- `enquiries` rows attributed to an organization and a BDM.

Functions only; nothing here commits -- the route owns the transaction. Organizations resolve through
`bdm_organizations.load_scoped`, so a lead list of an organization the caller can't read is the same 404 as a missing one. Logs and
audit rows carry ids, route, status and counts -- never the student's name, email, phone, interest or note.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Enquiry, User
from app.services.bdm_activities import day_range, india_date

logger = logging.getLogger("app.bdm")

DAILY_CAP = 200  # an abuse bound far above real use (bdm-009 V10's figure)
MAX_DUPLICATE_MATCHES = 10
NOT_ASSIGNED = "Only the organization's assigned BDM can add leads"
ARCHIVED = "This organization is archived"
DUPLICATE = "This student is already a lead of this organization"
NEWEST = (Enquiry.created_at.desc(), Enquiry.id.desc())


def default_message(org_name: str) -> str:
    """L5: `enquiries.message` is required; a lead entered without a note says where it came from."""
    return f"Lead entered by BDM at {org_name}"


def refused(user: User, route: str, status: int, detail: str, **ids) -> HTTPException:
    """Assignee refusals are visible in the logs (ids, route, status), as bdm-009's `bdm_activity_write_refused`."""
    logger.warning("bdm_lead_write_refused", extra={"extra_fields": {
        "actor_id": str(user.id), "route": route, "status": status, **{k: str(v) for k, v in ids.items()}}})
    return HTTPException(status, detail)


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


def _rows(filters: list):
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

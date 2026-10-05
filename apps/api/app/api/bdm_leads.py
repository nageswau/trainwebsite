"""bdm-017 (DEC-SCOPE-070, spec §4): an organization's student leads.

Reads are open to everyone who can read the organization (`load_scoped`; L6 mirrors bdm-009 V5). A lead is added by the organization's
assigned BDM in one transaction -- role (403), scope + organization lock (404), assignee (403), archived (422), daily cap (409),
duplicate (409), insert, audit, one commit -- and only then queued for the CRM, exactly as the public enquiry form (L3)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Enquiry, User
from app.schemas import BdmLeadCreate, BdmLeadOut, BdmLeadPage
from app.services import bdm_leads as svc
from app.services import bdm_organizations as org_svc
from app.services.bdm import BDM_DIVISION, bdm_context
from app.services.bdm_appointments import db_now
from app.worker import sync_enquiry_to_crm_task

router = APIRouter(prefix="/bdm/organizations", tags=["bdm-leads"])


@router.get("/{org_id}/leads", response_model=BdmLeadPage)
async def organization_leads(org_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    org = await org_svc.load_scoped(db, user, org_id)
    return await svc.page(db, org.id, limit, offset)


@router.post("/{org_id}/leads", status_code=201, response_model=BdmLeadOut)
async def add_lead(org_id: UUID, payload: BdmLeadCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await bdm_context(db, user)
    org = await org_svc.load_scoped(db, user, org_id, lock=True)  # out of type -> 404; serializes adds, archive and reassign
    if org.assigned_bdm_user_id != user.id:
        raise svc.refused(user, "lead_create", 403, svc.NOT_ASSIGNED, organization_id=org.id)
    if org.archived_at is not None:
        raise HTTPException(422, svc.ARCHIVED)
    await svc.check_daily_cap(db, user.id, await db_now(db))
    if not payload.acknowledge_duplicate:
        await svc.check_duplicates(db, org.id, payload.email)
    lead = Enquiry(
        division=BDM_DIVISION[org.bdm_type], name=payload.name, email=payload.email, phone=payload.phone, subject=payload.interest,
        message=payload.note or svc.default_message(org.name), source="bdm", status="new", crm_sync_status="pending", metadata_json={},
        bdm_organization_id=org.id, bdm_user_id=user.id,
    )
    db.add(lead)
    await db.flush()
    svc.audit(db, user, lead)
    await db.commit()
    svc.log("bdm_lead_created", user, lead.id, organization_id=str(org.id), duplicate_acknowledged=payload.acknowledge_duplicate)
    try:
        sync_enquiry_to_crm_task.delay(str(lead.id))
    except Exception:  # the lead is committed; a 500 here would only invite a duplicate retry. It stays `pending` for the CRM.
        svc.logger.warning("bdm_lead_crm_enqueue_failed", extra={"extra_fields": {"lead_id": str(lead.id)}}, exc_info=True)
    return await svc.one(db, lead.id)

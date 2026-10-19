"""csc-004 (DEC-SCOPE-229; W1, W2, W4, W5) -- an overseas counselor records a walk-in as a lead. tel-005's intake (catalogue checks, the
duplicate panel, "Add enquiry to this lead") under the counselor's own prefix: the lead is the counselor's (`owner_id`), in their division,
distributed to a telecaller like a manager's lead (tel-007) and read-only for that telecaller (D1/T19). The counselor then works it from
My Leads (tel-018). API_CONTRACT.md §12EO; RBAC_MATRIX.md §2.151."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import LeadEnquiryCreate, TelecallerLeadCreate
from app.services import lead_handover, lead_intake
from app.worker import sync_enquiry_to_crm_task

router = APIRouter(prefix="/counselor/walk-in-leads", tags=["counselor-walk-in-leads"])
OVERSEAS_COUNSELOR_ONLY = "Only an overseas counselor can record walk-in leads"


def _require_overseas_counselor(user: User) -> None:
    if user.role != "counselor" or user.division != "overseas":  # W1: an IT counselor works handed-over leads only (tel-017)
        raise HTTPException(403, OVERSEAS_COUNSELOR_ONLY)


@router.get("/duplicate-check")
async def duplicate_check(phone: str | None = None, email: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """tel-005 R2: the §18 panel for a mobile and/or email before the lead is created; `in_scope` marks the counselor's own leads."""
    _require_overseas_counselor(user)
    return {"matches": await lead_intake.duplicate_matches(db, user, phone, email)}


@router.post("", status_code=201)
async def create_walk_in_lead(payload: TelecallerLeadCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A known person is 409 with the duplicate panel (tel-005 I2). Queued for the CRM only after the commit (tel-005 R10)."""
    _require_overseas_counselor(user)
    lead = await lead_intake.create_lead(db, user, payload)
    await db.commit()
    sync_enquiry_to_crm_task.delay(str(lead.id))
    return {**await lead_handover.detail(db, lead.id, lead_handover.counselor_scope(user)), "in_scope": True}


@router.post("/{lead_id}/enquiries", status_code=201)
async def add_enquiry(lead_id: UUID, payload: LeadEnquiryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """tel-005 I5 from the duplicate panel: append-only to any lead, no read access granted (C11)."""
    _require_overseas_counselor(user)
    out = await lead_intake.add_enquiry(db, user, lead_id, payload)
    await db.commit()
    return out

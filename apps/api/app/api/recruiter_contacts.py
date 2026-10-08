"""rec-004 (DEC-SCOPE-125, spec §3): a company's contacts. Scope and write rights are the company's (C1): out of scope = 404, the wrong
role = 403, an archived company = 409. Every write is one transaction -- company lock, change, audit, one commit here -- and returns the
company's whole list, because a primary change touches two rows."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import RecContactIn, RecContactList, RecContactUpdate
from app.services import recruiter_companies as companies
from app.services import recruiter_contacts as svc

router = APIRouter(prefix="/recruiter", tags=["recruiter-contacts"])


@router.get("/companies/{company_id}/contacts", response_model=RecContactList)
async def list_contacts(company_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    company = await companies.load_scoped(db, user, company_id)
    return await svc.list_out(db, user, company)


@router.post("/companies/{company_id}/contacts", status_code=201, response_model=RecContactList)
async def add_contact(company_id: UUID, payload: RecContactIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    company = await companies.load_scoped(db, user, company_id, lock=True)
    companies.require(user, company, "can_edit", "contact_create")
    contact = await svc.add(db, user, company, payload)
    await db.commit()
    companies.log("recruiter_contact_created", user, company.id, contact_id=str(contact.id))
    return await svc.list_out(db, user, company)


@router.patch("/contacts/{contact_id}", response_model=RecContactList)
async def update_contact(contact_id: UUID, payload: RecContactUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Only the fields sent; values equal to the stored ones are not changes (no audit). `is_primary` and `active` follow C2."""
    company, contact = await svc.load_for_write(db, user, contact_id, "contact_update")
    changed = await svc.update(db, user, company, contact, payload.model_dump(exclude_unset=True))
    await db.commit()
    if changed:
        companies.log("recruiter_contact_updated", user, company.id, contact_id=str(contact.id), fields=changed)
    return await svc.list_out(db, user, company)

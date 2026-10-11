"""rec-029 (DEC-SCOPE-177, spec §3): campus recruitment drives -- the list, the college picker, create, a drive with its funnel, edit, the
funnel alone and the candidates added through the drive.

Scope is the company's (rec-003 `caller_scope`; other roles 403, out of scope 404). Every write is one transaction -- scope, the company
lock, `can_edit` (DR8), the drive lock and state, validation, change, audit, one commit here, log. Candidates are added through rec-017's
`POST /recruiter/requirements/{id}/candidates` with `drive_id` (DR9)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import RECRUITMENT_DRIVE_STATUSES, User
from app.schemas import RecDriveCreate, RecDriveUpdate
from app.services import recruiter_companies as companies
from app.services import recruitment_drives as svc

router = APIRouter(prefix="/recruiter", tags=["recruiter-drives"])


@router.get("/drives")
async def list_drives(
    q: str | None = SEARCH,
    status: Literal[RECRUITMENT_DRIVE_STATUSES] | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DR8: a recruiter's own companies, a manager's team and the unassigned queue (read only), the assigned BDM's companies (read only),
    super_admin all."""
    return await svc.list_page(db, user, like_pattern(q), status, limit, offset)


@router.get("/drives/college-options")
async def college_options(q: str | None = SEARCH, limit: int = LIMIT, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """DR2's picker, for the people who can create companies (recruiters, managers, super_admin)."""
    companies.require_creator(user)
    return await svc.college_options(db, like_pattern(q), limit)


@router.post("/drives", status_code=201)
async def create_drive(payload: RecDriveCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry creates a second drive)."""
    company = await companies.load_scoped(db, user, payload.company_id, lock=True)
    companies.require(user, company, "can_edit", "drive_create")
    drive = await svc.create(db, user, company, payload)
    await db.commit()
    svc.log("recruitment_drive_created", user, drive.id, company_id=str(company.id))
    return await svc.detail(db, user, drive.id)


@router.get("/drives/{drive_id}")
async def get_drive(drive_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.load(db, user, drive_id)
    return await svc.detail(db, user, drive_id)


@router.patch("/drives/{drive_id}")
async def update_drive(drive_id: UUID, payload: RecDriveUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """DR3: a cancelled drive takes no edits (409). Values equal to the stored ones are not changes (no audit)."""
    company, drive = await svc.load(db, user, drive_id, lock=True)
    companies.require(user, company, "can_edit", "drive_update")
    changed = await svc.update(db, user, drive, payload)
    await db.commit()
    if changed:
        svc.log("recruitment_drive_updated", user, drive_id, fields=changed)
    return await svc.detail(db, user, drive_id)


@router.get("/drives/{drive_id}/funnel")
async def drive_funnel(drive_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.load(db, user, drive_id)
    return await svc.funnel(db, drive_id)


@router.get("/drives/{drive_id}/candidates")
async def drive_candidates(drive_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.load(db, user, drive_id)
    return await svc.candidates_page(db, drive_id, limit, offset)

"""upc-006 (DEC-SCOPE-121, spec §3): university contacts -- the role catalogue, list, add, edit and delete.

Every write is one transaction: the university row lock (FOR UPDATE, which serialises the primary, limit and email checks per
university), the scope check (`can_edit_contacts`), the change, the audit row, one commit here, then a structured log (ids only)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import University, UniversityContact, UniversityContactRole, User
from app.schemas import (
    UNIVERSITY_MAX_CONTACTS,
    UniversityContactEnvelope,
    UniversityContactIn,
    UniversityContactPage,
    UniversityContactRolePage,
    UniversityContactUpdate,
)
from app.services import partnership_universities as unis
from app.services import university_contacts as svc

router = APIRouter(prefix="/partnership", tags=["partnership-universities"])


async def _locked_university(db: AsyncSession, user: User, university_id: UUID, route: str) -> University:
    """The caller has passed require_reader (so a role without access is a 403 before any id is looked up)."""
    uni = await unis.load(db, university_id, lock=True)
    unis.require(user, uni, await unis.team_of(db, user), "can_edit_contacts", route)
    return uni


@router.get("/contact-roles", response_model=UniversityContactRolePage)
async def contact_roles(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await unis.require_reader(db, user)
    rows = (await db.scalars(select(UniversityContactRole).order_by(UniversityContactRole.position))).all()
    return {"items": [{"code": r.code, "label": r.label} for r in rows]}


@router.get("/universities/{university_id}/contacts", response_model=UniversityContactPage)
async def list_contacts(
    university_id: UUID,
    limit: int = Query(UNIVERSITY_MAX_CONTACTS, ge=1, le=UNIVERSITY_MAX_CONTACTS),
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Primary first, then by name. Partnership roles see every contact; overseas_admin the shareable ones without notes (CT5)."""
    await unis.require_reader(db, user)
    await unis.load(db, university_id)
    filters = svc.visible(user, university_id)
    total = await db.scalar(select(func.count()).select_from(UniversityContact).where(*filters))
    stmt = (
        select(UniversityContact, UniversityContactRole)
        .outerjoin(UniversityContactRole, UniversityContactRole.code == UniversityContact.role_code)
        .where(*filters)
        .order_by(*svc.ORDER)
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    return {"items": [svc.contact_out(user, c, role) for c, role in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("/universities/{university_id}/contacts", status_code=201, response_model=UniversityContactEnvelope)
async def add_contact(university_id: UUID, payload: UniversityContactIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1/CT6: the first contact becomes primary; `is_primary` on a later one moves the primary to it."""
    await unis.require_reader(db, user)
    uni = await _locked_university(db, user, university_id, "contact_create")
    existing = await svc.count(db, uni.id)
    if existing >= UNIVERSITY_MAX_CONTACTS:
        raise HTTPException(409, f"A university can have at most {UNIVERSITY_MAX_CONTACTS} contacts")
    await svc.check_role(db, payload.role_code)
    await svc.check_email_free(db, uni.id, payload.email)
    values = payload.model_dump()
    values["is_primary"] = values["is_primary"] or existing == 0
    if values["is_primary"] and existing:
        await svc.clear_primary(db, uni.id)
    contact = UniversityContact(university_id=uni.id, **values)
    db.add(contact)
    await db.flush()
    sent = sorted(k for k, v in values.items() if v not in (None, "", False))
    svc.audit(db, user, "create", contact.id, uni.id, sent)
    await db.commit()
    svc.log("university_contact_created", user, contact.id, uni.id)
    return {"contact": await svc.detail_out(db, user, contact)}


@router.patch("/contacts/{contact_id}", response_model=UniversityContactEnvelope)
async def update_contact(contact_id: UUID, payload: UniversityContactUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Only the fields sent; a value equal to the stored one is not a change (no audit)."""
    await unis.require_reader(db, user)
    uni = await _locked_university(db, user, await svc.university_of(db, contact_id), "contact_update")
    contact = await svc.load(db, contact_id)
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(k for k, v in changes.items() if getattr(contact, k) != v)
    if "is_primary" in changed and not changes["is_primary"]:
        raise HTTPException(422, "Make another contact primary instead")
    if "role_code" in changed:
        await svc.check_role(db, changes["role_code"])
    if "email" in changed:
        await svc.check_email_free(db, uni.id, changes["email"], contact.id)
    if "is_primary" in changed:
        await svc.clear_primary(db, uni.id)
    for key in changed:
        setattr(contact, key, changes[key])
    if changed:
        svc.audit(db, user, "update", contact.id, uni.id, changed)
    await db.commit()
    if changed:
        svc.log("university_contact_updated", user, contact.id, uni.id, fields=changed)
    return {"contact": await svc.detail_out(db, user, contact)}


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CT7: removes the person's details. The primary goes last: while others remain, another one is made primary first (CT6)."""
    await unis.require_reader(db, user)
    uni = await _locked_university(db, user, await svc.university_of(db, contact_id), "contact_delete")
    contact = await svc.load(db, contact_id)
    if contact.is_primary and await svc.count(db, uni.id) > 1:
        raise HTTPException(409, "Make another contact primary before deleting this one")
    await db.delete(contact)
    svc.audit(db, user, "delete", contact.id, uni.id)
    await db.commit()
    svc.log("university_contact_deleted", user, contact.id, uni.id)
    return Response(status_code=204)

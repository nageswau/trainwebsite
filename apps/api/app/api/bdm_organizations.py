"""bdm-002 (DEC-SCOPE-060, spec §5.3): the BDM Organization CRM.

Every `{org_id}` resolves through `services.bdm_organizations.load_scoped` (out of scope = 404); every write is one transaction --
scope, row lock, change, audit, one commit here. Lists are {items, total, limit, offset}, ordered by name then id."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import BdmOrganization, BdmOrganizationContact, User
from app.schemas import (
    BDM_MAX_CONTACTS,
    BDM_ORG_FIELDS,
    BdmContactIn,
    BdmContactUpdate,
    BdmOrganizationAssign,
    BdmOrganizationCreate,
    BdmOrganizationEnvelope,
    BdmOrganizationPage,
    BdmOrganizationUpdate,
    BdmOrgType,
    BdmSchoolBoard,
)
from app.services import bdm_organizations as svc
from app.services import bdm_tasks as task_svc
from app.services.bdm import bdm_context

router = APIRouter(prefix="/bdm/organizations", tags=["bdm-organizations"])
Primary = aliased(BdmOrganizationContact)
ASSIGNED_INVALID = "assigned must be me or a BDM id"


def _assigned(user: User, assigned: str | None) -> UUID | None:
    if assigned is None:
        return None
    if assigned == "me":
        if user.role != "bdm":
            raise HTTPException(422, ASSIGNED_INVALID)
        return user.id
    try:
        return UUID(assigned)
    except ValueError:
        raise HTTPException(422, ASSIGNED_INVALID) from None


@router.get("", response_model=BdmOrganizationPage)
async def list_organizations(
    q: str | None = SEARCH,
    org_type: BdmOrgType | None = None,
    city: str | None = Query(None, max_length=120),
    board: BdmSchoolBoard | None = None,
    affiliation: str | None = Query(None, max_length=200),
    territory: str | None = Query(None, max_length=120),
    assigned: str | None = Query(None, max_length=36),
    include_archived: bool = False,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters are ANDed with the caller's scope, so they can only narrow it. One query: assignee + primary contact (no N+1)."""
    filters = await svc.caller_scope(db, user)
    if not include_archived:
        filters.append(BdmOrganization.archived_at.is_(None))
    if org_type:
        filters.append(BdmOrganization.org_type == org_type)
    filters += _matching(like_pattern(q), BdmOrganization.name, BdmOrganization.code)
    filters += _matching(like_pattern(city), BdmOrganization.city)
    if board:
        filters.append(BdmOrganization.board == board)
    filters += _matching(like_pattern(affiliation), BdmOrganization.affiliation)  # bdm-003: literal, case-insensitive substrings
    filters += _matching(like_pattern(territory), BdmOrganization.territory)
    assignee = _assigned(user, assigned)
    if assignee is not None:
        filters.append(BdmOrganization.assigned_bdm_user_id == assignee)
    # Both joins are at most 1:1 (NOT NULL assignee; one primary per organization), so the count needs neither.
    total = await db.scalar(select(func.count()).select_from(BdmOrganization).where(*filters))
    stmt = (
        select(BdmOrganization, User, Primary, *svc.meeting_columns())
        .join(User, User.id == BdmOrganization.assigned_bdm_user_id)
        .outerjoin(Primary, and_(Primary.organization_id == BdmOrganization.id, Primary.is_primary.is_(True)))
        .where(*filters)
    )
    rows = (await db.execute(stmt.order_by(BdmOrganization.name, BdmOrganization.id).limit(limit).offset(offset))).all()
    return {"items": [svc.row_out(user, org, assignee_, primary, last, upcoming) for org, assignee_, primary, last, upcoming in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("", status_code=201, response_model=BdmOrganizationEnvelope)
async def create_organization(payload: BdmOrganizationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1/AC2: BDMs only (C9: the creator is the assignee; C3: the creator's module). A likely duplicate is a 409 the BDM must
    acknowledge with confirm_duplicate; nothing is ever merged (Q-18). Concurrent identical creates both succeed (warn-only).
    bdm-003: the profile is checked against org_type before anything is read or written, so a refusal takes no ORG- number."""
    bdm_profile = await bdm_context(db, user)
    sent = payload.profile.model_dump(exclude_unset=True) if payload.profile else {}
    svc.check_profile(payload.org_type, sent, None)
    name_key, city_key = svc.org_keys(payload.name, payload.city)
    matches, total = await svc.find_duplicates(db, bdm_profile.bdm_type, name_key, city_key)
    if total and not payload.confirm_duplicate:
        svc.log("bdm_org_duplicate_warned", user, "-", match_count=total)
        raise svc.duplicate_conflict(matches, total)
    org = BdmOrganization(
        code=await svc.next_code(db),
        bdm_type=bdm_profile.bdm_type,
        name_key=name_key,
        city_key=city_key,
        assigned_bdm_user_id=user.id,
        created_by_user_id=user.id,
        **{k: getattr(payload, k) for k in BDM_ORG_FIELDS},
        **sent,
    )
    db.add(org)
    await db.flush()
    primary = next((i for i, c in enumerate(payload.contacts) if c.is_primary), 0)
    for i, contact in enumerate(payload.contacts):
        db.add(BdmOrganizationContact(organization_id=org.id, **contact.model_dump(exclude={"is_primary"}), is_primary=i == primary))
        await db.flush()  # one at a time: `position` follows the payload order
    svc.audit(
        db,
        user,
        "create",
        org.id,
        {
            "code": org.code,
            "org_type": org.org_type,
            "bdm_type": org.bdm_type,
            "fields": sorted([k for k in BDM_ORG_FIELDS if getattr(payload, k) not in (None, False)] + [k for k, v in sent.items() if v is not None]),
            "contact_count": len(payload.contacts),
        },
    )
    if total:
        svc.audit(db, user, "duplicate_override", org.id, {"match_count": total})
    await db.commit()
    svc.log("bdm_org_created", user, org.id, contact_count=len(payload.contacts), duplicate_override=bool(total))
    return {"organization": await svc.organization_out(db, user, org)}


@router.get("/{org_id}", response_model=BdmOrganizationEnvelope)
async def get_organization(org_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await svc.load_scoped(db, user, org_id)
    return {"organization": await svc.organization_out(db, user, org, refresh=False)}  # nothing was written


@router.patch("/{org_id}", response_model=BdmOrganizationEnvelope)
async def update_organization(org_id: UUID, payload: BdmOrganizationUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """PATCH: only the fields sent; values equal to the stored ones are not changes (no audit, no updated_at bump, §12.1 A6). A
    changed name or city re-runs the duplicate check (AC2). bdm-003: the profile is checked against the effective type (the new one when
    org_type changes) after the lock, so `org` is current; a type change into another profile group is a 409 while the old group has
    data (P4). Profile keys are columns, so the diff, audit and no-op rules below apply to them as they are."""
    org = await svc.load_scoped(db, user, org_id, lock=True)
    svc.require(user, org, "can_edit", "update")
    changes = payload.model_dump(exclude_unset=True, exclude={"confirm_duplicate", "profile"})
    sent = payload.profile.model_dump(exclude_unset=True) if payload.profile else {}
    new_type = changes.get("org_type", org.org_type)
    svc.check_profile(new_type, sent, org)
    if new_type != org.org_type:
        svc.check_type_change(user, org, new_type)
    changes |= sent
    changed = sorted(k for k, v in changes.items() if getattr(org, k) != v)
    total = 0
    if {"name", "city"} & set(changed):
        name_key, city_key = svc.org_keys(changes.get("name", org.name), changes.get("city", org.city))
        matches, total = await svc.find_duplicates(db, org.bdm_type, name_key, city_key, exclude_id=org.id)
        if total and not payload.confirm_duplicate:
            svc.log("bdm_org_duplicate_warned", user, org.id, match_count=total)
            raise svc.duplicate_conflict(matches, total)
        org.name_key, org.city_key = name_key, city_key
    if changed:
        for key in changed:
            setattr(org, key, changes[key])
        svc.audit(db, user, "update", org.id, {"fields": changed})
        if total:
            svc.audit(db, user, "duplicate_override", org.id, {"match_count": total})
    await db.commit()
    if changed:
        svc.log("bdm_org_updated", user, org.id, fields=changed)
    return {"organization": await svc.organization_out(db, user, org)}


async def _set_archived(org_id: UUID, user: User, db: AsyncSession, archive: bool) -> dict:
    org = await svc.load_scoped(db, user, org_id, lock=True)
    action = "archive" if archive else "restore"
    svc.require(user, org, "can_archive" if archive else "can_restore", action)
    org.archived_at = datetime.now(UTC) if archive else None
    # bdm-008 F6: every assignee's open follow-ups / tasks on it are cancelled under the organization lock; restore reopens nothing.
    cancelled = await task_svc.cancel_open_for_organization(db, org.id) if archive else 0
    extra = {"tasks_cancelled": cancelled} if cancelled else {}
    svc.audit(db, user, action, org.id, extra or None)
    await db.commit()
    svc.log(f"bdm_org_{action}d", user, org.id, **extra)
    return {"organization": await svc.organization_out(db, user, org)}


@router.post("/{org_id}/archive", response_model=BdmOrganizationEnvelope)
async def archive_organization(org_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """C5: the assigned BDM or super_admin. Archived = hidden by default and read-only (C15)."""
    return await _set_archived(org_id, user, db, True)


@router.post("/{org_id}/restore", response_model=BdmOrganizationEnvelope)
async def restore_organization(org_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """C5: the team manager or super_admin."""
    return await _set_archived(org_id, user, db, False)


@router.post("/{org_id}/assign", response_model=BdmOrganizationEnvelope)
async def assign_organization(org_id: UUID, payload: BdmOrganizationAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC4: lock order organization -> target user (FOR SHARE), the same for every bdm-002 write."""
    org = await svc.load_scoped(db, user, org_id, lock=True)
    svc.require(user, org, "can_reassign", "assign")
    target = await svc.locked_reassign_target(db, user, org, payload.bdm_user_id)
    before = org.assigned_bdm_user_id
    org.assigned_bdm_user_id = target.id
    svc.audit(db, user, "assign", org.id, {"from": str(before), "to": str(target.id)})
    await db.commit()
    svc.log("bdm_org_reassigned", user, org.id, from_user=str(before), to_user=str(target.id))
    return {"organization": await svc.organization_out(db, user, org)}


async def _editable(org_id: UUID, user: User, db: AsyncSession, route: str) -> BdmOrganization:
    org = await svc.load_scoped(db, user, org_id, lock=True)
    svc.require(user, org, "can_edit", route)
    return org


@router.post("/{org_id}/contacts", status_code=201, response_model=BdmOrganizationEnvelope)
async def add_contact(org_id: UUID, payload: BdmContactIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await _editable(org_id, user, db, "contact_create")
    contacts = await svc.contacts_of(db, org.id)
    if len(contacts) >= BDM_MAX_CONTACTS:
        raise HTTPException(409, f"An organization can have at most {BDM_MAX_CONTACTS} contacts")
    contact = BdmOrganizationContact(organization_id=org.id, **payload.model_dump(exclude={"is_primary"}), is_primary=False)
    db.add(contact)
    await db.flush()
    if payload.is_primary:
        await svc.make_primary(db, contacts, contact)
    fields = sorted(k for k, v in payload.model_dump().items() if v not in (None, False))
    svc.audit(db, user, "contact_create", org.id, {"contact_id": str(contact.id), "fields": fields})
    await db.commit()
    svc.log("bdm_org_contact_created", user, org.id, contact_id=str(contact.id))
    return {"organization": await svc.organization_out(db, user, org)}


@router.patch("/{org_id}/contacts/{contact_id}", response_model=BdmOrganizationEnvelope)
async def update_contact(org_id: UUID, contact_id: UUID, payload: BdmContactUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await _editable(org_id, user, db, "contact_update")
    contact = await svc.load_contact(db, org, contact_id)
    changes = payload.model_dump(exclude_unset=True)
    primary = changes.pop("is_primary", None)
    if primary is False and contact.is_primary:
        raise HTTPException(422, "Choose another primary contact instead")
    changed = sorted(k for k, v in changes.items() if getattr(contact, k) != v)
    for key in changed:
        setattr(contact, key, changes[key])
    if primary and not contact.is_primary:
        await svc.make_primary(db, await svc.contacts_of(db, org.id), contact)
        changed.append("is_primary")
    if changed:
        svc.audit(db, user, "contact_update", org.id, {"contact_id": str(contact.id), "fields": changed})
    await db.commit()
    if changed:
        svc.log("bdm_org_contact_updated", user, org.id, contact_id=str(contact.id), fields=changed)
    return {"organization": await svc.organization_out(db, user, org)}


@router.delete("/{org_id}/contacts/{contact_id}", response_model=BdmOrganizationEnvelope)
async def delete_contact(org_id: UUID, contact_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """C1: never the last contact. Deleting the primary promotes the oldest remaining one (insertion order). A hard delete: real
    erasure of that person's details (§12.3 personal data)."""
    org = await _editable(org_id, user, db, "contact_delete")
    contacts = await svc.contacts_of(db, org.id)
    contact = next((c for c in contacts if c.id == contact_id), None)
    if contact is None:
        raise HTTPException(404, svc.CONTACT_NOT_FOUND)
    if len(contacts) <= 1:
        raise HTTPException(409, "An organization needs at least one contact")
    was_primary = contact.is_primary
    await db.delete(contact)
    await db.flush()
    promoted = None
    if was_primary:
        promoted = next(c for c in contacts if c is not contact)
        promoted.is_primary = True
        await db.flush()
    svc.audit(db, user, "contact_delete", org.id, {"contact_id": str(contact_id), "promoted_contact_id": str(promoted.id) if promoted else None})
    await db.commit()
    svc.log("bdm_org_contact_deleted", user, org.id, contact_id=str(contact_id))
    return {"organization": await svc.organization_out(db, user, org)}

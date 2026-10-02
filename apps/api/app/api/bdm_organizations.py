"""bdm-002 (DEC-SCOPE-058, spec §5.3): the BDM Organization CRM.

Every `{org_id}` resolves through `services.bdm_organizations.load_scoped` (out of scope = 404); every write is one transaction --
scope, row lock, change, audit, one commit here. Lists are {items, total, limit, offset}, ordered by name then id."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.bdm import _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import BdmOrganization, BdmOrganizationContact, User
from app.schemas import BDM_ORG_FIELDS, BdmOrganizationCreate, BdmOrganizationEnvelope, BdmOrganizationPage, BdmOrgType
from app.services import bdm_organizations as svc
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
    q: str | None = Query(None, max_length=200),
    org_type: BdmOrgType | None = None,
    city: str | None = Query(None, max_length=120),
    assigned: str | None = Query(None, max_length=36),
    include_archived: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters are ANDed with the caller's scope, so they can only narrow it. One query: assignee + primary contact (no N+1)."""
    filters, _ = await svc.caller_scope(db, user)
    if not include_archived:
        filters.append(BdmOrganization.archived_at.is_(None))
    if org_type:
        filters.append(BdmOrganization.org_type == org_type)
    filters += _matching(like_pattern(q), BdmOrganization.name, BdmOrganization.code)
    filters += _matching(like_pattern(city), BdmOrganization.city)
    assignee = _assigned(user, assigned)
    if assignee is not None:
        filters.append(BdmOrganization.assigned_bdm_user_id == assignee)
    stmt = (
        select(BdmOrganization, User, Primary)
        .join(User, User.id == BdmOrganization.assigned_bdm_user_id)
        .outerjoin(Primary, and_(Primary.organization_id == BdmOrganization.id, Primary.is_primary.is_(True)))
        .where(*filters)
    )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(BdmOrganization.name, BdmOrganization.id).limit(limit).offset(offset))).all()
    return {"items": [svc.row_out(user, org, assignee_, primary) for org, assignee_, primary in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("", status_code=201, response_model=BdmOrganizationEnvelope)
async def create_organization(payload: BdmOrganizationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1/AC2: BDMs only (C9: the creator is the assignee; C3: the creator's module). A likely duplicate is a 409 the BDM must
    acknowledge with confirm_duplicate; nothing is ever merged (Q-18). Concurrent identical creates both succeed (warn-only)."""
    profile = await bdm_context(db, user)
    name_key, city_key = svc.normalize_key(payload.name), svc.normalize_key(payload.city)
    matches, total = await svc.find_duplicates(db, profile.bdm_type, name_key, city_key)
    if total and not payload.confirm_duplicate:
        svc.log("bdm_org_duplicate_warned", user, "-", match_count=total)
        raise svc.duplicate_conflict(matches, total)
    org = BdmOrganization(
        code=await svc.next_code(db),
        bdm_type=profile.bdm_type,
        name_key=name_key,
        city_key=city_key,
        assigned_bdm_user_id=user.id,
        created_by_user_id=user.id,
        **{k: getattr(payload, k) for k in BDM_ORG_FIELDS},
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
            "fields": sorted(k for k in BDM_ORG_FIELDS if getattr(payload, k) not in (None, False)),
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
    return {"organization": await svc.organization_out(db, user, org)}

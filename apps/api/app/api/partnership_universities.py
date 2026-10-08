"""upc-003 (DEC-SCOPE-120, spec §3): the Global University Master -- list, create, detail, edit, assign, publish and deactivate.

Every write is one transaction: the university row lock (FOR UPDATE), the scope check, the change, the audit row, one commit here, then a
structured log. Lists are {items, total, limit, offset}, ordered by name then id, in one joined query (no N+1)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching, _paged
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import COUNTRY_REGIONS, Country, PartnershipProfile, University, UniversityAssignmentHistory, User
from app.schemas import (
    InstitutionType,
    PartnershipHeadPage,
    PartnershipPotential,
    RelationshipStrength,
    UniversityAssign,
    UniversityCreate,
    UniversityDeactivate,
    UniversityEnvelope,
    UniversityPage,
    UniversityPriority,
    UniversityUpdate,
)
from app.services import partnership_universities as svc

router = APIRouter(prefix="/partnership/universities", tags=["partnership-universities"])
Primary, Backup = aliased(User), aliased(User)
MANAGER_FILTER_INVALID = "manager must be me, none or a manager id"


def _manager_filter(user: User, manager: str | None) -> list:
    if manager is None:
        return []
    if manager == "none":
        return [University.primary_manager_user_id.is_(None)]
    try:
        manager_id = user.id if manager == "me" else UUID(manager)
    except ValueError:
        raise HTTPException(422, MANAGER_FILTER_INVALID) from None
    return [(University.primary_manager_user_id == manager_id) | (University.backup_manager_user_id == manager_id)]


@router.get("", response_model=UniversityPage)
async def list_universities(
    q: str | None = SEARCH,
    country_id: UUID | None = None,
    region: Literal[COUNTRY_REGIONS] | None = None,
    institution_type: InstitutionType | None = None,
    priority: UniversityPriority | None = None,
    partnership_potential: PartnershipPotential | None = None,
    relationship_strength: RelationshipStrength | None = None,
    manager: str | None = Query(None, max_length=36),
    visibility: Literal["public", "internal"] | None = None,
    include_inactive: bool = False,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters are ANDed and only narrow. `q` matches name, code or city (literal, case-insensitive)."""
    await svc.require_reader(db, user)
    filters = svc.search_filters(like_pattern(q)) + _manager_filter(user, manager)
    if not include_inactive:
        filters.append(University.active.is_(True))
    for column, value in (
        (University.country_id, country_id),
        (Country.region, region),
        (University.institution_type, institution_type),
        (University.priority, priority),
        (University.partnership_potential, partnership_potential),
        (University.relationship_strength, relationship_strength),
    ):
        if value is not None:
            filters.append(column == value)
    if visibility is not None:
        filters.append(University.catalogue_visible.is_(visibility == "public"))
    base = select(University.id).join(Country, Country.id == University.country_id).where(*filters)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    stmt = (
        select(University, Country, Primary, Backup)
        .join(Country, Country.id == University.country_id)
        .outerjoin(Primary, Primary.id == University.primary_manager_user_id)
        .outerjoin(Backup, Backup.id == University.backup_manager_user_id)
        .where(*filters)
        .order_by(University.name, University.id)
        .limit(limit)
        .offset(offset)
    )
    team = await svc.team_of(db, user)
    rows = (await db.execute(stmt)).all()
    return {"items": [svc.row_out(user, uni, country, primary, backup, team) for uni, country, primary, backup in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("", status_code=201, response_model=UniversityEnvelope)
async def create_university(payload: UniversityCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """UM5/UM8: a head, overseas_admin or super_admin adds a university; it starts internal (not public). Any country, internal ISO rows
    included -- publishing is what needs a catalogue country (UM6)."""
    svc.require_creator(user)
    await svc.country_or_422(db, payload.country_id)
    code = await svc.next_code(db)
    values = payload.model_dump(exclude={"rankings"})
    uni = University(university_code=code, slug=await svc.free_slug(db, payload.name, code), catalogue_visible=False, requirements=[], deadlines=[], scholarships=[], **values)
    db.add(uni)
    try:
        await db.flush()
    except IntegrityError:  # two creates of the same name in the same instant took the same slug
        await db.rollback()
        raise HTTPException(409, "Another university with this name was just added. Try again.") from None
    await svc.replace_rankings(db, uni, payload.rankings)
    sent = sorted(k for k, v in values.items() if v not in (None, "", []))
    svc.audit(db, user, "create", uni.id, {"code": code, "fields": sent + (["rankings"] if payload.rankings else [])})
    await db.commit()
    svc.log("university_created", user, uni.id, code=code)
    return {"university": await svc.detail_out(db, user, uni)}


@router.get("/manager-options", response_model=PartnershipHeadPage)
async def manager_options(q: str | None = SEARCH, limit: int = Query(20, ge=1, le=50), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The assign picker (UM3): a head's active direct reports, or every active manager for super_admin; email tells same-name managers
    apart."""
    if user.role not in svc.ASSIGN_ROLES:
        raise HTTPException(403, svc.ROLE_REFUSALS["can_assign"])
    stmt = (
        select(User.id, User.full_name, User.email)
        .join(PartnershipProfile, PartnershipProfile.user_id == User.id)
        .where(*svc.manager_options_filter(user), *_matching(like_pattern(q), User.full_name, User.email))
    )
    return await _paged(db, stmt, limit, 0, lambda id_, full_name, email: {"id": id_, "full_name": full_name, "email": email})


@router.get("/{university_id}", response_model=UniversityEnvelope)
async def get_university(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_reader(db, user)
    return {"university": await svc.detail_out(db, user, await svc.load(db, university_id), refresh=False)}


async def _locked(db: AsyncSession, user: User, university_id: UUID, action: str, route: str) -> tuple[University, frozenset]:
    await svc.require_reader(db, user)
    uni = await svc.load(db, university_id, lock=True)
    team = await svc.team_of(db, user)
    svc.require(user, uni, team, action, route)
    return uni, team


@router.patch("/{university_id}", response_model=UniversityEnvelope)
async def update_university(university_id: UUID, payload: UniversityUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1/AC4: only the fields sent; a value equal to the stored one is not a change (no audit). A published university stays
    publishable (UM6), so it cannot lose its overview or move to an internal country."""
    uni, team = await _locked(db, user, university_id, "can_edit", "update")
    changes = payload.model_dump(exclude_unset=True, exclude={"rankings"})
    changed = sorted(k for k, v in changes.items() if getattr(uni, k) != v)
    country = await svc.country_or_422(db, changes["country_id"]) if "country_id" in changed else None
    for key in changed:
        setattr(uni, key, changes[key])
    if payload.rankings is not None:
        stored = [(r.system, r.other_name, r.year, r.rank) for r in await svc.rankings_of(db, uni.id)]
        sent = [(r.system, r.other_name, r.year, r.rank) for r in payload.rankings]
        if sorted(stored, key=str) != sorted(sent, key=str):
            await svc.replace_rankings(db, uni, payload.rankings)
            changed = sorted([*changed, "rankings"])
    if uni.catalogue_visible and {"overview", "country_id"} & set(changed):
        svc.check_publishable(uni, country if country is not None else await db.get_one(Country, uni.country_id))
    if changed:
        svc.audit(db, user, "update", uni.id, {"fields": changed})
    await db.commit()
    if changed:
        svc.log("university_updated", user, uni.id, fields=changed)
    return {"university": await svc.detail_out(db, user, uni, team)}


@router.post("/{university_id}/assign", response_model=UniversityEnvelope)
async def assign_university(university_id: UUID, payload: UniversityAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§27 / UM3: the whole ownership (primary + optional backup). Lock order: university, then each new manager (FOR SHARE). One history
    row per slot that changed."""
    uni, team = await _locked(db, user, university_id, "can_assign", "assign")
    wanted = {"primary": payload.primary_manager_user_id, "backup": payload.backup_manager_user_id}
    current = {"primary": uni.primary_manager_user_id, "backup": uni.backup_manager_user_id}
    changed = [slot for slot in ("primary", "backup") if wanted[slot] != current[slot]]
    for slot in changed:
        target = wanted[slot]
        if target is not None:
            await svc.locked_manager(db, user, target)
    if changed:
        uni.primary_manager_user_id, uni.backup_manager_user_id = wanted["primary"], wanted["backup"]
        db.add_all(UniversityAssignmentHistory(university_id=uni.id, slot=slot, from_user_id=current[slot], to_user_id=wanted[slot], actor_user_id=user.id) for slot in changed)
        svc.audit(db, user, "assign", uni.id, {slot: [str(current[slot]) if current[slot] else None, str(wanted[slot]) if wanted[slot] else None] for slot in changed})
    await db.commit()
    if changed:
        svc.log("university_assigned", user, uni.id, slots=changed)
    return {"university": await svc.detail_out(db, user, uni, team)}


async def _set_visible(university_id: UUID, user: User, db: AsyncSession, visible: bool) -> dict:
    action = "publish" if visible else "unpublish"
    uni, team = await _locked(db, user, university_id, "can_publish", action)
    if uni.catalogue_visible == visible:
        raise HTTPException(409, "Already published" if visible else "Already internal")
    if visible:
        svc.check_publishable(uni, await db.get_one(Country, uni.country_id))
    uni.catalogue_visible = visible
    svc.audit(db, user, action, uni.id)
    await db.commit()
    svc.log(f"university_{action}ed", user, uni.id)
    return {"university": await svc.detail_out(db, user, uni, team)}


@router.post("/{university_id}/publish", response_model=UniversityEnvelope)
async def publish_university(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """UM5/UM6: shown in the public catalogue from now on."""
    return await _set_visible(university_id, user, db, True)


@router.post("/{university_id}/unpublish", response_model=UniversityEnvelope)
async def unpublish_university(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _set_visible(university_id, user, db, False)


@router.post("/{university_id}/deactivate", response_model=UniversityEnvelope)
async def deactivate_university(university_id: UUID, payload: UniversityDeactivate | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """UM10: inactive = hidden from the catalogue and read-only. Existing applications keep working, but the caller confirms first."""
    uni, team = await _locked(db, user, university_id, "can_deactivate", "deactivate")
    if not uni.active:
        raise HTTPException(409, "Already inactive")
    count = await svc.application_count(db, uni.id)
    if count and not (payload and payload.confirm):
        raise HTTPException(409, {"message": f"This university has {count} application(s). Deactivate it anyway?", "code": "has_applications", "count": count})
    uni.active, uni.catalogue_visible = False, False
    svc.audit(db, user, "deactivate", uni.id, {"application_count": count})
    await db.commit()
    svc.log("university_deactivated", user, uni.id, application_count=count)
    return {"university": await svc.detail_out(db, user, uni, team)}


@router.post("/{university_id}/reactivate", response_model=UniversityEnvelope)
async def reactivate_university(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Active again, but still internal: publishing is a separate decision."""
    uni, team = await _locked(db, user, university_id, "can_deactivate", "reactivate")
    if uni.active:
        raise HTTPException(409, "Already active")
    uni.active = True
    svc.audit(db, user, "reactivate", uni.id)
    await db.commit()
    svc.log("university_reactivated", user, uni.id)
    return {"university": await svc.detail_out(db, user, uni, team)}

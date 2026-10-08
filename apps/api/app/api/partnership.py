"""upc-001 (DEC-SCOPE-117, spec §5): partnership manager and head reads, the manager's phone self-edit (PU3), the admin list and the
reporting-head picker.

Scope always comes from the session -- no /partnership route takes a user id -- so there is no IDOR surface. Lists reuse bdm-001's
paging helpers: {items, total, limit, offset}, ordered by name then id."""

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.admin import ensure_admin
from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching, _paged
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import AuditLog, PartnershipProfile, User
from app.schemas import PartnershipAdminPage, PartnershipHeadPage, PartnershipMeOut, PartnershipTeamPage
from app.services.partnership import partnership_context, profile_out, require_creator_may, require_head, team_filter
from app.services.telecaller import parse_self_update, person_ref

router = APIRouter(prefix="/partnership", tags=["partnership"])
admin_router = APIRouter(prefix="/admin", tags=["partnership-admin"])
Head = aliased(User)


def _team_row(profile: PartnershipProfile, user: User) -> dict:
    return {"id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active, "employee_id": profile.employee_id}


def _admin_row(profile: PartnershipProfile, user: User, head: User) -> dict:
    return {**_team_row(profile, user), "reporting_head": person_ref(head), "head_active": head.active}


def _profiles(filters: list):
    """One query: profile + its user + its head (no N+1)."""
    return (
        select(PartnershipProfile, User, Head)
        .join(User, User.id == PartnershipProfile.user_id)
        .join(Head, Head.id == PartnershipProfile.reporting_head_user_id)
        .where(*filters)
    )


def _searched(q: str | None) -> list:
    return _matching(like_pattern(q), User.full_name, User.email, PartnershipProfile.employee_id)


async def _me(db: AsyncSession, user: User, profile: PartnershipProfile) -> dict:
    head = await db.get(User, profile.reporting_head_user_id)
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "division": user.division, "partnership_profile": profile_out(profile, head),
    }


@router.get("/me", response_model=PartnershipMeOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _me(db, user, await partnership_context(db, user))


@router.patch("/profile", response_model=PartnershipMeOut)
async def update_own_profile(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """PU3: the phone only; every other key is a 422 (tel-001's TelecallerSelfUpdate forbids extras). The audit row names the field,
    not the value."""
    profile = await partnership_context(db, user)
    user.phone = parse_self_update(payload).phone
    db.add(AuditLog(user_id=user.id, action="partnership.profile_update", entity_type="user", entity_id=str(user.id), metadata_json={"fields": ["phone"]}))
    out = await _me(db, user, profile)
    await db.commit()
    return out


@router.get("/head/team", response_model=PartnershipTeamPage)
async def team(q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC4: a head's direct reports (inactive included, with their status); super_admin sees all. `q` only narrows."""
    require_head(user)
    return await _paged(db, _profiles(team_filter(user) + _searched(q)), limit, offset, lambda profile, member, _head: _team_row(profile, member))


@admin_router.get("/partnership-managers", response_model=PartnershipAdminPage)
async def admin_managers(
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(ensure_admin),
    db: AsyncSession = Depends(get_db),
):
    """PU7: the admins who manage partnership managers (ensure_admin alone would also let it_admin in). `q` matches name, email or
    Employee ID; `active` narrows by status."""
    require_creator_may(user, "/admin/partnership-managers")
    filters = _searched(q)
    if active is not None:
        filters.append(User.active.is_(active))
    return await _paged(db, _profiles(filters), limit, offset, _admin_row)


@admin_router.get("/partnership-heads", response_model=PartnershipHeadPage)
async def admin_heads(q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """The reporting-head picker: active heads only, searchable by name or email; email tells same-name heads apart."""
    require_creator_may(user, "/admin/partnership-heads")
    stmt = select(User.id, User.full_name, User.email).where(
        User.role == "partnership_head", User.active.is_(True), *_matching(like_pattern(q), User.full_name, User.email)
    )
    return await _paged(db, stmt, limit, offset, lambda id_, full_name, email: {"id": id_, "full_name": full_name, "email": email})

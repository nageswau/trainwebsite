"""tel-001 (DEC-SCOPE-073, spec §5.7): telecaller and manager reads, the telecaller's phone self-edit (TL3), the admin telecaller
list and the reporting-manager picker.

Scope always comes from the session -- no /telecaller route takes a user id -- so there is no IDOR surface; the admin list is
narrowed by team in SQL (T21). Lists reuse bdm-001's paging helpers: {items, total, limit, offset}, ordered by name then id."""

from typing import Literal

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.admin import ensure_admin
from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching, _paged
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import AuditLog, TelecallerProfile, User
from app.schemas import BdmManagerPage, TelecallerAdminPage, TelecallerMeOut, TelecallerTeamPage
from app.services.telecaller import admin_team_filter, parse_self_update, person_ref, profile_out, require_manager, team_filter, telecaller_context

router = APIRouter(prefix="/telecaller", tags=["telecaller"])
admin_router = APIRouter(prefix="/admin", tags=["telecaller-admin"])
Manager = aliased(User)


def _team_row(profile: TelecallerProfile, user: User) -> dict:
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "team": profile.team, "employee_id": profile.employee_id,
    }


def _admin_row(profile: TelecallerProfile, user: User, manager: User) -> dict:
    return {**_team_row(profile, user), "reporting_manager": person_ref(manager), "manager_active": manager.active}


def _profiles(filters: list):
    """One query: profile + its user + its manager (no N+1)."""
    return (
        select(TelecallerProfile, User, Manager)
        .join(User, User.id == TelecallerProfile.user_id)
        .join(Manager, Manager.id == TelecallerProfile.reporting_manager_user_id)
        .where(*filters)
    )


def _me(user: User, profile: TelecallerProfile, manager: User) -> dict:
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "division": user.division, "telecaller_profile": profile_out(profile, manager),
    }


@router.get("/me", response_model=TelecallerMeOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await telecaller_context(db, user)
    return _me(user, profile, await db.get(User, profile.reporting_manager_user_id))


@router.patch("/profile", response_model=TelecallerMeOut)
async def update_own_profile(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """TL3: the phone only; every other key is a 422 (TelecallerSelfUpdate forbids extras). The audit row names the field, not the
    value (no phone numbers in the log)."""
    profile = await telecaller_context(db, user)
    user.phone = parse_self_update(payload).phone
    db.add(AuditLog(user_id=user.id, action="telecaller.profile_update", entity_type="user", entity_id=str(user.id), metadata_json={"fields": ["phone"]}))
    out = _me(user, profile, await db.get(User, profile.reporting_manager_user_id))
    await db.commit()
    return out


@router.get("/manager/team", response_model=TelecallerTeamPage)
async def team(q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """T23 / AC4: a manager's direct reports (inactive included, with their status); super_admin sees all. `q` only narrows."""
    require_manager(user)
    filters = team_filter(user) + _matching(like_pattern(q), User.full_name, User.email, TelecallerProfile.employee_id)
    return await _paged(db, _profiles(filters), limit, offset, lambda profile, member, _manager: _team_row(profile, member))


@admin_router.get("/telecallers", response_model=TelecallerAdminPage)
async def admin_telecallers(
    team: Literal["it", "overseas"] | None = None,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(ensure_admin),
    db: AsyncSession = Depends(get_db),
):
    """`q` matches name, email or Employee ID; it is ANDed with the caller's team scope, so it can never widen it."""
    filters = admin_team_filter(user, team)
    if active is not None:
        filters.append(User.active.is_(active))
    filters += _matching(like_pattern(q), User.full_name, User.email, TelecallerProfile.employee_id)
    return await _paged(db, _profiles(filters), limit, offset, _admin_row)


@admin_router.get("/telecaller-managers", response_model=BdmManagerPage)
async def telecaller_managers(q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """The reporting-manager picker: active telecaller managers only, searchable by name or email; email tells same-name managers apart."""
    stmt = select(User.id, User.full_name, User.email).where(
        User.role == "telecaller_manager", User.active.is_(True), *_matching(like_pattern(q), User.full_name, User.email)
    )
    return await _paged(db, stmt, limit, offset, lambda id_, full_name, email: {"id": id_, "full_name": full_name, "email": email})

"""bdm-001 (DEC-SCOPE-052, spec §5.7): BDM and BDM-manager reads, plus the admin BDM list and manager picker.

Read-only. Scope always comes from the session -- no route takes a user id -- so there is no IDOR surface; the admin list is
narrowed by type in SQL (D10). Lists are {items, total, limit, offset} (the AGN-008 convention), stably ordered by name then id."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.admin import ensure_admin
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmProfile, User
from app.schemas import BdmAdminPage, BdmManagerPage, BdmMeOut, BdmTeamPage
from app.services.bdm import admin_type_filter, bdm_context, profile_out, require_manager, team_filter

router = APIRouter(prefix="/bdm", tags=["bdm"])
admin_router = APIRouter(prefix="/admin", tags=["bdm-admin"])
Manager = aliased(User)
LIMIT = Query(50, ge=1, le=100)
OFFSET = Query(0, ge=0)


def _team_row(profile: BdmProfile, user: User, manager: User) -> dict:
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "bdm_type": profile.bdm_type, "employee_id": profile.employee_id, "designation": profile.designation,
        "department": profile.department, "territory": profile.territory,
    }


def _admin_row(profile: BdmProfile, user: User, manager: User) -> dict:
    ref = {"id": manager.id, "full_name": manager.full_name, "active": manager.active}
    return {**_team_row(profile, user, manager), "reporting_manager": ref, "manager_active": manager.active}


async def _paged(db: AsyncSession, stmt, limit: int, offset: int, shape) -> dict:
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(User.full_name, User.id).limit(limit).offset(offset))).all()
    return {"items": [shape(*row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


def _profiles(filters: list):
    """One query: profile + its user + its manager (no N+1)."""
    return (
        select(BdmProfile, User, Manager)
        .join(User, User.id == BdmProfile.user_id)
        .join(Manager, Manager.id == BdmProfile.reporting_manager_user_id)
        .where(*filters)
    )


@router.get("/me", response_model=BdmMeOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await bdm_context(db, user)
    manager = await db.get(User, profile.reporting_manager_user_id)
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "division": user.division, "bdm_profile": profile_out(profile, manager),
    }


@router.get("/manager/team", response_model=BdmTeamPage)
async def team(limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    return await _paged(db, _profiles(team_filter(user)), limit, offset, _team_row)


@admin_router.get("/bdms", response_model=BdmAdminPage)
async def admin_bdms(
    bdm_type: Literal["agent", "school", "college"] | None = None,
    active: bool | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(ensure_admin),
    db: AsyncSession = Depends(get_db),
):
    filters = admin_type_filter(user, bdm_type)
    if active is not None:
        filters.append(User.active.is_(active))
    return await _paged(db, _profiles(filters), limit, offset, _admin_row)


@admin_router.get("/bdm-managers", response_model=BdmManagerPage)
async def bdm_managers(limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """The reporting-manager picker: active managers only, id and name only (no email -- data minimisation)."""
    stmt = select(User.id, User.full_name).where(User.role == "bdm_manager", User.active.is_(True))
    return await _paged(db, stmt, limit, offset, lambda id_, full_name: {"id": id_, "full_name": full_name})

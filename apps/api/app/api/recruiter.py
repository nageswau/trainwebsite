"""rec-001 (DEC-SCOPE-116, spec §4): recruiter and placement-manager reads, the recruiter's phone self-edit, the admin Recruiter Staff
list and the reporting-manager picker.

Scope always comes from the session -- no /recruiter route takes a user id -- so there is no IDOR surface. The admin routes are
super_admin / it_admin only (recruiters are IT). Lists reuse bdm-001's paging helpers: {items, total, limit, offset}, ordered by name
then id; one query each (the manager is an outer join, since a backfilled recruiter has none)."""

from fastapi import APIRouter, Body, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching, _paged
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import AuditLog, RecruiterProfile, User
from app.schemas import PlacementManagerPage, RecruiterAdminPage, RecruiterMeOut, RecruiterTeamPage
from app.services.recruiter import MANAGER_ROLE, manager_ref, profile_out, recruiter_context, require_manager, require_recruiter_admin, team_filter
from app.services.telecaller import parse_self_update

router = APIRouter(prefix="/recruiter", tags=["recruiter"])
admin_router = APIRouter(prefix="/admin", tags=["recruiter-admin"])
Manager = aliased(User)


def _team_row(profile: RecruiterProfile, user: User, _manager: User | None = None) -> dict:
    return {"id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active, "employee_id": profile.employee_id}


def _admin_row(profile: RecruiterProfile, user: User, manager: User | None) -> dict:
    return {**_team_row(profile, user), "reporting_manager": manager_ref(manager)}


def _profiles(filters: list):
    return (
        select(RecruiterProfile, User, Manager)
        .join(User, User.id == RecruiterProfile.user_id)
        .outerjoin(Manager, Manager.id == RecruiterProfile.reporting_manager_user_id)
        .where(User.role == "placement_team", *filters)
    )


def _searched(q: str | None) -> list:
    return _matching(like_pattern(q), User.full_name, User.email, RecruiterProfile.employee_id)


async def _me(db: AsyncSession, user: User, profile: RecruiterProfile) -> dict:
    manager = await db.get(User, profile.reporting_manager_user_id) if profile.reporting_manager_user_id else None
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "division": user.division, "recruiter_profile": profile_out(profile, manager),
    }


@router.get("/me", response_model=RecruiterMeOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _me(db, user, await recruiter_context(db, user))


@router.patch("/profile", response_model=RecruiterMeOut)
async def update_own_profile(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The phone only (the tel-001 TL3 rule); every other key is a 422. The audit row names the field, not the value."""
    profile = await recruiter_context(db, user)
    user.phone = parse_self_update(payload).phone
    db.add(AuditLog(user_id=user.id, action="recruiter.profile_update", entity_type="user", entity_id=str(user.id), metadata_json={"fields": ["phone"]}))
    out = await _me(db, user, profile)
    await db.commit()
    return out


@router.get("/manager/team", response_model=RecruiterTeamPage)
async def team(q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC4: a manager's direct reports (inactive included, with their status); super_admin sees all. `q` only narrows."""
    require_manager(user)
    return await _paged(db, _profiles(team_filter(user) + _searched(q)), limit, offset, _team_row)


@admin_router.get("/recruiters", response_model=RecruiterAdminPage)
async def admin_recruiters(
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The Recruiter Staff page: every recruiter, with their manager or none (AC5 flags those). `q` matches name, email or Employee ID."""
    require_recruiter_admin(user, "/admin/recruiters")
    filters = _searched(q)
    if active is not None:
        filters.append(User.active.is_(active))
    return await _paged(db, _profiles(filters), limit, offset, _admin_row)


@admin_router.get("/placement-managers", response_model=PlacementManagerPage)
async def placement_managers(q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The reporting-manager picker: active placement managers only (an inactive one cannot be chosen), searchable by name or email;
    `recruiter_count` counts every report, active or not, in one correlated subquery."""
    require_recruiter_admin(user, "/admin/placement-managers")
    count = select(func.count()).where(RecruiterProfile.reporting_manager_user_id == User.id).scalar_subquery()
    stmt = select(User.id, User.full_name, User.email, count).where(
        User.role == MANAGER_ROLE, User.active.is_(True), *_matching(like_pattern(q), User.full_name, User.email)
    )
    return await _paged(db, stmt, limit, offset, lambda id_, full_name, email, n: {"id": id_, "full_name": full_name, "email": email, "recruiter_count": n})

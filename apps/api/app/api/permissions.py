"""nehn-005 (DEC-SCOPE-281, API §12GG, RBAC §2.195): the permission catalogue, a role's grants, and the caller's own effective set.

Only super_admin reads or edits grants (P6). Checks run caller (401/403) → role (404) → body (422) → target (409), so a refused caller
never learns which role names exist.

nehn-007 (DEC-SCOPE-299, API §12GW, RBAC §2.210): one user's overrides (read / replace) and the report of every active override, under
the same super_admin guard; the caller's own set now includes their overrides."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core import rbac
from app.core.database import get_db
from app.models import User
from app.schemas import RolePermissionsUpdate, UserPermissionOverridesUpdate
from app.services import permissions

admin_router = APIRouter(prefix="/admin", tags=["permissions"])
me_router = APIRouter(prefix="/auth", tags=["permissions"])


async def _super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != permissions.SUPER_ADMIN:
        raise HTTPException(403, "Only a super admin can manage permissions")
    return user


def _known_role(role: str) -> str:
    if role not in rbac.ROLES:
        raise HTTPException(404, "Role not found")
    return role


async def _role_out(db: AsyncSession, role: str) -> dict:
    return {"role": role, "permissions": await permissions.role_grants(db, role), "editable": role != permissions.SUPER_ADMIN}


@admin_router.get("/permissions/catalogue")
async def catalogue(_: User = Depends(_super_admin)):
    # nehn-006 (DEC-SCOPE-295 M3): `roles` is what the matrix screen's role picker offers (additive).
    return {
        "roles": list(rbac.ROLES),
        "actions": list(rbac.ACTIONS),
        "resources": [{"key": key, "label": entry["label"], "actions": list(entry["actions"])} for key, entry in rbac.CATALOGUE.items()],
    }


@admin_router.get("/roles/{role}/permissions")
async def read_role_permissions(_: User = Depends(_super_admin), role: str = Depends(_known_role), db: AsyncSession = Depends(get_db)):
    return await _role_out(db, role)


@admin_router.put("/roles/{role}/permissions")
async def replace_role_permissions(payload: RolePermissionsUpdate, user: User = Depends(_super_admin), role: str = Depends(_known_role), db: AsyncSession = Depends(get_db)):
    await permissions.replace_role_grants(db, user.id, role, payload.permissions)
    return await _role_out(db, role)


@admin_router.get("/permissions/overrides")
async def override_report(_: User = Depends(_super_admin), db: AsyncSession = Depends(get_db)):
    return await permissions.override_report(db)


async def _target_user(user_id: UUID, db: AsyncSession = Depends(get_db)) -> User:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    return target


async def _user_out(db: AsyncSession, target: User) -> dict:
    return {
        "user": {"id": target.id, "full_name": target.full_name, "email": target.email, "role": target.role},
        "editable": target.role != permissions.SUPER_ADMIN,
        "role_permissions": await permissions.role_grants(db, target.role),
        "overrides": [permissions.override_out(row) for row in await permissions.active_overrides(db, target.id)],
        "effective": await permissions.user_grants(db, target),
    }


@admin_router.get("/users/{user_id}/permissions")
async def read_user_permissions(_: User = Depends(_super_admin), target: User = Depends(_target_user), db: AsyncSession = Depends(get_db)):
    return await _user_out(db, target)


@admin_router.put("/users/{user_id}/permissions")
async def replace_user_permissions(payload: UserPermissionOverridesUpdate, user: User = Depends(_super_admin), target: User = Depends(_target_user), db: AsyncSession = Depends(get_db)):
    await permissions.replace_user_overrides(db, user.id, target, payload.overrides)
    return await _user_out(db, target)


@me_router.get("/me/permissions")
async def my_permissions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"role": user.role, "permissions": await permissions.user_grants(db, user)}

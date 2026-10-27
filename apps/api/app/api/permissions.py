"""nehn-005 (DEC-SCOPE-281, API §12GG, RBAC §2.195): the permission catalogue, a role's grants, and the caller's own effective set.

Only super_admin reads or edits grants (P6). Checks run caller (401/403) → role (404) → body (422) → target (409), so a refused caller
never learns which role names exist."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core import rbac
from app.core.database import get_db
from app.models import User
from app.schemas import RolePermissionsUpdate
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


@me_router.get("/me/permissions")
async def my_permissions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"role": user.role, "permissions": await permissions.role_grants(db, user.role)}

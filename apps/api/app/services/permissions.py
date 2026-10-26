"""nehn-005 (DEC-SCOPE-280): the permission engine's reads and its one write.

The engine says whether a role *may* use a resource action; each route's own record scope (division, own team) still says *which rows*.
There is no in-process cache (P7): a check is one primary-key lookup, so a change applies on the next request on every worker."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.models import AuditLog, RolePermission

logger = logging.getLogger("app.permissions")

SUPER_ADMIN = "super_admin"
AUDIT_ACTION = "role_permissions.update"


async def has_grant(db: AsyncSession, role: str, resource: str, action: str) -> bool:
    """Deny by default: a key outside the catalogue is refused for everyone, super_admin included."""
    if action not in rbac.CATALOGUE.get(resource, {}).get("actions", ()):
        return False
    if role == SUPER_ADMIN:
        return True
    return await db.get(RolePermission, (role, resource, action)) is not None


async def role_grants(db: AsyncSession, role: str) -> list[str]:
    """The role's keys, sorted. super_admin holds the whole catalogue. A stored key that has left the catalogue is not reported."""
    if role == SUPER_ADMIN:
        return sorted(rbac.all_keys())
    rows = await db.execute(select(RolePermission.resource, RolePermission.action).where(RolePermission.role == role))
    return sorted({f"{resource}.{action}" for resource, action in rows} & set(rbac.all_keys()))


async def replace_role_grants(db: AsyncSession, actor_id: UUID, role: str, keys: list[str]) -> list[str]:
    """Replace the role's grants with `keys` (already validated against the catalogue). Unchanged grants keep who granted them and when;
    a real change is audited in the same transaction, a no-op writes nothing. A concurrent edit of the same role is a 409."""
    if role == SUPER_ADMIN:
        raise HTTPException(409, "super_admin always holds every permission and cannot be changed")
    before, after = await role_grants(db, role), sorted(set(keys))
    added, removed = sorted(set(after) - set(before)), sorted(set(before) - set(after))
    if not added and not removed:
        return before
    for key in removed:
        resource, action = rbac.parse_key(key)
        await db.execute(delete(RolePermission).where(RolePermission.role == role, RolePermission.resource == resource, RolePermission.action == action))
    for key in added:
        resource, action = rbac.parse_key(key)
        db.add(RolePermission(role=role, resource=resource, action=action, granted_by_id=actor_id))
    db.add(AuditLog(user_id=actor_id, action=AUDIT_ACTION, entity_type="role", entity_id=role, metadata_json={"before": before, "after": after, "added": added, "removed": removed}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "These permissions were changed by someone else. Reload and try again.") from None
    logger.info("role_permissions.update", extra={"extra_fields": {"actor_id": str(actor_id), "role": role, "added": added, "removed": removed}})
    return after

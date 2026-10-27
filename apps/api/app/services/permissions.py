"""nehn-005 (DEC-SCOPE-281): the permission engine's reads and its writes.

The engine says whether a role *may* use a resource action; each route's own record scope (division, own team) still says *which rows*.
There is no in-process cache (P7): a check is at most two indexed lookups, so a change applies on the next request on every worker.
nehn-007 (DEC-SCOPE-297): a user's effective set is (role grants + active allows) - active denies; super_admin holds everything."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.models import AuditLog, RolePermission, User, UserPermissionOverride

logger = logging.getLogger("app.permissions")

SUPER_ADMIN = "super_admin"
AUDIT_ACTION = "role_permissions.update"
OVERRIDE_AUDIT_ACTION = "user_permission_overrides.update"


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


# --- nehn-007: per-user overrides ------------------------------------------------------------------------------------------------------


def _active():
    return or_(UserPermissionOverride.expires_at.is_(None), UserPermissionOverride.expires_at > datetime.now(UTC))


def _key(row: UserPermissionOverride) -> str:
    return f"{row.resource}.{row.action}"


def override_out(row: UserPermissionOverride) -> dict:
    return {"permission": _key(row), "effect": row.effect, "reason": row.reason, "expires_at": row.expires_at, "created_at": row.created_at}


async def active_overrides(db: AsyncSession, user_id: UUID) -> list[UserPermissionOverride]:
    """The user's overrides still in force, by key. A row whose key has left the catalogue is not reported."""
    rows = await db.scalars(select(UserPermissionOverride).where(UserPermissionOverride.user_id == user_id, _active()).order_by(UserPermissionOverride.resource, UserPermissionOverride.action))
    keys = set(rbac.all_keys())
    return [row for row in rows if _key(row) in keys]


async def user_has_grant(db: AsyncSession, user: User, resource: str, action: str) -> bool:
    """The user's own active override for the key decides; otherwise their role does."""
    if action not in rbac.CATALOGUE.get(resource, {}).get("actions", ()):
        return False
    if user.role == SUPER_ADMIN:
        return True
    effect = await db.scalar(
        select(UserPermissionOverride.effect).where(UserPermissionOverride.user_id == user.id, UserPermissionOverride.resource == resource, UserPermissionOverride.action == action, _active())
    )
    if effect is not None:
        return effect == "allow"
    return await has_grant(db, user.role, resource, action)


async def user_grants(db: AsyncSession, user: User) -> list[str]:
    """The user's effective keys, sorted: (role grants + active allows) - active denies."""
    keys = set(await role_grants(db, user.role))
    if user.role == SUPER_ADMIN:
        return sorted(keys)
    for row in await active_overrides(db, user.id):
        if row.effect == "allow":
            keys.add(_key(row))
        else:
            keys.discard(_key(row))
    return sorted(keys)


async def override_report(db: AsyncSession) -> list[dict]:
    """Every override in force, with its user, by user name then key (U6: the report of active overrides)."""
    rows = await db.execute(
        select(UserPermissionOverride, User)
        .join(User, User.id == UserPermissionOverride.user_id)
        .where(_active())
        .order_by(User.full_name, User.id, UserPermissionOverride.resource, UserPermissionOverride.action)
    )
    keys = set(rbac.all_keys())
    return [{"user_id": user.id, "full_name": user.full_name, "email": user.email, "role": user.role, **override_out(row)} for row, user in rows if _key(row) in keys]


async def replace_user_overrides(db: AsyncSession, actor_id: UUID, user: User, items: list) -> None:
    """Replace the user's overrides with `items` (validated `UserPermissionOverrideIn`). An unchanged override keeps who set it and when;
    every other row of the user goes, expired ones too (their history is in the audit log). A real change is audited in the same
    transaction, a no-op writes nothing; a concurrent edit of the same user is a 409."""
    if user.role == SUPER_ADMIN:
        raise HTTPException(409, "A super admin always holds every permission and cannot have overrides")

    def snapshot(entries) -> list[dict]:
        return sorted(
            ({"permission": e["permission"], "effect": e["effect"], "reason": e["reason"], "expires_at": e["expires_at"].astimezone(UTC).isoformat() if e["expires_at"] else None} for e in entries),
            key=lambda e: e["permission"],
        )

    current = {_key(row): row for row in await active_overrides(db, user.id)}
    before = snapshot(override_out(row) for row in current.values())
    after = snapshot(item.model_dump() for item in items)
    if before == after:
        return
    unchanged = {entry["permission"] for entry in after if entry in before}
    kept = [current[key].id for key in unchanged]
    await db.execute(delete(UserPermissionOverride).where(UserPermissionOverride.user_id == user.id, UserPermissionOverride.id.not_in(kept)))
    for item in items:
        if item.permission in unchanged:
            continue
        resource, action = rbac.parse_key(item.permission)
        db.add(UserPermissionOverride(user_id=user.id, resource=resource, action=action, effect=item.effect, reason=item.reason, expires_at=item.expires_at, created_by_id=actor_id))
    db.add(AuditLog(user_id=actor_id, action=OVERRIDE_AUDIT_ACTION, entity_type="user", entity_id=str(user.id), metadata_json={"before": before, "after": after}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "These overrides were changed by someone else. Reload and try again.") from None
    logger.info(OVERRIDE_AUDIT_ACTION, extra={"extra_fields": {"actor_id": str(actor_id), "user_id": str(user.id), "permissions": [e["permission"] for e in after]}})

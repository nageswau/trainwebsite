from uuid import UUID

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.rbac import user_has_division, user_has_permission, user_has_role
from app.core.security import decode_token
from app.models import User


async def get_current_user(edusphere_access: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)) -> User:
    if not edusphere_access:
        raise HTTPException(401, "Not authenticated")
    try:
        p = decode_token(edusphere_access)
        uid = UUID(p["sub"])
        if p.get("type") != "access":
            raise ValueError()
    except Exception as exc:
        raise HTTPException(401, "Invalid session") from exc
    user = await db.scalar(
        select(User).where(User.id == uid, User.active.is_(True)).options(selectinload(User.role_assignments))
    )
    if not user:
        raise HTTPException(401, "User unavailable")
    return user


def require_division(*divisions: str):
    """Deny-by-default: 403 unless the caller holds an active assignment in one of `divisions`.

    Only `super_admin` (division="global") should be granted every division elsewhere in
    route wiring -- this dependency does not special-case it, per FND-002's rule that
    frontend/route-level convenience never substitutes for an explicit, checked grant.
    """

    async def _dependency(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
        if not await user_has_division(db, user.id, *divisions):
            raise HTTPException(403, "Not permitted for this division")
        return user

    return _dependency


def require_role(*roles: str):
    """Deny-by-default: 403 unless the caller holds an active, usable assignment in one of `roles`."""

    async def _dependency(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
        if not await user_has_role(db, user.id, *roles):
            raise HTTPException(403, "Not permitted for this role")
        return user

    return _dependency


def require_permission(permission: str):
    """Deny-by-default: 403 unless an active, usable assignment's role grants `permission`."""

    async def _dependency(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
        if not await user_has_permission(db, user.id, permission):
            raise HTTPException(403, "Insufficient permission")
        return user

    return _dependency

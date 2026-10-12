"""mgmt-001 (Management M13): who sees which tier of the Command Center. Every management route and serializer asks these helpers;
partner-only data (investments, capital, salaries per M2) is refused to `super_admin` and the accountant here, not only in the UI."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

OPERATIONAL_ROLES = frozenset({"partner", "super_admin"})  # operational dashboards, plans, tasks, meetings, discussions
FINANCE_ROLES = frozenset({"partner", "accountant"})  # ledger, finance dashboards, salaries
PARTNER_ONLY_ROLES = frozenset({"partner"})  # investments, capital accounts, everything
MANAGEMENT_ROLES = OPERATIONAL_ROLES | FINANCE_ROLES
NEW_ROLES = frozenset({"partner", "accountant"})  # global, created by a super_admin only (MG1)

NO_ACCESS = "Management access required"
PARTNER_ONLY = "Only partners can open this"


def can_view_operational(user: User) -> bool:
    return user.role in OPERATIONAL_ROLES


def can_view_finance(user: User) -> bool:
    return user.role in FINANCE_ROLES


def can_view_partner_only(user: User) -> bool:
    return user.role in PARTNER_ONLY_ROLES


def tiers(user: User) -> dict[str, bool]:
    return {"operational": can_view_operational(user), "finance": can_view_finance(user), "partner_only": can_view_partner_only(user)}


def require_management(user: User) -> User:
    if user.role not in MANAGEMENT_ROLES:
        raise HTTPException(403, NO_ACCESS)
    return user


def require_partner_only(user: User) -> User:
    if not can_view_partner_only(user):
        raise HTTPException(403, PARTNER_ONLY)
    return user


async def refuse_last_partner_deactivation(db: AsyncSession, user: User) -> None:
    """MG6, before any write. Every active partner row is locked first, so two admins deactivating the last two partners at once
    serialise and the second sees one left. 422, not 409: the Users page reads 409 as the trainer "confirm cascade" prompt."""
    if user.role != "partner":
        return
    active = (await db.scalars(select(User.id).where(User.role == "partner", User.active.is_(True)).with_for_update())).all()
    if all(partner_id == user.id for partner_id in active):
        raise HTTPException(422, "At least one partner must stay active")

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
# mgmt-027 (M14, spec MD6): the internal staff who can take part in a discussion, be responsible for a decision or own a task.
# Students, parents, agents, university reps, employers and school-side users are not EduSphere staff.
STAFF_ROLES = MANAGEMENT_ROLES | frozenset({
    "it_admin", "overseas_admin", "trainer", "placement_team", "placement_manager", "hr_team", "counselor", "academic_team",
    "career_counselor", "psychometric_team", "bdm", "bdm_manager", "telecaller", "telecaller_manager", "partnership_manager",
    "partnership_head",
})

# ccrm-034 (DEC-SCOPE-263, R1): the CRM reports carry no money, so the operational tier and the Overseas Admin read them.
CRM_REPORT_ROLES = OPERATIONAL_ROLES | frozenset({"overseas_admin"})

NO_ACCESS = "Management access required"
PARTNER_ONLY = "Only partners can open this"


def can_view_operational(user: User) -> bool:
    return user.role in OPERATIONAL_ROLES


def can_view_finance(user: User) -> bool:
    return user.role in FINANCE_ROLES


def can_view_partner_only(user: User) -> bool:
    return user.role in PARTNER_ONLY_ROLES


def can_view_university_commission(user: User) -> bool:
    """mgmt-006 (M3, U2 as amended; MG11): on management pages university commission is the partners'; the accountant never sees it.
    `partnership_access.COMMISSION_ROLES` stays as it is, so partners gain no partnership-module commission routes (MG2)."""
    return user.role in PARTNER_ONLY_ROLES


def tiers(user: User) -> dict[str, bool]:
    return {"operational": can_view_operational(user), "finance": can_view_finance(user), "partner_only": can_view_partner_only(user)}


def require_management(user: User) -> User:
    if user.role not in MANAGEMENT_ROLES:
        raise HTTPException(403, NO_ACCESS)
    return user


def require_crm_reports(user: User) -> User:
    if user.role not in CRM_REPORT_ROLES:
        raise HTTPException(403, "Management or Overseas Administrator access required")
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

"""Division-aware RBAC core (FND-002).

Deny-by-default: a request is only permitted if it matches an explicit grant below or an
active UserRoleAssignment row (app.models.UserRoleAssignment). Nothing here trusts the
frontend -- every check is meant to run again on the server for every protected request,
per RBAC_MATRIX.md and ARCHITECTURE.md §6.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRoleAssignment

# Coarse-grained permission bundles per role, inherited unchanged from the base codebase.
# require_permission() below is the framework entry point that resolves against these.
PERMISSIONS: dict[str, set[str]] = {
    "super_admin": {"*"},
    "it_admin": {"it:*", "content:*", "users:read", "users:write", "reports:read"},
    "it_student": {"it:student:self", "content:read", "support:self"},
    "trainer": {"it:training:manage", "it:students:assigned", "content:read"},
    "placement_team": {"it:placement:manage", "it:candidates:read", "reports:placement"},
    "hr_team": {"it:hiring:manage", "it:candidates:read", "reports:placement"},
    "overseas_admin": {"overseas:*", "content:*", "users:read", "users:write", "reports:read"},
    "overseas_student": {"overseas:student:self", "content:read", "support:self"},
    "counselor": {"overseas:students:manage", "overseas:applications:manage", "overseas:visa:manage", "reports:overseas"},
    "university_rep": {"overseas:university:applications", "overseas:university:offers", "reports:university"},
    "agent": {"overseas:agent:students", "overseas:agent:applications", "overseas:agent:commissions"},
    # Net-new roles per DATA_MODEL.md / RBAC_MATRIX.md -- no base-codebase equivalent.
    "employer": {"employer:self", "employer:jobs:own", "employer:candidates:read"},
    # School domain (SCH-003, DEC-SCOPE-011/012/013/014) -- own-institution/own-portfolio
    # scoping is enforced at the query layer (RBAC_MATRIX.md §2.12), not by these coarse
    # bundles alone. Deliberately distinct role identifiers from `trainer`/`coordinator`
    # (SCH-001-AC05, RBAC_MATRIX.md §2.12's role-name collision guard) even though none of
    # those two pre-existing roles is actually implemented as a real UserRoleAssignment
    # anywhere in this codebase today.
    "school_coordinator": {"school:coordinator:own_institution"},
    "school_principal": {"school:principal:own_institution:read"},
    "school_teacher": {"school:teacher:assigned:read"},
    "school_parent": {"school:parent:own_child:read"},
    # Service-delivery roles (SCH-004/005/006, DEC-ROLE-006) -- scoped to a school
    # portfolio (DEC-SCOPE-013, SchoolStaffAssignment), not a single institution; enforced
    # at the query layer, not by these coarse bundles alone.
    "academic_team": {"school:academic_team:portfolio"},
    "career_counselor": {"school:career_counselor:portfolio"},
    "psychometric_team": {"school:psychometric_team:portfolio"},
}


def has_permission(role: str, permission: str) -> bool:
    perms = PERMISSIONS.get(role, set())
    if "*" in perms or permission in perms:
        return True
    return permission.split(":", 1)[0] + ":*" in perms


def _assignment_is_usable(assignment: UserRoleAssignment) -> bool:
    """An assignment only grants access if active and, for role=agent, approved.

    This is the concrete enforcement of RBAC_MATRIX.md §2.8's deny rule: a Pending or
    Rejected Agent has zero grants under any permission/role/division check below, even
    though the User row itself is active and can log in.
    """

    if not assignment.is_active:
        return False
    if assignment.role == "agent" and assignment.approval_status != "approved":
        return False
    return True


def agent_is_approved(user) -> bool:
    """Sync check against an already-loaded `user.role_assignments` (eager-loaded by
    `get_current_user` for every request) -- AGT-001-AC02: a Pending/Rejected Agent must
    be denied even though the User row itself is active and can log in. Route-level
    checks in `workflows.py`/`portal.py` use `user.role` directly (a legacy column with
    no approval concept) rather than this module's own async `user_has_role`/
    `get_active_assignments`, so every one of those call sites must additionally call
    this for role="agent" -- it is not implied by passing the simpler role check.
    """

    if user.role != "agent":
        return True
    assignment = next((a for a in user.role_assignments if a.role == "agent" and a.division == user.division and a.is_active), None)
    return bool(assignment and assignment.approval_status == "approved")


async def get_active_assignments(db: AsyncSession, user_id: UUID) -> list[UserRoleAssignment]:
    rows = await db.scalars(
        select(UserRoleAssignment).where(UserRoleAssignment.user_id == user_id, UserRoleAssignment.is_active.is_(True))
    )
    return [a for a in rows if _assignment_is_usable(a)]


async def user_has_division(db: AsyncSession, user_id: UUID, *divisions: str) -> bool:
    assignments = await get_active_assignments(db, user_id)
    return any(a.division in divisions for a in assignments)


async def user_has_role(db: AsyncSession, user_id: UUID, *roles: str) -> bool:
    assignments = await get_active_assignments(db, user_id)
    return any(a.role in roles for a in assignments)


async def user_has_permission(db: AsyncSession, user_id: UUID, permission: str) -> bool:
    assignments = await get_active_assignments(db, user_id)
    return any(has_permission(a.role, permission) for a in assignments)

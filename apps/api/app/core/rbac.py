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
    # bdm-001 (DEC-SCOPE-055): BDM CRM. Type/own/team scope is enforced in services/bdm.py, not by these bundles alone.
    "bdm": {"bdm:self"},
    "bdm_manager": {"bdm:team"},
    # tel-001 (DEC-SCOPE-073): coarse bundles; self/team scope is enforced in services/telecaller.py.
    "telecaller": {"telecaller:self"},
    "telecaller_manager": {"telecaller:team"},
    # rec-001 (DEC-SCOPE-116, R2): `placement_team` is the recruiter (bundle above, unchanged); its manager's team scope is enforced
    # in services/recruiter.py.
    "placement_manager": {"placement:team"},
    # upc-001 (DEC-SCOPE-118): coarse bundles; self/team scope is enforced in services/partnership.py.
    "partnership_manager": {"partnership:self"},
    "partnership_head": {"partnership:team"},
    # mgmt-001 (Management M2/M5/M13): coarse bundles; the tiers are enforced in services/management_access.py.
    "partner": {"management:*"},
    "accountant": {"management:finance"},
    # nehn-030 (DEC-ROLE-003, DEC-SCOPE-293): the IT certificate coordinator; it reads certificates through the `certificates.view` grant.
    "coordinator": {"it:certificates:read"},
}


ROLES: tuple[str, ...] = tuple(PERMISSIONS)

# nehn-005 (DEC-SCOPE-281): the grant-based permission catalogue -- role x resource x action, held in `role_permissions` and checked by
# `deps.require_permission`. It lists only resources whose routes are wired (P1); each later module slice adds its own resource. A key
# is "<resource>.<action>"; anything not listed is denied.
ACTIONS = ("view", "add", "edit", "delete", "download", "approve", "review", "issue", "override", "configure", "manage")  # nehn-031 adds override, configure
CATALOGUE: dict[str, dict] = {
    "payments": {"label": "Payments", "actions": ("view", "add")},
    "discounts": {"label": "Payment discounts", "actions": ("add",)},
    "reports.telecaller": {"label": "Telecaller reports", "actions": ("view", "download")},
    # nehn-030: the coordinator portal's Certificates section; nehn-031 (DEC-SCOPE-297): issuing, the eligibility override, thresholds;
    # nehn-032 (DEC-SCOPE-302 S6): `manage` -- the certificate signatures (no default holder: super_admin only until granted).
    "certificates": {"label": "Certificates", "actions": ("view", "issue", "override", "configure", "manage")},
    # nehn-008 (DEC-SCOPE-300): a report's financial columns (fees, payments, discounts, commission), in its JSON and downloads alike.
    "field.financial": {"label": "Financial columns", "actions": ("view",)},
    # nehn-009 (DEC-SCOPE-303): the report library's training reports (the `enrollments` pilot; nehn-010 adds the rest).
    "reports.training": {"label": "Training reports", "actions": ("view", "download")},
    # nehn-018 (DEC-SCOPE-304): which student features unlock at which payment state.
    "student_access": {"label": "Student access rules", "actions": ("configure",)},
}
# The day-one grants, equal to the inline checks they replace (P3): admin.ensure_admin and telecaller_reports' REPORT_ROLES.
# super_admin holds every key implicitly and never has rows (P5). Migration 0196 seeds a frozen copy.
_PAYMENT_ADMIN = ("payments.view", "payments.add", "discounts.add")
_TELECALLER_REPORTS = ("reports.telecaller.view", "reports.telecaller.download")
_TRAINING_REPORTS = ("reports.training.view", "reports.training.download")  # nehn-009 (migration 0210 seeds it); a trainer's rows are own batches
DEFAULT_GRANTS: dict[str, tuple[str, ...]] = {
    "it_admin": _PAYMENT_ADMIN + _TELECALLER_REPORTS + ("certificates.configure", "student_access.configure") + _TRAINING_REPORTS,  # nehn-031 W2 (0204); nehn-018 (0211)
    "trainer": _TRAINING_REPORTS,
    "overseas_admin": _PAYMENT_ADMIN + _TELECALLER_REPORTS,
    "telecaller_manager": _TELECALLER_REPORTS,
    # nehn-030 (0201 seeds view); nehn-031 W3/W4 (0204 seeds issue, override): issuance is the coordinator's alone (DEC-ROLE-003).
    "coordinator": ("certificates.view", "certificates.issue", "certificates.override"),
    # nehn-008 F3 (migration 0207 seeds it): today's partnership commission readers (upc-001 U2), so no report changes on day one.
    "partnership_manager": ("field.financial.view",),
    "partnership_head": ("field.financial.view",),
}


def all_keys() -> list[str]:
    return [f"{resource}.{action}" for resource, entry in CATALOGUE.items() for action in entry["actions"]]


def parse_key(key: str) -> tuple[str, str]:
    """"reports.telecaller.view" -> ("reports.telecaller", "view"). Raises ValueError for a key outside the catalogue."""
    resource, _, action = key.rpartition(".")
    if action not in CATALOGUE.get(resource, {}).get("actions", ()):
        raise ValueError(f"Unknown permission: {key}")
    return resource, action


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


PENDING_MESSAGE = "Agent registration is pending approval"
SUSPENDED_MESSAGE = "Your agency's account is suspended"
DEACTIVATED_MESSAGE = "Your Master account is deactivated"


def agent_denial_reason(user) -> str | None:
    """AGN-001 (DEC-SCOPE-038 D6, spec E10): why an agent is denied every agent route, or None.

    Reads `user.agent_membership` (+ `.org`), eager-loaded by `get_current_user` on every request, so a suspension
    applies on the member's next request. The organisation's status is the gate (AGT-001-AC02 preserved: a pending or
    rejected organisation is denied with the same message as before). Route-level checks in `workflows.py`/`portal.py`
    use the legacy `user.role` column, so every one of those call sites must additionally call this for role="agent".
    Non-agents are never denied here."""

    if user.role != "agent":
        return None
    membership = user.agent_membership
    if membership is None:
        return PENDING_MESSAGE
    if membership.status != "active":
        return DEACTIVATED_MESSAGE
    if membership.org.status == "suspended":
        return SUSPENDED_MESSAGE
    if membership.org.status != "active":
        return PENDING_MESSAGE
    return None


def is_agent_staff(user) -> bool:
    """AGN-002 (DEC-SCOPE-040 S1/S2): a staff member of an agent organisation. Staff share `role='agent'` with Masters, so the
    Master-only actions (team management, commissions) call this. Reads the membership `get_current_user` eager-loads."""

    if user.role != "agent":
        return False
    membership = user.agent_membership
    return membership is not None and membership.role == "staff"


# AGN-003 (DEC-SCOPE-044): the two optional §6 rows. The column names on AgentOrgMember are also the API keys.
STAFF_PERMISSIONS = ("can_verify_documents", "can_view_reports")
REPORTS_REFUSED = "Your agency Master hasn't given you access to reports"
VERIFY_REFUSED = "Your agency Master hasn't given you permission to verify documents"
REVIEW_MASTER_ONLY = "Only an agency Master can reject documents or request changes"
REVIEW_REASON_REQUIRED = "Give a reason when you reject a document or ask for changes"  # AGN-009 (DEC-SCOPE-052 G1)


def agent_may(user, permission: str) -> bool:
    """AGN-003 (DEC-SCOPE-044 P1/P2): whether the caller may use an optional §6 row. Masters (and every non-staff caller -- route
    role checks run first) are never limited; staff follow their own flag. Reads the membership `get_current_user` eager-loads on
    every request, so a Master's change applies on the staff member's next request."""

    assert permission in STAFF_PERMISSIONS, permission
    if not is_agent_staff(user):
        return True
    return bool(getattr(user.agent_membership, permission))


def agent_permissions(user) -> dict[str, bool] | None:
    """The effective permissions an agency member's portal shows (GET /auth/me); None for anyone without a membership."""

    if user.role != "agent" or user.agent_membership is None:
        return None
    return {name: agent_may(user, name) for name in STAFF_PERMISSIONS}


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

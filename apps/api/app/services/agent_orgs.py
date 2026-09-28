"""AGN-001 / DEC-SCOPE-034 -- agent organisations (tenants) and their Master members.

Functions only -- no class layer (same shape as `services/provisioning.py`). Spec:
docs/superpowers/specs/2026-09-28-agn-001-multi-tenant-agent-crm-design.md.
"""

import re
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrg, AgentOrgMember, AuditLog, User, UserRoleAssignment

MASTER_LIMIT = 3
ORG_STATUSES = ("pending", "active", "rejected", "suspended")

_LATIN = re.compile(r"[A-Za-z]")


def derive_prefix_base(name: str | None) -> str:
    """D5: the first three Latin letters, uppercased, padded with X; no Latin letters -> AGT."""
    letters = _LATIN.findall(name or "")
    if not letters:
        return "AGT"
    return "".join(letters[:3]).upper().ljust(3, "X")


def pick_prefix(base: str, taken: set[str]) -> str:
    """D5 collision rule: the base if free, else the lowest free base+N for N >= 2."""
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def member_code(prefix: str, seq: int) -> str:
    return f"{prefix}-M{seq:03d}"


_PREFIX_ATTEMPTS = 5


async def next_free_prefix(db: AsyncSession, base: str) -> str:
    taken = set((await db.scalars(select(AgentOrg.prefix).where(AgentOrg.prefix.like(f"{base}%")))).all())
    return pick_prefix(base, taken)


async def _status_from_assignment(db: AsyncSession, user: User) -> str:
    """D10 mapping, shared by the migration backfill and runtime creation: approved -> active, else pending."""
    approval = await db.scalar(
        select(UserRoleAssignment.approval_status).where(UserRoleAssignment.user_id == user.id, UserRoleAssignment.division == "overseas", UserRoleAssignment.role == "agent")
    )
    return "active" if approval == "approved" else "pending"


async def ensure_agent_org(db: AsyncSession, user: User, *, agency_name: str | None = None, status: str | None = None) -> AgentOrgMember:
    """No commit. Idempotent: returns the user's membership, creating their organisation + Master M001 when missing (E7).

    Two creations racing for one prefix are settled by `uq_agent_orgs_prefix`: the loser's savepoint rolls back and it
    retries with the next free prefix. Two creations racing for one USER are settled by `uq_agent_org_members_user`: the
    loser re-reads and returns the winner's membership."""
    existing = await db.scalar(select(AgentOrgMember).where(AgentOrgMember.user_id == user.id))
    if existing:
        return existing
    name = (agency_name or "").strip()[:160] or user.full_name
    status = status or await _status_from_assignment(db, user)
    for _ in range(_PREFIX_ATTEMPTS):
        prefix = await next_free_prefix(db, derive_prefix_base(name))
        try:
            async with db.begin_nested():
                org = AgentOrg(name=name, prefix=prefix, status=status, master_seq=1)
                db.add(org)
                await db.flush()
                member = AgentOrgMember(org_id=org.id, user_id=user.id, role="master", seq=1, code=member_code(prefix, 1), status="active")
                db.add(member)
                await db.flush()
            return member
        except IntegrityError as exc:
            if "uq_agent_org_members_user" in str(exc.orig):
                winner = await db.scalar(select(AgentOrgMember).where(AgentOrgMember.user_id == user.id))
                if winner:
                    return winner
    raise HTTPException(409, "Please try again")


TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "approve": (frozenset({"pending", "rejected"}), "active"),
    "reject": (frozenset({"pending"}), "rejected"),
    "suspend": (frozenset({"active"}), "suspended"),
    "reinstate": (frozenset({"suspended"}), "active"),
}


async def lock_org(db: AsyncSession, org_id) -> AgentOrg:
    """Row lock on the organisation; serialises every status change and member change for it."""
    org = await db.scalar(select(AgentOrg).where(AgentOrg.id == org_id).with_for_update().execution_options(populate_existing=True))
    if not org:
        raise HTTPException(404, "Agent organisation not found")
    return org


async def set_org_status(db: AsyncSession, org: AgentOrg, status: str, actor: User, *, write_through: bool) -> None:
    """No commit. E11: approve/reject also set the Master assignments' approval_status; suspend/reinstate do not."""
    now = datetime.now(UTC)
    org.status = status
    org.status_changed_by_user_id = actor.id
    org.status_changed_at = now
    if write_through:
        await db.execute(
            update(UserRoleAssignment)
            .where(UserRoleAssignment.role == "agent", UserRoleAssignment.division == "overseas", UserRoleAssignment.user_id.in_(select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == org.id)))
            .values(approval_status="approved" if status == "active" else "rejected", approved_by_user_id=actor.id, approved_at=now)
        )


async def transition_org(db: AsyncSession, org_id, action: str, actor: User) -> AgentOrg:
    """No commit. D6/D7: validate the move under the row lock, change status, audit in the same transaction."""
    org = await lock_org(db, org_id)
    allowed, target = TRANSITIONS[action]
    if org.status not in allowed:
        raise HTTPException(409, f"Cannot {action} an organisation that is {org.status}")
    previous = org.status
    await set_org_status(db, org, target, actor, write_through=action in {"approve", "reject"})
    db.add(AuditLog(user_id=actor.id, action=f"agent_org.{action}", entity_type="agent_org", entity_id=str(org.id), outcome=target, metadata_json={"from": previous}))
    return org


def org_member_ids(user: User) -> Select:
    """The user ids whose agent rows the caller may see: every member of the caller's organisation (D1). A user with no
    membership (super_admin passing `_require`) keeps today's self-scope."""
    membership = user.agent_membership
    if membership is None:
        return select(User.id).where(User.id == user.id)
    return select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == membership.org_id)


async def member_user_ids(db: AsyncSession, user: User) -> set:
    return set((await db.scalars(org_member_ids(user))).all())


async def notification_recipients(db: AsyncSession, agent: User) -> list[User]:
    """D12: every active Master of the agent's organisation; the agent alone when it has no membership."""
    org_id = await db.scalar(select(AgentOrgMember.org_id).where(AgentOrgMember.user_id == agent.id))
    if org_id is None:
        return [agent]
    return list(
        (await db.scalars(select(User).join(AgentOrgMember, AgentOrgMember.user_id == User.id).where(AgentOrgMember.org_id == org_id, AgentOrgMember.status == "active").order_by(AgentOrgMember.seq))).all()
    )

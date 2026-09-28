"""AGN-001 / DEC-SCOPE-034 -- agent organisations (tenants) and their Master members.

Functions only -- no class layer (same shape as `services/provisioning.py`). Spec:
docs/superpowers/specs/2026-09-28-agn-001-multi-tenant-agent-crm-design.md.
"""

import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrg, AgentOrgMember, User, UserRoleAssignment

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

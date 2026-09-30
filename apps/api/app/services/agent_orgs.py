"""AGN-001 / DEC-SCOPE-038 -- agent organisations (tenants) and their Master members; AGN-002 / DEC-SCOPE-040 -- their staff.

Functions only -- no class layer (same shape as `services/provisioning.py`). Specs:
docs/superpowers/specs/2026-09-28-agn-001-multi-tenant-agent-crm-design.md,
docs/superpowers/specs/2026-09-30-agn-002-staff-logins-design.md.
"""

import logging
import math
import re
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from fastapi import HTTPException
from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrg, AgentOrgMember, AuditLog, User, UserRoleAssignment
from app.services.provisioning import (
    flush_unique_email,
    issue_welcome_token,
    provisioning_statuses,
    resend_wait_seconds,
    revoke_welcome_tokens,
    unusable_password_hash,
)

logger = logging.getLogger("app.agent_orgs")

MASTER_LIMIT = 3
MASTER, STAFF = "master", "staff"  # AgentOrgMember.role (AGN-002 adds staff)

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


def staff_code(prefix: str, seq: int) -> str:
    return f"{prefix}-S{seq:03d}"


_PREFIX_ATTEMPTS = 5


async def next_free_prefix(db: AsyncSession, base: str) -> str:
    taken = set((await db.scalars(select(AgentOrg.prefix).where(AgentOrg.prefix.like(f"{base}%")))).all())
    return pick_prefix(base, taken)


async def _status_from_assignment(db: AsyncSession, user: User) -> str:
    """D10 mapping (the migration backfill applies the same rule): approved -> active, else pending."""
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
            detail = str(exc.orig)
            if "uq_agent_org_members_user" in detail:
                winner = await db.scalar(select(AgentOrgMember).where(AgentOrgMember.user_id == user.id))
                if winner:
                    return winner
                raise
            if "uq_agent_orgs_prefix" not in detail:
                raise  # anything but a prefix clash is a real error, never a silent retry (final review #3)
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


async def count_active_masters(db: AsyncSession, org_id) -> int:
    """Active Masters only; staff never count (AGN-002 S2)."""
    return await db.scalar(
        select(func.count()).select_from(AgentOrgMember).where(AgentOrgMember.org_id == org_id, AgentOrgMember.role == MASTER, AgentOrgMember.status == "active")
    )


INVITE_LIMIT = 10
INVITE_WINDOW = timedelta(hours=24)


INVITE_ACTIONS = ("agent_org.master_invite", "agent_org.master_invite_rejected")  # QA-10: failed attempts count too
STAFF_ACTION_LIMIT = 20
STAFF_ACTIONS = ("agent_org.staff_create", "agent_org.staff_create_rejected", "agent_org.staff_reset")


async def _wait_seconds(db: AsyncSession, org_id, actions: tuple[str, ...], limit: int) -> int:
    """Seconds before this agency may perform another of `actions`; 0 means allowed. Counted from the audit rows (the
    change-password throttle's no-new-table pattern), so the count is shared by every API instance and invite -> deactivate ->
    invite loops cannot turn the platform's mail into a relay (security review, 2026-09-29). Master invites (R1, budget
    INVITE_LIMIT) and staff creations + resets (AGN-002 E2, budget STAFF_ACTION_LIMIT) are separate budgets. Runs under the
    organisation lock, so it is race-free."""
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.entity_type == "agent_org", AuditLog.entity_id == str(org_id), AuditLog.action.in_(actions), AuditLog.created_at > now - INVITE_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    ).all()
    if len(recent) < limit:
        return 0
    return max(1, math.ceil((recent[-1] + INVITE_WINDOW - now).total_seconds()))


async def _reject_existing_email(db: AsyncSession, org_id, actor_id, *, action: str, event: str) -> NoReturn:
    """Browser QA-10: a Master invite or staff creation for an existing address is audited and COUNTED toward its throttle, so
    probing which emails have accounts is capped per agency per day. Committed before the 409 (a raised request would otherwise
    roll the row back). The address itself is never recorded."""
    db.add(AuditLog(user_id=actor_id, action=action, entity_type="agent_org", entity_id=str(org_id), outcome="rejected", metadata_json={"reason": "email_exists"}))
    await db.commit()
    logger.info(event, extra={"extra_fields": {"org_id": str(org_id), "actor_id": str(actor_id), "reason": "email_exists"}})
    raise HTTPException(409, "Email already exists")


async def invite_master(db: AsyncSession, org: AgentOrg, actor: User, *, full_name: str, email: str, phone: str | None):
    """No commit; `org` must be locked. D4/D9/E5/E6: a real agent account with an unusable password + a DEC-SCOPE-019
    welcome token; the next code is master_seq + 1. At most INVITE_LIMIT invites per agency per INVITE_WINDOW."""
    org_id, actor_id = org.id, actor.id  # plain values: a rollback below expires the ORM objects
    if await count_active_masters(db, org_id) >= MASTER_LIMIT:
        raise HTTPException(422, "This agency already has 3 active Masters")
    wait = await _wait_seconds(db, org_id, INVITE_ACTIONS, INVITE_LIMIT)
    if wait:
        logger.warning("agent_org_invite_throttled", extra={"extra_fields": {"org_id": str(org_id), "actor_id": str(actor_id), "wait_seconds": wait}})
        raise HTTPException(429, f"This agency has made {INVITE_LIMIT} invite attempts in the last 24 hours. Try again later.", headers={"Retry-After": str(wait)})
    email = email.lower().strip()
    rejected = {"action": "agent_org.master_invite_rejected", "event": "agent_org_invite_rejected"}
    if await db.scalar(select(User.id).where(User.email == email)):
        await _reject_existing_email(db, org_id, actor_id, **rejected)
    now = datetime.now(UTC)
    user = User(email=email, password_hash=unusable_password_hash(), full_name=full_name, role="agent", division="overseas", phone=phone, active=True, email_verified=False, profile={"registration_source": "agent_master_invite"})
    db.add(user)
    try:
        await flush_unique_email(db)  # a collision rolls back (releasing the org lock) and raises 409
    except HTTPException:
        await _reject_existing_email(db, org_id, actor_id, **rejected)
    db.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", is_active=True, assigned_by_user_id=actor.id, approval_status="approved", approved_by_user_id=actor.id, approved_at=now))
    org.master_seq += 1
    member = AgentOrgMember(org_id=org.id, user_id=user.id, role="master", seq=org.master_seq, code=member_code(org.prefix, org.master_seq), status="active", invited_by_user_id=actor.id)
    db.add(member)
    await db.flush()
    issued = await issue_welcome_token(db, user=user, issued_by=actor)
    db.add(AuditLog(user_id=actor.id, action="agent_org.master_invite", entity_type="agent_org", entity_id=str(org.id), outcome="invited", metadata_json={"member_id": str(member.id), "code": member.code}))
    return member, user, issued


async def _check_staff_budget(db: AsyncSession, org_id, actor_id) -> None:
    wait = await _wait_seconds(db, org_id, STAFF_ACTIONS, STAFF_ACTION_LIMIT)
    if wait:
        logger.warning("agent_org_staff_throttled", extra={"extra_fields": {"org_id": str(org_id), "actor_id": str(actor_id), "wait_seconds": wait}})
        raise HTTPException(
            429, f"This agency has created or reset {STAFF_ACTION_LIMIT} staff logins in the last 24 hours. Try again later.", headers={"Retry-After": str(wait)}
        )


async def create_staff(db: AsyncSession, org: AgentOrg, actor: User, *, full_name: str, email: str, phone: str | None):
    """No commit; `org` must be locked. AGN-002 (S2-S4): a real agent account with an unusable password, an approved agent
    assignment, a staff member numbered from `staff_seq` (never reused) and a DEC-SCOPE-019 welcome token."""
    org_id, actor_id = org.id, actor.id  # plain values: a rollback below expires the ORM objects
    await _check_staff_budget(db, org_id, actor_id)
    email = email.lower().strip()
    rejected = {"action": "agent_org.staff_create_rejected", "event": "agent_org_staff_create_rejected"}
    if await db.scalar(select(User.id).where(User.email == email)):
        await _reject_existing_email(db, org_id, actor_id, **rejected)
    now = datetime.now(UTC)
    user = User(
        email=email, password_hash=unusable_password_hash(), full_name=full_name, role="agent", division="overseas", phone=phone, active=True, email_verified=False,
        profile={"registration_source": "agent_staff_create"},
    )
    db.add(user)
    try:
        await flush_unique_email(db)  # a collision rolls back (releasing the org lock) and raises 409
    except HTTPException:
        await _reject_existing_email(db, org_id, actor_id, **rejected)
    db.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", is_active=True, assigned_by_user_id=actor_id, approval_status="approved", approved_by_user_id=actor_id, approved_at=now))
    org.staff_seq += 1
    member = AgentOrgMember(org_id=org_id, user_id=user.id, role=STAFF, seq=org.staff_seq, code=staff_code(org.prefix, org.staff_seq), status="active", invited_by_user_id=actor_id)
    db.add(member)
    await db.flush()
    issued = await issue_welcome_token(db, user=user, issued_by=actor)
    _staff_audit(db, actor, org, member, "staff_create", "created")
    return member, user, issued


def _staff_audit(db: AsyncSession, actor: User, org: AgentOrg, member: AgentOrgMember, action: str, outcome: str, **extra) -> None:
    """S6: every staff action, in the caller's transaction; ids and codes only (never an email, password or token)."""
    db.add(
        AuditLog(
            user_id=actor.id, action=f"agent_org.{action}", entity_type="agent_org", entity_id=str(org.id), outcome=outcome,
            metadata_json={"member_id": str(member.id), "code": member.code, **extra},
        )
    )


async def _staff_member(db: AsyncSession, org: AgentOrg, member_id) -> tuple[AgentOrgMember, User]:
    """The caller's organisation's staff member, else 404 -- another agency's member and every Master read the same (no
    disclosure). The user row is locked after the organisation (lock order: org -> user -> tokens, as reset-password/Re-send)."""
    member = await db.scalar(
        select(AgentOrgMember).where(AgentOrgMember.id == member_id, AgentOrgMember.org_id == org.id, AgentOrgMember.role == STAFF).execution_options(populate_existing=True)
    )
    if not member:
        raise HTTPException(404, "Staff member not found")
    user = await db.get(User, member.user_id, with_for_update=True, populate_existing=True)
    return member, user


async def update_staff(db: AsyncSession, org: AgentOrg, member_id, actor: User, changes: dict) -> tuple[AgentOrgMember, User]:
    """No commit; `org` locked. S4: `changes` holds only `full_name` / `phone`; audited by field name, never by value."""
    member, user = await _staff_member(db, org, member_id)
    for field, value in changes.items():
        setattr(user, field, value)
    _staff_audit(db, actor, org, member, "staff_update", "updated", fields=sorted(changes))
    return member, user


async def deactivate_staff(db: AsyncSession, org: AgentOrg, member_id, actor: User) -> tuple[AgentOrgMember, User]:
    """No commit; `org` locked. S5 + E6: login disabled (every API refuses on the next request), sessions ended by the version,
    any open set-password link revoked."""
    member, user = await _staff_member(db, org, member_id)
    if member.status != "active":
        raise HTTPException(409, "Already deactivated")
    member.status, member.deactivated_at, member.deactivated_by_user_id = "deactivated", datetime.now(UTC), actor.id
    user.active = False
    user.session_version += 1
    await revoke_welcome_tokens(db, user.id)
    _staff_audit(db, actor, org, member, "staff_deactivate", "deactivated")
    return member, user


async def reactivate_staff(db: AsyncSession, org: AgentOrg, member_id, actor: User) -> tuple[AgentOrgMember, User]:
    """No commit; `org` locked. S5 / E3: restores the login only. Open links stay revoked (as admin reactivation); a staff
    member who never set a password is sent a new link with Reset."""
    member, user = await _staff_member(db, org, member_id)
    if member.status == "active":
        raise HTTPException(409, "Already active")
    member.status, member.deactivated_at, member.deactivated_by_user_id = "active", None, None
    user.active = True
    await revoke_welcome_tokens(db, user.id)
    _staff_audit(db, actor, org, member, "staff_reactivate", "reactivated")
    return member, user


async def reset_staff(db: AsyncSession, org: AgentOrg, member_id, actor: User):
    """No commit; `org` locked. S3: the password stops working, every session ends, and a new DEC-SCOPE-019 link (which revokes
    the previous one) goes to the staff member's own address. Counts toward the staff budget; E7: per-account 60 s cooldown."""
    member, user = await _staff_member(db, org, member_id)
    if member.status != "active":
        raise HTTPException(409, "Reactivate this staff member first")
    await _check_staff_budget(db, org.id, actor.id)
    wait = await resend_wait_seconds(db, user.id)
    if wait:
        logger.warning("agent_org_staff_reset_cooldown", extra={"extra_fields": {"org_id": str(org.id), "member_id": str(member.id), "wait_seconds": wait}})
        raise HTTPException(429, f"A link was just sent; wait {wait} seconds before resetting again", headers={"Retry-After": str(wait)})
    user.password_hash = unusable_password_hash()
    user.session_version += 1
    issued = await issue_welcome_token(db, user=user, issued_by=actor)
    _staff_audit(db, actor, org, member, "staff_reset", "reset")
    return member, user, issued


async def deactivate_master(db: AsyncSession, org: AgentOrg, member_id, actor: User) -> tuple[AgentOrgMember, User]:
    """No commit; `org` must be locked. D8/E3: never the last active Master; login disabled; open invite revoked."""
    member = await db.scalar(
        select(AgentOrgMember).where(AgentOrgMember.id == member_id, AgentOrgMember.org_id == org.id, AgentOrgMember.role == MASTER).execution_options(populate_existing=True)
    )
    if not member:
        raise HTTPException(404, "Master not found")
    if member.status != "active":
        raise HTTPException(409, "Already deactivated")
    if await count_active_masters(db, org.id) <= 1:
        raise HTTPException(422, "An agency must keep at least one active Master")
    # Review #6 (user decision 2026-09-29): some OTHER active Master must be able to sign in -- login enabled and
    # invite accepted (password set) -- or an unaccepted/expired invite would lock the whole agency out.
    others = (
        await db.scalars(
            select(User.id)
            .join(AgentOrgMember, AgentOrgMember.user_id == User.id)
            .where(AgentOrgMember.org_id == org.id, AgentOrgMember.role == MASTER, AgentOrgMember.status == "active", AgentOrgMember.id != member.id, User.active.is_(True))
        )
    ).all()
    pending = await provisioning_statuses(db, others)
    if not any(uid not in pending for uid in others):
        raise HTTPException(422, "At least one other Master must have accepted their invite first")
    member.status = "deactivated"
    member.deactivated_at = datetime.now(UTC)
    member.deactivated_by_user_id = actor.id
    target = await db.get(User, member.user_id, populate_existing=True)
    target.active = False
    await revoke_welcome_tokens(db, target.id)
    db.add(AuditLog(user_id=actor.id, action="agent_org.master_deactivate", entity_type="agent_org", entity_id=str(org.id), outcome="deactivated", metadata_json={"member_id": str(member.id), "code": member.code}))
    return member, target


async def notification_recipients(db: AsyncSession, agent: User) -> list[User]:
    """D12: every active Master (never staff, AGN-002) of the agent's organisation; the agent alone when it has no membership."""
    org_id = await db.scalar(select(AgentOrgMember.org_id).where(AgentOrgMember.user_id == agent.id))
    if org_id is None:
        return [agent]
    return list(
        (
            await db.scalars(
                select(User)
                .join(AgentOrgMember, AgentOrgMember.user_id == User.id)
                .where(AgentOrgMember.org_id == org_id, AgentOrgMember.role == MASTER, AgentOrgMember.status == "active")
                .order_by(AgentOrgMember.seq)
            )
        ).all()
    )

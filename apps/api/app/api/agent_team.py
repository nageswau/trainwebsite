"""AGN-001 -- an agency's Master team: list, invite, deactivate (DEC-SCOPE-038 D4, D8, D9; spec §5.4).
AGN-002 -- the agency's staff logins: list, create, edit, deactivate, reactivate, reset (DEC-SCOPE-040; spec §6).

Only an active Master of an ACTIVE organisation reaches these routes (same gate as every agent route, plus the member role);
every change locks the organisation row so codes, the throttles, the 3-Master limit and the last-Master rule hold under
concurrency. Set-password links are delivered after the commit and their raw token is never returned to a Master.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rbac import PENDING_MESSAGE, SUSPENDED_MESSAGE, agent_denial_reason, is_agent_staff
from app.models import AgentOrg, AgentOrgMember, User
from app.schemas import AgentMasterInvite, AgentStaffCreate, AgentStaffUpdate
from app.services.agent_orgs import (
    MASTER_LIMIT,
    create_staff,
    deactivate_master,
    deactivate_staff,
    invite_master,
    lock_org,
    org_masters,
    reactivate_staff,
    reset_staff,
    update_staff,
)
from app.services.provisioning import deliver_welcome_link, provisioning_statuses

logger = logging.getLogger("app.agent_orgs")

router = APIRouter(prefix="/workflows/overseas/agent/team", tags=["agent-team"])

MASTER_ONLY = "Only an agency Master can manage the team"


def _require_master(user: User) -> AgentOrgMember:
    if user.role != "agent" or user.division != "overseas":
        raise HTTPException(403, "This role cannot perform this operation")
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)
    if is_agent_staff(user):  # AGN-002 (S1): staff never manage the team
        raise HTTPException(403, MASTER_ONLY)
    return user.agent_membership


def _member_out(member: AgentOrgMember, member_user: User, pending: set, caller: User) -> dict:
    return {
        "id": member.id,
        "code": member.code,
        "full_name": member_user.full_name,
        "email": member_user.email,
        "status": member.status,
        "invite_pending": member_user.id in pending,
        "is_you": member_user.id == caller.id,
    }


async def _locked_active_org(db: AsyncSession, membership: AgentOrgMember):
    org = await lock_org(db, membership.org_id)
    if org.status != "active":  # suspended between the gate check and the lock
        raise HTTPException(403, SUSPENDED_MESSAGE if org.status == "suspended" else PENDING_MESSAGE)
    return org


@router.get("")
async def team(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _require_master(user)
    org = membership.org
    rows = (await db.execute(org_masters(org.id))).all()
    pending = set(await provisioning_statuses(db, [u.id for _, u in rows]))
    return {"org": {"id": org.id, "name": org.name, "prefix": org.prefix, "status": org.status}, "masters": [_member_out(m, u, pending, user) for m, u in rows], "limit": MASTER_LIMIT}


@router.post("/masters", status_code=201)
async def invite(payload: AgentMasterInvite, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _require_master(user)
    org = await _locked_active_org(db, membership)
    member, invited, issued = await invite_master(db, org, user, full_name=payload.full_name, email=payload.email, phone=payload.phone)
    out = _member_out(member, invited, {invited.id}, user)
    await db.commit()
    return {"member": out, **await _deliver(invited, issued, user)}


@router.post("/masters/{member_id}/deactivate")
async def deactivate(member_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _require_master(user)
    org = await _locked_active_org(db, membership)
    member, target = await deactivate_master(db, org, member_id, user)
    out = _member_out(member, target, set(), user)
    await db.commit()
    return {"member": out}


# --- AGN-002: staff -----------------------------------------------------------------------------------------------------------------


def _staff_out(member: AgentOrgMember, staff: User, statuses: dict) -> dict:
    """AGN-002 member shape; `setup` is the DEC-SCOPE-019 provisioning status (None once the staff member has a password)."""
    return {"id": member.id, "code": member.code, "full_name": staff.full_name, "email": staff.email, "phone": staff.phone, "status": member.status, "setup": statuses.get(staff.id)}


async def _deliver(target: User, issued, actor: User) -> dict:
    """After the commit. Only an admin may see the dev/test raw link token; a Master must never be able to set another
    account's password (AGN-001 invite, AGN-002 S3)."""
    delivery = await deliver_welcome_link(user=target, issued=issued, issued_by=actor)
    delivery.pop("development_welcome_token", None)
    return delivery


async def _staff_org(db: AsyncSession, user: User) -> AgentOrg:
    """The calling Master's organisation, row-locked and re-checked `active` (every staff change runs under it)."""
    return await _locked_active_org(db, _require_master(user))


async def _commit_staff_change(db: AsyncSession, event: str, org: AgentOrg, user: User, member: AgentOrgMember, staff: User, statuses: dict) -> dict:
    """Build the response BEFORE the commit (the commit expires the ORM objects), commit, then log ids/codes only."""
    out, org_id = _staff_out(member, staff, statuses), str(org.id)
    await db.commit()
    logger.info(event, extra={"extra_fields": {"org_id": org_id, "actor_id": str(user.id), "member_id": str(out["id"]), "code": out["code"]}})
    return out


@router.get("/staff")
async def staff_list(limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The agency's staff, in code order, `{items, total, limit, offset}` (the organisation-list shape)."""
    membership = _require_master(user)
    scope = (AgentOrgMember.org_id == membership.org_id, AgentOrgMember.role == "staff")
    total = await db.scalar(select(func.count()).select_from(AgentOrgMember).where(*scope))
    rows = (await db.execute(select(AgentOrgMember, User).join(User, User.id == AgentOrgMember.user_id).where(*scope).order_by(AgentOrgMember.seq).limit(limit).offset(offset))).all()
    statuses = await provisioning_statuses(db, [u.id for _, u in rows])
    return {"items": [_staff_out(m, u, statuses) for m, u in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("/staff", status_code=201)
async def create_staff_login(payload: AgentStaffCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await _staff_org(db, user)
    member, staff, issued = await create_staff(db, org, user, full_name=payload.full_name, email=payload.email, phone=payload.phone)
    out = await _commit_staff_change(db, "agent_org_staff_created", org, user, member, staff, {staff.id: "pending_setup"})
    return {"member": out, **await _deliver(staff, issued, user)}


@router.patch("/staff/{member_id}")
async def edit_staff(member_id: UUID, payload: AgentStaffUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await _staff_org(db, user)
    member, staff = await update_staff(db, org, member_id, user, payload.model_dump(exclude_unset=True))
    return {"member": await _commit_staff_change(db, "agent_org_staff_updated", org, user, member, staff, await provisioning_statuses(db, [staff.id]))}


@router.post("/staff/{member_id}/deactivate")
async def deactivate_staff_login(member_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await _staff_org(db, user)
    member, staff = await deactivate_staff(db, org, member_id, user)
    return {"member": await _commit_staff_change(db, "agent_org_staff_deactivated", org, user, member, staff, await provisioning_statuses(db, [staff.id]))}


@router.post("/staff/{member_id}/reactivate")
async def reactivate_staff_login(member_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await _staff_org(db, user)
    member, staff = await reactivate_staff(db, org, member_id, user)
    return {"member": await _commit_staff_change(db, "agent_org_staff_reactivated", org, user, member, staff, await provisioning_statuses(db, [staff.id]))}


@router.post("/staff/{member_id}/reset")
async def reset_staff_login(member_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await _staff_org(db, user)
    member, staff, issued = await reset_staff(db, org, member_id, user)
    out = await _commit_staff_change(db, "agent_org_staff_reset", org, user, member, staff, {staff.id: "pending_setup"})
    return {"member": out, **await _deliver(staff, issued, user)}

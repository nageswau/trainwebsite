"""AGN-001 -- an agency's Master team: list, invite, deactivate (DEC-SCOPE-034 D4, D8, D9; spec §5.4).

Only an active Master of an ACTIVE organisation reaches these routes (same gate as every agent route); every change
locks the organisation row so the 3-Master limit and the last-Master rule hold under concurrency.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rbac import PENDING_MESSAGE, SUSPENDED_MESSAGE, agent_denial_reason
from app.models import AgentOrgMember, User
from app.schemas import AgentMasterInvite
from app.services.agent_orgs import MASTER_LIMIT, deactivate_master, invite_master, lock_org
from app.services.provisioning import deliver_welcome_link, provisioning_statuses

router = APIRouter(prefix="/workflows/overseas/agent/team", tags=["agent-team"])


def _require_master(user: User) -> AgentOrgMember:
    if user.role != "agent" or user.division != "overseas":
        raise HTTPException(403, "This role cannot perform this operation")
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)
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
    rows = (await db.execute(select(AgentOrgMember, User).join(User, User.id == AgentOrgMember.user_id).where(AgentOrgMember.org_id == org.id).order_by(AgentOrgMember.seq))).all()
    pending = set(await provisioning_statuses(db, [u.id for _, u in rows]))
    return {"org": {"id": org.id, "name": org.name, "prefix": org.prefix, "status": org.status}, "masters": [_member_out(m, u, pending, user) for m, u in rows], "limit": MASTER_LIMIT}


@router.post("/masters", status_code=201)
async def invite(payload: AgentMasterInvite, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _require_master(user)
    org = await _locked_active_org(db, membership)
    member, invited, issued = await invite_master(db, org, user, full_name=payload.full_name, email=payload.email, phone=payload.phone)
    out = _member_out(member, invited, {invited.id}, user)
    await db.commit()
    delivery = await deliver_welcome_link(user=invited, issued=issued, issued_by=user)
    # Only an admin may see the dev/test raw link token; a Master must never be able to set the invitee's password.
    delivery.pop("development_welcome_token", None)
    return {"member": out, **delivery}


@router.post("/masters/{member_id}/deactivate")
async def deactivate(member_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _require_master(user)
    org = await _locked_active_org(db, membership)
    member, target = await deactivate_master(db, org, member_id, user)
    out = _member_out(member, target, set(), user)
    await db.commit()
    return {"member": out}

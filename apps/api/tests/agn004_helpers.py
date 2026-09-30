"""AGN-004 test helpers. Staff are inserted directly with AGN-002's data shape (AGN-002 owns the Staff API)."""

import re

from app.models import AgentOrg, AgentOrgMember, AgentStudent, UserRoleAssignment
from tests.agn001_helpers import mk_user

RECORDS = "/api/v1/workflows/overseas/agent/crm/students"


async def mk_staff(db, org: AgentOrg, *, full_name: str = "Staff Member", active: bool = True) -> dict:
    org = await db.get(AgentOrg, org.id, populate_existing=True)
    user = await mk_user(db, role="agent", full_name=full_name, active=active)
    db.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", approval_status="approved"))
    org.staff_seq += 1
    member = AgentOrgMember(org_id=org.id, user_id=user.id, role="staff", seq=org.staff_seq, code=f"{org.prefix}-S{org.staff_seq:03d}", status="active" if active else "deactivated")
    db.add(member)
    await db.commit()
    return {"user": user, "member": member}


async def mk_record(db, *, agent, full_name: str, email: str | None = None, phone: str | None = None, assigned_member=None, status: str = "active") -> AgentStudent:
    row = AgentStudent(
        agent_id=agent.id,
        student_id=None,
        status=status,
        full_name=full_name,
        email=email,
        phone=phone,
        phone_digits=(re.sub(r"\D", "", phone or "") or None),
        assigned_member_id=assigned_member.id if assigned_member else None,
    )
    db.add(row)
    await db.commit()
    return row

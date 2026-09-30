"""AGN-002 test helpers: a staff member inserted directly (the API path is tested in test_agn_002_staff.py)."""

from app.models import AgentOrg, AgentOrgMember, UserRoleAssignment
from tests.agn001_helpers import mk_user

STAFF = "/api/v1/workflows/overseas/agent/team/staff"


async def mk_staff(db, org: AgentOrg, *, full_name: str = "Staff Member", active: bool = True) -> dict:
    org = await db.get(AgentOrg, org.id, populate_existing=True)
    user = await mk_user(db, role="agent", full_name=full_name, active=active)
    db.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", approval_status="approved"))
    org.staff_seq += 1
    member = AgentOrgMember(
        org_id=org.id, user_id=user.id, role="staff", seq=org.staff_seq, code=f"{org.prefix}-S{org.staff_seq:03d}", status="active" if active else "deactivated"
    )
    db.add(member)
    await db.commit()
    return {"user": user, "member": member}

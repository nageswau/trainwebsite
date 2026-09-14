from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rbac import agent_is_approved
from app.models import User
from app.services.portal import section_payload

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/{division}/{role}/{section}")
async def portal(division: str, role: str, section: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    route_role = {
        "student": "it_student" if division == "it" else "overseas_student",
        "trainer": "trainer",
        "placement": "placement_team",
        "hr": "hr_team",
        "admin": "it_admin" if division == "it" else "overseas_admin",
        "counselor": "counselor",
        "university": "university_rep",
        "agent": "agent",
        "super_admin": "super_admin",
    }.get(role, role)
    if user.role != "super_admin" and (user.division != division or user.role != route_role):
        raise HTTPException(403, "Role/division mismatch")
    # AGT-001-AC02: a Pending/Rejected Agent cannot view data, even though the role/
    # division check above already passed (that check reads the legacy `User.role`
    # column, which has no approval concept of its own).
    if not agent_is_approved(user):
        raise HTTPException(403, "Agent registration is pending approval")
    payload = await section_payload(db, user, section)
    if payload is None:
        raise HTTPException(404, "Workspace not found")
    return payload

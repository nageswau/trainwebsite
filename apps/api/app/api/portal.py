from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rbac import REPORTS_REFUSED, agent_denial_reason, agent_may, is_agent_staff
from app.models import User
from app.services import application_filters
from app.services.portal import section_payload

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/{division}/{role}/{section}")
async def portal(division: str, role: str, section: str, request: Request, agency: str | None = None, counselor: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)
    # AGN-002 (DEC-SCOPE-040 S1): the agency's team and commissions are Master-only pages.
    if is_agent_staff(user) and section in {"team", "commissions"}:
        raise HTTPException(403, "Only an agency Master can open this page")
    # AGN-003 (DEC-SCOPE-044 P1): Reports is an optional §6 row -- off for staff until their Master switches it on.
    if section == "reports" and user.role == "agent" and not agent_may(user, "can_view_reports"):
        raise HTTPException(403, REPORTS_REFUSED)
    # AGN-023 (DEC-SCOPE-090 H11): optional list filters; a filter on the wrong section or role is a 422, never ignored.
    # A repeated filter key would otherwise keep only the last value silently (B7).
    if any(len(request.query_params.getlist(key)) > 1 for key in ("agency", "counselor")):
        raise HTTPException(422, "Unknown filter value")
    filters = await application_filters.parse(db, user, section, agency, counselor)
    payload = await section_payload(db, user, section, filters=filters)
    if payload is None:
        raise HTTPException(404, "Workspace not found")
    return payload

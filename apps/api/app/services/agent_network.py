"""AGN-022 -- Overseas Admin's agent network figures (DEC-SCOPE-063; spec §4, §5.1).

Read-only: nothing here writes, locks or commits. Every function takes organisation ids, never a user -- the admin is not a member
of the agencies it reads. Students, applications and commissions belong to an organisation through the `agent_id` of one of its
members, exactly as AGN-001 scopes them, and the definitions (active student, non-withdrawn application, enrolled) are AGN-018's,
so an agency's own dashboard and this screen cannot disagree."""

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrgMember, AgentStudent, OverseasApplication
from app.services.agent_applications import WITHDRAWN

# School-bridged applications are not agency applications (`with_owner`, A12).
NETWORK_APPLICATION = OverseasApplication.school_student_id.is_(None)


def members_of(org_id) -> Select:
    """User ids of every member of one organisation (any member status): the org's side of every `agent_id` join."""
    return select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == org_id)


async def org_counts(db: AsyncSession, org_ids) -> dict:
    """`{org_id: {staff_count, students, applications, enrollments}}` for the given orgs -- three statements grouped by
    organisation (never one per org); an org with nothing gets zeros."""
    ids = list(org_ids)
    if not ids:
        return {}
    result = {oid: {"staff_count": 0, "students": 0, "applications": 0, "enrollments": 0} for oid in ids}
    org = AgentOrgMember.org_id
    staff = select(org, func.count()).where(org.in_(ids), AgentOrgMember.role == "staff", AgentOrgMember.status == "active").group_by(org)
    students = (
        select(org, func.count())
        .join(AgentStudent, AgentStudent.agent_id == AgentOrgMember.user_id)
        .where(org.in_(ids), AgentStudent.status == "active")
        .group_by(org)
    )
    applications = (
        select(org, func.count(case((OverseasApplication.status != WITHDRAWN, 1))), func.count(case((OverseasApplication.status == "enrolled", 1))))
        .join(OverseasApplication, OverseasApplication.agent_id == AgentOrgMember.user_id)
        .where(org.in_(ids), NETWORK_APPLICATION)
        .group_by(org)
    )
    for oid, n in (await db.execute(staff)).all():
        result[oid]["staff_count"] = n
    for oid, n in (await db.execute(students)).all():
        result[oid]["students"] = n
    for oid, open_apps, enrolled in (await db.execute(applications)).all():
        result[oid]["applications"], result[oid]["enrollments"] = open_apps, enrolled
    return result

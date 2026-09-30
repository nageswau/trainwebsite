"""AGN-004 / DEC-SCOPE-041 -- agent students: scoping, students with no login, duplicate warning.

Functions only (the shape of services/agent_orgs.py); write functions never commit -- the router locks the organisation, writes,
audits and commits. Spec: docs/superpowers/specs/2026-09-30-agn-004-agent-students-design.md.
"""

import logging
import re

from sqlalchemy import ColumnElement, Select, select

from app.core.rbac import is_agent_staff
from app.models import AgentStudent, OverseasApplication, User
from app.services.agent_orgs import org_member_ids

logger = logging.getLogger("app.agent_students")

PHONE_MIN_DIGITS = 7


def student_scope(user: User) -> list[ColumnElement]:
    """The agent_students rows the caller may see: the organisation's (AGN-001 D1); a staff member only those assigned to them
    (G4). For a Master this is exactly the AGN-001 clause."""
    clauses = [AgentStudent.agent_id.in_(org_member_ids(user))]
    if is_agent_staff(user):
        clauses.append(AgentStudent.assigned_member_id == user.agent_membership.id)
    return clauses


def visible_student_user_ids(user: User) -> Select:
    """User ids of the linked students (with an account) the caller may see."""
    return select(AgentStudent.student_id).where(*student_scope(user), AgentStudent.student_id.is_not(None))


def application_scope(user: User) -> list[ColumnElement]:
    """The organisation's applications; a staff member only those of their assigned students (G4)."""
    clauses = [OverseasApplication.agent_id.in_(org_member_ids(user))]
    if is_agent_staff(user):
        clauses.append(OverseasApplication.student_id.in_(visible_student_user_ids(user)))
    return clauses


def phone_digits(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")[:20]
    return digits or None

"""AGN-008 / DEC-SCOPE-050 -- an agency's applications for its students, with or without a login; and the NULL-safe owner join
every shared application list uses.

Functions only (the services/agent_students.py shape): nothing here commits -- the router locks, writes, audits and commits.
Spec: docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md.
"""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import Select, func

from app.models import AgentStudent, OverseasApplication, User

# DEC-WF-001 / OVS-003: the confirmed stage sequence (moved here from api/workflows.py, which imports it back -- one definition).
OVERSEAS_APPLICATION_STAGES = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"]
WITHDRAWN = "withdrawn"  # A1: terminal; only an agent sets it (spec §5.3)
AGENT_MAX_STAGE = "status_tracking"  # A4: `enrolled` stays with counselor, university and admin
DEFAULT_NEXT_ACTION = "Complete profile and required document checklist"


class Owner(NamedTuple):
    """An application's student: `id` is their account (None when the student has no login); `full_name` is the account's name,
    else the agency record's."""

    id: UUID | None
    full_name: str | None


OWNER_NAME = func.coalesce(User.full_name, AgentStudent.full_name)


def with_owner(stmt: Select) -> Select:
    """Add the owner (account row + display name) to a query over overseas_applications as OUTER joins, so an application of a
    student with no login is listed instead of silently dropped (A6). School-bridged rows stay out, exactly as the old inner join on
    users left them out (A12)."""
    return (
        stmt.add_columns(User, OWNER_NAME)
        .outerjoin(User, User.id == OverseasApplication.student_id)
        .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
        .where(OverseasApplication.school_student_id.is_(None))
    )


def owned(rows) -> list[tuple]:
    """`with_owner` rows with the trailing (account, name) pair folded into one `Owner`, so `for a, u, s in rows: s.full_name`
    keeps working; `s.id` is None for a student with no login."""
    return [(*row[:-2], Owner(row[-2].id if row[-2] is not None else None, row[-1])) for row in rows]

"""AGN-021 / DEC-SCOPE-046 -- a Master reads one staff member's student-journey work from the audit log.

Spec: docs/superpowers/specs/2026-10-01-agn-021-staff-activity-design.md §4-§5. Read-only: no new audit writes, no lock, no cache
(A4: an action is visible on the next request). Subjects are things the Master may already read -- every entity a staff member can
act on is inside the agency (AGN-004 G4) and agency membership is permanent -- and only names/labels leave this module: never
notes, field values, emails or other metadata (A3).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrgMember, AgentStudent, AuditLog, OverseasApplication, StudentDocument, University, User
from app.services.agent_applications import OWNER_NAME

# A1: student-journey work only. Every action is written today with the staff user as `user_id` (spec §4 table).
STAFF_ACTIVITY_ACTIONS = (
    "agent_student.create",
    "agent_student.update",
    "agent_student.duplicate_override",
    "agent_student.counseling",  # AGN-006 (DEC-SCOPE-048 C7): field names only, like an edit
    # AGN-007 (DEC-SCOPE-049): shortlist work on a student; the agent_student subject resolver already names the student.
    "agent_student.shortlist_add",
    "agent_student.shortlist_update",
    "agent_student.shortlist_remove",
    # AGN-016 (DEC-SCOPE-053): task work on a student; the subject is the student, never the task's title.
    "agent_student.task_add",
    "agent_student.task_update",
    "agent_student.task_complete",
    "agent_student.task_cancel",
    "agent.student_link",
    "overseas.application.create",
    "overseas.application.update",
    "overseas.application.advance",
    "overseas.application.withdraw",
    "overseas.application.offer",  # AGN-010 (DEC-SCOPE-056): ids and field names only, like the other application rows
    # AGN-012 (DEC-SCOPE-057): visa work on an application; the view shows field names only, never the decision.
    "overseas.application.visa_start",
    "overseas.application.visa_update",
    "overseas.application.visa_advance",
    "overseas.application.visa_decision",
    "document.upload",
    "document.verify",
)
MAX_ACTIVITY_OFFSET = 10_000
UNAVAILABLE = "No longer available"


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _joined(*parts: str | None) -> str:
    return " — ".join(p for p in parts if p) or UNAVAILABLE


async def _subjects(db: AsyncSession, rows: list[AuditLog]) -> dict[tuple[str, uuid.UUID], str]:
    """At most one batched query per entity type on the page; keyed by (entity_type, entity UUID)."""
    wanted: dict[str, set[uuid.UUID]] = {"agent_student": set(), "overseas_application": set(), "student_document": set()}
    for row in rows:
        parsed = _uuid(row.entity_id)
        if parsed and row.entity_type in wanted:
            wanted[row.entity_type].add(parsed)
    names: dict[tuple[str, uuid.UUID], str] = {}
    if wanted["agent_student"]:
        query = select(AgentStudent.id, AgentStudent.full_name, User.full_name).outerjoin(User, User.id == AgentStudent.student_id).where(AgentStudent.id.in_(wanted["agent_student"]))
        for rid, own, linked in (await db.execute(query)).all():
            names[("agent_student", rid)] = _joined(own or linked)
    if wanted["overseas_application"]:
        query = (
            select(OverseasApplication.id, OWNER_NAME, University.name)
            .outerjoin(User, User.id == OverseasApplication.student_id)
            .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
            .outerjoin(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.id.in_(wanted["overseas_application"]))
        )
        for rid, student, university in (await db.execute(query)).all():
            names[("overseas_application", rid)] = _joined(student, university)
    if wanted["student_document"]:
        query = select(StudentDocument.id, StudentDocument.document_type, User.full_name).outerjoin(User, User.id == StudentDocument.student_id).where(StudentDocument.id.in_(wanted["student_document"]))
        for rid, document_type, student in (await db.execute(query)).all():
            names[("student_document", rid)] = _joined(document_type, student)
    return names


def _fields(row: AuditLog) -> list[str] | None:
    """Edited field NAMES for an edit, a counseling save or a task edit only (A3; AGN-006 C7; AGN-016); anything that is not a list of
    strings is dropped."""
    if row.action not in ("agent_student.update", "agent_student.counseling", "agent_student.task_update"):
        return None
    value = (row.metadata_json or {}).get("fields")
    return [f for f in value if isinstance(f, str)] if isinstance(value, list) else None


async def staff_activity_page(db: AsyncSession, member: AgentOrgMember, *, limit: int, offset: int) -> dict:
    """One page of the staff member's allow-listed audit rows, newest first (`id` breaks equal timestamps: rows written in one
    transaction share `created_at`), in the organisation-list shape `{items, total, limit, offset}`."""
    where = (AuditLog.user_id == member.user_id, AuditLog.action.in_(STAFF_ACTIVITY_ACTIONS))
    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*where))
    rows = list((await db.scalars(select(AuditLog).where(*where).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset))).all())
    names = await _subjects(db, rows)
    items = [
        {"id": row.id, "at": row.created_at, "action": row.action, "subject": names.get((row.entity_type, _uuid(row.entity_id)), UNAVAILABLE), "fields": _fields(row)}
        for row in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}

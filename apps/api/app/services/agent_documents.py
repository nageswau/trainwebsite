"""AGN-009 / DEC-SCOPE-051 -- agency documents: scope, history events, stored files, list items.

Functions only (the shape of services/agent_applications.py); write functions never commit -- the router locks, writes, audits and
commits once. Spec: docs/superpowers/specs/2026-10-02-agn-009-agent-documents-design.md.
"""

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentStudent, DocumentEvent, DocumentRequest, OverseasApplication, StudentDocument, User
from app.services.agent_students import application_scope, student_scope, visible_student_user_ids


def document_scope(user: User) -> list[ColumnElement]:
    """The documents an agency member may reach. A document attached to an application follows the application (the AGN-003 review
    rule); an unattached one follows its owner -- the agency record, or the linked student's account. Staff therefore reach only
    their assigned students' documents (G4). Never compares a NULL `student_id` (`== None` would compile to IS NULL and match every
    no-login student)."""
    scoped_applications = select(OverseasApplication.id).where(*application_scope(user))
    scoped_records = select(AgentStudent.id).where(*student_scope(user))
    return [
        or_(
            and_(StudentDocument.application_id.is_not(None), StudentDocument.application_id.in_(scoped_applications)),
            and_(
                StudentDocument.application_id.is_(None),
                or_(StudentDocument.agent_student_id.in_(scoped_records), StudentDocument.student_id.in_(visible_student_user_ids(user))),
            ),
        )
    ]


async def in_scope(db: AsyncSession, user: User, document_id) -> bool:
    return bool(await db.scalar(select(StudentDocument.id).where(StudentDocument.id == document_id, *document_scope(user))))


def add_event(
    db: AsyncSession,
    *,
    event: str,
    actor: User | None,
    document: StudentDocument | None = None,
    request: DocumentRequest | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    notes: str | None = None,
    file_key: str | None = None,
) -> None:
    """One history row, in the caller's transaction (append-only; never updated)."""
    db.add(
        DocumentEvent(
            document_id=document.id if document else None,
            request_id=request.id if request else None,
            event=event,
            actor_user_id=actor.id if actor else None,
            from_status=from_status,
            to_status=to_status,
            notes=notes,
            file_key=file_key,
        )
    )

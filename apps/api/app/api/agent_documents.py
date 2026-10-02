"""AGN-009 -- an agency's documents for its students, with or without a login (DEC-SCOPE-051; spec §4).

Masters see the agency's documents; staff only those of students assigned to them (G4); anything outside the caller's scope is 404.
Every write locks the organisation row first, then the student, the request and the document (AGN-004's lock order), writes its
history and audit rows in the same transaction and commits once. A file is stored before the commit under a server-generated key
and deleted again if the commit fails (ENH-025's order). Review stays on the AGN-003 route (`PATCH /workflows/overseas/documents/
{id}/verify`), download on the OVS-005 route; both are scope-checked through `services.agent_documents.document_scope`.
"""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AgentOrgMember, AgentStudent, AuditLog, StudentDocument, User
from app.services import agent_documents as svc
from app.services.agent_applications import load_scoped as load_scoped_application
from app.services.agent_orgs import lock_active_org
from app.services.agent_students import load_scoped as load_scoped_student

logger = logging.getLogger("app.agent_documents")

router = APIRouter(prefix="/workflows/overseas/agent/crm", tags=["agent-documents"])

DocumentType = Literal["Passport", "Academic certificates", "Transcripts", "English test", "CV", "SOP", "LOR", "Financial documents", "Other"]
NOT_AGENCY_DOCUMENT = "Only documents your agency uploaded can be replaced"
DECIDED_BY_STAFF = "A counselor or administrator has reviewed this document, so it can't be replaced"
APPLICATION_MISMATCH = "Document student does not match the application"


def _audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed, SEC-001); ids, types and statuses only."""
    db.add(AuditLog(user_id=user.id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata or {}))


def _log(event: str, membership: AgentOrgMember, user: User, *, level: int = logging.INFO, **extra) -> None:
    logger.log(level, event, extra={"extra_fields": {"org_id": str(membership.org_id), "actor_id": str(user.id), **{k: str(v) for k, v in extra.items()}}})


async def _throttle(db: AsyncSession, user: User, membership: AgentOrgMember, actions: tuple[str, ...], limit: int, message: str) -> None:
    wait = await svc.wait_seconds(db, user, actions, limit)
    if wait:
        _log("agent_document_throttled", membership, user, level=logging.WARNING, wait_seconds=wait, action=actions[0])
        raise HTTPException(429, message, headers={"Retry-After": str(wait)})


async def _writable_record(db: AsyncSession, user: User, agent_student_id) -> AgentStudent:
    """The caller's student, locked, or 404; an archived student's documents are read-only (AGN-008 A15)."""
    record = await load_scoped_student(db, user, agent_student_id, lock=True)
    if record.status == "archived":
        raise HTTPException(409, svc.ARCHIVED)
    return record


@router.post("/documents", status_code=201)
async def upload_document(
    agent_student_id: UUID = Form(...),
    document_type: DocumentType = Form(...),
    document_label: str | None = Form(None, max_length=200),
    application_id: UUID | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = _gate(user)
    label = svc.clean_label(document_type, document_label)
    data, content_type, filename = await svc.read_upload(file)
    await lock_active_org(db, membership.org_id)  # serialises the throttle count for the agency
    await _throttle(db, user, membership, svc.UPLOAD_ACTIONS, svc.UPLOAD_LIMIT, svc.UPLOAD_THROTTLED)
    record = await _writable_record(db, user, agent_student_id)
    if application_id is not None:
        application = await load_scoped_application(db, user, application_id)  # 404 outside scope
        if application.agent_student_id != record.id and (record.student_id is None or application.student_id != record.student_id):
            raise HTTPException(422, APPLICATION_MISMATCH)
    key = svc.store(data, content_type)
    try:
        item = StudentDocument(
            agent_student_id=record.id,
            student_id=record.student_id,
            application_id=application_id,
            document_type=document_type,
            document_label=label,
            file_url=key,
            verification_status="pending",
            original_filename=filename,
            content_type=content_type,
            file_size=len(data),
            uploaded_by_user_id=user.id,
        )
        db.add(item)
        await db.flush()
        svc.add_event(db, event="uploaded", actor=user, document=item, to_status="pending")
        _audit(db, user, "document.upload", "student_document", item.id, {"agent_student_id": str(record.id), "document_type": document_type})
        await db.commit()
    except Exception:  # nothing was written: the stored object goes too
        await db.rollback()
        svc.discard(key)
        raise
    _log("agent_document_uploaded", membership, user, document_id=item.id, agent_student_id=record.id)
    return {"document": await svc.item_by_id(db, user, item.id)}


@router.put("/documents/{document_id}/file")
async def replace_document_file(document_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """G6: a new file on the same document, back to `pending`; the old object is kept and named in the `replaced` event."""
    membership = _gate(user)
    data, content_type, filename = await svc.read_upload(file)
    await lock_active_org(db, membership.org_id)
    await _throttle(db, user, membership, svc.UPLOAD_ACTIONS, svc.UPLOAD_LIMIT, svc.UPLOAD_THROTTLED)
    owner = (await svc.load_scoped(db, user, document_id)).agent_student_id  # 404 outside scope, before any lock on the student
    if owner is None:
        raise HTTPException(409, NOT_AGENCY_DOCUMENT)
    await _writable_record(db, user, owner)
    item = await svc.load_scoped(db, user, document_id, lock=True)
    if svc.decided_by_staff(item, await svc.reviewer_role(db, item)):
        raise HTTPException(409, DECIDED_BY_STAFF)
    key = svc.store(data, content_type)
    old_key, old_status = item.file_url, item.verification_status
    try:
        item.file_url, item.content_type, item.original_filename, item.file_size = key, content_type, filename, len(data)
        item.verification_status, item.verified_by_id, item.reviewer_notes, item.uploaded_by_user_id = "pending", None, None, user.id
        svc.add_event(db, event="replaced", actor=user, document=item, from_status=old_status, to_status="pending", file_key=old_key)
        _audit(db, user, "document.replace", "student_document", item.id, {"from_status": old_status})
        await db.commit()
    except Exception:  # the row keeps its old file; the new object goes
        await db.rollback()
        svc.discard(key)
        raise
    _log("agent_document_replaced", membership, user, document_id=item.id, from_status=old_status)
    return {"document": await svc.item_by_id(db, user, item.id)}

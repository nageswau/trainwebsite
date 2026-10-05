"""AGN-009 -- an agency's documents for its students, with or without a login (DEC-SCOPE-052; spec §4).

Masters see the agency's documents; staff only those of students assigned to them (G4); anything outside the caller's scope is 404.
Every write locks the organisation row first, then the student, the request and the document (AGN-004's lock order), writes its
history and audit rows in the same transaction and commits once. A file is stored before the commit under a server-generated key
and deleted again if the commit fails (ENH-025's order). Review stays on the AGN-003 route (`PATCH /workflows/overseas/documents/
{id}/verify`), download on the OVS-005 route; both are scope-checked through `services.agent_documents.document_scope`.
"""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AgentOrgMember, AgentStudent, AuditLog, DocumentRequest, StudentDocument, User
from app.schemas import AgentDocumentRequestCreate, AgentUploadDocumentType
from app.services import agent_documents as svc
from app.services import agent_notifications as notices
from app.services.agent_applications import load_scoped as load_scoped_application
from app.services.agent_orgs import lock_active_org
from app.services.agent_students import load_scoped as load_scoped_student

logger = logging.getLogger("app.agent_documents")

router = APIRouter(prefix="/workflows/overseas/agent/crm", tags=["agent-documents"])

NOT_AGENCY_DOCUMENT = "Only documents your agency uploaded can be replaced"
DECIDED_BY_STAFF = "A counselor or administrator has reviewed this document, so it can't be replaced"
APPLICATION_MISMATCH = "Document student does not match the application"
OFFER_LETTER_NEEDS_APPLICATION = "Choose the application this offer letter belongs to"  # AGN-010 O3


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


async def _open_request_of(db: AsyncSession, user: User, request_id, record: AgentStudent) -> DocumentRequest:
    """The caller's open request for this student, locked (after the student: the lock order), or 404/422/409."""
    request = await svc.load_request(db, user, request_id, lock=True)
    if request.agent_student_id != record.id:
        raise HTTPException(422, svc.REQUEST_OTHER_STUDENT)
    if request.status != "open":
        raise HTTPException(409, svc.REQUEST_CLOSED)
    return request


async def _writable_record(db: AsyncSession, user: User, agent_student_id) -> AgentStudent:
    """The caller's student, locked, or 404; an archived student's documents are read-only (AGN-008 A15)."""
    record = await load_scoped_student(db, user, agent_student_id, lock=True)
    if record.status == "archived":
        raise HTTPException(409, svc.ARCHIVED)
    return record


async def _filter_record(db: AsyncSession, user: User, student: UUID | None) -> AgentStudent | None:
    return None if student is None else await load_scoped_student(db, user, student)  # 404 outside scope


@router.get("/documents")
async def list_documents(
    view: Literal["pending", "uploaded"] = "uploaded",
    student: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    return await svc.list_page(db, user, view=view, record=await _filter_record(db, user, student), limit=limit, offset=offset)


@router.post("/documents", status_code=201)
async def upload_document(
    agent_student_id: UUID = Form(...),
    document_type: AgentUploadDocumentType = Form(...),
    document_label: str | None = Form(None, max_length=200),
    application_id: UUID | None = Form(None),
    request_id: UUID | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = _gate(user)
    label = svc.clean_label(document_type, document_label)
    if document_type == svc.OFFER_LETTER and application_id is None:
        raise HTTPException(422, OFFER_LETTER_NEEDS_APPLICATION)
    data, content_type, filename = await svc.read_upload(file)
    await lock_active_org(db, membership.org_id)  # serialises the throttle count for the agency
    await _throttle(db, user, membership, svc.UPLOAD_ACTIONS, svc.UPLOAD_LIMIT, svc.UPLOAD_THROTTLED)
    record = await _writable_record(db, user, agent_student_id)
    if application_id is not None:
        application = await load_scoped_application(db, user, application_id)  # 404 outside scope
        if application.agent_student_id != record.id and (record.student_id is None or application.student_id != record.student_id):
            raise HTTPException(422, APPLICATION_MISMATCH)
    request = await _open_request_of(db, user, request_id, record) if request_id is not None else None
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
            fulfils_request_id=request.id if request else None,
        )
        db.add(item)
        await db.flush()
        svc.add_event(db, event="uploaded", actor=user, document=item, to_status="pending")
        if request is not None:  # G5: fulfilled at upload time, whatever type was uploaded (the uploader's explicit choice)
            svc.close_request(request, "fulfilled", user)
            svc.add_event(db, event="fulfilled", actor=user, document=item, request=request, to_status="fulfilled")
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


@router.get("/documents/{document_id}/history")
async def document_history(
    document_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    return await svc.history_page(db, await svc.load_scoped(db, user, document_id), limit=limit, offset=offset)


@router.get("/document-requests")
async def list_requests(
    status: Literal["open", "all"] = "open",
    student: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    return await svc.request_page(db, user, status=status, record=await _filter_record(db, user, student), limit=limit, offset=offset)


@router.post("/document-requests", status_code=201)
async def create_request(payload: AgentDocumentRequestCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """G4: Master or Staff (within scope) ask for an additional document; one open request per type and label."""
    membership = _gate(user)
    label = svc.clean_label(payload.document_type, payload.document_label)
    note = (payload.note or "").strip() or None
    await lock_active_org(db, membership.org_id)  # serialises the throttle and the duplicate check for the agency
    await _throttle(db, user, membership, svc.REQUEST_ACTIONS, svc.REQUEST_LIMIT, svc.REQUEST_THROTTLED)
    record = await _writable_record(db, user, payload.agent_student_id)
    if await svc.open_request_exists(db, record, payload.document_type, label):
        raise HTTPException(409, svc.REQUEST_EXISTS)
    request = DocumentRequest(agent_student_id=record.id, document_type=payload.document_type, document_label=label, note=note, status="open", requested_by_user_id=user.id)
    db.add(request)
    await db.flush()
    svc.add_event(db, event="requested", actor=user, request=request, to_status="open", notes=note)
    await notices.document_requested(db, record, payload.document_type, user)  # AGN-017 (DEC-SCOPE-059): never the label or note
    _audit(db, user, "document_request.create", "document_request", request.id, {"agent_student_id": str(record.id), "document_type": payload.document_type})
    await db.commit()
    _log("agent_document_requested", membership, user, request_id=request.id, agent_student_id=record.id)
    return {"request": await svc.request_by_id(db, user, request.id)}


@router.post("/document-requests/{request_id}/cancel")
async def cancel_request(request_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    await lock_active_org(db, membership.org_id)
    owner = (await svc.load_request(db, user, request_id)).agent_student_id  # 404 outside scope, before any lock on the student
    await _writable_record(db, user, owner)
    request = await svc.load_request(db, user, request_id, lock=True)
    if request.status != "open":
        raise HTTPException(409, svc.REQUEST_CLOSED)
    svc.close_request(request, "cancelled", user)
    svc.add_event(db, event="cancelled", actor=user, request=request, from_status="open", to_status="cancelled")
    _audit(db, user, "document_request.cancel", "document_request", request.id)
    await db.commit()
    _log("agent_document_request_cancelled", membership, user, request_id=request.id)
    return {"request": await svc.request_by_id(db, user, request.id)}

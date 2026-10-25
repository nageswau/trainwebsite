"""ccrm-020 (DEC-SCOPE-262) -- a counselor's / Overseas Admin's document requests to a direct student (`document_requests.student_user_id`).

R1 a staff rejection of the fulfilling document reopens the request; R2 a checklist item's request marks the item Requested and the
student's upload is linked to it; R5 one open request per student, application, type and label; R8 `overdue` = open and past the due date
(IST). Agency requests (AGN-009, `agent_student_id`) never pass through here. Functions only; never commits (the routes do).
Spec: docs/superpowers/specs/2026-10-25-ccrm-020-document-requests-design.md.
"""

from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.document_checklists import STATUS_LABELS
from app.models import ApplicationChecklistItem, DocumentEvent, DocumentRequest, OverseasApplication, StudentDocument, University, User
from app.schemas import StudentDocumentRequestCreate
from app.services import application_checklists as checklists
from app.services.agent_documents import REQUEST_CLOSED, REQUEST_EXISTS, add_event, clean_label, close_request

INDIA = ZoneInfo("Asia/Kolkata")
REQUEST_NOT_FOUND = "Request not found"
DUE_IN_PAST = "Choose a due date from today onwards"
NOT_THE_STUDENTS_APPLICATION = "Choose an application of this student"
# R1: the review outcomes that send the student back to upload again (ccrm-021 codes; legacy inputs are mapped before this is read).
REOPENING = frozenset({"incomplete", "reupload_required"})
_Requester = aliased(User)


def today() -> date:
    return datetime.now(UTC).astimezone(INDIA).date()


def name(request: DocumentRequest) -> str:
    return request.document_label or request.document_type


def _stmt() -> Select:
    # browser QA-01: why a request is open again -- the note of its latest reopen (R1) event
    review_note = (
        select(DocumentEvent.notes)
        .where(DocumentEvent.request_id == DocumentRequest.id, DocumentEvent.event == "requested", DocumentEvent.from_status == "fulfilled")
        .order_by(DocumentEvent.seq.desc())
        .limit(1)
        .scalar_subquery()
    )
    return (
        select(DocumentRequest, _Requester.full_name, OverseasApplication.application_code, University.name, StudentDocument, review_note)
        .outerjoin(_Requester, _Requester.id == DocumentRequest.requested_by_user_id)
        .outerjoin(OverseasApplication, OverseasApplication.id == DocumentRequest.application_id)
        .outerjoin(University, University.id == OverseasApplication.university_id)
        .outerjoin(StudentDocument, StudentDocument.fulfils_request_id == DocumentRequest.id)
    )


def _item(row: tuple, now: date) -> dict:
    request, requester, application_code, university, document, review_note = row
    return {
        "id": request.id,
        "document_type": request.document_type,
        "document_label": request.document_label,
        "name": name(request),
        "note": request.note,
        "review_note": review_note if request.status == "open" else None,
        "status": request.status,
        "due_date": request.due_date,
        "overdue": request.status == "open" and request.due_date is not None and request.due_date < now,
        "application_id": request.application_id,
        "application_code": application_code,
        "university": university,
        "checklist_item_id": request.checklist_item_id,
        "requested_by": requester,
        "created_at": request.created_at,
        "closed_at": request.closed_at,
        "document": None
        if document is None
        else {
            "id": document.id,
            "original_filename": document.original_filename,
            "verification_status": document.verification_status,
            "status_label": STATUS_LABELS.get(document.verification_status, document.verification_status),
        },
    }


async def view(db: AsyncSession, request_id: UUID) -> dict:
    row = (await db.execute(_stmt().where(DocumentRequest.id == request_id).execution_options(populate_existing=True))).one()
    return _item(tuple(row), today())


async def page(db: AsyncSession, student_id: UUID, *, status: str, limit: int, offset: int) -> dict:
    """Open requests by due date, then the closed ones newest first (browser QA-02); `status=open` keeps only the open ones."""
    clauses = [DocumentRequest.student_user_id == student_id]
    if status == "open":
        clauses.append(DocumentRequest.status == "open")
    is_open = DocumentRequest.status == "open"
    order = [is_open.desc(), case((is_open, DocumentRequest.due_date)), DocumentRequest.created_at.desc(), DocumentRequest.id]
    total = await db.scalar(select(func.count()).select_from(DocumentRequest).where(*clauses))
    rows = (await db.execute(_stmt().where(*clauses).order_by(*order).limit(limit).offset(offset))).all()
    now = today()
    return {"items": [_item(tuple(r), now) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


async def lock_student(db: AsyncSession, student: User) -> None:
    """Serialises one student's requests, so the R5 duplicate check cannot race."""
    await db.execute(select(User.id).where(User.id == student.id).with_for_update())


async def create(db: AsyncSession, user: User, student: User, payload: StudentDocumentRequestCreate, application: OverseasApplication | None) -> DocumentRequest:
    """`application` is already scope-checked and locked by the route (the checklist writers' entry)."""
    if payload.due_date < today():
        raise HTTPException(422, DUE_IN_PAST)
    if application is not None and application.student_id != student.id:
        raise HTTPException(422, NOT_THE_STUDENTS_APPLICATION)
    item = None
    if payload.checklist_item_id is not None:
        item = await db.get(ApplicationChecklistItem, payload.checklist_item_id)
        if item is None or item.application_id != application.id:
            raise HTTPException(404, checklists.ITEM_NOT_FOUND)
        document_type, label = item.document_type, item.label
    else:
        document_type, label = payload.document_type, clean_label(payload.document_type, payload.document_label)
    label_clause = DocumentRequest.document_label.is_(None) if label is None else func.lower(DocumentRequest.document_label) == label.lower()
    application_clause = DocumentRequest.application_id.is_(None) if application is None else DocumentRequest.application_id == application.id
    duplicate = select(DocumentRequest.id).where(
        DocumentRequest.student_user_id == student.id, DocumentRequest.status == "open", DocumentRequest.document_type == document_type, label_clause, application_clause
    )
    if await db.scalar(duplicate):
        raise HTTPException(409, REQUEST_EXISTS)
    request = DocumentRequest(
        student_user_id=student.id,
        application_id=application.id if application else None,
        checklist_item_id=item.id if item else None,
        document_type=document_type,
        document_label=label,
        note=(payload.note or "").strip() or None,
        due_date=payload.due_date,
        status="open",
        requested_by_user_id=user.id,
    )
    db.add(request)
    await db.flush()
    add_event(db, event="requested", actor=user, request=request, to_status="open", notes=request.note)
    if item is not None and item.mark is None and (not item.allowed_statuses or "requested" in item.allowed_statuses):
        item.mark, item.marked_by_id, item.marked_at = "requested", user.id, datetime.now(UTC)  # R2
    return request


async def _load(db: AsyncSession, request_id: UUID, student_id: UUID) -> DocumentRequest:
    request = await db.scalar(
        select(DocumentRequest).where(DocumentRequest.id == request_id, DocumentRequest.student_user_id == student_id).with_for_update().execution_options(populate_existing=True)
    )
    if request is None:
        raise HTTPException(404, REQUEST_NOT_FOUND)
    return request


async def open_request(db: AsyncSession, request_id: UUID, student_id: UUID) -> DocumentRequest:
    """The student's open request, locked, or 404 / 409."""
    request = await _load(db, request_id, student_id)
    if request.status != "open":
        raise HTTPException(409, REQUEST_CLOSED)
    return request


async def cancel(db: AsyncSession, user: User, request_id: UUID, student_id: UUID) -> DocumentRequest:
    request = await open_request(db, request_id, student_id)
    close_request(request, "cancelled", user)
    add_event(db, event="cancelled", actor=user, request=request, from_status="open", to_status="cancelled")
    item = await db.get(ApplicationChecklistItem, request.checklist_item_id) if request.checklist_item_id else None
    if item is not None and item.mark == "requested":  # R2: only the mark the request set; a document link already cleared it
        item.mark = item.marked_by_id = item.marked_at = None
    return request


async def fulfil(db: AsyncSession, user: User, request: DocumentRequest, document: StudentDocument) -> None:
    """The student's upload closes the request and, for a checklist request, is linked to the item (which clears its mark, R2)."""
    close_request(request, "fulfilled", user)
    add_event(db, event="fulfilled", actor=user, document=document, request=request, to_status="fulfilled")
    if request.application_id is None:
        return
    application = await db.get(OverseasApplication, request.application_id)
    if request.checklist_item_id is not None:
        await checklists.link(db, user, application, request.checklist_item_id, document.id)
    await checklists.sync_completion(db, application)


async def reopen_on_rejection(db: AsyncSession, actor: User, document: StudentDocument) -> DocumentRequest | None:
    """R1: called by the review routes after a status change. A direct student's fulfilled request goes back to open; the rejected
    document keeps its file and history but no longer fulfils it, so the student can upload against the same request again."""
    if document.fulfils_request_id is None or document.verification_status not in REOPENING:
        return None
    request = await db.scalar(select(DocumentRequest).where(DocumentRequest.id == document.fulfils_request_id).with_for_update())
    if request is None or request.student_user_id is None or request.status != "fulfilled":
        return None
    request.status, request.closed_by_user_id, request.closed_at = "open", None, None
    document.fulfils_request_id = None
    add_event(db, event="requested", actor=actor, document=document, request=request, from_status="fulfilled", to_status="open", notes=document.reviewer_notes)
    return request

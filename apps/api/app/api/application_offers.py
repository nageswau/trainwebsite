"""ccrm-023 (DEC-SCOPE-245) -- an application's offers: list, upload an offer letter, record an offer, withdraw/expire it.

CC4: the counselor records offers on their applications, direct and agency; the Overseas Admin on any. The student and the agency read.
Every write uses `/sub-status`'s entry (api/workflows.py): role, `_assigned_application` scope, the row lock, the swapped-counselor
re-check, then the withdrawn and archived-agency refusals. The row lock serialises offer writes for one application, so concurrent saves
queue and the last one wins; the other side is told (CC5). Spec: docs/superpowers/specs/2026-10-23-ccrm-023-application-offers-design.md.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.workflows import _agency_record_archived, _assigned_application, _audit, _notify_user, _recheck_counselor_scope, _require
from app.application_sub_status import label as sub_status_label
from app.core.database import get_db
from app.models import ApplicationOffer, ApplicationStatusHistory, OverseasApplication, StudentDocument, User
from app.schemas import ApplicationOfferClose, ApplicationOfferCreate
from app.services import agent_documents as documents
from app.services import agent_notifications as agency_notices
from app.services import application_offers as offers
from app.services.agent_applications import ARCHIVED, OFFER_DOCUMENT_MISMATCH, OFFER_LETTERS_SHOWN, WITHDRAWN

logger = logging.getLogger("app.application_offers")

router = APIRouter(prefix="/workflows/overseas/applications", tags=["application-offers"])

WRITERS = {"counselor", "overseas_admin"}
READERS = WRITERS | {"overseas_student", "agent"}
NO_OWNER = "An offer letter can only be attached to a student's or an agency's application"
STUDENT_URL = "/overseas/student/applications"


async def _writable(db: AsyncSession, user: User, application_id: UUID) -> OverseasApplication:
    _require(user, WRITERS, "overseas")
    item = await _assigned_application(db, user, application_id)
    await db.refresh(item, with_for_update=True)
    _recheck_counselor_scope(user, item)
    if item.status == WITHDRAWN:
        raise HTTPException(409, "This application is withdrawn")
    if item.agent_id is not None and await _agency_record_archived(db, item):
        raise HTTPException(409, ARCHIVED)
    return item


async def _letters(db: AsyncSession, item: OverseasApplication) -> list[dict]:
    rows = await db.scalars(
        select(StudentDocument)
        .where(StudentDocument.application_id == item.id, StudentDocument.document_type == documents.OFFER_LETTER)
        .order_by(StudentDocument.created_at.desc(), StudentDocument.id)
        .limit(OFFER_LETTERS_SHOWN)
    )
    return [offers.document_view(d) | {"created_at": d.created_at} for d in rows]


async def _offer_view(db: AsyncSession, offer: ApplicationOffer) -> dict:
    [view] = await offers.views(db, offer.application_id, offer_id=offer.id)
    return view


def _result(item: OverseasApplication, offer: dict, *, changed: bool) -> dict:
    return {"id": item.id, "status": item.status, "sub_status": item.sub_status, "sub_status_label": sub_status_label(item.sub_status), "offer": offer, "changed": changed}


async def _tell_student(db: AsyncSession, item: OverseasApplication, title: str, body: str) -> None:
    student = await db.get(User, item.student_id) if item.student_id else None
    if student:
        await _notify_user(db, student, title, body, STUDENT_URL)


@router.get("/{application_id}/offers")
async def list_offers(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every offer, newest first. The offer letters to pick from go to the writers only."""
    _require(user, READERS, "overseas")
    item = await _assigned_application(db, user, application_id)
    return {"offers": await offers.views(db, item.id), "offer_letters": await _letters(db, item) if user.role in WRITERS | {"super_admin"} else []}


@router.post("/{application_id}/offer-letters", status_code=201)
async def upload_offer_letter(application_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """An "Offer letter" document attached to the application, owned like it (the account and/or the agency record). The AGN-009
    upload rules apply: the type is sniffed from the bytes (PDF or image) and the storage key is server-generated."""
    item = await _writable(db, user, application_id)
    if item.student_id is None and item.agent_student_id is None:
        raise HTTPException(422, NO_OWNER)
    data, content_type, filename = await documents.read_upload(file)
    key = documents.store(data, content_type)
    try:
        document = StudentDocument(
            student_id=item.student_id,
            agent_student_id=item.agent_student_id,
            application_id=item.id,
            document_type=documents.OFFER_LETTER,
            file_url=key,
            verification_status="pending",
            original_filename=filename,
            content_type=content_type,
            file_size=len(data),
            uploaded_by_user_id=user.id,
        )
        db.add(document)
        await db.flush()
        documents.add_event(db, event="uploaded", actor=user, document=document, to_status="pending")
        await _audit(db, user, "document.upload", "student_document", document.id, {"application_id": str(item.id), "document_type": documents.OFFER_LETTER})
        await db.commit()
    except Exception:  # nothing was written: the stored object goes too
        await db.rollback()
        documents.discard(key)
        raise
    logger.info("offer_letter_uploaded", extra={"extra_fields": {"application_id": str(item.id), "document_id": str(document.id), "actor_id": str(user.id)}})
    return {"document": offers.document_view(document)}


@router.post("/{application_id}/offers", status_code=201)
async def record_offer(application_id: UUID, payload: ApplicationOfferCreate, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A new offer supersedes the active one. Identical to the active offer: 200 and nothing written (a retry is safe)."""
    item = await _writable(db, user, application_id)
    document = await db.get(StudentDocument, payload.offer_document_id)
    if document is None or document.application_id != item.id or document.document_type != documents.OFFER_LETTER:
        raise HTTPException(422, OFFER_DOCUMENT_MISMATCH)
    values = payload.model_dump()
    current = await offers.active_offer(db, item)
    if offers.values_of(current) == values:
        response.status_code = 200
        return _result(item, await _offer_view(db, current), changed=False)
    before = (item.status, item.sub_status)
    offer = await offers.record(db, user, item, values)
    offers.apply_stage(item, offer.offer_type)
    note = ("New offer recorded, superseding the previous one: " if current else "Offer recorded: ") + offers.summary(offer)
    db.add(
        ApplicationStatusHistory(
            application_id=item.id, from_status=before[0], to_status=item.status, from_sub_status=before[1], to_sub_status=item.sub_status,
            next_action=item.next_action, notes=note, changed_by_id=user.id,
        )
    )  # fmt: skip
    await _tell_student(db, item, "Offer recorded", f"{offers.TYPE_LABELS[offer.offer_type]} offer recorded on your application.")
    await agency_notices.offer_changed(db, item, user, "Offer recorded")
    await _audit(
        db,
        user,
        "overseas.application.offer",
        "overseas_application",
        item.id,
        {"offer_id": str(offer.id), "offer_type": offer.offer_type, "from_status": before[0], "to_status": item.status, "superseded": current is not None},
    )
    await db.commit()
    logger.info("application_offer_recorded", extra={"extra_fields": {"application_id": str(item.id), "offer_id": str(offer.id), "actor_id": str(user.id)}})
    return _result(item, await _offer_view(db, offer), changed=True)


@router.post("/{application_id}/offers/{offer_id}/withdraw")
async def close_offer(application_id: UUID, offer_id: UUID, payload: ApplicationOfferClose, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """OF4: the university withdrew the current offer, or it expired."""
    item = await _writable(db, user, application_id)
    offer = await db.get(ApplicationOffer, offer_id)
    if offer is None or offer.application_id != item.id:
        raise HTTPException(404, offers.OFFER_NOT_FOUND)
    if offer.status != "active":
        raise HTTPException(409, offers.NOT_ACTIVE)
    before = item.sub_status
    offers.close(user, item, offer, payload.status, payload.reason)
    title = offers.CLOSE_LABELS[payload.status]
    db.add(
        ApplicationStatusHistory(
            application_id=item.id, from_status=item.status, to_status=item.status, from_sub_status=before, to_sub_status=item.sub_status,
            next_action=item.next_action, notes=f"{title}: {payload.reason}", changed_by_id=user.id,
        )
    )  # fmt: skip
    short = "Offer withdrawn" if payload.status == "withdrawn_by_university" else "Offer expired"
    await _tell_student(db, item, short, f"{title}.")
    await agency_notices.offer_changed(db, item, user, short)
    await _audit(db, user, "overseas.application.offer_close", "overseas_application", item.id, {"offer_id": str(offer.id), "status": payload.status})
    await db.commit()
    logger.info("application_offer_closed", extra={"extra_fields": {"application_id": str(item.id), "offer_id": str(offer.id), "status": payload.status, "actor_id": str(user.id)}})
    return _result(item, await _offer_view(db, offer), changed=True)

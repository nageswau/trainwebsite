"""ccrm-023 (DEC-SCOPE-245) -- an application's offers: list, upload an offer letter, record an offer, withdraw/expire it. The post-offer
writes that follow share this router: ccrm-025's decision and deposit, ccrm-027's enrolment confirmation (DEC-SCOPE-259).

CC4: the counselor records offers on their applications, direct and agency; the Overseas Admin on any. The student and the agency read.
Every write uses `/sub-status`'s entry (api/workflows.py): role, `_assigned_application` scope, the row lock, the swapped-counselor
re-check, then the withdrawn and archived-agency refusals. The row lock serialises offer writes for one application, so concurrent saves
queue and the last one wins; the other side is told (CC5). Spec: docs/superpowers/specs/2026-10-23-ccrm-023-application-offers-design.md.
"""

import logging
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.workflows import (
    _agency_record_archived,
    _assigned_application,
    _audit,
    _maybe_trigger_agent_commission,
    _notify_user,
    _recheck_counselor_scope,
    _require,
    _tell_outcome,
)
from app.application_outcome import label as outcome_label
from app.application_sub_status import label as sub_status_label
from app.core.database import get_db
from app.models import ApplicationOffer, ApplicationStatusHistory, OverseasApplication, StudentDocument, User
from app.schemas import ApplicationEnrollmentSave, ApplicationOfferClose, ApplicationOfferCreate, ApplicationOutcomeSet, DepositRecordSave, OfferDecisionSet
from app.services import agent_documents as documents
from app.services import agent_notifications as agency_notices
from app.services import application_deposit_records as deposits
from app.services import application_enrollment as enrollment
from app.services import application_offers as offers
from app.services import application_outcomes as outcomes
from app.services.agent_applications import ARCHIVED, OFFER_DOCUMENT_MISMATCH, OFFER_LETTERS_SHOWN, STALE

logger = logging.getLogger("app.application_offers")

router = APIRouter(prefix="/workflows/overseas/applications", tags=["application-offers"])

WRITERS = {"counselor", "overseas_admin"}
READERS = WRITERS | {"overseas_student", "agent"}
NO_OWNER = "An offer letter can only be attached to a student's or an agency's application"
STUDENT_URL = "/overseas/student/applications"


async def _writable(db: AsyncSession, user: User, application_id: UUID, *, moves_stage: bool = True) -> OverseasApplication:
    """ccrm-015: withdrawn or a terminal outcome is closed (409); on hold also refuses a write that moves the stage or sub-status."""
    _require(user, WRITERS, "overseas")
    item = await _assigned_application(db, user, application_id)
    await db.refresh(item, with_for_update=True)
    _recheck_counselor_scope(user, item)
    outcomes.refuse_closed(item)
    if moves_stage:
        outcomes.refuse_on_hold(item)
    if item.agent_id is not None and await _agency_record_archived(db, item):
        raise HTTPException(409, ARCHIVED)
    return item


async def _letters(db: AsyncSession, item: OverseasApplication, document_type: str = documents.OFFER_LETTER) -> list[dict]:
    rows = await db.scalars(
        select(StudentDocument)
        .where(StudentDocument.application_id == item.id, StudentDocument.document_type == document_type)
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
    return await _upload(db, user, application_id, file, documents.OFFER_LETTER)


@router.post("/{application_id}/deposit-receipts", status_code=201)
async def upload_deposit_receipt(application_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-025: a "Deposit receipt" document, under the offer letter's rules."""
    return await _upload(db, user, application_id, file, deposits.RECEIPT)


async def _upload(db: AsyncSession, user: User, application_id: UUID, file: UploadFile, document_type: str) -> dict:
    item = await _writable(db, user, application_id, moves_stage=False)
    if item.student_id is None and item.agent_student_id is None:
        raise HTTPException(422, NO_OWNER)
    data, content_type, filename = await documents.read_upload(file)
    key = documents.store(data, content_type)
    try:
        document = StudentDocument(
            student_id=item.student_id,
            agent_student_id=item.agent_student_id,
            application_id=item.id,
            document_type=document_type,
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
        await _audit(db, user, "document.upload", "student_document", document.id, {"application_id": str(item.id), "document_type": document_type})
        await db.commit()
    except Exception:  # nothing was written: the stored object goes too
        await db.rollback()
        documents.discard(key)
        raise
    logger.info("application_document_uploaded", extra={"extra_fields": {"application_id": str(item.id), "document_id": str(document.id), "document_type": document_type, "actor_id": str(user.id)}})
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
            next_action=item.next_action, notes=f"{title}: {payload.reason}", reason=payload.reason, changed_by_id=user.id,
        )
    )  # fmt: skip
    short = "Offer withdrawn" if payload.status == "withdrawn_by_university" else "Offer expired"
    await _tell_student(db, item, short, f"{title}.")
    await agency_notices.offer_changed(db, item, user, short)
    await _audit(db, user, "overseas.application.offer_close", "overseas_application", item.id, {"offer_id": str(offer.id), "status": payload.status})
    await db.commit()
    logger.info("application_offer_closed", extra={"extra_fields": {"application_id": str(item.id), "offer_id": str(offer.id), "status": payload.status, "actor_id": str(user.id)}})
    return _result(item, await _offer_view(db, offer), changed=True)


@router.post("/{application_id}/offers/{offer_id}/decision")
async def decide_offer(application_id: UUID, offer_id: UUID, payload: OfferDecisionSet, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-025 (DEC-SCOPE-255): the student accepted or declined the current offer. A decline is ccrm-015's `offer_declined` outcome
    (terminal). Accepting never checks the student's other applications; it lists those already accepted (D1). Repeating it: 200, unchanged."""
    item = await _writable(db, user, application_id)
    offer = await db.get(ApplicationOffer, offer_id)
    if offer is None or offer.application_id != item.id:
        raise HTTPException(404, offers.OFFER_NOT_FOUND)
    if offer.status != "active":
        raise HTTPException(409, offers.NOT_DECIDABLE)
    on = payload.decision_date or date.today()
    if on < offer.issue_date:
        raise HTTPException(422, offers.DECIDED_BEFORE_ISSUE)
    if offer.decision == payload.decision:
        return _result(item, await _offer_view(db, offer), changed=False) | {"other_accepted": await offers.other_accepted(db, item)}
    audit = {"offer_id": str(offer.id), "decision": payload.decision, "from_decision": offer.decision}
    if payload.decision == "declined":
        body = ApplicationOutcomeSet(outcome="offer_declined", outcome_date=on, reason=payload.reason, another_offer_preferred=payload.another_offer_preferred)
        event = await outcomes.record(db, user, item, body)
        await db.flush()
        await _tell_outcome(db, user, item, outcome_label(item.outcome))
        audit["event_id"] = str(event.id)
    else:
        before = (item.status, item.sub_status)
        offers.accept(user, item, offer, on)
        db.add(
            ApplicationStatusHistory(
                application_id=item.id, from_status=before[0], to_status=item.status, from_sub_status=before[1], to_sub_status=item.sub_status,
                next_action=item.next_action, notes=f"Offer accepted on {on.isoformat()} ({offers.TYPE_LABELS[offer.offer_type].lower()} offer).", changed_by_id=user.id,
            )
        )  # fmt: skip
        await _tell_student(db, item, "Offer accepted", "Your acceptance of the offer is recorded on your application.")
        await agency_notices.offer_changed(db, item, user, "Offer accepted")
    await _audit(db, user, "overseas.application.offer_decision", "overseas_application", item.id, audit)
    await db.commit()
    logger.info("application_offer_decided", extra={"extra_fields": {"application_id": str(item.id), "offer_id": str(offer.id), "decision": payload.decision, "actor_id": str(user.id)}})
    others = await offers.other_accepted(db, item) if payload.decision == "accepted" else []
    return _result(item, await _offer_view(db, offer), changed=True) | {"other_accepted": others}


@router.get("/{application_id}/deposit")
async def get_deposit(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-025 (D2): the manual deposit record, the agency's AGN-011 deposit (read-only) and the current offer's deposit to start from.
    The receipts to pick from go to the writers only."""
    _require(user, READERS, "overseas")
    item = await _assigned_application(db, user, application_id)
    writer = user.role in WRITERS | {"super_admin"}
    return {
        "record": await deposits.view(db, item.id),
        "agency_deposit": await deposits.agency_deposit(db, item.id),
        "prefill": deposits.prefill(await offers.active_offer(db, item)),
        "receipts": await _letters(db, item, deposits.RECEIPT) if writer else [],
    }


@router.put("/{application_id}/deposit")
async def save_deposit(application_id: UUID, payload: DepositRecordSave, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-025 (D2): record or replace the deposit. Allowed on hold (it moves no stage); refused beside an AGN-011 deposit (409)."""
    item = await _writable(db, user, application_id, moves_stage=False)
    if await deposits.agency_deposit(db, item.id) is not None:
        raise HTTPException(409, deposits.AGENCY_MANAGED)
    if payload.receipt_document_id is not None:
        receipt = await db.get(StudentDocument, payload.receipt_document_id)
        if receipt is None or receipt.application_id != item.id or receipt.document_type != deposits.RECEIPT or receipt.archived_at is not None:
            raise HTTPException(422, deposits.RECEIPT_MISMATCH)
    values = payload.model_dump()
    record = await deposits.record_for(db, item.id)
    if deposits.values_of(record) == values:
        return {"record": await deposits.view(db, item.id), "changed": False}
    created = record is None
    record = deposits.save(user, item, record, values)
    db.add(record)
    db.add(
        ApplicationStatusHistory(
            application_id=item.id, from_status=item.status, to_status=item.status, from_sub_status=item.sub_status, to_sub_status=item.sub_status,
            next_action=item.next_action, notes=deposits.summary(record), changed_by_id=user.id,
        )
    )  # fmt: skip
    await _tell_student(db, item, "Deposit updated", "The university deposit on your application was updated.")
    await agency_notices.offer_changed(db, item, user, "Deposit updated")
    await _audit(db, user, "overseas.application.deposit_record", "overseas_application", item.id, {"payment_status": record.payment_status, "created": created})
    await db.commit()
    logger.info("application_deposit_recorded", extra={"extra_fields": {"application_id": str(item.id), "payment_status": record.payment_status, "actor_id": str(user.id)}})
    return {"record": await deposits.view(db, item.id), "changed": True}


@router.get("/{application_id}/enrollment")
async def get_enrollment(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-027 (DEC-SCOPE-259): the enrolment confirmation. The confirmation documents to pick from go to the writers only."""
    _require(user, READERS, "overseas")
    item = await _assigned_application(db, user, application_id)
    writer = user.role in WRITERS | {"super_admin"}
    return {"enrollment": await enrollment.view(db, item), "documents": await _letters(db, item, enrollment.CONFIRMATION) if writer else []}


@router.post("/{application_id}/enrollment-documents", status_code=201)
async def upload_enrollment_document(application_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-027: an "Enrolment confirmation" document, under the offer letter's rules."""
    return await _upload(db, user, application_id, file, enrollment.CONFIRMATION)


@router.put("/{application_id}/enrollment")
async def save_enrollment(application_id: UUID, payload: ApplicationEnrollmentSave, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ccrm-027 (DEC-SCOPE-259): confirm enrolment -- the only counselor/Admin way into `enrolled` (E3), on direct and agency applications
    (CC4): one history row, the AGT-003 commission trigger (at most one), the student and the agency told. Once enrolled it corrects the
    details (audit only, E7); an unchanged save writes nothing. `expected_status` makes a stale screen a 409."""
    item = await _writable(db, user, application_id)
    if payload.expected_status != item.status:
        raise HTTPException(409, STALE)
    await enrollment.check(db, item, payload.enrollment_document_id)
    values = payload.model_dump(include=set(enrollment.FIELDS))
    changed = [name for name in enrollment.FIELDS if getattr(item, name) != values[name]]
    confirming = item.status != "enrolled"
    if not confirming and not changed:
        return {"id": item.id, "status": item.status, "sub_status": item.sub_status, "enrollment": await enrollment.view(db, item), "changed": False}
    for name in changed:
        setattr(item, name, values[name])
    old = (item.status, item.sub_status)
    if confirming:
        item.enrollment_confirmed_at = datetime.now(UTC)
        item.status = "enrolled"
        db.add(
            ApplicationStatusHistory(
                application_id=item.id, from_status=old[0], to_status=item.status, from_sub_status=old[1], to_sub_status=item.sub_status,
                next_action=item.next_action, notes=f"Enrolment confirmed -- {payload.notes}" if payload.notes else "Enrolment confirmed", changed_by_id=user.id,
            )
        )  # fmt: skip
        had_commission = await agency_notices.has_commission(db, item.id)
        await _maybe_trigger_agent_commission(db, item, old[0], user)
        await agency_notices.status_changed(db, item, old[0], user, had_commission=had_commission)  # CC5
        await _tell_student(db, item, "Enrolment confirmed", "Your enrolment at the university is confirmed on your application.")
        audit = {"from_status": old[0], "to_status": item.status, "confirmed": True}
    else:
        await agency_notices.details_changed(db, item, user)  # CC5
        audit = {"fields": changed, "confirmed": False}
    await _audit(db, user, "overseas.application.enrollment", "overseas_application", item.id, audit)
    await db.commit()
    logger.info("application_enrollment_saved", extra={"extra_fields": {"application_id": str(item.id), "confirmed": confirming, "actor_id": str(user.id)}})
    return {"id": item.id, "status": item.status, "sub_status": item.sub_status, "enrollment": await enrollment.view(db, item), "changed": True}

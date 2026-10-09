"""rec-022 (DEC-SCOPE-155, spec §3): offers -- an application's offer, record, revise, status, the letter upload and download; and the
student's own offers. rec-023 (DEC-SCOPE-158, spec §3): the offer's joining, its proof and the joinings list.

Scope is the requirement's (rec-007 `caller_scope` through rec-017's `load_scoped`; other roles 403, out of scope 404). Every write is one
transaction -- scope, the application lock, the writer (403), the offer lock and state (409), validation, change, history, side effects,
audit, one commit here; then the event is logged. The student routes read only the caller's own offers (404 otherwise)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.portfolio_certificates import EXTENSION, HEADERS
from app.core.database import get_db
from app.models import JobOffer, User
from app.schemas import RecJoiningUpdate, RecOfferCreate, RecOfferStatusChange, RecOfferUpdate
from app.services import applications, joinings
from app.services import offers as svc
from app.services.agent_documents import read_upload
from app.services.bdm_appointments import db_now, today_ist

router = APIRouter(prefix="/recruiter", tags=["recruiter-offers"])
student_router = APIRouter(prefix="/workflows/it/student", tags=["recruiter-offers"])


async def _today(db: AsyncSession):
    return (await db_now(db)).date()


@router.get("/applications/{application_id}/offer")
async def application_offer(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    application, job = await applications.load_scoped(db, user, application_id)
    return await svc.for_application(db, user, application, job)


@router.post("/applications/{application_id}/offer", status_code=201)
async def record_offer(application_id: UUID, payload: RecOfferCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """OF4 / AC1. Not idempotent: a retry is the duplicate 409."""
    application, job = await applications.load_scoped(db, user, application_id, lock=True)
    applications.require_writer(user, application.id, "offer_create")
    offer = await svc.create(db, user, application, job, payload, await _today(db))
    await db.commit()
    svc.log("recruiter_offer_recorded", user, offer.id, application_id=str(application.id), status=offer.status)
    return {"offer": await svc.one(db, user, offer.id)}


@router.patch("/offers/{offer_id}")
async def revise_offer(offer_id: UUID, payload: RecOfferUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    offer, _application, _job = await svc.load_for_write(db, user, offer_id, "offer_update")
    changed = svc.revise(db, user, offer, payload, await _today(db))
    await db.commit()
    if changed:
        svc.log("recruiter_offer_revised", user, offer_id, fields=changed)
    return {"offer": await svc.one(db, user, offer_id)}


@router.post("/offers/{offer_id}/status")
async def change_offer_status(offer_id: UUID, payload: RecOfferStatusChange, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """OF3; OF6 feeds the application (Declined -> Withdrawn)."""
    offer, application, _job = await svc.load_for_write(db, user, offer_id, "offer_status")
    previous = await svc.change_status(db, user, offer, application, payload.status, payload.note)
    await db.commit()
    svc.log("recruiter_offer_status_changed", user, offer_id, from_status=previous, to_status=payload.status)
    return {"offer": await svc.one(db, user, offer_id)}


@router.put("/offers/{offer_id}/letter")
async def upload_letter(offer_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """OF7: scope and role first, then the bytes (type by content, size cap, metadata stripped) before any lock, then the locked write.
    The new object is deleted when anything after storing it fails; a replaced object is kept."""
    await svc.load_readable(db, user, offer_id)
    applications.require_writer(user, offer_id, "offer_letter")
    data, content_type, name = await read_upload(file)
    offer, _application, _job = await svc.load_for_write(db, user, offer_id, "offer_letter")
    svc.check_letter_open(offer)
    key = svc.store(data, content_type)
    try:
        svc.attach_letter(db, user, offer, key, content_type, name, len(data))
        await db.commit()
    except BaseException:
        await db.rollback()
        svc.discard(key)
        raise
    svc.log("recruiter_offer_letter_uploaded", user, offer_id, content_type=content_type, bytes=len(data))
    return {"offer": await svc.one(db, user, offer_id)}


@router.get("/offers/{offer_id}/letter")
async def download_letter(offer_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """In the requirement's read scope only. The audit row is committed before any byte leaves (a failed commit serves nothing)."""
    offer, _application, _job = await svc.load_readable(db, user, offer_id)
    return await _download(db, user, offer)


async def _download(db: AsyncSession, user: User, offer: JobOffer) -> Response:
    """The audit row is committed before any byte leaves (a failed commit serves nothing); the name is built, never the uploaded one."""
    data = svc.read_file(offer, offer.letter_key, svc.NO_LETTER)
    filename = await svc.letter_filename(db, offer, EXTENSION.get(offer.letter_content_type, "bin"))
    svc.audit(db, user, "letter_downloaded", offer, {"role": user.role})
    await db.commit()
    svc.log("recruiter_offer_letter_downloaded", user, offer.id, role=user.role)
    return _attachment(data, offer.letter_content_type, filename)


def _attachment(data: bytes, content_type: str | None, filename: str) -> Response:
    return Response(content=data, media_type=content_type or "application/octet-stream", headers={**HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'})


# --- rec-023: the joining ------------------------------------------------------------------------------------------------------------
@router.put("/offers/{offer_id}/joining")
async def update_joining(offer_id: UUID, payload: RecJoiningUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """JN1-JN8: the details and the move in one transaction; Joined also moves the application, the company and (vacancies filled) the
    requirement."""
    offer, application, job = await svc.load_for_write(db, user, offer_id, "joining_update")
    result = await joinings.update(db, user, offer, application, job, payload, today_ist(await db_now(db)))
    await db.commit()
    if result:
        svc.log("recruiter_joining_updated", user, offer_id, fields=result["fields"], from_status=result["from"], to_status=result["to"])
    return {"offer": await svc.one(db, user, offer_id)}


@router.put("/offers/{offer_id}/joining/proof")
async def upload_joining_proof(offer_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """JN4: as the letter (OF7) -- scope and role first, then the bytes before any lock; a new object is deleted when the write fails."""
    await svc.load_readable(db, user, offer_id)
    applications.require_writer(user, offer_id, "joining_proof")
    data, content_type, name = await read_upload(file)
    offer, _application, _job = await svc.load_for_write(db, user, offer_id, "joining_proof")
    joinings.check_proof_open(offer)
    key = svc.store(data, content_type, svc.PROOF_PREFIX)
    try:
        joinings.attach_proof(db, user, offer, key, content_type, name, len(data))
        await db.commit()
    except BaseException:
        await db.rollback()
        svc.discard(key)
        raise
    svc.log("recruiter_joining_proof_uploaded", user, offer_id, content_type=content_type, bytes=len(data))
    return {"offer": await svc.one(db, user, offer_id)}


@router.get("/offers/{offer_id}/joining/proof")
async def download_joining_proof(offer_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """In the requirement's read scope only; audited and committed before any byte leaves."""
    offer, _application, _job = await svc.load_readable(db, user, offer_id)
    data = svc.read_file(offer, offer.proof_key, joinings.NO_PROOF)
    filename = await svc.letter_filename(db, offer, EXTENSION.get(offer.proof_content_type, "bin"), "joining-proof")
    joinings.audit(db, user, "proof_downloaded", offer, {"role": user.role})
    await db.commit()
    svc.log("recruiter_joining_proof_downloaded", user, offer.id, role=user.role)
    return _attachment(data, offer.proof_content_type, filename)


@router.get("/joinings")
async def list_joinings(
    view: Literal["due", "joined", "did_not_join"] = "due",
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The "Joining due" list and the closed joinings: a recruiter's requirements, a manager's team and the unassigned queue, the assigned
    BDM's, super_admin all (read only for all but the writers)."""
    return await joinings.list_page(db, user, view, today_ist(await db_now(db)), limit, offset)


def _require_student(user: User) -> None:
    if user.role != "it_student":
        raise HTTPException(403, "Only a student can view their offers here")


@student_router.get("/offers")
async def my_offers(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_student(user)
    return await svc.student_list(db, user)


@student_router.get("/offers/{offer_id}/letter")
async def my_offer_letter(offer_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_student(user)
    return await _download(db, user, await svc.student_offer(db, user, offer_id))

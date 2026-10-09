"""rec-022 (DEC-SCOPE-152, spec §3): offers -- an application's offer, record, revise, status, the letter upload and download; and the
student's own offers.

Scope is the requirement's (rec-007 `caller_scope` through rec-017's `load_scoped`; other roles 403, out of scope 404). Every write is one
transaction -- scope, the application lock, the writer (403), the offer lock and state (409), validation, change, history, side effects,
audit, one commit here; then the event is logged. The student routes read only the caller's own offers (404 otherwise)."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.portfolio_certificates import EXTENSION, HEADERS
from app.core.database import get_db
from app.models import JobOffer, User
from app.schemas import RecOfferCreate, RecOfferStatusChange, RecOfferUpdate
from app.services import applications
from app.services import offers as svc
from app.services.agent_documents import read_upload
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/recruiter", tags=["recruiter-offers"])
student_router = APIRouter(prefix="/workflows/it/student", tags=["recruiter-offers"])


async def _today(db: AsyncSession):
    return (await db_now(db)).date()


def _file(data: bytes, offer: JobOffer, filename: str) -> Response:
    return Response(content=data, media_type=offer.letter_content_type or "application/octet-stream", headers={**HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/applications/{application_id}/offer")
async def application_offer(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    application, _job = await applications.load_scoped(db, user, application_id)
    return await svc.for_application(db, user, application)


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
    data = svc.read_letter(offer)
    filename = await svc.letter_filename(db, offer, EXTENSION.get(offer.letter_content_type, "bin"))
    svc.audit(db, user, "letter_downloaded", offer, {"role": user.role})
    await db.commit()
    svc.log("recruiter_offer_letter_downloaded", user, offer_id, role=user.role)
    return _file(data, offer, filename)


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
    offer = await svc.student_offer(db, user, offer_id)
    data = svc.read_letter(offer)
    filename = await svc.letter_filename(db, offer, EXTENSION.get(offer.letter_content_type, "bin"))
    svc.audit(db, user, "letter_downloaded", offer, {"role": user.role})
    await db.commit()
    return _file(data, offer, filename)

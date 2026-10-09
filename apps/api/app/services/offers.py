"""rec-022 (DEC-SCOPE-152, spec §1-§3): offer management -- the §16 statuses and their moves, record, revise, the letter, the side effects on
the application (rec-017) and the company (rec-005), the student notice and the reads.

An offer belongs to its application, so every recruiter read and write resolves through rec-017's `load_scoped` (rec-007's requirement
scope: out of scope = the same 404 as missing). The legacy /workflows routes come through `insert` and `legacy_status`, so every offer gets
its history (AC2) and the legacy accepted/joined -> Joined side effect is kept (AC3). Lock order: the application, then the offer. Functions
only; nothing here commits -- the route owns the transaction. Logs and audit carry ids, keys and field names, never the salary, a note or a
file name."""

import hashlib
import logging
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Candidate, Company, Job, JobApplication, JobOffer, JobOfferEvent, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.schemas import RecOfferCreate, RecOfferUpdate
from app.services import applications, company_pipeline
from app.services import recruiter_requirements as requirements
from app.services.interviews import field_error
from app.services.storage import storage

logger = logging.getLogger("app.recruiter")

STATUS_LABELS = {"offer_pending": "Offer Pending", "offer_received": "Offer Received", "accepted": "Accepted", "declined": "Declined"}
MOVES = {"offer_pending": ("offer_received", "accepted", "declined"), "offer_received": ("accepted", "declined"), "accepted": (), "declined": ()}
FINAL = ("accepted", "declined")
LEGACY = {"offered": "offer_received", "pending": "offer_pending", "joined": "accepted", "rejected": "declined"}  # OF9; the keys map to themselves
REVISABLE = ("position", "compensation", "currency", "offered_on", "joining_date")
STORAGE_PREFIX = "job-offers"

NOT_FOUND = "Offer not found"
NOT_SELECTED = "An offer can be recorded only for a Selected candidate"
DUPLICATE = "An offer already exists for this application"
DECIDED = "This offer is already decided"
UNKNOWN_STATUS = "Choose an offer status: offer_pending, offer_received, accepted or declined"
NO_LETTER = "No offer letter has been uploaded"
LETTER_CLOSED = "A declined offer's letter cannot be changed"
DATE_FUTURE = "The offer date cannot be in the future"
JOINING_EARLY = "The joining date cannot be before the offer date"
UNIQUE = "ix_job_offers_application_id"  # the unique index on job_offers.application_id


def status_label(key: str) -> str:
    return STATUS_LABELS.get(key, key)


def from_legacy(word: str | None) -> str | None:
    """A legacy status word or a key -> the key; None when it is neither."""
    return word if word in STATUS_LABELS else LEGACY.get(word)


def _event(db: AsyncSession, offer: JobOffer, actor: User | None, event: str, *, from_status=None, fields=None, note=None, letter_key=None) -> None:
    db.add(JobOfferEvent(offer_id=offer.id, event=event, from_status=from_status, to_status=offer.status, fields=fields, note=note, letter_key=letter_key, actor_user_id=actor.id if actor else None))


def _check_dates(offered_on: date, joining_date: date | None, today: date) -> None:
    if offered_on > today:
        raise field_error("offered_on", DATE_FUTURE, offered_on.isoformat())
    if joining_date is not None and joining_date < offered_on:
        raise field_error("joining_date", JOINING_EARLY, joining_date.isoformat())


async def _notify_received(db: AsyncSession, application: JobApplication) -> None:
    """OF6: the existing "Job offer received" notice, in-app for a student candidate; external candidates have no login."""
    student = await db.get(User, application.student_id) if application.student_id else None
    if student is None:
        return
    item = Notification(user_id=student.id, title="Job offer received", body="A job offer has been recorded in your placement portal.", read=False, action_url="/it/student/placement-status")
    db.add(item)
    await db.flush()
    await queue_deliveries(db, item, student)


# --- the core: insert and moves (every writer) --------------------------------------------------------------------------------------
async def insert(db: AsyncSession, actor: User, application: JobApplication, status: str, **fields) -> JobOffer:
    """One offer per application (`409`; the unique index decides a race), its `created` history row and, on Offer Received, the notice."""
    if await db.scalar(select(JobOffer.id).where(JobOffer.application_id == application.id)):
        raise HTTPException(409, DUPLICATE)
    offer = JobOffer(application_id=application.id, status=status, created_by_user_id=actor.id, **fields)
    db.add(offer)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if UNIQUE in str(exc.orig):
            raise HTTPException(409, DUPLICATE) from None
        raise
    _event(db, offer, actor, "created")
    if status == "offer_received":
        await _notify_received(db, application)
    return offer


async def _apply_status(db: AsyncSession, actor: User, offer: JobOffer, application: JobApplication, target: str, note: str | None, *, legacy: bool) -> str:
    """History, then the side effects (OF6): Declined withdraws the application; Received notifies the student; on the legacy routes only,
    Accepted joins it (AC3). Returns the previous status."""
    previous = offer.status
    offer.status = target
    _event(db, offer, actor, "status", from_status=previous, note=note)
    if target == "declined":
        applications.follow(db, actor, application, "withdrawn", "Offer declined")
    elif target == "offer_received":
        await _notify_received(db, application)
    elif target == "accepted" and legacy:
        applications.follow(db, actor, application, "joined", "Offer accepted")
    return previous


async def change_status(db: AsyncSession, user: User, offer: JobOffer, application: JobApplication, target: str, note: str | None) -> str:
    """OF3: the recruiter's moves; anything else is a 409."""
    if target not in MOVES.get(offer.status, ()):
        raise HTTPException(409, DECIDED if offer.status in FINAL else f"An offer cannot move from {status_label(offer.status)} to {status_label(target)}")
    previous = await _apply_status(db, user, offer, application, target, note, legacy=False)
    audit(db, user, "status", offer, {"from": previous, "to": target})
    return previous


async def legacy_status(db: AsyncSession, user: User, offer: JobOffer, application: JobApplication, word: str) -> None:
    """OF9: the legacy PATCH keeps its free moves among the four statuses (a word it always sent is mapped; any other is a 422). The same
    status is not a change, except that a legacy accepted/joined always re-applies its Joined side effect, as it always did."""
    target = from_legacy(word)
    if target is None:
        raise HTTPException(422, UNKNOWN_STATUS)
    if target != offer.status:
        await _apply_status(db, user, offer, application, target, None, legacy=True)
    elif target == "accepted":
        applications.follow(db, user, application, "joined", "Offer accepted")


# --- recruiter writes ---------------------------------------------------------------------------------------------------------------
async def create(db: AsyncSession, user: User, application: JobApplication, job: Job, payload: RecOfferCreate, today: date) -> JobOffer:
    """OF4 / AC1: the caller locked the application and checked the writer. Then rec-005's `candidate_selected` on the company."""
    if application.status != "selected":
        raise HTTPException(409, NOT_SELECTED)
    offered_on = payload.offered_on or today
    _check_dates(offered_on, payload.joining_date, today)
    offer = await insert(
        db, user, application, payload.status, position=payload.position, compensation=payload.compensation, currency=payload.currency, offered_on=offered_on, joining_date=payload.joining_date
    )
    company = await db.scalar(select(Company).where(Company.id == job.company_id).with_for_update().execution_options(populate_existing=True))
    moved = await company_pipeline.apply_event(db, company, "candidate_selected", user)
    audit(db, user, "create", offer, {"application_id": str(application.id), "status": offer.status, "stage_moved": moved})
    return offer


async def load_for_write(db: AsyncSession, user: User, offer_id: UUID, route: str) -> tuple[JobOffer, JobApplication, Job]:
    """In scope (404) -> the application lock -> the writer (403) -> the offer lock."""
    application_id = await db.scalar(select(JobOffer.application_id).where(JobOffer.id == offer_id))
    if application_id is None:
        raise HTTPException(404, NOT_FOUND)
    application, job = await _scoped(db, user, application_id, lock=True)
    applications.require_writer(user, offer_id, route)
    offer = await db.scalar(select(JobOffer).where(JobOffer.id == offer_id).with_for_update().execution_options(populate_existing=True))
    return offer, application, job


def revise(db: AsyncSession, user: User, offer: JobOffer, payload: RecOfferUpdate, today: date) -> list[str]:
    """OF5: only changed values count (no history or audit for none). Returns the changed field names."""
    if offer.status in FINAL:
        raise HTTPException(409, DECIDED)
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(key for key, value in changes.items() if getattr(offer, key) != value)
    if not changed:
        return []
    if {"offered_on", "joining_date"} & set(changed):
        _check_dates(changes.get("offered_on", offer.offered_on), changes.get("joining_date", offer.joining_date), today)
    for key in changed:
        setattr(offer, key, changes[key])
    _event(db, offer, user, "revised", from_status=offer.status, fields=changed)
    audit(db, user, "update", offer, {"fields": changed})
    return changed


# --- the letter (OF7) ---------------------------------------------------------------------------------------------------------------
def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def check_letter_open(offer: JobOffer) -> None:
    if offer.status == "declined":
        raise HTTPException(409, LETTER_CLOSED)


def store(data: bytes, content_type: str) -> str:
    """A server-generated key; the client never names a path. A storage failure is a 500, logged by key digest (never the key)."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("recruiter_offer_letter_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete an object stored for a write that did not commit; only this module's keys. A failure leaves a logged orphan."""
    if not key.startswith(f"{STORAGE_PREFIX}/"):
        logger.error("recruiter_offer_letter_discard_refused", extra={"extra_fields": {"key_digest": _digest(key)}})
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("recruiter_offer_letter_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def attach_letter(db: AsyncSession, user: User, offer: JobOffer, key: str, content_type: str, name: str | None, size: int) -> None:
    """The replaced object is kept; its key goes on the history row, never into a response."""
    old_key = offer.letter_key
    offer.letter_key, offer.letter_content_type, offer.letter_name, offer.letter_uploaded_at = key, content_type, name, datetime.now(UTC)
    _event(db, offer, user, "letter", from_status=offer.status, letter_key=old_key)
    audit(db, user, "letter", offer, {"content_type": content_type, "replaced": old_key is not None, "bytes": size})


def read_letter(offer: JobOffer) -> bytes:
    if offer.letter_key is None:
        raise HTTPException(404, NO_LETTER)
    try:
        return storage.read_bytes(offer.letter_key)
    except FileNotFoundError:
        logger.warning("recruiter_offer_letter_missing", extra={"extra_fields": {"offer_id": str(offer.id), "key_digest": _digest(offer.letter_key)}})
        raise HTTPException(404, NO_LETTER) from None


# --- reads --------------------------------------------------------------------------------------------------------------------------
async def _scoped(db: AsyncSession, user: User, application_id: UUID, *, lock: bool = False) -> tuple[JobApplication, Job]:
    try:
        return await applications.load_scoped(db, user, application_id, lock=lock)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, NOT_FOUND) from None
        raise


async def load_readable(db: AsyncSession, user: User, offer_id: UUID) -> tuple[JobOffer, JobApplication, Job]:
    application_id = await db.scalar(select(JobOffer.application_id).where(JobOffer.id == offer_id))
    if application_id is None:
        await requirements.caller_scope(db, user)  # the role check (403) comes before "not found"
        raise HTTPException(404, NOT_FOUND)
    application, job = await _scoped(db, user, application_id)
    return await db.get(JobOffer, offer_id), application, job


def safe_link(url: str | None) -> str | None:
    """The legacy typed link is shown only when it is http(s) (never a `javascript:` URL)."""
    return url if url and url.lower().startswith(("https://", "http://")) else None


def _letter(offer: JobOffer) -> dict | None:
    if offer.letter_key is None:
        return None
    return {"name": offer.letter_name, "content_type": offer.letter_content_type, "uploaded_at": offer.letter_uploaded_at}


async def _history(db: AsyncSession, offer_id: UUID) -> list[dict]:
    rows = await db.execute(select(JobOfferEvent, User).outerjoin(User, User.id == JobOfferEvent.actor_user_id).where(JobOfferEvent.offer_id == offer_id).order_by(JobOfferEvent.position))
    return [
        {
            "event": e.event,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "fields": e.fields,
            "note": e.note,
            "actor": {"id": u.id, "full_name": u.full_name} if u else None,
            "created_at": e.created_at,
        }
        for e, u in rows
    ]


async def one(db: AsyncSession, user: User, offer_id: UUID) -> dict:
    row = (
        await db.execute(
            select(JobOffer, JobApplication, Candidate, Job, Company)
            .join(JobApplication, JobApplication.id == JobOffer.application_id)
            .join(Candidate, Candidate.id == JobApplication.candidate_id)
            .join(Job, Job.id == JobApplication.job_id)
            .join(Company, Company.id == Job.company_id)
            .where(JobOffer.id == offer_id)
            .execution_options(populate_existing=True)
        )
    ).one()
    o, a, c, job, company = row
    writer = applications.can_write(user)
    return {
        "id": o.id,
        "status": o.status,
        "status_label": status_label(o.status),
        "position": o.position,
        "compensation": o.compensation,
        "currency": o.currency,
        "offered_on": o.offered_on,
        "joining_date": o.joining_date,
        "letter": _letter(o),
        "letter_url": safe_link(o.letter_url),
        "application": {"id": a.id, "status": a.status, "status_label": applications.label(a.status)},
        "candidate": {"id": c.id, "code": c.candidate_code, "name": c.name},
        "requirement": {"id": job.id, "code": job.requirement_code, "title": job.title},
        "company": {"id": company.id, "name": company.name},
        "history": await _history(db, o.id),
        "allowed_statuses": [{"key": k, "label": STATUS_LABELS[k]} for k in MOVES.get(o.status, ())] if writer else [],
        "can_edit": writer and o.status not in FINAL,
        "can_upload": writer and o.status != "declined",
    }


async def for_application(db: AsyncSession, user: User, application: JobApplication, job: Job) -> dict:
    """The offer, or none with `can_create` and the requirement title the form starts the position from."""
    offer_id = await db.scalar(select(JobOffer.id).where(JobOffer.application_id == application.id))
    if offer_id is not None:
        return {"offer": await one(db, user, offer_id), "can_create": False}
    return {"offer": None, "can_create": applications.can_write(user) and application.status == "selected", "suggested_position": job.title}


def _student_rows(user: User):
    return (
        select(JobOffer, Job, Company)
        .join(JobApplication, JobApplication.id == JobOffer.application_id)
        .join(Job, Job.id == JobApplication.job_id)
        .join(Company, Company.id == Job.company_id)
        .where(JobApplication.student_id == user.id)
    )


async def student_list(db: AsyncSession, user: User) -> dict:
    """OF8: the student's own offers -- no history, no candidate record, no actor names."""
    rows = (await db.execute(_student_rows(user).order_by(JobOffer.created_at.desc(), JobOffer.id))).all()
    return {
        "items": [
            {
                "id": o.id,
                "company": company.name,
                "requirement": job.title,
                "position": o.position,
                "status": o.status,
                "status_label": status_label(o.status),
                "compensation": o.compensation,
                "currency": o.currency,
                "offered_on": o.offered_on,
                "joining_date": o.joining_date,
                "has_letter": o.letter_key is not None,
                "letter_url": safe_link(o.letter_url),
            }
            for o, job, company in rows
        ]
    }


async def student_offer(db: AsyncSession, user: User, offer_id: UUID) -> JobOffer:
    """Only the caller's own (404 otherwise: no IDOR)."""
    row = (await db.execute(_student_rows(user).where(JobOffer.id == offer_id))).first()
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row[0]


async def letter_filename(db: AsyncSession, offer: JobOffer, extension: str) -> str:
    """Built from the candidate code, never the uploaded name."""
    code = await db.scalar(select(Candidate.candidate_code).join(JobApplication, JobApplication.candidate_id == Candidate.id).where(JobApplication.id == offer.application_id))
    return f"offer-{code}.{extension}"


def audit(db: AsyncSession, user: User, action: str, offer: JobOffer, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"recruiter_offer.{action}", entity_type="job_offer", entity_id=str(offer.id), metadata_json=metadata or {}))


def log(event: str, user: User, offer_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "offer_id": str(offer_id), **extra}})

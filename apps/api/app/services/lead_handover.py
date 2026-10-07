"""tel-018 (DEC-SCOPE-098, spec §3.2): the counselor handover, the return, the student link and the computed conversion (T4, T5, T19,
T20, T29; HO1-HO4).

Functions only; nothing here commits except the conversion observers, which own their own small transaction. Every write runs on a lead
the caller locked first (lock order lead -> counselor / student -> appointment, as the tel-016 writes). Logs and audit rows carry ids
and stage keys, never the lead's contact details or the return reason (that lives in the stage history only)."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED, ORDER
from app.models import AuditLog, Batch, Enquiry, Enrollment, OverseasApplication, University, User, VisaCase
from app.services import bdm_leads, lead_appointments, lead_pipeline

logger = logging.getLogger("app.leads")

COUNSELOR_REQUIRED = "Counselor role required"
HANDOVER_CLOSED = "This lead is closed; reopen it before handing it over"
HANDOVER_PAST = "This lead is already past the counselor handover"
SAME_COUNSELOR = "This lead is already with this counselor"
RETURN_LINKED = "Unlink the student before returning the lead"
UNLINK_CONVERTED = "Only an admin can unlink a converted lead"
HANDED_OVER = "Handed over to counselor"  # the cancel reason on the follow-ups a handover cancelled
RETURNED = "Returned to telecaller"  # and on the counselling appointment a return cancelled
LINKED_FROM = ORDER.index("application_enrollment")
SWEEP_BATCH = 500
MAX_SUGGESTIONS = 10


def _log(event: str, user: User | None, lead_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id) if user else None, "lead_id": str(lead_id), **extra}})


# --- handover (HO4) ---------------------------------------------------------------------------------------------------------------

async def handover(db: AsyncSession, user: User, lead: Enquiry, counselor_id: UUID) -> None:
    """The lead's telecaller (the route applies tel-008's 403 once handed over) or their manager gives the lead to an active counselor
    of its division. The stage stays; open follow-ups are cancelled -- the telecaller no longer works the lead (T19)."""
    if lead.status in CLOSED:
        raise HTTPException(409, HANDOVER_CLOSED)
    if ORDER.index(lead.status) >= LINKED_FROM:
        raise HTTPException(409, HANDOVER_PAST)
    counselor = await lead_appointments.lock_counselor(db, counselor_id, lead.division)
    if lead.owner_id == counselor.id:
        raise HTTPException(409, SAME_COUNSELOR)
    previous, lead.owner_id = lead.owner_id, counselor.id
    await lead_pipeline.cancel_open_follow_ups(db, lead, HANDED_OVER)
    db.add(AuditLog(user_id=user.id, action="lead.handover", entity_type="enquiry", entity_id=str(lead.id),
                    metadata_json={"counselor_id": str(counselor.id), "from_counselor_id": str(previous) if previous else None}))
    _log("lead_handed_over", user, lead.id, counselor_id=str(counselor.id))


# --- the counselor's side --------------------------------------------------------------------------------------------------------

def counselor_scope(user: User) -> list:
    """The leads handed to this counselor, in their own division (tel-017). Anyone else is 403; a lead outside it reads as missing."""
    if user.role != "counselor":
        raise HTTPException(403, COUNSELOR_REQUIRED)
    return [Enquiry.owner_id == user.id, Enquiry.division == user.division]


def permissions(lead: Enquiry) -> dict:
    linked = lead.converted_user_id is not None
    return {"return": not linked, "link": not linked and lead.status not in CLOSED, "unlink": linked and lead.status != "converted"}


async def return_lead(db: AsyncSession, user: User, lead: Enquiry, reason: str) -> None:
    """T19 / HO4: back to Follow-up with the reason in the stage history; the telecaller works the lead again (tel-020 alerts them).
    A linked lead is the counselor's to unlink first."""
    if lead.converted_user_id is not None:
        raise HTTPException(409, RETURN_LINKED)
    await lead_pipeline.apply_event(db, lead, "returned", user, reason)
    lead.owner_id = None
    await lead_pipeline.cancel_open_appointments(db, lead, user, RETURNED, "lead_returned")
    db.add(AuditLog(user_id=user.id, action="lead.return", entity_type="enquiry", entity_id=str(lead.id), metadata_json={"counselor_id": str(user.id)}))
    _log("lead_returned", user, lead.id)


# --- the student link (T20, T29; HO1, HO2) --------------------------------------------------------------------------------------

async def link_student(db: AsyncSession, user: User, lead: Enquiry, match) -> None:
    """The admin and the counselor link by the same rules (AC5): one student per lead (409), an active student of the lead's division
    (one 422), a student linked once (409; `uq_enquiries_converted_user` is the backstop the route turns into 409). The event runs first:
    its read autoflushes, and an autoflush must never see a half-set link (ck_enquiries_conversion)."""
    if lead.converted_user_id is not None:
        raise HTTPException(409, bdm_leads.ALREADY_LINKED)
    student = await bdm_leads.locked_student(db, lead, match)
    await bdm_leads.check_student_free(db, student)
    await lead_pipeline.apply_event(db, lead, "student_linked", user)
    now = await db.scalar(select(func.now()))
    lead.converted_user_id, lead.converted_at, lead.converted_by_user_id = student.id, now, user.id
    bdm_leads.audit_conversion(db, user, lead, "lead.convert", student.id)
    with db.no_autoflush:  # the link is flushed at the commit, where `commit_link` turns the unique-student race into 409
        await sync_conversion(db, lead)


async def commit_link(db: AsyncSession, user: User, lead_id: UUID) -> None:
    """Shared with the admin link: two people linking one student at the same instant -> the unique index -> 409."""
    actor_id = str(user.id)  # a rollback expires every loaded row, the caller included
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning("lead_convert_conflict", extra={"extra_fields": {"actor_id": actor_id, "lead_id": str(lead_id)}})
        raise HTTPException(409, bdm_leads.STUDENT_TAKEN) from None
    logger.info("lead_converted", extra={"extra_fields": {"actor_id": actor_id, "lead_id": str(lead_id)}})


async def unlink_student(db: AsyncSession, user: User, lead: Enquiry, *, admin: bool) -> None:
    """HO1 / HO2: the counselor undoes a mistaken link before conversion; only an admin unlinks a converted lead. Either way the lead
    goes back to Follow-up and no longer counts as converted."""
    if lead.converted_user_id is None:
        raise HTTPException(409, bdm_leads.NOT_LINKED)
    if lead.status == "converted" and not admin:
        raise HTTPException(409, UNLINK_CONVERTED)
    await lead_pipeline.apply_event(db, lead, "student_unlinked", user)
    bdm_leads.audit_conversion(db, user, lead, "lead.unconvert", lead.converted_user_id)
    lead.converted_user_id = lead.converted_at = lead.converted_by_user_id = None


# --- the computed conversion (T5, HO3) --------------------------------------------------------------------------------------------

def _evidence(student_id):
    """An active IT enrolment or an enrolled overseas application of the linked student, whenever it was made (HO3)."""
    return or_(
        exists().where(Enrollment.student_id == student_id, Enrollment.status == "active"),
        exists().where(OverseasApplication.student_id == student_id, OverseasApplication.status == "enrolled"),
    )


def _convertible():
    return [Enquiry.status == "application_enrollment", Enquiry.converted_user_id.is_not(None), _evidence(Enquiry.converted_user_id)]


async def sync_conversion(db: AsyncSession, lead: Enquiry) -> bool:
    """On a locked lead: Application/Enrollment + the evidence -> Converted, by the system (recorded once: the event's from-set)."""
    if lead.status != "application_enrollment" or lead.converted_user_id is None:
        return False
    if not await db.scalar(select(_evidence(lead.converted_user_id))):
        return False
    await lead_pipeline.apply_event(db, lead, "converted")
    _log("lead_converted_observed", None, lead.id)
    return True


async def observe_conversion(db: AsyncSession, lead_id: UUID) -> None:
    """Before a detail read: one indexed check; only a lead that has just converted is locked, moved and committed."""
    if await db.scalar(select(Enquiry.id).where(Enquiry.id == lead_id, *_convertible())) is None:
        return
    lead = await db.scalar(select(Enquiry).where(Enquiry.id == lead_id).with_for_update().execution_options(populate_existing=True))
    if await sync_conversion(db, lead):
        await db.commit()


async def sweep_conversions(db: AsyncSession) -> int:
    """The 15-minute beat job: a bounded batch of the leads nobody opened. SKIP LOCKED, so it never waits on a person's write."""
    stmt = select(Enquiry).where(*_convertible()).limit(SWEEP_BATCH).with_for_update(skip_locked=True)
    moved = 0
    for lead in (await db.scalars(stmt.execution_options(populate_existing=True))).all():
        moved += await sync_conversion(db, lead)
    await db.commit()
    if moved:
        logger.info("lead_conversion_sweep", extra={"extra_fields": {"converted": moved}})
    return moved


# --- reads ------------------------------------------------------------------------------------------------------------------------

async def milestones(db: AsyncSession, lead: Enquiry) -> dict:
    """T4: once linked, the student's IT enrolments or overseas applications and visa cases, read live. Read only."""
    if lead.converted_user_id is None:
        return {"student": None, "items": []}
    student = await db.get(User, lead.converted_user_id)
    items: list[dict] = []
    enrolments = await db.execute(select(Enrollment, Batch.name).join(Batch, Batch.id == Enrollment.batch_id)
                                  .where(Enrollment.student_id == student.id).order_by(Enrollment.created_at))
    for row, batch in enrolments.all():
        items.append({"kind": "enrollment", "label": batch, "status": row.status, "reference": row.enrollment_code, "at": row.created_at})
    applications = await db.execute(select(OverseasApplication, University.name).join(University, University.id == OverseasApplication.university_id)
                                    .where(OverseasApplication.student_id == student.id).order_by(OverseasApplication.created_at))
    for row, university in applications.all():
        items.append({"kind": "application", "label": university, "status": row.status, "reference": row.application_reference, "at": row.updated_at})
        for visa in (await db.scalars(select(VisaCase).where(VisaCase.application_id == row.id).order_by(VisaCase.created_at))).all():
            items.append({"kind": "visa", "label": university, "status": visa.status, "reference": visa.tracking_reference, "at": visa.updated_at})
    return {"student": {"id": student.id, "full_name": student.full_name, "email": student.email}, "items": items}


async def detail(db: AsyncSession, lead_id: UUID, filters: list) -> dict:
    await observe_conversion(db, lead_id)
    row = (await db.execute(bdm_leads.admin_rows().where(Enquiry.id == lead_id, *filters).execution_options(populate_existing=True))).one_or_none()
    if row is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    lead = row[0]
    return {**bdm_leads.admin_out(row), "message": lead.message, "milestones": await milestones(db, lead), "permissions": permissions(lead)}


async def page(db: AsyncSession, filters: list, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(Enquiry).where(*filters))
    rows = (await db.execute(bdm_leads.admin_rows().where(*filters).order_by(*bdm_leads.NEWEST).limit(limit).offset(offset))).all()
    return {"items": [bdm_leads.admin_out(row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


async def suggestions(db: AsyncSession, lead: Enquiry, pattern: str | None) -> dict:
    """T20: active students of the lead's division -- without a search, the accounts whose email or mobile (last ten digits) equals the
    lead's (the suggested match); with one, a literal substring of name, email or mobile. A counselor already sees this division's
    students, so this reveals nothing new. Each says whether another lead already holds it."""
    filters = [User.role == f"{lead.division}_student", User.division == lead.division, User.active.is_(True)]
    if pattern:
        filters.append(or_(*(c.ilike(pattern, escape="\\") for c in (User.full_name, User.email, User.phone))))
    else:
        matches = []
        if lead.email:
            matches.append(func.lower(User.email) == lead.email.lower())
        digits = "".join(ch for ch in (lead.phone_normalized or "") if ch.isdigit())[-10:]
        if len(digits) == 10:
            matches.append(func.right(func.regexp_replace(User.phone, r"\D", "", "g"), 10) == digits)
        if not matches:
            return {"items": []}
        filters.append(or_(*matches))
    taken = exists().where(Enquiry.converted_user_id == User.id, Enquiry.id != lead.id)
    rows = (await db.execute(select(User, taken).where(*filters).order_by(User.full_name, User.id).limit(MAX_SUGGESTIONS))).all()
    return {"items": [{"id": u.id, "full_name": u.full_name, "email": u.email, "phone": u.phone, "linked_elsewhere": linked} for u, linked in rows]}

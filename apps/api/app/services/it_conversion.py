"""itc-011 -- the one-step IT conversion: a lead handed to an IT counselor (or any IT lead, for the IT Admin) becomes an IT student, an
enrolment, its fee rows and its onboarding checklist, all in one transaction (docs/superpowers/specs/2026-11-03-itc-011-it-one-step-
conversion-design.md, C1-C10).

Reuses csc-002's account (`counselor_students.create_student`, division "it"), tel-018's link (`lead_handover.link_student`: the stage
moves to Application/Enrollment and itc-003 gives the student the lead owner as counselor), the enrolment rules (`it_enrollments.seat`)
and the itc-013 fee rows. Functions only: the route locks the lead, commits through `lead_handover.commit_link` and mails the
set-password link after the commit. Every refusal comes before anything is written. Logs and audit rows carry ids only."""

import logging
import re
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED
from app.models import (
    AuditLog,
    Batch,
    Enquiry,
    Enrollment,
    ItConversion,
    ItOnboardingItem,
    ItOnboardingTemplateItem,
    ItStudentCounselor,
    LeadCounselingRecord,
    Notification,
    Payment,
    Program,
    TelProduct,
    User,
)
from app.notifications.dispatch import queue_deliveries
from app.schemas import ItConversionIn
from app.services import bdm_leads, counselor_students, fee_accounts, it_enrollments, it_lifecycle, lead_handover
from app.services.bdm_appointments import db_now, today_ist
from app.services.lead_pipeline import invalid
from app.services.provisioning import IssuedWelcome

logger = logging.getLogger("app.leads")

KEY_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,120}")
KEY_REQUIRED = "Idempotency-Key header is required"
KEY_INVALID = "Idempotency-Key must be 1-120 letters, digits or . _ : -"
NOT_IT = "Only an IT lead can be converted to an IT student"
CLOSED_LEAD = "This lead is closed; reopen it before converting it"
NOT_CONVERTIBLE = "Move the lead to Qualified to convert it; a lead at Application/Enrollment or later is already past it"
STUDENT_EXISTS = "An IT student already has this email or mobile. Link the existing student instead."
EMAIL_TAKEN = "This email belongs to another account. Use a different email."
SUM_MISMATCH = "The installments must add up to the fee"
NO_FEE_PLAN = "A fee of 0 takes no installments"
DUE_PAST = "Each installment is due today or later"
NOT_FOUND = "Enrolment not found"
ITEM_NOT_FOUND = "Checklist item not found"
NO_ACCESS = "You do not have access to onboarding checklists"
CONVERTED = "lead.convert_it"
TICKED = "it.onboarding.item_update"


def require_key(key: str | None) -> str:
    if not key:
        raise HTTPException(422, KEY_REQUIRED)
    if not KEY_PATTERN.fullmatch(key):
        raise HTTPException(422, KEY_INVALID)
    return key


async def _latest_counseling(db: AsyncSession, lead_id: UUID) -> LeadCounselingRecord | None:
    stmt = select(LeadCounselingRecord).where(LeadCounselingRecord.lead_id == lead_id).order_by(LeadCounselingRecord.created_at.desc()).limit(1)
    return await db.scalar(stmt)


async def template(db: AsyncSession) -> list[str]:
    stmt = select(ItOnboardingTemplateItem.label).where(ItOnboardingTemplateItem.active.is_(True)).order_by(ItOnboardingTemplateItem.position, ItOnboardingTemplateItem.id)
    return list(await db.scalars(stmt))


async def options(db: AsyncSession, lead: Enquiry) -> dict:
    """The dialog's prefill (the lead's contact, the latest counseling session's fee and recommended course), the open IT batches with a
    seat left (the recommended course's first) and the checklist preview. Read only."""
    record = await _latest_counseling(db, lead.id)
    product = await db.get(TelProduct, record.recommended_product_id) if record and record.recommended_product_id else None
    recommended = product.program_id if product else None
    seats = select(Enrollment.batch_id, func.count(Enrollment.id).label("taken")).where(Enrollment.status.in_(it_enrollments.SEATED)).group_by(Enrollment.batch_id).subquery()
    stmt = (
        select(Batch, Program, func.coalesce(seats.c.taken, 0))
        .join(Program, Program.id == Batch.program_id)
        .outerjoin(seats, seats.c.batch_id == Batch.id)
        .where(Batch.enrollment_open.is_(True), Batch.status.in_(("upcoming", "active")), Batch.end_date >= today_ist(await db_now(db)))
        .order_by(Batch.start_date, Batch.name)
    )
    batches = [
        {"id": b.id, "name": b.name, "program_id": p.id, "program": p.title, "fee": float(p.fees), "start_date": b.start_date, "end_date": b.end_date,
         "schedule": b.schedule, "mode": b.mode, "available": b.capacity - taken, "recommended": p.id == recommended}
        for b, p, taken in (await db.execute(stmt)).all()
        if taken < b.capacity
    ]  # fmt: skip
    batches.sort(key=lambda b: not b["recommended"])  # stable: the recommended course's batches first, each group by start date
    return {
        "prefill": {
            "full_name": lead.name, "email": lead.email, "phone": lead.phone,
            "fee": float(record.fee_quoted) if record and record.fee_quoted is not None else None,
            "recommended_program_id": recommended, "recommended_course": product.name if product else None,
        },
        "batches": batches,
        "checklist": await template(db),
    }  # fmt: skip


async def replay(db: AsyncSession, lead: Enquiry, key: str) -> ItConversion | None:
    return await db.scalar(select(ItConversion).where(ItConversion.lead_id == lead.id, ItConversion.idempotency_key == key))


def _check_lead(lead: Enquiry) -> None:
    if lead.division != "it":
        raise HTTPException(409, NOT_IT)
    if lead.converted_user_id is not None:
        raise HTTPException(409, bdm_leads.ALREADY_LINKED)
    if lead.status in CLOSED:
        raise HTTPException(409, CLOSED_LEAD)
    if not lead_handover.convertible_stage(lead.status):
        raise HTTPException(409, NOT_CONVERTIBLE)


async def _check_plan(db: AsyncSession, payload: ItConversionIn) -> None:
    """C6/C7: no plan for a fee of 0; otherwise the installments (if any) add up to the fee and fall due today or later (IST)."""
    if not payload.installments:
        return
    if payload.fee == 0:
        raise invalid("installments", NO_FEE_PLAN, len(payload.installments))
    if sum((i.amount for i in payload.installments), Decimal(0)) != payload.fee:
        raise invalid("installments", SUM_MISMATCH, str(payload.fee))
    today = today_ist(await db_now(db))
    if any(i.due_date < today for i in payload.installments):
        raise invalid("installments", DUE_PAST, today.isoformat())


async def _student(db: AsyncSession, actor: User, lead: Enquiry, payload: ItConversionIn) -> tuple[User, IssuedWelcome | None]:
    """C3: the chosen existing IT student (the link's own one-message 422), or a new account. A new account whose email or mobile matches
    an active IT student is 409 `student_exists` (the dialog offers that student); an email of any other account is 409 without naming
    it (C4)."""
    if payload.student_id is not None:
        return await bdm_leads.locked_student(db, lead, User.id == payload.student_id), None
    entry = payload.student
    matches = lead_handover.contact_matches(entry.email, entry.phone)
    if matches and await db.scalar(select(exists().where(*lead_handover.student_filters("it"), or_(*matches)))):
        raise HTTPException(409, {"code": "student_exists", "message": STUDENT_EXISTS})
    if await db.scalar(select(exists().where(func.lower(User.email) == entry.email.lower()))):
        raise HTTPException(409, EMAIL_TAKEN)
    return await counselor_students.create_student(db, actor, entry, registration_source="lead_conversion", division="it")


async def _bill(db: AsyncSession, student: User, enrollment: Enrollment, payload: ItConversionIn) -> int:
    """itc-013's fee rows: none for a fee of 0 (C6), one pending row for the whole fee, or one per installment (C7). Each gets its invoice."""
    from app.api.payments import _ensure_invoice  # noqa: PLC0415 -- the payments API imports fee_accounts, which this module imports

    if payload.fee == 0:
        return 0
    parts = [(i.amount, i.due_date, n) for n, i in enumerate(payload.installments, start=1)] or [(payload.fee, None, None)]
    for amount, due, number in parts:
        payment = Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=amount, currency="INR",
                          provider="manual", status="pending", is_manual=True, due_date=due, installment_no=number)  # fmt: skip
        db.add(payment)
        await db.flush()
        await _ensure_invoice(db, payment, student)
    return len(parts)


async def _checklist(db: AsyncSession, enrollment: Enrollment) -> int:
    labels = await template(db)
    db.add_all(ItOnboardingItem(enrollment_id=enrollment.id, label=label, position=n) for n, label in enumerate(labels, start=1))
    return len(labels)


async def convert(db: AsyncSession, actor: User, lead: Enquiry, payload: ItConversionIn, key: str) -> tuple[ItConversion, IssuedWelcome | None]:
    """On the locked lead, no commit. Lock order: lead -> actor (a new account's mail budget) -> student -> batch."""
    _check_lead(lead)
    await _check_plan(db, payload)
    student, issued = await _student(db, actor, lead, payload)
    student_id = student.id
    await lead_handover.link_student(db, actor, lead, User.id == student_id)
    enrollment, batch = await it_enrollments.seat(db, student, payload.batch_id)
    rows = await _bill(db, student, enrollment, payload)
    await it_lifecycle.sync(db, [enrollment.id], actor=actor, cause="enrolment")  # itc-031: the first history row, as POST /it/enrollments
    items = await _checklist(db, enrollment)
    row = ItConversion(lead_id=lead.id, idempotency_key=key, actor_user_id=actor.id, student_user_id=student_id, enrollment_id=enrollment.id,
                       created_account=issued is not None)  # fmt: skip
    db.add(row)
    db.add(AuditLog(user_id=actor.id, action=CONVERTED, entity_type="enquiry", entity_id=str(lead.id),
                    metadata_json={"student_id": str(student_id), "enrollment_id": str(enrollment.id), "batch_id": str(batch.id),
                                   "created_account": issued is not None, "fee_rows": rows, "checklist_items": items}))  # fmt: skip
    notice = Notification(user_id=student_id, title="Enrollment confirmed", read=False, action_url="/it/student/course",
                          body=f"You are enrolled in {batch.name}. Your enrollment number is {enrollment.enrollment_code}. "
                               "Review and accept the enrolment agreement to activate it.")  # fmt: skip
    db.add(notice)
    await db.flush()
    await queue_deliveries(db, notice, student)
    logger.info("lead_converted_to_it_student", extra={"extra_fields": {"actor_id": str(actor.id), "lead_id": str(lead.id), "student_id": str(student_id),
                                                                        "enrollment_id": str(enrollment.id), "created_account": issued is not None}})  # fmt: skip
    return row, issued


# --- the onboarding checklist ---------------------------------------------------------------------------------------------------


async def checklist(db: AsyncSession, enrollment_id: UUID) -> list[dict]:
    stmt = select(ItOnboardingItem).where(ItOnboardingItem.enrollment_id == enrollment_id).order_by(ItOnboardingItem.position, ItOnboardingItem.id)
    return [{"id": i.id, "label": i.label, "position": i.position, "done": i.done_at is not None, "done_at": i.done_at} for i in await db.scalars(stmt)]


async def reachable(db: AsyncSession, user: User, enrollment_id: UUID, *, write: bool) -> Enrollment:
    """The student reads their own; the student's IT counselor (itc-003) and the IT Admin read and tick. Out of reach 404, any other
    role 403."""
    student = user.role == "it_student"
    counselor = user.role == "counselor" and user.division == "it"
    if not (counselor or user.role == "it_admin" or (student and not write)):
        raise HTTPException(403, NO_ACCESS)
    enrollment = await db.get(Enrollment, enrollment_id)
    if enrollment is None or (student and enrollment.student_id != user.id):
        raise HTTPException(404, NOT_FOUND)
    if counselor:
        linked = await db.scalar(select(ItStudentCounselor.id).where(ItStudentCounselor.student_user_id == enrollment.student_id, ItStudentCounselor.counselor_user_id == user.id))
        if linked is None:
            raise HTTPException(404, NOT_FOUND)
    return enrollment


async def tick(db: AsyncSession, user: User, enrollment: Enrollment, item_id: UUID, done: bool) -> None:
    """No commit. The same value changes nothing; a change is audited (ids only)."""
    stmt = select(ItOnboardingItem).where(ItOnboardingItem.id == item_id, ItOnboardingItem.enrollment_id == enrollment.id).with_for_update()
    item = await db.scalar(stmt)
    if item is None:
        raise HTTPException(404, ITEM_NOT_FOUND)
    if (item.done_at is not None) == done:
        return
    item.done_at, item.done_by_user_id = (await db_now(db), user.id) if done else (None, None)
    db.add(AuditLog(user_id=user.id, action=TICKED, entity_type="enrollment", entity_id=str(enrollment.id), metadata_json={"item_id": str(item.id), "done": done}))


async def out(db: AsyncSession, row: ItConversion) -> dict:
    """The conversion's result as it now is: the student, the enrolment, its fee account and checklist."""
    student = await db.get(User, row.student_user_id)
    enrollment = await db.get(Enrollment, row.enrollment_id)
    account = await fee_accounts.account(db, enrollment)
    return {
        "student": counselor_students.student_out(student, "pending_setup" if row.created_account else None),
        "enrollment": {"id": enrollment.id, "enrollment_code": enrollment.enrollment_code, "status": enrollment.status, "course": account["course"],
                       "batch": account["batch"]},
        "fee_account": account,
        "checklist": await checklist(db, enrollment.id),
    }  # fmt: skip

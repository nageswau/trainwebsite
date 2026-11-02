"""itc-020 (DEC-SCOPE-344): the batch timetable -- weekly slots edited by the IT Admin, single classes cancelled, and the calendar of dated
classes every IT role reads (`occurrences`).

Classes are COMPUTED from the slots over a bounded window (T1); nothing is materialised, so editing a slot moves every future class at
once. Existing `LiveSession`s of the same batches are merged into the calendar. Slot writes lock the batch row (and its trainer's user
row) FOR UPDATE, so two concurrent edits cannot both pass the overlap check. Functions here never commit; audit rows carry ids and field
names only."""

import logging
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Batch, BatchTimetableCancellation, BatchTimetableSlot, Enrollment, ItStudentCounselor, LiveSession, Program, User
from app.notifications.events import notify
from app.schemas import TimetableCancelIn, TimetableSlotIn
from app.services import student_access

logger = logging.getLogger("app.batch_timetable")

EDITORS = {"it_admin", "super_admin"}
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MAX_DAYS = 62
DEFAULT_DAYS = 14
IST = ZoneInfo("Asia/Kolkata")
STUDENT_URL = "/it/student/timetable"
FIELDS = ("weekday", "start_time", "end_time", "mode", "room", "meeting_url", "topic")


def require_editor(user: User) -> None:
    if user.role not in EDITORS:
        raise HTTPException(403, "Only the IT Admin can edit a timetable")


def _zone(batch: Batch) -> ZoneInfo:
    try:
        return ZoneInfo(batch.timezone or "Asia/Kolkata")
    except ZoneInfoNotFoundError:
        return IST


def today_for(batch: Batch) -> date:
    return datetime.now(UTC).astimezone(_zone(batch)).date()


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def slot_out(slot: BatchTimetableSlot) -> dict:
    return {"id": slot.id, "batch_id": slot.batch_id, "weekday": slot.weekday, "day": DAYS[slot.weekday], "start_time": _hhmm(slot.start_time),
            "end_time": _hhmm(slot.end_time), "mode": slot.mode, "room": slot.room, "meeting_url": slot.meeting_url, "topic": slot.topic}  # fmt: skip


async def batch_or_404(db: AsyncSession, batch_id: UUID, *, lock: bool = True) -> Batch:
    stmt = select(Batch).where(Batch.id == batch_id)
    batch = await db.scalar(stmt.with_for_update() if lock else stmt)
    if batch is None:
        raise HTTPException(404, "Batch not found")
    return batch


async def slots_of(db: AsyncSession, batch: Batch) -> list[BatchTimetableSlot]:
    stmt = select(BatchTimetableSlot).where(BatchTimetableSlot.batch_id == batch.id)
    return list(await db.scalars(stmt.order_by(BatchTimetableSlot.weekday, BatchTimetableSlot.start_time)))


async def _slot(db: AsyncSession, batch: Batch, slot_id: UUID) -> BatchTimetableSlot:
    slot = await db.scalar(select(BatchTimetableSlot).where(BatchTimetableSlot.id == slot_id, BatchTimetableSlot.batch_id == batch.id))
    if slot is None:
        raise HTTPException(404, "Timetable slot not found")
    return slot


async def _refuse_overlap(db: AsyncSession, batch: Batch, data: TimetableSlotIn, exclude: UUID | None) -> None:
    """T3: same weekday and intersecting times -- in this batch, or in another batch of the same trainer whose dates intersect -> 409."""
    clash = (BatchTimetableSlot.weekday == data.weekday, BatchTimetableSlot.start_time < data.end_time, BatchTimetableSlot.end_time > data.start_time)
    if exclude is not None:
        clash = (*clash, BatchTimetableSlot.id != exclude)
    own = await db.scalar(select(BatchTimetableSlot).where(BatchTimetableSlot.batch_id == batch.id, *clash).limit(1))
    if own is not None:
        raise HTTPException(409, f"This batch already has a class on {DAYS[own.weekday]} {_hhmm(own.start_time)}–{_hhmm(own.end_time)}")
    if batch.trainer_id is None:
        return
    await db.scalar(select(User.id).where(User.id == batch.trainer_id).with_for_update())  # serialises edits of this trainer's batches
    other = await db.scalar(
        select(Batch.name)
        .join(BatchTimetableSlot, BatchTimetableSlot.batch_id == Batch.id)
        .where(Batch.trainer_id == batch.trainer_id, Batch.id != batch.id, Batch.start_date <= batch.end_date, Batch.end_date >= batch.start_date, *clash)
        .limit(1)
    )
    if other is not None:
        raise HTTPException(409, f"The trainer already teaches {other} at that time")


def _audit(user: User, action: str, batch: Batch, slot_id: UUID, meta: dict) -> AuditLog:
    return AuditLog(user_id=user.id, action=action, entity_type="batch", entity_id=str(batch.id), metadata_json={"slot_id": str(slot_id), **meta})


async def create_slot(db: AsyncSession, user: User, batch: Batch, data: TimetableSlotIn) -> BatchTimetableSlot:
    await _refuse_overlap(db, batch, data, None)
    slot = BatchTimetableSlot(batch_id=batch.id, **data.model_dump())
    db.add(slot)
    await db.flush()
    db.add(_audit(user, "batch.timetable.create", batch, slot.id, {"weekday": slot.weekday, "mode": slot.mode}))
    return slot


async def update_slot(db: AsyncSession, user: User, batch: Batch, slot_id: UUID, data: TimetableSlotIn) -> BatchTimetableSlot:
    slot = await _slot(db, batch, slot_id)
    changed = [f for f in FIELDS if getattr(slot, f) != getattr(data, f)]
    if changed:
        await _refuse_overlap(db, batch, data, slot.id)
        for field in changed:
            setattr(slot, field, getattr(data, field))
        db.add(_audit(user, "batch.timetable.update", batch, slot.id, {"changed": changed}))
    return slot


async def delete_slot(db: AsyncSession, user: User, batch: Batch, slot_id: UUID) -> None:
    slot = await _slot(db, batch, slot_id)
    await db.delete(slot)  # its cancellations go with it (ON DELETE CASCADE)
    db.add(_audit(user, "batch.timetable.delete", batch, slot_id, {"weekday": slot.weekday}))


async def cancel_class(db: AsyncSession, user: User, batch: Batch, slot_id: UUID, data: TimetableCancelIn) -> BatchTimetableCancellation:
    slot = await _slot(db, batch, slot_id)
    day = data.occurs_on
    if day.weekday() != slot.weekday or not batch.start_date <= day <= batch.end_date:
        raise HTTPException(422, "That date is not a class of this slot")
    if day < today_for(batch):
        raise HTTPException(422, "A past class cannot be cancelled")
    if await db.scalar(select(BatchTimetableCancellation.id).where(BatchTimetableCancellation.slot_id == slot.id, BatchTimetableCancellation.occurs_on == day)):
        raise HTTPException(409, "That class is already cancelled")
    row = BatchTimetableCancellation(slot_id=slot.id, occurs_on=day, reason=data.reason, cancelled_by_user_id=user.id)
    db.add(row)
    db.add(_audit(user, "batch.timetable.cancel", batch, slot.id, {"occurs_on": day.isoformat()}))
    students = await db.scalars(select(User).join(Enrollment, Enrollment.student_id == User.id).where(Enrollment.batch_id == batch.id, Enrollment.status == "active"))
    await notify(db, students, "it.batch.changed", batch.id, action_url=STUDENT_URL)  # itc-002: fixed text; counselors are itc-025
    logger.info("timetable_class_cancelled", extra={"extra_fields": {"batch_id": str(batch.id), "slot_id": str(slot.id), "occurs_on": day.isoformat()}})
    return row


# --- the calendar ---------------------------------------------------------------------------------------------------------------------


def window(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    start = start or today
    end = end or start + timedelta(days=DEFAULT_DAYS - 1)
    if end < start:
        raise HTTPException(422, "The end date must be on or after the start date")
    if (end - start).days >= MAX_DAYS:
        raise HTTPException(422, f"Choose at most {MAX_DAYS} days")
    return start, end


def _scoped_batches(user: User):
    """The batches whose classes `user` may read (spec §4), or None for a role that reads none."""
    stmt = select(Batch, Program).join(Program, Program.id == Batch.program_id)
    if user.role in EDITORS:
        return stmt
    if user.role == "trainer":
        return stmt.where(Batch.trainer_id == user.id)
    if user.role == "it_student":
        return stmt.join(Enrollment, Enrollment.batch_id == Batch.id).where(Enrollment.student_id == user.id, Enrollment.status == "active")
    if user.role == "counselor" and user.division == "it":
        linked = select(Enrollment.batch_id).join(ItStudentCounselor, ItStudentCounselor.student_user_id == Enrollment.student_id)
        return stmt.where(Batch.id.in_(linked.where(ItStudentCounselor.counselor_user_id == user.id, Enrollment.status == "active")))
    return None


def _expand(slot: BatchTimetableSlot, batch: Batch, start: date, end: date):
    lo, hi = max(start, batch.start_date), min(end, batch.end_date)
    if lo > hi:
        return
    day = lo + timedelta(days=(slot.weekday - lo.weekday()) % 7)
    while day <= hi:
        yield day
        day += timedelta(days=7)


async def occurrences(db: AsyncSession, user: User, start: date | None, end: date | None, batch_id: UUID | None) -> dict:
    stmt = _scoped_batches(user)
    if stmt is None:
        raise HTTPException(403, "You cannot view a batch timetable")
    start, end = window(start, end, datetime.now(UTC).astimezone(IST).date())
    if batch_id is not None:
        found = (await db.execute(stmt.where(Batch.id == batch_id))).first()
        if found is None:
            raise HTTPException(404, "Batch not found")
    stmt = stmt.where(Batch.start_date <= end, Batch.end_date >= start)
    if batch_id is not None:
        stmt = stmt.where(Batch.id == batch_id)
    batches = {b.id: (b, p) for b, p in (await db.execute(stmt)).all()}
    student = user.role == "it_student"
    hide_links = user.role == "counselor" or (student and student_access.lock(await student_access.summary(db, user), "live_classes") is not None)
    items = []
    if batches:
        slots = list(await db.scalars(select(BatchTimetableSlot).where(BatchTimetableSlot.batch_id.in_(list(batches)))))
        rows = await db.scalars(select(BatchTimetableCancellation).where(BatchTimetableCancellation.slot_id.in_([s.id for s in slots]), BatchTimetableCancellation.occurs_on.between(start, end)))
        cancelled = {(c.slot_id, c.occurs_on): c.reason for c in rows}
        for slot in slots:
            batch, program = batches[slot.batch_id]
            zone = _zone(batch)
            for day in _expand(slot, batch, start, end):
                reason = cancelled.get((slot.id, day))
                items.append({
                    "id": f"{slot.id}:{day.isoformat()}", "kind": "class", "slot_id": slot.id, "batch_id": batch.id, "batch": batch.name,
                    "program": program.title, "date": day, "starts_at": datetime.combine(day, slot.start_time, zone),
                    "ends_at": datetime.combine(day, slot.end_time, zone), "mode": slot.mode, "room": slot.room, "meeting_url": slot.meeting_url,
                    "topic": slot.topic, "status": "cancelled" if reason is not None else "scheduled", "cancel_reason": reason,
                })  # fmt: skip
        lo = datetime.combine(start, time(), IST)
        hi = datetime.combine(end + timedelta(days=1), time(), IST)
        sessions = await db.scalars(select(LiveSession).where(LiveSession.batch_id.in_(list(batches)), LiveSession.starts_at >= lo, LiveSession.starts_at < hi))
        for s in sessions:
            batch, program = batches[s.batch_id]
            cancelled_session = s.status == "cancelled"
            items.append({
                "id": str(s.id), "kind": "live_session", "slot_id": None, "batch_id": batch.id, "batch": batch.name, "program": program.title,
                "date": s.starts_at.astimezone(_zone(batch)).date(), "starts_at": s.starts_at, "ends_at": s.ends_at, "mode": "online", "room": None,
                "meeting_url": s.meeting_url, "topic": s.title, "status": "cancelled" if cancelled_session else "scheduled",
                "cancel_reason": s.cancel_reason if cancelled_session else None,
            })  # fmt: skip
    if student:
        items = [i for i in items if i["status"] != "cancelled"]
    if hide_links:
        for item in items:
            item["meeting_url"] = None
    items.sort(key=lambda i: (i["starts_at"], i["batch"]))
    return {"from": start, "to": end, "can_edit": user.role in EDITORS, "items": items}

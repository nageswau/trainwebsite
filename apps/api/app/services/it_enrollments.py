"""itc-011: seating an IT student in a batch -- the checks and the insert `POST /it/enrollments` always made (`api/workflows.py`), shared
with the one-step conversion (`services/it_conversion.py`). No commit; the batch row is locked so the capacity check holds under
concurrency. DEC-WF-002: the slot is locked at once; STU-009-AC02: the enrolment starts `pending_consent` until the student accepts the
agreement."""

import secrets
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Batch, Enrollment, User

SEATED = ("active", "pending_consent")  # both hold a seat
BATCH_NOT_FOUND = "Batch not found"
BATCH_CLOSED = "Enrollment is closed for this batch"
ALREADY_ENROLLED = "Student is already enrolled in this batch"
BATCH_FULL = "This batch is full"


async def seat(db: AsyncSession, student: User, batch_id: UUID) -> tuple[Enrollment, Batch]:
    batch = await db.scalar(select(Batch).where(Batch.id == batch_id).with_for_update())
    if not batch:
        raise HTTPException(404, BATCH_NOT_FOUND)
    if not batch.enrollment_open or batch.status not in {"upcoming", "active"}:
        raise HTTPException(409, BATCH_CLOSED)
    existing = await db.scalar(select(Enrollment).where(Enrollment.student_id == student.id, Enrollment.batch_id == batch.id))
    if existing:
        raise HTTPException(409, ALREADY_ENROLLED)
    count = await db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.batch_id == batch.id, Enrollment.status.in_(SEATED))) or 0
    if count >= batch.capacity:
        raise HTTPException(409, BATCH_FULL)
    code = f"EDU-{date.today():%Y%m%d}-{secrets.token_hex(3).upper()}"
    item = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=code, enrolled_on=date.today(), slot_locked=True, status="pending_consent", progress_percent=0)
    db.add(item)
    await db.flush()
    return item, batch

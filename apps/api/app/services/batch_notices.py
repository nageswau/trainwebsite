"""itc-025 (DEC-SCOPE-346): a batch, course or timetable change, or a student transfer, tells the affected IT students and their linked
IT counselors (itc-003) -- one notice each (itc-002 dedupes per recipient, event and batch in the transaction), with a summary of the
changed fields from the fixed `CHANGE_LABELS` vocabulary. Never commits: the caller's transaction publishes, a rollback sends nothing."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Enrollment, ItStudentCounselor, User
from app.notifications.events import notify

COURSE_URL, COUNSELOR_URL = "/it/student/course", "/it/counselor/timetable"
# The batch columns students see -> their change label. Capacity, enrolment-open and status are admin-internal and notify nobody.
BATCH_FIELDS = {"name": "name", "start_date": "start_date", "end_date": "end_date", "trainer_id": "trainer", "schedule": "timetable", "timezone": "timezone", "mode": "mode"}


async def notify_batch_change(db: AsyncSession, batch_id: UUID, changes: Sequence[str], *, action_url: str, students: Sequence[User] | None = None) -> None:
    """`students` defaults to the batch's active enrolments (the rule itc-020 and nehn-029 already use); a transfer passes the one
    student who moved."""
    if students is None:
        query = select(User).join(Enrollment, Enrollment.student_id == User.id).where(Enrollment.batch_id == batch_id, Enrollment.status == "active")
        students = list(await db.scalars(query))
    if not students:
        return
    await notify(db, students, "it.batch.changed", batch_id, action_url=action_url, changes=changes)
    linked = select(ItStudentCounselor.counselor_user_id).where(ItStudentCounselor.student_user_id.in_([s.id for s in students]))
    counselors = await db.scalars(select(User).where(User.id.in_(linked)))
    await notify(db, counselors, "it.batch.student_changed", batch_id, action_url=COUNSELOR_URL, changes=changes)

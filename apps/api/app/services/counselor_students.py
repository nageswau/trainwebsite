"""csc-001 (DEC-SCOPE-226, W3): the overseas students a counselor works with -- the students of the counselor's own applications plus
the students linked to the counselor (`OverseasStudentCounselor`). The picker (`GET /lookups/overseas-students`) and the write it feeds
(`POST /workflows/overseas/appointments`) share this, so the picker never offers a student the write refuses (ENH-031 §5)."""

from uuid import UUID

from sqlalchemy import exists, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OverseasApplication, OverseasStudentCounselor, User


def visible_student_ids(counselor: User):
    """A subquery of student user ids, for `User.id.in_(...)`. A bridged application's NULL `student_id` matches nothing there."""
    return union(
        select(OverseasApplication.student_id).where(OverseasApplication.counselor_id == counselor.id),
        select(OverseasStudentCounselor.student_user_id).where(OverseasStudentCounselor.counselor_user_id == counselor.id),
    )


async def is_visible_student(db: AsyncSession, counselor: User, student_id: UUID) -> bool:
    return bool(await db.scalar(select(exists().where(User.id == student_id, User.id.in_(visible_student_ids(counselor))))))

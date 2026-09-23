"""Shared builders for the ENH-018 database tests. Schools come from ENH-005's `mk_school` (coordinator, principal, teacher,
parent, students), so each test owns throwaway rows and runs never collide."""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import SchoolActivity, SchoolActivityAttendance

FEEDBACK = {"rating": 4, "satisfaction": 5, "trainer_name": "Ms. Rao", "feedback": "Students were engaged.", "suggestions": "Longer Q&A."}
URL = "/api/v1/school/activities/{aid}/feedback"


async def mk_activity(db, school, coordinator, *, activity_type: str | None = "career_seminar", minutes: int = -60, title: str | None = None) -> SchoolActivity:
    activity = SchoolActivity(
        school_id=school.id, title=title or f"ENH-018 Activity {uuid.uuid4().hex[:6]}", scheduled_at=datetime.now(UTC) + timedelta(minutes=minutes),
        created_by_user_id=coordinator.id, activity_type=activity_type,
    )
    db.add(activity)
    await db.commit()
    return activity


async def mark(db, activity, coordinator, present: list, absent: list = ()) -> None:
    for student, was_present in [*((s, True) for s in present), *((s, False) for s in absent)]:
        db.add(SchoolActivityAttendance(activity_id=activity.id, school_student_id=student.id, present=was_present, marked_by_user_id=coordinator.id))
    await db.commit()

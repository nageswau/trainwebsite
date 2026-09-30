"""ENH-030 -- SchoolAttendanceRecord constraints (spec §4, D4/D5)."""

from datetime import date

import pytest
from enh005_helpers import mk_school
from sqlalchemy.exc import IntegrityError

from app.models import ATTENDANCE_STATUSES, SchoolAttendanceRecord


def test_statuses_mirror_it_attendance():
    assert ATTENDANCE_STATUSES == ("present", "absent", "late", "excused")


def _row(w, **over):
    s = w["students"][0]
    fields = {"school_student_id": s.id, "school_id": w["school"].id, "session_date": date(2026, 9, 1), "status": "present", "marked_by_user_id": w["teacher"].id}
    return SchoolAttendanceRecord(**{**fields, **over})


@pytest.mark.asyncio
async def test_one_record_per_student_per_day(db_session):
    w = await mk_school(db_session, label="AttModel")
    db_session.add(_row(w))
    await db_session.commit()
    db_session.add(_row(w, status="absent"))
    with pytest.raises(IntegrityError, match="uq_school_attendance_student_school_date"):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_status_is_checked_in_the_database(db_session):
    w = await mk_school(db_session, label="AttModel")
    db_session.add(_row(w, status="sick"))
    with pytest.raises(IntegrityError, match="ck_school_attendance_status"):
        await db_session.commit()
    await db_session.rollback()

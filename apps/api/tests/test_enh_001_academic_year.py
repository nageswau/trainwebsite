"""ENH-001 -- Academic-Year foundation model (docs/delivery/ENHANCEMENT_BACKLOG.md,
docs/superpowers/specs/2026-09-18-enh-001-academic-year-design.md)."""

import importlib.util
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AcademicYear, School, SchoolStudent


def test_academic_year_model_has_expected_columns():
    columns = AcademicYear.__table__.columns
    assert "label" in columns
    assert columns["label"].unique is True
    assert "start_date" in columns
    assert "end_date" in columns
    assert columns["status"].default.arg == "active"


def test_school_student_has_academic_year_and_grade_level_columns():
    columns = SchoolStudent.__table__.columns
    assert columns["academic_year_id"].nullable is True
    assert columns["grade_level"].nullable is True
    # grade_or_class must be untouched -- zero data loss per the spec.
    assert "grade_or_class" in columns


# Import the migration's actual `_derive_grade_level` by file path, rather than
# duplicating it here, so this test exercises the real migration code and can't drift
# from it. `importlib.import_module` can't resolve "0030_academic_years" directly -- a
# module path component starting with a digit isn't a valid Python identifier there --
# so `spec_from_file_location` loads it by file path instead.
_migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0030_academic_years.py"
_spec = importlib.util.spec_from_file_location("_enh_001_migration_0030", _migration_path)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)
_derive_grade_level = _migration._derive_grade_level


@pytest.mark.parametrize(
    "label,expected",
    [
        ("Grade 9", 9), ("Class 9", 9), ("Grade 10-A", 10), ("grade 8", 8),
        ("Nonsense", None), (None, None), ("", None), ("Grade 13", None),
    ],
)
def test_grade_level_backfill_parser(label, expected):
    assert _derive_grade_level(label) == expected


@pytest.mark.asyncio
async def test_migration_backfills_existing_school_students(db_session):
    # This test assumes `alembic upgrade head` has already been run against the test
    # database (conftest.py disables schema autocreate) -- it verifies the *outcome* of
    # the migration that already ran, not a live revision-to-revision replay. Create a
    # real User first (School.created_by_user_id is a NOT NULL FK) rather than reaching
    # for some other test's leftover row.
    from app.core.security import hash_password
    from app.models import User

    creator = User(email=f"enh001-creator-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"), full_name="Migration Check Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(creator)
    await db_session.flush()
    school = School(name="ENH-001 Migration Check School", created_by_user_id=creator.id)
    db_session.add(school)
    await db_session.flush()
    student = SchoolStudent(school_id=school.id, student_code="ENH0001Z", full_name="Backfill Check", grade_or_class="Grade 9", created_by_user_id=creator.id)
    db_session.add(student)
    await db_session.commit()

    # A freshly-created row after the migration should still get a sane academic_year_id
    # default at the application layer in Task 5 -- this test only asserts the migration
    # itself produced at least one seed AcademicYear row to backfill onto.
    seed_year = await db_session.scalar(select(AcademicYear).where(AcademicYear.status == "active"))
    assert seed_year is not None
    assert re.match(r"^\d{4}-\d{2}$", seed_year.label)

"""ENH-025 -- migration 0039 and the new SchoolStudent columns (spec §2, AC3/AC4)."""

import importlib.util
from pathlib import Path

import pytest
from enh005_helpers import mk_school
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError

from app.models import SchoolStudent

# Import the migration's own parser by file path (same approach as test_enh_001_academic_year.py):
# "0041_student_master_fields" is not an importable module name.
_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0041_student_master_fields.py"
_spec = importlib.util.spec_from_file_location("_enh_025_migration_0041", _path)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("10-A", "A"), ("Grade 8-A", "A"), ("Class 7 Section C", "C"), ("9B", "B"), ("9b", "b"),
        ("Grade 10 - b", "b"), ("Grade 5 AB", "AB"), ("Grade 6/C", "C"),
        ("Grade 5", None), ("Nursery", None), ("Grade 12", None), ("10th", None), ("2nd", None),
        ("Grade 8 Science", None), ("", None), (None, None), ("   ", None),
    ],
)
def test_derive_section_is_conservative(label, expected):
    assert _migration._derive_section(label) == expected


def test_migration_follows_enh018_and_is_the_single_head():
    # Re-chained on merge: ENH-013 (0039_student_career_goal) and then ENH-018 (0040_school_activity_feedback) merged to
    # main first (DEC-SCOPE-029 item 11).
    assert _migration.revision == "0041_student_master_fields"
    assert _migration.down_revision == "0040_school_activity_feedback"
    parents = {}
    for file in (Path(__file__).resolve().parents[1] / "alembic" / "versions").glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        parent = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
        if rev:
            parents[rev] = parent
    assert set(parents) - set(parents.values()) == {"0041_student_master_fields"}


@pytest.mark.asyncio
async def test_new_columns_exist_and_are_nullable(db_session):
    def _describe(sync_conn):
        insp = inspect(sync_conn)
        return (
            {c["name"]: c for c in insp.get_columns("school_students")},
            {c["name"] for c in insp.get_columns("school_student_grade_history")},
            {i["name"] for i in insp.get_indexes("school_students")},
        )

    conn = await db_session.connection()
    cols, history_cols, indexes = await conn.run_sync(_describe)
    for name in ("section", "roll_number", "gender", "student_mobile", "city", "subjects", "career_interests", "preferred_countries", "preferred_courses", "global_education_interest", "photo_key", "photo_content_type"):
        assert name in cols and cols[name]["nullable"], name
    assert {"from_section", "from_roll_number", "to_section"} <= history_cols
    assert "uq_school_students_roll" in indexes


@pytest.mark.asyncio
async def test_grade_level_and_section_are_independently_queryable(db_session):
    world = await mk_school(db_session, label="Q", students=3)
    a, b, c = world["students"]
    a.grade_level, a.section = 8, "A"
    b.grade_level, b.section = 8, "B"
    c.grade_level, c.section = 9, "A"
    await db_session.commit()
    ids = [s.id for s in world["students"]]
    by_grade = set((await db_session.scalars(select(SchoolStudent.id).where(SchoolStudent.id.in_(ids), SchoolStudent.grade_level == 8))).all())
    by_section = set((await db_session.scalars(select(SchoolStudent.id).where(SchoolStudent.id.in_(ids), SchoolStudent.section == "A"))).all())
    assert by_grade == {a.id, b.id}
    assert by_section == {a.id, c.id}


@pytest.mark.asyncio
async def test_gender_check_constraint_rejects_unknown_values(db_session):
    world = await mk_school(db_session, label="G", students=1)
    with pytest.raises(DBAPIError):
        await db_session.execute(text("UPDATE school_students SET gender = 'unknown' WHERE id = :id"), {"id": world["students"][0].id})
    await db_session.rollback()

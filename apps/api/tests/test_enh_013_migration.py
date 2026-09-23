"""ENH-013 -- school_students.career_goal (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §5):
additive, nullable, no default, no backfill."""
import pytest
from sqlalchemy import text

from tests.enh005_helpers import mk_school


@pytest.mark.asyncio
async def test_career_goal_column_is_a_nullable_varchar_120_without_default(db_session):
    row = (await db_session.execute(text(
        "SELECT data_type, character_maximum_length, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_name = 'school_students' AND column_name = 'career_goal'"
    ))).one_or_none()
    assert row is not None, "migration 0039 not applied"
    assert tuple(row) == ("character varying", 120, "YES", None)


@pytest.mark.asyncio
async def test_alembic_is_at_0039(db_session):
    assert await db_session.scalar(text("SELECT version_num FROM alembic_version")) == "0039_student_career_goal"


@pytest.mark.asyncio
async def test_students_default_to_no_career_goal(db_session):
    ctx = await mk_school(db_session, label="E13-Mig")
    assert ctx["students"][0].career_goal is None

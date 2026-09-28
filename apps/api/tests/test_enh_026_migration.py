"""ENH-026 -- school_career_records structured fields (spec §4.1, DEC-SCOPE-031): additive, nullable, no backfill."""
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from enh005_helpers import mk_school, mk_staff
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import SchoolCareerRecord

NEW_COLUMNS = {
    "status": "character varying", "scheduled_for": "timestamp with time zone", "completed_on": "date",
    "next_follow_up_date": "date", "career_interests": "json", "global_education_interest": "boolean",
    "academic_strengths": "json", "weak_areas": "json", "recommended_careers": "json", "recommended_courses": "json",
    "recommended_stream": "json", "recommended_skills": "json", "parent_participated": "boolean",
    "parent_participation_note": "character varying", "updated_by_user_id": "uuid",
}


@pytest.mark.asyncio
async def test_new_columns_exist_nullable_without_default(db_session):
    rows = (await db_session.execute(text(
        "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_name = 'school_career_records'"
    ))).all()
    found = {r[0]: r for r in rows}
    for name, data_type in NEW_COLUMNS.items():
        assert name in found, f"{name} missing -- migration 0042 not applied"
        assert tuple(found[name][1:]) == (data_type, "YES", None), name


@pytest.mark.asyncio
async def test_alembic_is_at_head_and_includes_0042(db_session):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    version = await db_session.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == script.get_current_head()
    assert "0042_career_record_fields" in {rev.revision for rev in script.iterate_revisions(version, "base")}


@pytest.mark.asyncio
async def test_a_record_written_the_old_way_has_every_new_field_null(db_session):
    ctx = await mk_school(db_session, label="E26-Mig")
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    record = SchoolCareerRecord(school_student_id=ctx["students"][0].id, career_counselor_user_id=counselor.id, record_type="counselling_note", notes="old")
    db_session.add(record)
    await db_session.commit()
    raw = (await db_session.execute(text("SELECT " + ", ".join(NEW_COLUMNS) + " FROM school_career_records WHERE id = :id"), {"id": record.id})).one()
    assert all(value is None for value in raw)  # SQL NULL, never JSON 'null'


@pytest.mark.asyncio
async def test_status_check_rejects_an_unknown_value(db_session):
    ctx = await mk_school(db_session, label="E26-Chk")
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    db_session.add(SchoolCareerRecord(school_student_id=ctx["students"][0].id, career_counselor_user_id=counselor.id, record_type="counselling_note", notes="n", status="done"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

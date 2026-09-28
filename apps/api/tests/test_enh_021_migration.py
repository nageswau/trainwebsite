"""ENH-021 -- portfolio_entries internship tracking columns (spec §4.2, DEC-SCOPE-032): additive, nullable, no backfill."""
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from enh005_helpers import mk_school
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import PortfolioEntry

COLUMNS = ("mentor_name", "mentor_designation", "attendance_percent", "completion_status", "feedback", "skills_acquired", "certificate_key", "certificate_content_type")


async def _entry(db, ctx, **kw):
    s, c = ctx["students"][0], ctx["coordinator"]
    entry = PortfolioEntry(school_student_id=s.id, title="Intern", created_by_user_id=c.id, updated_by_user_id=c.id, **{"section": "internship", **kw})
    db.add(entry)
    await db.commit()
    return entry


@pytest.mark.asyncio
async def test_columns_exist_and_are_nullable(db_session):
    rows = dict((await db_session.execute(text("SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name = 'portfolio_entries'"))).all())
    missing = [c for c in COLUMNS if rows.get(c) != "YES"]
    assert not missing, f"missing or not nullable: {missing} -- migration 0043 not applied"


@pytest.mark.asyncio
async def test_alembic_is_at_head_and_includes_0043(db_session):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    version = await db_session.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == script.get_current_head()
    assert "0043_portfolio_internship" in {rev.revision for rev in script.iterate_revisions(version, "base")}


@pytest.mark.asyncio
async def test_existing_style_entries_keep_every_new_field_null(db_session):
    ctx = await mk_school(db_session, label="E21-Mig")
    entry = await _entry(db_session, ctx, section="project")
    raw = (await db_session.execute(text("SELECT " + ", ".join(COLUMNS) + " FROM portfolio_entries WHERE id = :id"), {"id": entry.id})).one()
    assert all(v is None for v in raw)  # SQL NULL, never JSON 'null'
    assert entry.has_certificate is False


@pytest.mark.parametrize("kw", [{"attendance_percent": 101}, {"completion_status": "done"}, {"section": "project", "mentor_name": "M"}])
@pytest.mark.asyncio
async def test_checks_reject_bad_values(db_session, kw):
    ctx = await mk_school(db_session, label="E21-Chk")
    with pytest.raises(IntegrityError):
        await _entry(db_session, ctx, **kw)
    await db_session.rollback()

"""ENH-024 -- Skill India certification tracking.
docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md
"""

from datetime import date
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import PortfolioEntry
from tests.enh005_helpers import mk_school


def _row(ctx, **overrides) -> PortfolioEntry:
    fields = {"section": "certification", "title": "Retail Sales Associate", "created_by_user_id": ctx["coordinator"].id, "updated_by_user_id": ctx["coordinator"].id, **overrides}
    return PortfolioEntry(school_student_id=ctx["students"][0].id, **fields)


# --- Schema (migration 0042) --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_columns_are_nullable_and_sized(db_session):  # AC-10
    rows = (
        await db_session.execute(
            text(
                "SELECT column_name, data_type, character_maximum_length, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'portfolio_entries' AND column_name IN ('certification_type', 'certification_status', 'certificate_number', 'issued_on') "
                "ORDER BY column_name"
            )
        )
    ).all()
    assert [tuple(r) for r in rows] == [
        ("certificate_number", "character varying", 100, "YES"),
        ("certification_status", "character varying", 20, "YES"),
        ("certification_type", "character varying", 30, "YES"),
        ("issued_on", "date", None, "YES"),
    ]


@pytest.mark.asyncio
async def test_alembic_is_at_head_and_includes_0042(db_session):  # AC-10
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    version = await db_session.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == script.get_current_head()
    assert "0042_skill_india_certification" in {rev.revision for rev in script.iterate_revisions(version, "base")}


@pytest.mark.asyncio
async def test_a_plain_entry_stays_untagged(db_session):  # AC-10, AC-12
    ctx = await mk_school(db_session, label="E24-Plain")
    entry = _row(ctx)
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    assert (entry.certification_type, entry.certification_status, entry.certificate_number, entry.issued_on) == (None, None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"section": "award", "certification_type": "skill_india", "certification_status": "enrolled"},
        {"certification_type": "nsdc", "certification_status": "enrolled"},
        {"certification_type": "skill_india"},
        {"certification_status": "enrolled"},
        {"certificate_number": "SI-1"},
        {"issued_on": date(2026, 5, 1)},
        {"certification_type": "skill_india", "certification_status": "passed"},
        {"certification_type": "skill_india", "certification_status": "certified", "issued_on": date(2026, 5, 1)},
        {"certification_type": "skill_india", "certification_status": "certified", "certificate_number": "SI-1"},
    ],
)
async def test_database_rejects_every_invalid_combination(db_session, overrides):  # AC-09
    ctx = await mk_school(db_session, label="E24-Check")
    db_session.add(_row(ctx, **overrides))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_database_accepts_a_certified_skill_india_row(db_session):  # AC-09
    ctx = await mk_school(db_session, label="E24-CheckOK")
    db_session.add(_row(ctx, certification_type="skill_india", certification_status="certified", certificate_number="SI-1", issued_on=date(2026, 5, 1)))
    await db_session.commit()

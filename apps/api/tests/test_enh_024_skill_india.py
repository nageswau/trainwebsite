"""ENH-024 -- Skill India certification tracking.
docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md
"""

from datetime import date
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import PortfolioEntry
from app.schemas import (
    CERT_CERTIFIED_ERROR,
    CERT_FIELDS_UNTAGGED_ERROR,
    CERT_STATUS_REQUIRED_ERROR,
    CERT_TYPE_SECTION_ERROR,
    PortfolioEntryCreate,
    PortfolioEntryUpdate,
    skill_india_error,
)
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


# --- Schemas ------------------------------------------------------------------------------------------------------

SKILL_INDIA = {"section": "certification", "title": "Retail Sales Associate", "certification_type": "skill_india"}


def test_create_accepts_a_skill_india_certification():
    entry = PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled")
    assert (entry.certification_type, entry.certification_status, entry.certificate_number, entry.issued_on) == ("skill_india", "enrolled", None, None)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"section": "award", "certification_type": "skill_india", "certification_status": "enrolled"}, CERT_TYPE_SECTION_ERROR),
        ({"section": "certification", "certification_type": "skill_india"}, CERT_STATUS_REQUIRED_ERROR),
        ({"section": "certification", "certification_status": "enrolled"}, CERT_FIELDS_UNTAGGED_ERROR),
        ({"section": "certification", "certificate_number": "SI-1"}, CERT_FIELDS_UNTAGGED_ERROR),
        ({"section": "certification", "issued_on": "2026-05-01"}, CERT_FIELDS_UNTAGGED_ERROR),
        ({"section": "certification", "certification_type": "skill_india", "certification_status": "certified", "issued_on": "2026-05-01"}, CERT_CERTIFIED_ERROR),
        ({"section": "certification", "certification_type": "skill_india", "certification_status": "certified", "certificate_number": "SI-1"}, CERT_CERTIFIED_ERROR),
    ],
)
def test_create_rejects_with_a_plain_message(payload, message):  # AC-04
    with pytest.raises(ValidationError) as exc:
        PortfolioEntryCreate(title="Retail Sales Associate", **payload)
    assert message in exc.value.errors()[0]["msg"]


def test_create_accepts_explicit_nulls_on_an_untagged_entry():  # Review Focus 2
    entry = PortfolioEntryCreate(section="project", title="X", certification_type=None, certification_status=None, certificate_number=None, issued_on=None)
    assert entry.certification_type is None


def test_certificate_number_is_trimmed_and_blank_becomes_none():  # Review Focus 4
    assert PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled", certificate_number="  SI-9 ").certificate_number == "SI-9"
    assert PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled", certificate_number="   ").certificate_number is None


@pytest.mark.parametrize("bad", ["SI\n1", "SI\x001", "a" * 101])
def test_certificate_number_rejects_control_characters_and_overlength(bad):  # Review Focus 4
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled", certificate_number=bad)


@pytest.mark.parametrize("payload", [{"certification_type": "nsdc", "certification_status": "enrolled"}, {"certification_type": "skill_india", "certification_status": "passed"}])
def test_unknown_tag_or_status_is_rejected(payload):
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="certification", title="X", **payload)


def test_update_accepts_detail_fields_but_never_the_tag():  # AC-05
    update_ = PortfolioEntryUpdate(certification_status="certified", certificate_number="SI-1", issued_on="2026-05-01")
    assert update_.model_fields_set == {"certification_status", "certificate_number", "issued_on"}
    with pytest.raises(ValidationError):
        PortfolioEntryUpdate(certification_type="skill_india")


def test_skill_india_error_covers_every_rule():
    assert skill_india_error(None, None, None, None) is None
    assert skill_india_error(None, "enrolled", None, None) == CERT_FIELDS_UNTAGGED_ERROR
    assert skill_india_error("skill_india", None, None, None) == CERT_STATUS_REQUIRED_ERROR
    assert skill_india_error("skill_india", "certified", "SI-1", None) == CERT_CERTIFIED_ERROR
    assert skill_india_error("skill_india", "certified", "SI-1", date(2026, 5, 1)) is None
    assert skill_india_error("skill_india", "in_progress", None, None) is None

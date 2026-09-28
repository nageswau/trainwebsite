"""ENH-027 -- migration 0045 and the new SchoolPsychometricRecord columns (spec §3, AC09)."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_enh_027_migration_0045", VERSIONS / "0045_psychometric_result_fields.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

NEW_COLUMNS = (
    "test_date", "strengths", "interest_areas", "personality_indicators", "recommended_careers",
    "recommended_stream", "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on",
)


def test_migration_follows_enh024_and_is_the_single_head():
    # Re-chained on merge: ENH-024 (0044_skill_india_certification) reached main first on the same parent (DEC-SCOPE-035 ID note).
    assert _migration.revision == "0045_psychometric_result_fields"
    assert _migration.down_revision == "0044_skill_india_certification"
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        parent = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
        if rev:
            parents[rev] = parent
    assert set(parents) - set(parents.values()) == {"0045_psychometric_result_fields"}


def test_migration_adds_exactly_the_ten_columns():
    assert tuple(name for name, _ in _migration.COLUMNS) == NEW_COLUMNS


def test_model_declares_the_ten_nullable_columns():
    from app.models import SchoolPsychometricRecord

    columns = SchoolPsychometricRecord.__table__.columns
    for name in NEW_COLUMNS:
        assert name in columns and columns[name].nullable, name


@pytest.mark.asyncio
async def test_new_columns_exist_and_are_nullable(db_session):
    def _cols(sync_conn):
        return {c["name"]: c for c in inspect(sync_conn).get_columns("school_psychometric_records")}

    conn = await db_session.connection()
    cols = await conn.run_sync(_cols)
    for name in NEW_COLUMNS:
        assert name in cols and cols[name]["nullable"], name

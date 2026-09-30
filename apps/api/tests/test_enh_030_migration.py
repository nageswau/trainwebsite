"""ENH-030 -- migration 0046 (spec §4, AC13): single head, create-table only, matches the model."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_enh_030_migration_0046", VERSIONS / "0046_school_attendance_records.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def _parents() -> dict[str, str | None]:
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        parent = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
        if rev:
            parents[rev] = parent
    return parents


def test_migration_follows_0045_and_is_the_single_head():
    assert _migration.revision == "0046_school_attendance_records"
    assert _migration.down_revision == "0045_psychometric_result_fields"
    parents = _parents()
    heads = set(parents) - set(parents.values())
    assert len(heads) == 1
    assert "0045_psychometric_result_fields" in set(parents.values())


@pytest.mark.asyncio
async def test_table_matches_the_model(db_session):
    def _describe(sync_conn):
        insp = inspect(sync_conn)
        return (
            {c["name"]: c["nullable"] for c in insp.get_columns("school_attendance_records")},
            {u["name"] for u in insp.get_unique_constraints("school_attendance_records")},
            {c["name"] for c in insp.get_check_constraints("school_attendance_records")},
            {i["name"] for i in insp.get_indexes("school_attendance_records") if not i.get("duplicates_constraint")},
        )

    conn = await db_session.connection()
    columns, uniques, checks, indexes = await conn.run_sync(_describe)
    assert columns == {"id": False, "school_student_id": False, "school_id": False, "session_date": False, "status": False, "marked_by_user_id": False, "created_at": False, "updated_at": False}
    assert uniques == {"uq_school_attendance_student_school_date"}
    assert checks == {"ck_school_attendance_status"}
    assert indexes == set()  # the unique constraint's index is the only one (spec §11 A4)

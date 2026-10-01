"""ENH-028 -- migration 0051 (spec §4, AC13): single head, create-table only, matches the model."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_enh_028_migration_0051", VERSIONS / "0051_school_bulk_uploads.py")
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


def test_migration_follows_0050_and_is_the_single_head():
    assert _migration.revision == "0051_school_bulk_uploads"
    assert _migration.down_revision == "0050_notification_channels"
    parents = _parents()
    heads = set(parents) - set(parents.values())
    assert heads == {"0051_school_bulk_uploads"}


def test_migration_only_creates_and_drops_its_own_tables():
    source = (VERSIONS / "0051_school_bulk_uploads.py").read_text(encoding="utf-8")
    for forbidden in ("op.add_column", "op.alter_column", "op.drop_column", "op.execute", "UPDATE ", "DELETE "):
        assert forbidden not in source
    assert source.count("op.create_table(") == 2
    assert source.count("op.drop_table(") == 2


@pytest.mark.asyncio
async def test_tables_match_the_model(db_session):
    def _describe(sync_conn):
        insp = inspect(sync_conn)
        return {
            table: (
                {c["name"]: c["nullable"] for c in insp.get_columns(table)},
                {u["name"]: tuple(u["column_names"]) for u in insp.get_unique_constraints(table)},
                {c["name"] for c in insp.get_check_constraints(table)},
                {i["name"] for i in insp.get_indexes(table) if not i.get("duplicates_constraint")},
            )
            for table in ("school_bulk_upload_batches", "school_bulk_upload_rows")
        }

    conn = await db_session.connection()
    described = await conn.run_sync(_describe)

    columns, uniques, checks, indexes = described["school_bulk_upload_batches"]
    assert columns == {
        "id": False,
        "target_type": False,
        "uploaded_by_user_id": False,
        "idempotency_key": False,
        "file_sha256": False,
        "total_rows": False,
        "accepted_count": False,
        "rejected_count": False,
        "created_at": False,
        "updated_at": False,
    }
    assert uniques == {"uq_school_bulk_upload_key": ("uploaded_by_user_id", "target_type", "idempotency_key")}
    assert checks == {"ck_school_bulk_upload_target_type"}
    assert indexes == set()  # the unique constraint's index is the only one (spec §4)

    columns, uniques, checks, indexes = described["school_bulk_upload_rows"]
    assert columns == {
        "id": False,
        "batch_id": False,
        "row_number": False,
        "status": False,
        "error_message": True,
        "student_code": True,
        "created_record_id": True,
        "created_at": False,
        "updated_at": False,
    }
    assert uniques == {}
    assert checks == {"ck_school_bulk_upload_row_status"}
    assert indexes == {"ix_school_bulk_upload_rows_batch_id"}

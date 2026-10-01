"""ENH-029 -- migration 0052 (spec §4, AC10): single head, CHECK swap + nullable created_user_id, data preserved, guarded downgrade."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models import SchoolBulkUploadBatch
from tests.enh029_helpers import mk_admin
from tests.test_enh_028_migration import _parents

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_enh_029_migration_0052", VERSIONS / "0052_school_onboarding_bulk.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def test_migration_follows_0051_and_is_the_single_head():
    assert _migration.revision == "0052_school_onboarding_bulk"
    assert _migration.down_revision == "0051_school_bulk_uploads"
    parents = _parents()
    assert set(parents) - set(parents.values()) == {"0052_school_onboarding_bulk"}


def test_migration_touches_only_the_constraint_and_the_new_column():
    source = (VERSIONS / "0052_school_onboarding_bulk.py").read_text(encoding="utf-8")
    for forbidden in ("op.create_table", "op.drop_table", "op.alter_column", "UPDATE ", "DELETE ", "INSERT "):
        assert forbidden not in source
    assert source.count("op.add_column(") == 1
    assert source.count("op.drop_column(") == 1


def test_downgrade_refuses_when_onboarding_batches_exist():
    downgrade = (VERSIONS / "0052_school_onboarding_bulk.py").read_text(encoding="utf-8").split("def downgrade", 1)[1]
    assert "target_type = 'school_onboarding'" in downgrade
    assert "raise RuntimeError" in downgrade


@pytest.mark.asyncio
async def test_rows_table_has_a_nullable_created_user_id_fk(db_session):
    def _describe(sync_conn):
        insp = inspect(sync_conn)
        cols = {c["name"]: c["nullable"] for c in insp.get_columns("school_bulk_upload_rows")}
        fks = {(tuple(f["constrained_columns"]), f["referred_table"]) for f in insp.get_foreign_keys("school_bulk_upload_rows")}
        return cols, fks

    cols, fks = await (await db_session.connection()).run_sync(_describe)
    assert cols["created_user_id"] is True
    assert (("created_user_id",), "users") in fks


@pytest.mark.asyncio
async def test_constraint_accepts_school_onboarding_and_still_rejects_unknown(db_session):
    admin = await mk_admin(db_session)
    db_session.add(SchoolBulkUploadBatch(target_type="school_onboarding", uploaded_by_user_id=admin.id, idempotency_key=uuid.uuid4().hex, file_sha256="0" * 64))
    await db_session.commit()
    db_session.add(SchoolBulkUploadBatch(target_type="nonsense", uploaded_by_user_id=admin.id, idempotency_key=uuid.uuid4().hex, file_sha256="0" * 64))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

"""ENH-029 -- migration 0054 (spec §4, AC10): single head, CHECK swap + nullable created_user_id, data preserved, guarded downgrade."""

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings
from app.models import SchoolBulkUploadBatch
from tests.enh029_helpers import mk_admin
from tests.test_agn_004_migration import _sql
from tests.test_enh_028_migration import _parents

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
MIGRATION = VERSIONS / "0054_school_onboarding_bulk.py"
_spec = importlib.util.spec_from_file_location("_enh_029_migration_0054", MIGRATION)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def test_migration_follows_0053_and_is_the_single_head():
    # Cut as 0052 after 0051; renumbered to 0054 after AGN-003's 0052 and ENH-020's 0053 on merging main.
    assert _migration.revision == "0054_school_onboarding_bulk"
    assert _migration.down_revision == "0053_school_funding_records"
    parents = _parents()
    assert set(parents) - set(parents.values()) == {"0054_school_onboarding_bulk"}


def test_migration_touches_only_the_constraint_and_the_new_column():
    source = MIGRATION.read_text(encoding="utf-8")
    for forbidden in ("op.create_table", "op.drop_table", "op.alter_column", "UPDATE ", "DELETE ", "INSERT "):
        assert forbidden not in source
    assert source.count("op.add_column(") == 1
    assert source.count("op.drop_column(") == 1


def test_downgrade_refuses_when_onboarding_batches_exist():
    downgrade = MIGRATION.read_text(encoding="utf-8").split("def downgrade", 1)[1]
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


# --- Behaviour on a throwaway database (final review; the AGN-004 / ENH-001 harness) ------------------------------------------
# 0001 builds a fresh database from the current models, so it already has 0054's shape; each test first downgrades to the real
# pre-0054 schema (0053), then exercises the upgrade. Plain tests: alembic/env.py calls asyncio.run() itself.

BEFORE, AFTER = "0053_school_funding_records", "0054_school_onboarding_bulk"
ROWS_SQL = "SELECT id, batch_id, row_number, status, error_message, student_code, created_record_id FROM school_bulk_upload_rows ORDER BY id"


def _columns(url: str) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'school_bulk_upload_rows'")}


@pytest.fixture
def db_before_0054():
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"enh029_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, AFTER)
        command.downgrade(cfg, BEFORE)
        user = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Academic', 'academic_team', 'overseas', true, true, 'en-GB', '{}')",
            {"id": user, "email": f"{name}@example.local"},
        )
        yield {"cfg": cfg, "url": url, "user": user}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _add_batch(url: str, user, target_type: str):
    batch = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO school_bulk_upload_batches (id, target_type, uploaded_by_user_id, idempotency_key, file_sha256, total_rows, accepted_count, rejected_count) VALUES (:id, :t, :u, :k, :h, 1, 1, 0)",
        {"id": batch, "t": target_type, "u": user, "k": uuid.uuid4().hex, "h": "0" * 64},
    )
    _sql(
        url,
        "INSERT INTO school_bulk_upload_rows (id, batch_id, row_number, status, student_code, created_record_id) VALUES (:id, :b, 2, 'accepted', 'AB12CD34', :r)",
        {"id": uuid.uuid4(), "b": batch, "r": uuid.uuid4()},
    )
    return batch


def test_round_trip_keeps_existing_enh028_rows_identical(db_before_0054):
    cfg, url, user = db_before_0054["cfg"], db_before_0054["url"], db_before_0054["user"]
    assert "created_user_id" not in _columns(url)  # really before 0054
    _add_batch(url, user, "academic_result")
    before = _sql(url, ROWS_SQL)
    command.upgrade(cfg, AFTER)
    assert _sql(url, ROWS_SQL) == before
    assert _sql(url, "SELECT created_user_id FROM school_bulk_upload_rows") == [(None,)]
    _add_batch(url, user, "school_onboarding")  # the widened CHECK accepts the new target
    _sql(url, "DELETE FROM school_bulk_upload_rows WHERE batch_id IN (SELECT id FROM school_bulk_upload_batches WHERE target_type = 'school_onboarding')")
    _sql(url, "DELETE FROM school_bulk_upload_batches WHERE target_type = 'school_onboarding'")
    command.downgrade(cfg, BEFORE)
    assert _sql(url, ROWS_SQL) == before
    assert "created_user_id" not in _columns(url)
    with pytest.raises(sa.exc.IntegrityError):  # the pre-0054 CHECK is back
        _add_batch(url, user, "school_onboarding")


def test_downgrade_refuses_while_onboarding_batches_exist(db_before_0054):
    cfg, url, user = db_before_0054["cfg"], db_before_0054["url"], db_before_0054["user"]
    command.upgrade(cfg, AFTER)
    _add_batch(url, user, "school_onboarding")
    with pytest.raises(RuntimeError, match="school_onboarding bulk batches exist"):
        command.downgrade(cfg, BEFORE)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [(AFTER,)]
    assert "created_user_id" in _columns(url)

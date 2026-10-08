"""upc-005 -- migration 0110_university_imports (spec §2). The round trip and the downgrade refusal run in a throwaway database (the upc-001
pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_upc_005_migration_0110", VERSIONS / "0110_university_imports.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0109_university_duplicates", "0110_university_imports"


def test_migration_chains_after_0109_and_there_is_one_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import UniversityImportBatch

    table = UniversityImportBatch.__table__
    assert {c.name for c in table.columns} == {
        "id",
        "uploaded_by_user_id",
        "idempotency_key",
        "file_sha256",
        "total_rows",
        "created_count",
        "duplicate_count",
        "invalid_count",
        "results_json",
        "created_at",
        "updated_at",
    }
    checks = {c.name: str(c.sqltext) for c in table.constraints if c.name == _migration.COUNTS_CHECK}
    assert checks == {_migration.COUNTS_CHECK: _migration.COUNTS_SQL}
    assert {_migration.KEY_UNIQUE, _migration.UPLOADER_INDEX} <= {c.name for c in table.constraints} | {i.name for i in table.indexes}


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    conn = await db_session.connection()
    indexes = await conn.run_sync(lambda sync: {i["name"] for i in inspect(sync).get_indexes("university_import_batches")})
    assert _migration.UPLOADER_INDEX in indexes


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"upc005_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_and_downgrade_refuses_while_imports_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), :e, 'x', 'H', 'partnership_head', 'global', true, true, 'en-GB', '{}') RETURNING id",
        {"e": f"{uuid.uuid4().hex[:8]}@example.local"},
    )[0][0]
    with pytest.raises(Exception, match=_migration.COUNTS_CHECK):
        _sql(
            url, "INSERT INTO university_import_batches (id, uploaded_by_user_id, idempotency_key, file_sha256, total_rows, created_count) VALUES (gen_random_uuid(), :u, 'k1', 'x', 2, 1)", {"u": user}
        )
    _sql(url, "INSERT INTO university_import_batches (id, uploaded_by_user_id, idempotency_key, file_sha256) VALUES (gen_random_uuid(), :u, 'k1', 'x')", {"u": user})
    with pytest.raises(Exception, match="import history"):
        command.downgrade(cfg, BASE)

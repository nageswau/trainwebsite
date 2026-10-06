"""tel-006 -- migration 0087_lead_import_batches (spec §2). The round trip runs in a throwaway database (the tel-004/005 pattern); a
downgrade never runs against the shared test database. 0001 builds a fresh database from the current models, so each test first
downgrades to 0086_lead_enquiries to reach the real pre-tel-006 shape."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_tel_006_migration_0087", VERSIONS / "0087_lead_import_batches.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0086_lead_enquiries", "0087_lead_import_batches"
COLUMNS = {"id", "campaign_id", "division", "uploaded_by_user_id", "idempotency_key", "file_sha256", "total_rows", "created_count",
           "attached_count", "rejected_count", "results_json", "created_at", "updated_at"}


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def _sql(url: str, sql: str, params: dict | None = None, *, autocommit: bool = False):
    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text(sql), params or {})
                return result.fetchall() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def test_migration_chains_after_0086_lead_enquiries_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import LeadImportBatch

    table = LeadImportBatch.__table__
    assert {c.name for c in table.columns} == COLUMNS
    assert not any(table.c[name].nullable for name in COLUMNS - {"id"})
    assert {fk.parent.name: fk.column.table.name for fk in table.foreign_keys} == {"campaign_id": "tel_campaigns", "uploaded_by_user_id": "users"}
    checks = {c.name for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks == {"ck_lead_import_batches_division", "ck_lead_import_batches_counts"}
    uniques = {c.name: [col.name for col in c.columns] for c in table.constraints if isinstance(c, sa.UniqueConstraint)}
    assert uniques == {"uq_lead_import_batches_key": ["uploaded_by_user_id", "idempotency_key"]}
    assert "ix_lead_import_batches_uploader" in {i.name for i in table.indexes}


@pytest.fixture
def base_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel006_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


EXISTS = "SELECT to_regclass('lead_import_batches')"
SEED = ("INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) "
        "VALUES (:user, :email, 'Importer', 'telecaller_manager', 'global', 'x', true, true, 'en-GB', '{}');"
        "INSERT INTO tel_products (id, product_group, name, team) VALUES (:product, 'it', :cname, 'it');"
        "INSERT INTO tel_campaigns (id, name, source, product_id, start_date) VALUES (:campaign, :cname, 'instagram', :product, '2026-09-01')")
BATCH = ("INSERT INTO lead_import_batches (id, campaign_id, division, uploaded_by_user_id, idempotency_key, file_sha256, total_rows, created_count, "
         "attached_count, rejected_count) VALUES (:id, :campaign, :division, :user, :key, 'abc', :total, 1, 0, 0)")


def test_downgrade_to_0086_has_no_table(base_db):
    assert _sql(base_db["url"], EXISTS) == [(None,)]


def test_upgrade_adds_the_table_with_its_checks_and_key(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    command.upgrade(cfg, HEAD)
    user, campaign, product = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    params = {"user": user, "email": f"imp-{user.hex[:8]}@example.com", "campaign": campaign, "product": product, "cname": f"C {user.hex[:6]}"}
    for statement in SEED.split(";"):
        _sql(url, statement, params)
    row = {"campaign": campaign, "user": user, "division": "it", "key": "k1", "total": 1}
    _sql(url, BATCH, {"id": uuid.uuid4(), **row})
    assert _sql(url, "SELECT results_json::text, created_at IS NOT NULL FROM lead_import_batches") == [("[]", True)]
    with pytest.raises(Exception, match="uq_lead_import_batches_key"):
        _sql(url, BATCH, {"id": uuid.uuid4(), **row})
    with pytest.raises(Exception, match="ck_lead_import_batches_counts"):
        _sql(url, BATCH, {"id": uuid.uuid4(), **row, "key": "k2", "total": 5})
    with pytest.raises(Exception, match="ck_lead_import_batches_division"):
        _sql(url, BATCH, {"id": uuid.uuid4(), **row, "key": "k3", "division": "global"})


def test_downgrade_drops_the_table(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, EXISTS) == [(None,)]

"""tel-003 -- migration 0078_enquiry_lead_record (spec §3; AC1, AC4, AC5, L1, L2). The backfill, the round trip and the downgrade
refusal run in a throwaway database (the bdm-017 pattern); a downgrade never runs against the shared test database.

0001 builds a fresh database from the current models, which already carry the new columns, so each test first downgrades to 0077 to
reach the real pre-tel-003 shape, inserts legacy rows there, and then runs the real upgrade."""

import asyncio
import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
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
_spec = importlib.util.spec_from_file_location("_tel_003_migration_0078", VERSIONS / "0078_enquiry_lead_record.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0077_bdm_tasks_followups", "0078_enquiry_lead_record"
NEW_COLUMNS = {"lead_code", "phone_normalized", "whatsapp_number", "city", "state", "qualification", "passing_year", "institution",
               "product_id", "campaign_id", "telecaller_user_id", "priority", "stage_changed_at"}
BDM_017 = {"bdm_organization_id", "bdm_user_id", "converted_user_id", "converted_at", "converted_by_user_id"}


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0077_bdm_tasks_followups_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())  # tel-004 chains after it: one head that still contains HEAD
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import LEAD_CODE_DEFAULT, Enquiry
    from app.tel_sources import TEL_SOURCES

    table = Enquiry.__table__
    assert NEW_COLUMNS <= {c.name for c in table.columns}
    assert not table.c.lead_code.nullable and not table.c.priority.nullable and not table.c.stage_changed_at.nullable
    assert LEAD_CODE_DEFAULT == _migration.LEAD_CODE_DEFAULT
    assert _migration.SOURCES == TEL_SOURCES  # the frozen copy still equals the live list
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    for name, sql in _migration.CHECKS.items():
        assert checks[name] == sql
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"uq_enquiries_lead_code", "ix_enquiries_telecaller_status", "ix_enquiries_phone_normalized", "ix_enquiries_email_lower",
            "ix_enquiries_campaign", "ix_enquiries_product"} <= names
    fks = {fk.parent.name: (fk.column.table.name, fk.ondelete) for fk in table.foreign_keys}
    assert fks["product_id"][0] == "tel_products" and fks["campaign_id"][0] == "tel_campaigns"
    assert fks["telecaller_user_id"] == ("users", "RESTRICT")


@pytest.mark.asyncio
async def test_columns_exist_in_the_shared_database(db_session):
    rows = (await db_session.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'enquiries' AND column_name = ANY(:names)"),
        {"names": sorted(NEW_COLUMNS)})).scalars().all()
    assert set(rows) == NEW_COLUMNS


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


LEGACY = (
    "INSERT INTO enquiries (id, division, name, email, phone, subject, message, source, status, crm_sync_status, metadata_json, created_at) "
    "VALUES (:id, 'it', :name, 'web@example.local', :phone, 'Python', 'Hello there', :source, 'new', 'pending', CAST(:meta AS json), "
    ":at)"
)
# (name, phone, source, age): inserted newest-first so the backfill must order by created_at, not by insert order
ROWS = (
    ("Third", None, "bdm", timedelta(hours=1)),
    ("Second", "12", "facebook ads", timedelta(days=2)),
    ("First", "098765 43210", " Website ", timedelta(days=3)),
)


@pytest.fixture
def legacy_db():
    """A fresh database at 0077_bdm_tasks_followups (the real pre-tel-003 shape) holding three legacy enquiries."""
    cfg = _config()
    original = settings.database_url
    name = f"tel003_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)
        command.downgrade(cfg, BASE)  # 0001's create_all already built the new columns; drop them to reach the legacy shape
        for row_name, phone, source, age in ROWS:
            _sql(url, LEGACY, {"id": uuid.uuid4(), "name": row_name, "phone": phone, "source": source, "meta": '{"utm": "x"}', "at": datetime.now(UTC) - age})
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _leads(url):
    return _sql(url, "SELECT name, lead_code, source, phone_normalized, metadata_json, priority, stage_changed_at = created_at "
                     "FROM enquiries ORDER BY created_at")


def test_downgrade_to_0077_leaves_the_legacy_shape(legacy_db):
    columns = {r[0] for r in _sql(legacy_db["url"], "SELECT column_name FROM information_schema.columns WHERE table_name = 'enquiries'")}
    assert not (NEW_COLUMNS & columns)
    assert BDM_017 <= columns  # AC4: bdm-017's columns are untouched


def test_upgrade_backfills_codes_oldest_first_maps_sources_and_normalises_phones(legacy_db):
    cfg, url = legacy_db["cfg"], legacy_db["url"]
    command.upgrade(cfg, HEAD)
    assert _leads(url) == [
        ("First", "LD-000001", "website", "+919876543210", {"utm": "x"}, "warm", True),
        ("Second", "LD-000002", "other", None, {"utm": "x", "legacy_source": "facebook ads"}, "warm", True),
        ("Third", "LD-000003", "bdm", None, {"utm": "x"}, "warm", True),
    ]
    _sql(url, LEGACY, {"id": uuid.uuid4(), "name": "New", "phone": None, "source": "google", "meta": "{}", "at": datetime.now(UTC)})
    assert _sql(url, "SELECT lead_code FROM enquiries WHERE name = 'New'") == [("LD-000004",)]  # the sequence continues


def test_checks_hold_after_upgrade(legacy_db):
    cfg, url = legacy_db["cfg"], legacy_db["url"]
    command.upgrade(cfg, HEAD)
    for sql, constraint in (
        ("UPDATE enquiries SET source = 'tiktok'", "ck_enquiries_source"),
        ("UPDATE enquiries SET priority = 'urgent'", "ck_enquiries_priority"),
        ("UPDATE enquiries SET passing_year = 1800", "ck_enquiries_passing_year"),
        ("UPDATE enquiries SET lead_code = 'LD-000001'", "uq_enquiries_lead_code"),
    ):
        with pytest.raises(Exception, match=constraint):
            _sql(url, sql)


def test_clean_downgrade_restores_the_legacy_source(legacy_db):
    cfg, url = legacy_db["cfg"], legacy_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT name, source, metadata_json FROM enquiries ORDER BY created_at") == [
        ("First", "website", {"utm": "x"}),
        ("Second", "facebook ads", {"utm": "x"}),
        ("Third", "bdm", {"utm": "x"}),
    ]
    assert _sql(url, "SELECT count(*) FROM pg_class WHERE relname = 'enquiry_lead_code_seq'") == [(0,)]


@pytest.mark.parametrize("change", ["city = 'Kochi'", "passing_year = 2024", "priority = 'hot'", "whatsapp_number = '+919876543210'"])
def test_downgrade_refuses_while_new_data_exists(legacy_db, change):
    cfg, url = legacy_db["cfg"], legacy_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, f"UPDATE enquiries SET {change} WHERE lead_code = 'LD-000001'")
    with pytest.raises(RuntimeError, match="lead data exists"):
        command.downgrade(cfg, BASE)

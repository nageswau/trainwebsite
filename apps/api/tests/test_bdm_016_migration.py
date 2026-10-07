"""bdm-016 -- migration 0095_bdm_targets (spec §4). The round trip and the downgrade refusal run in a throwaway database (the bdm-015
pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from datetime import date
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
_spec = importlib.util.spec_from_file_location("_bdm_016_migration_0095", VERSIONS / "0095_bdm_targets.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0094_bdm_daily_reports", "0095_bdm_targets"
TABLE = "bdm_targets"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0094_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import BDM_TARGET_CHECKS, BdmTarget

    table = BdmTarget.__table__
    assert {c.name for c in table.columns} == {"id", "bdm_user_id", "month", "kpi_key", "target", "set_by_user_id", "set_at", "created_at", "updated_at"}
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"uq_bdm_targets_bdm_month_kpi", *BDM_TARGET_CHECKS} <= names
    assert _migration.CHECKS == BDM_TARGET_CHECKS  # the migration's frozen copy stays identical
    assert {fk.parent.name: fk.ondelete for fk in table.foreign_keys} == {"bdm_user_id": "RESTRICT", "set_by_user_id": "RESTRICT"}


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    rows = (await db_session.execute(sa.text(f"SELECT relname FROM pg_class WHERE relname = '{TABLE}'"))).all()
    assert rows == [(TABLE,)]


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


@pytest.fixture
def isolated_db():
    """A fresh database at BASE with one BDM user."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm016_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        owner = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Owner', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": owner, "email": f"owner-{name}@example.local"},
        )
        yield {"cfg": cfg, "url": url, "owner": owner}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


TARGET = f"INSERT INTO {TABLE} (id, bdm_user_id, month, kpi_key, target, set_by_user_id) VALUES (:id, :owner, :month, 'meetings', :target, :owner)"


def _target(db, **over) -> dict:
    params = {"id": uuid.uuid4(), "owner": db["owner"], "month": date(2026, 10, 1), "target": 30}
    params.update(over)
    return params


def test_round_trip_and_downgrade_refuses_while_targets_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, f"SELECT count(*) FROM pg_class WHERE relname = '{TABLE}'")[0][0] == 0
    command.upgrade(cfg, HEAD)
    for over, constraint in (
        ({"month": date(2026, 10, 2)}, "ck_bdm_targets_month_start"),
        ({"target": -1}, "ck_bdm_targets_target_range"),
        ({"target": 100_001}, "ck_bdm_targets_target_range"),
    ):
        with pytest.raises(Exception, match=constraint):
            _sql(url, TARGET, _target(isolated_db, **over))
    _sql(url, TARGET, _target(isolated_db))
    with pytest.raises(Exception, match="uq_bdm_targets_bdm_month_kpi"):
        _sql(url, TARGET, _target(isolated_db))
    with pytest.raises(RuntimeError, match="targets exist"):
        command.downgrade(cfg, BASE)

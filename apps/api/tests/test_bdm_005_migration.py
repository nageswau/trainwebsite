"""bdm-005 -- migration 0076_bdm_mous (spec §5; AC2 backstop, AC7 index). Round trip and the downgrade refusal run in a throwaway
database (the bdm-003/004 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
D1 = date(2026, 1, 1)
BASE, HEAD = "0075_telecaller_profiles", "0076_bdm_mous"


def _migration():
    spec = importlib.util.spec_from_file_location("_bdm_005_migration_0076", VERSIONS / f"{HEAD}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0075_and_is_the_single_head():
    migration = _migration()
    assert (migration.revision, migration.down_revision) == (HEAD, BASE)
    assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]


def test_frozen_lists_and_checks_equal_the_model():
    from app.models import BDM_MOU_CHECKS, BDM_MOU_EVENT_KINDS, BDM_MOU_SETTABLE, BdmMou, BdmMouEvent

    migration = _migration()
    assert migration.STATUSES == BDM_MOU_SETTABLE
    assert migration.EVENT_KINDS == BDM_MOU_EVENT_KINDS
    assert migration.CHECKS == BDM_MOU_CHECKS
    model_checks = {c.name: str(c.sqltext) for c in BdmMou.__table__.constraints if isinstance(c, CheckConstraint)}
    assert BDM_MOU_CHECKS.items() <= model_checks.items()
    assert {"uq_bdm_mous_current", "ix_bdm_mous_org", "ix_bdm_mous_status"} <= {i.name for i in BdmMou.__table__.indexes}
    assert {fk.parent.name: fk.ondelete for fk in BdmMouEvent.__table__.foreign_keys} == {"mou_id": "RESTRICT", "actor_user_id": "RESTRICT"}


@pytest.mark.asyncio
async def test_tables_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    assert {"bdm_mous", "bdm_mou_events"} <= tables


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
    """A fresh database at HEAD with one bdm user and one organization."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm005_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": user_id, "email": f"bdm-{name}@example.local"},
        )
        _sql(
            url,
            "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id) "
            "VALUES (:id, 'ORG-M1', 'college', 'college', 'A', 'a', 'K', 'k', :u, :u)",
            {"id": org_id, "u": user_id},
        )
        yield {"cfg": cfg, "url": url, "user": user_id, "org": org_id}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _mou(db, **values) -> uuid.UUID:
    mou_id = uuid.uuid4()
    cols = "".join(f", {k}" for k in values)
    vals = "".join(f", :{k}" for k in values)
    _sql(db["url"], f"INSERT INTO bdm_mous (id, organization_id, created_by_user_id{cols}) VALUES (:id, :o, :u{vals})", {"id": mou_id, "o": db["org"], "u": db["user"], **values})
    return mou_id


def test_round_trip_creates_the_tables_and_enforces_the_checks(isolated_db):
    """0001 builds BASE from the current models, so go up, down to BASE (the migration drops the tables), and up again: the CHECKs
    and indexes below are 0076's own DDL."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    tables = {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert not ({"bdm_mous", "bdm_mou_events"} & tables)
    command.upgrade(cfg, HEAD)
    first = _mou(isolated_db, status="rejected", is_current=False)
    assert _sql(url, "SELECT status, is_current FROM bdm_mous WHERE id = :id", {"id": first}) == [("rejected", False)]
    bad = [
        ({"status": "expired"}, "ck_bdm_mous_status"),
        ({"status": "signed"}, "ck_bdm_mous_signed_on"),
        ({"status": "active", "signed_on": D1}, "ck_bdm_mous_active_window"),
        ({"valid_from": date(2026, 2, 1), "valid_until": date(2026, 1, 31)}, "ck_bdm_mous_window"),
        ({"document_key": "bdm-mous/x"}, "ck_bdm_mous_document"),
    ]
    for values, check in bad:
        with pytest.raises(Exception, match=check):
            _mou(isolated_db, is_current=False, **values)
    _mou(isolated_db, status="active", signed_on=D1, valid_from=D1, valid_until=D1)  # current
    with pytest.raises(Exception, match="uq_bdm_mous_current"):
        _mou(isolated_db)
    with pytest.raises(Exception, match="ck_bdm_mou_events_kind"):
        _sql(url, "INSERT INTO bdm_mou_events (id, mou_id, actor_user_id, kind, to_status, changed) VALUES (:id, :m, :u, 'expired', 'expired', '[]')", {"id": uuid.uuid4(), "m": first, "u": isolated_db["user"]})


def test_downgrade_refuses_while_mous_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _mou(isolated_db)
    with pytest.raises(Exception, match="MoU data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM bdm_mous")
    command.downgrade(cfg, BASE)

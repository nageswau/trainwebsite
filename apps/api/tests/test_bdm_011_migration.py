"""bdm-011 -- migration 0084_bdm_appointment_trip (spec §3): one nullable FK + index on bdm_appointments, additive."""

import asyncio
import importlib.util
import io
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings
from app.models import BdmAppointment

API_ROOT = Path(__file__).resolve().parents[1]
BASE, HEAD = "0083_tel_content", "0084_bdm_appointment_trip"


def _migration():
    spec = importlib.util.spec_from_file_location("_bdm_011_migration_0084", API_ROOT / "alembic" / "versions" / f"{HEAD}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0083_and_is_on_the_single_chain():
    migration = _migration()
    assert (migration.revision, migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_carries_the_nullable_trip_link():
    column = BdmAppointment.__table__.c.trip_id
    assert column.nullable and {fk.target_fullname for fk in column.foreign_keys} == {"bdm_trips.id"}
    assert next(iter(column.foreign_keys)).ondelete == "RESTRICT"
    assert "ix_bdm_appointments_trip" in {i.name for i in BdmAppointment.__table__.indexes}


@pytest.mark.asyncio
async def test_column_and_index_exist_in_the_shared_database(db_session):
    def read(sync):
        insp = inspect(sync)
        return {c["name"]: c["nullable"] for c in insp.get_columns("bdm_appointments")}, {i["name"] for i in insp.get_indexes("bdm_appointments")}

    columns, indexes = await (await db_session.connection()).run_sync(read)
    assert columns.get("trip_id") is True and "ix_bdm_appointments_trip" in indexes


def test_offline_sql_is_the_additive_column_fk_and_index():
    """`alembic upgrade --sql` (a reviewed script for production) renders without a database: no inspection, only the three DDL steps."""
    buffer = io.StringIO()
    cfg = Config(str(API_ROOT / "alembic.ini"), output_buffer=buffer)
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    command.upgrade(cfg, f"{BASE}:{HEAD}", sql=True)
    statements = [line for line in buffer.getvalue().splitlines() if line.startswith(("ALTER", "CREATE", "DROP", "UPDATE", "INSERT", "DELETE"))]
    ddl = [s for s in statements if "alembic_version" not in s]  # no row of any app table is written
    assert ddl == [
        "ALTER TABLE bdm_appointments ADD COLUMN trip_id UUID;",
        "ALTER TABLE bdm_appointments ADD CONSTRAINT fk_bdm_appointments_trip_id FOREIGN KEY(trip_id) REFERENCES bdm_trips (id) ON DELETE RESTRICT;",
        "CREATE INDEX ix_bdm_appointments_trip ON bdm_appointments (trip_id);",
    ]


def _sql(url: str, sql: str, *, autocommit: bool = False):
    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text(sql))
                return result.fetchall() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def test_round_trip_runs_the_migrations_own_ddl():
    """0001 builds BASE from the current models (column included), so go down to BASE -- 0084 drops it -- and up again: what is
    left is 0083 own column, FK and index. A throwaway database; the shared one is never downgraded."""
    cfg, original = _config(), settings.database_url
    name = f"bdm011_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    columns = "SELECT column_name FROM information_schema.columns WHERE table_name = 'bdm_appointments' AND column_name = 'trip_id'"
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)
        command.downgrade(cfg, BASE)
        assert _sql(url, columns) == []
        command.upgrade(cfg, HEAD)
        assert _sql(url, columns) == [("trip_id",)]
        assert _sql(url, "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_bdm_appointments_trip'") == [(1,)]
        fk = "SELECT confdeltype::text FROM pg_constraint WHERE conname = 'fk_bdm_appointments_trip_id'"
        assert _sql(url, fk) == [("r",)]  # RESTRICT
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)

"""bdm-025 -- migration 0082_bdm_assignment_history (spec §4). Round trip and the downgrade refusal run in a throwaway database
(the bdm-009 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_bdm_025_migration_0078", VERSIONS / "0082_bdm_assignment_history.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0081_lead_stage_pipeline", "0082_bdm_assignment_history"
USERS = "SELECT id, email, role FROM users ORDER BY id"
TABLE = "bdm_assignment_history"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0081_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import BdmAssignmentHistory

    table = BdmAssignmentHistory.__table__
    assert {c.name for c in table.columns} == {"id", "entity_type", "entity_id", "from_user_id", "to_user_id", "actor_user_id", "reason", "created_at"}
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {
        "ck_bdm_assignment_history_entity_type", "ck_bdm_assignment_history_reason",
        "ix_bdm_assignment_history_entity", "ix_bdm_assignment_history_from",
    } <= names
    assert {fk.parent.name: fk.ondelete for fk in table.foreign_keys} == {"from_user_id": "RESTRICT", "to_user_id": "RESTRICT", "actor_user_id": "RESTRICT"}


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
    """A fresh database at 0081 (tel-004) with one user."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm025_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Owner', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": user, "email": f"owner-{name}@example.local"},
        )
        yield {"cfg": cfg, "url": url, "user": user}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


ROW = (
    f"INSERT INTO {TABLE} (id, entity_type, entity_id, from_user_id, to_user_id, actor_user_id, reason) "
    "VALUES (:id, :entity_type, :entity_id, :u, :u, :u, :reason)"
)


def _row(db, **over) -> dict:
    params = {"id": uuid.uuid4(), "entity_type": "organization", "entity_id": uuid.uuid4(), "u": db["user"], "reason": "bdm_deactivated"}
    params.update(over)
    return params


def test_round_trip_keeps_users(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, USERS)
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, f"SELECT count(*) FROM pg_class WHERE relname = '{TABLE}'")[0][0] == 0
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before


def test_checks_hold_and_downgrade_refuses_while_history_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="ck_bdm_assignment_history_entity_type"):
        _sql(url, ROW, _row(isolated_db, entity_type="trip"))
    with pytest.raises(Exception, match="ck_bdm_assignment_history_reason"):
        _sql(url, ROW, _row(isolated_db, reason="whim"))
    for entity_type in ("organization", "appointment", "task"):
        for reason in ("bdm_deactivated", "portfolio_handover", "organization_reassigned"):
            _sql(url, ROW, _row(isolated_db, entity_type=entity_type, reason=reason))
    with pytest.raises(Exception, match="assignment history exists"):
        command.downgrade(cfg, BASE)

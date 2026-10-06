"""bdm-008 -- migration 0076_bdm_tasks_followups (spec §4). Isolated database per test (the bdm-007 pattern)."""

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
_spec = importlib.util.spec_from_file_location("_bdm_008_migration_0076", VERSIONS / "0076_bdm_tasks_followups.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0075_telecaller_profiles"
HEAD = "0076_bdm_tasks_followups"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0075_and_is_on_the_single_chain():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_models_match_the_migration():
    from app.models import BdmTask

    table = BdmTask.__table__
    assert {"notes", "cancelled_at", "cancel_reason"} <= {c.name for c in table.columns}
    assert (table.c.notes.type.length, table.c.cancel_reason.type.length) == (2000, 500)
    assert set(_migration.CHECKS) <= {c.name for c in table.constraints}


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


TASK = (
    "INSERT INTO bdm_tasks (id, kind, title, due_on, source, assignee_user_id, status, updated_at) "
    "VALUES (:id, 'follow_up', 'T', '2026-09-22', :source, :u, :status, '2026-09-20T10:00:00+00')"
)


@pytest.fixture
def isolated_db():
    """A fresh database at 0075 whose bdm_tasks is put back to 0072's shape (0001's create_all builds it from the models), holding one
    open and one cancelled (bdm-007 "date cleared") task."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm008_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        _sql(url, "ALTER TABLE bdm_tasks DROP CONSTRAINT IF EXISTS ck_bdm_tasks_cancelled, DROP CONSTRAINT IF EXISTS ck_bdm_tasks_cancel_reason, "
                  "DROP COLUMN IF EXISTS notes, DROP COLUMN IF EXISTS cancelled_at, DROP COLUMN IF EXISTS cancel_reason")
        user = uuid.uuid4()
        _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')", {"id": user, "email": f"bdm-{name}@example.local"})
        tasks = {"open": uuid.uuid4(), "cancelled": uuid.uuid4()}
        for status, task_id in tasks.items():
            _sql(url, TASK, {"id": task_id, "source": "manual", "u": user, "status": status})
        yield {"cfg": cfg, "url": url, "user": user, "tasks": tasks}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_adds_the_columns_and_backfills_cancelled_rows(isolated_db):
    url, tasks = isolated_db["url"], isolated_db["tasks"]
    command.upgrade(isolated_db["cfg"], HEAD)
    rows = dict((r[0], r[1:]) for r in _sql(url, "SELECT id, cancelled_at, cancel_reason, notes FROM bdm_tasks"))
    assert rows[tasks["open"]] == (None, None, None)
    at, reason, notes = rows[tasks["cancelled"]]
    assert at.isoformat().startswith("2026-09-20T10:00") and reason == _migration.REPORT_CLEARED and notes is None


def test_constraints_hold(isolated_db):
    cfg, url, user = isolated_db["cfg"], isolated_db["url"], isolated_db["user"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="ck_bdm_tasks_cancelled"):
        _sql(url, TASK, {"id": uuid.uuid4(), "source": "manual", "u": user, "status": "cancelled"})  # no cancelled_at
    with pytest.raises(Exception, match="ck_bdm_tasks_cancel_reason"):
        _sql(url, "UPDATE bdm_tasks SET cancel_reason = 'x' WHERE id = :id", {"id": isolated_db["tasks"]["open"]})


def test_downgrade_refuses_while_manual_tasks_exist_and_round_trips_otherwise(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="manual tasks exist"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE bdm_tasks SET source = 'mou'")  # nothing manual left: allowed
    command.downgrade(cfg, BASE)
    assert "cancel_reason" not in {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'bdm_tasks'")}
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT count(*) FROM bdm_tasks WHERE status = 'cancelled' AND cancelled_at IS NOT NULL") == [(1,)]

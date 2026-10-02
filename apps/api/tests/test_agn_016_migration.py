"""AGN-016 -- migration 0059_agent_tasks (spec §2). The round trip and the downgrade refusal run in a throwaway database built from
scratch (the AGN-008 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run() itself."""

import asyncio
import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_016_migration_0059", VERSIONS / "0059_agent_tasks.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0058_agent_documents"
HEAD = "0059_agent_tasks"


def test_migration_chains_after_0058_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    assert set(parents) - set(parents.values()) == {HEAD}


def test_model_declares_the_table():
    from app.models import AgentTask

    columns = AgentTask.__table__.columns
    for name in ("agent_student_id", "title", "due_at", "status", "created_by_user_id", "updated_by_user_id"):
        assert not columns[name].nullable, name
    for name in ("application_id", "notes", "closed_at", "closed_by_user_id"):
        assert columns[name].nullable, name
    assert columns["due_at"].type.timezone and columns["closed_at"].type.timezone


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    conn = await db_session.connection()
    indexes = await conn.run_sync(lambda sync: {i["name"] for i in inspect(sync).get_indexes("agent_tasks")})
    assert _migration.STUDENT_INDEX in indexes


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
    """A fresh database at 0058 with one agent and one agency student with no login."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"agn016_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("agent", "record")}
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Agent', 'agent', 'overseas', true, true, 'en-GB', '{}')",
            {"id": ids["agent"], "email": f"agent-{name}@example.local"},
        )
        _sql(url, "INSERT INTO agent_students (id, agent_id, student_id, status, full_name) VALUES (:id, :agent, NULL, 'active', 'No Login')", {"id": ids["record"], "agent": ids["agent"]})
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


INSERT = (
    "INSERT INTO agent_tasks (id, agent_student_id, title, due_at, status, closed_at, closed_by_user_id, created_by_user_id, updated_by_user_id) "
    "VALUES (:id, :record, 'Call', now(), :status, :closed_at, :closed_by, :agent, :agent)"
)


def _insert(isolated, *, status="open", closed=False):
    ids = isolated["ids"]
    params = {"id": uuid.uuid4(), "record": ids["record"], "agent": ids["agent"], "status": status, "closed_at": None, "closed_by": None}
    if closed:
        params |= {"closed_at": datetime(2026, 10, 2, 10, tzinfo=UTC), "closed_by": ids["agent"]}
    _sql(isolated["url"], INSERT, params)


def test_upgrade_creates_the_table_and_its_checks(isolated_db):
    command.upgrade(isolated_db["cfg"], HEAD)
    _insert(isolated_db)
    _insert(isolated_db, status="done", closed=True)
    for status, closed in (("open", True), ("done", False), ("archived", False)):
        with pytest.raises(IntegrityError):
            _insert(isolated_db, status=status, closed=closed)
    assert _sql(isolated_db["url"], "SELECT count(*) FROM agent_tasks") == [(2,)]


def test_downgrade_refuses_while_tasks_exist_and_drops_an_empty_table(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _insert(isolated_db)
    with pytest.raises(RuntimeError, match="tasks exist"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM agent_tasks")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('agent_tasks')") == [(None,)]
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [(HEAD,)]

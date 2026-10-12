"""mgmt-028 -- migration 0153_management_tasks (spec §3). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_mgmt_028_migration_0153", VERSIONS / "0153_management_tasks.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0152_management_discussions", "0153_management_tasks"


def test_migration_chains_after_0152_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from typing import get_args

    from app.models import TASK_PRIORITIES, TASK_SOURCES, TASK_STATUSES, ManagementTask
    from app.schemas import TaskPriority, TaskStatus

    assert TASK_STATUSES == _migration.STATUSES == ("open", "in_progress", "completed", "cancelled")
    assert TASK_PRIORITIES == _migration.PRIORITIES == ("high", "medium", "low")
    assert TASK_SOURCES == _migration.SOURCES == ("manual", "decision", "meeting", "plan")
    assert get_args(TaskStatus) == TASK_STATUSES and get_args(TaskPriority) == TASK_PRIORITIES
    assert {c.name for c in ManagementTask.__table__.columns} == {
        "id", "title", "owner_user_id", "priority", "deadline", "status", "source", "source_id", "completed_at",
        "created_by_user_id", "updated_by_user_id", "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_table_and_index_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables, indexes = await conn.run_sync(lambda sync: (set(inspect(sync).get_table_names()), {i["name"] for i in inspect(sync).get_indexes("management_tasks")}))
    assert "management_tasks" in tables
    assert {"ix_management_tasks_owner_deadline_status", "ix_management_tasks_status_deadline"} <= indexes


@pytest.fixture
def isolated_db():
    """A fresh database at 0152."""
    cfg = _config()
    original = settings.database_url
    name = f"mgmt028_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_round_trips_and_downgrade_refuses_while_tasks_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'management_tasks'")
    command.upgrade(cfg, HEAD)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 'p@example.local', 'x', 'P', 'partner', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    insert = (
        "INSERT INTO management_tasks (id, title, owner_user_id, priority, deadline, status, created_by_user_id, updated_by_user_id) "
        "VALUES (gen_random_uuid(), 'Approve marketing budget', :p, :priority, current_date, :status, :p, :p)"
    )
    with pytest.raises(Exception, match="ck_management_tasks_priority"):
        _sql(url, insert, {"p": user, "priority": "urgent", "status": "open"})
    with pytest.raises(Exception, match="ck_management_tasks_status"):
        _sql(url, insert, {"p": user, "priority": "high", "status": "done"})
    _sql(url, insert, {"p": user, "priority": "high", "status": "open"})
    assert _sql(url, "SELECT source FROM management_tasks")[0][0] == "manual"
    with pytest.raises(Exception, match="tasks exist"):
        command.downgrade(cfg, BASE)

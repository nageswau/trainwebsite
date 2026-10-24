"""ccrm-029 -- migration 0174_counselor_tasks (DEC-SCOPE-250): the chain, the CHECKs it repeats, the table, the one-link rule and the
round trip, in a throwaway database (the ccrm-018 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_029_migration_0174", VERSIONS / "0174_counselor_tasks.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0174_counselor_tasks", "0173_checklist_templates"


def test_migration_chains_after_0173_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_model_checks():
    from app.models import COUNSELOR_TASK_CHECKS

    assert _migration.CHECKS == COUNSELOR_TASK_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm029_migration_{uuid.uuid4().hex[:8]}"
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


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def test_table_checks_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "counselor_tasks" not in _tables(url)
    command.upgrade(cfg, HEAD)
    assert "counselor_tasks" in _tables(url)
    user = uuid.uuid4()
    _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, profile, email_verified, locale) "
         "VALUES (:id, :email, 'x', 'C', 'counselor', 'overseas', true, '{}', true, 'en')",
         {"id": user, "email": f"{user.hex[:8]}@example.local"})
    insert = "INSERT INTO counselor_tasks (id, title, counselor_user_id, due_on, created_by_user_id, updated_by_user_id, student_user_id, status) VALUES (:id, 'T', :u, CURRENT_DATE, :u, :u, :s, :status)"
    _sql(url, insert, {"id": uuid.uuid4(), "u": user, "s": user, "status": "open"})
    row = _sql(url, "SELECT priority, source, status FROM counselor_tasks WHERE counselor_user_id = :u", {"u": user})[0]
    assert tuple(row) == ("medium", "manual", "open")
    with pytest.raises(sa.exc.IntegrityError):
        _sql(url, insert, {"id": uuid.uuid4(), "u": user, "s": None, "status": "pending"})
    names = {r[0] for r in _sql(url, "SELECT conname FROM pg_constraint WHERE conrelid = 'counselor_tasks'::regclass AND contype = 'c'")}
    assert names == set(_migration.CHECKS)
    command.downgrade(cfg, BASE)
    assert "counselor_tasks" not in _tables(url)

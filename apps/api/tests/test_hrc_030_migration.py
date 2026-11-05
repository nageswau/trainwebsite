"""hrc-030 -- migration 0287_interview_results (DEC-SCOPE-409 R1/R4/R5): the results table, the global release setting, the frozen checks,
the `results.release` grant for the HR Manager, the chain and the round trip, in a throwaway database (the hrc-020 pattern). Plain tests:
alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.core.rbac import DEFAULT_GRANTS
from app.models import InterviewResult
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_030_migration_0287", VERSIONS / "0287_interview_results.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0287_interview_results", "0284_interview_panel"
TABLES = ("interview_results", "result_release_settings")
GRANT = "SELECT 1 FROM role_permissions WHERE role = 'hr_manager' AND resource = 'results' AND action = 'release'"


def test_migration_chains_after_0284_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert HEAD in {r.revision for r in script.walk_revisions()} and len(script.get_heads()) == 1


def test_checks_are_frozen_copies_of_the_model_and_the_seed_matches_the_default_grant():
    assert {c.name: str(c.sqltext) for c in InterviewResult.__table__.constraints if c.name and c.name.startswith("ck_")} == _migration.CHECKS
    assert "results.release" in DEFAULT_GRANTS["hr_manager"]
    assert _migration.SEED == (("hr_manager", "results", "release"),)


def _tables(url) -> set[str]:
    names = ", ".join(f"'{t}'" for t in TABLES)
    return {r[0] for r in _sql(url, f"SELECT table_name FROM information_schema.tables WHERE table_name IN ({names})")}


def test_round_trip():
    cfg = _config()
    original = settings.database_url
    name = f"hrc030_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        assert _tables(url) == set(TABLES) and _sql(url, GRANT)
        command.downgrade(cfg, BASE)
        assert _tables(url) == set() and not _sql(url, GRANT)
        command.upgrade(cfg, HEAD)  # replays cleanly, now really creating the tables
        assert _tables(url) == set(TABLES) and _sql(url, GRANT)
        checks = {r[0] for r in _sql(url, "SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_interview_results%'")}
        assert set(_migration.CHECKS) <= checks
        assert _sql(url, "SELECT auto_release FROM result_release_settings WHERE id = 1") == [(False,)]
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)

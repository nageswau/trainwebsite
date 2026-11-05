"""hrc-020 -- migration 0277_saved_candidate_searches (DEC-SCOPE-401 X1/X12): the table, the frozen check and seed, the chain and the round
trip, in a throwaway database (the hrc-011 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core import rbac
from app.core.config import settings
from app.models import SavedCandidateSearch
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_020_migration_0277", VERSIONS / "0277_saved_candidate_searches.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0277_saved_candidate_searches", "0276_interview_completion"


def test_migration_chains_after_0276():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_and_seed_are_frozen_copies():
    model = {c.name: str(c.sqltext) for c in SavedCandidateSearch.__table__.constraints if c.name and c.name.startswith("ck_")}
    assert model == _migration.CHECKS
    assert {(role, f"{r}.{a}") for role, r, a in _migration.SEED} == {(role, "candidates.export") for role, keys in rbac.DEFAULT_GRANTS.items() if "candidates.export" in keys}


def _state(url) -> tuple[bool, int]:
    table = _sql(url, "SELECT count(*) FROM information_schema.tables WHERE table_name = 'saved_candidate_searches'")[0][0] == 1
    grants = _sql(url, "SELECT count(*) FROM role_permissions WHERE resource = 'candidates' AND action = 'export'")[0][0]
    return table, grants


def test_round_trip():
    cfg = _config()
    original = settings.database_url
    name = f"hrc020_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        assert _state(url) == (True, 1)
        command.downgrade(cfg, BASE)
        assert _state(url) == (False, 0)
        command.upgrade(cfg, HEAD)  # replays cleanly
        assert _state(url) == (True, 1)
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)

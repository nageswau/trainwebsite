"""hrc-019 -- migration 0275_candidate_search_indexes (DEC-SCOPE-399 S12): pg_trgm and the search indexes, the chain and the round trip,
in a throwaway database (the hrc-011 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import Candidate
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_019_migration_0275", VERSIONS / "0275_candidate_search_indexes.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0275_candidate_search_indexes", "0273_candidate_privacy"


def test_migration_chains_after_0273():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert HEAD in {r.revision for r in script.walk_revisions()}


def test_the_model_declares_the_btree_indexes():
    names = {i.name for i in Candidate.__table__.indexes}
    assert {name for name, *_ in _migration.BTREE} <= names


def _indexes(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")}


def test_round_trip():
    cfg = _config()
    original = settings.database_url
    name = f"hrc019_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    expected = {n for n, *_ in _migration.BTREE} | {n for n, *_ in _migration.TRIGRAM}
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        assert expected <= _indexes(url)
        assert _sql(url, "SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'")[0][0] == 1
        command.downgrade(cfg, BASE)
        assert not (expected & _indexes(url))
        command.upgrade(cfg, HEAD)  # replays cleanly
        assert expected <= _indexes(url)
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)

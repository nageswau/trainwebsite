"""pob-019 -- migration 0319_candidate_tags (DEC-SCOPE-437): the chain, model parity and the round trip, in a throwaway database (the
pob-025 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import CandidateTagLink, RecCandidateTag
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_019_migration", VERSIONS / "0319_candidate_tags.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = _migration.revision, _migration.down_revision


def test_migration_is_in_the_single_chain():
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_tables_match_the_models():
    assert (_migration.TAGS, _migration.LINKS) == (RecCandidateTag.__tablename__, CandidateTagLink.__tablename__)


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob019_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def test_the_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.stamp(cfg, HEAD)  # 0001 builds today's models: drop the tables so the guarded upgrade must create them again
    command.downgrade(cfg, BASE)
    assert not {_migration.TAGS, _migration.LINKS} & _tables(url)
    command.upgrade(cfg, HEAD)
    assert {_migration.TAGS, _migration.LINKS} <= _tables(url)
    indexes = {r[0] for r in _sql(url, "SELECT indexname FROM pg_indexes WHERE tablename IN ('rec_candidate_tags', 'candidate_tag_links')")}
    assert {"uq_rec_candidate_tags_name", "ix_candidate_tag_links_tag"} <= indexes
    command.upgrade(cfg, HEAD)  # a rerun is a no-op
    command.downgrade(cfg, BASE)
    assert not {_migration.TAGS, _migration.LINKS} & _tables(url)

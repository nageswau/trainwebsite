"""hrc-022 -- migration 0261_candidate_portal (DEC-SCOPE-384): the chain, the frozen checks and the round trip in a throwaway database
(the hrc-012 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import UserVerificationToken
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_022_migration_0261", VERSIONS / "0261_candidate_portal.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0261_candidate_portal", "0260_candidate_profile"
TABLES = {"user_verification_tokens", "candidate_self_service_settings"}


def test_migration_chains_after_0260():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_are_frozen_copies():
    model = {c.name: str(c.sqltext) for c in UserVerificationToken.__table__.constraints if c.name in _migration.TOKEN_CHECKS}
    assert model == _migration.TOKEN_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc022_migration_{uuid.uuid4().hex[:8]}"
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
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def test_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not TABLES & _tables(url)
    command.upgrade(cfg, HEAD)
    assert TABLES <= _tables(url)
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert not TABLES & _tables(url)
    command.upgrade(cfg, HEAD)

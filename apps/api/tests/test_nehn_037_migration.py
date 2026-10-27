"""nehn-037 part 4 -- migration 0203_application_interviews (DEC-SCOPE-296): the chain, the constants it repeats, the CHECKs, and the
round trip, in a throwaway database (the ccrm-021 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_037_migration_0203", VERSIONS / "0203_application_interviews.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0203_application_interviews", "0201_coordinator_role"


def test_migration_chains_after_its_base_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_model_constants():
    from app.models import APPLICATION_INTERVIEW_MODES, APPLICATION_INTERVIEW_OUTCOMES

    assert _migration.MODES == APPLICATION_INTERVIEW_MODES and _migration.OUTCOMES == APPLICATION_INTERVIEW_OUTCOMES


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"nehn037_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def test_checks_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "application_interviews" in _tables(url)
    # PostgreSQL checks the CHECKs on the row before the foreign key, so a made-up application id still names the CHECK that failed.
    for mode, outcome, constraint in (("'video'", "NULL", "ck_application_interviews_mode"), ("'online'", "'maybe'", "ck_application_interviews_outcome")):
        with pytest.raises(sa.exc.IntegrityError, match=constraint):
            _sql(url, f"INSERT INTO application_interviews (id, application_id, scheduled_at, mode, outcome) VALUES (gen_random_uuid(), gen_random_uuid(), now(), {mode}, {outcome})")
    command.downgrade(cfg, BASE)
    assert "application_interviews" not in _tables(url)
    command.upgrade(cfg, HEAD)
    assert "application_interviews" in _tables(url)

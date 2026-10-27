"""nehn-018 -- migration 0206_student_access_rules (DEC-SCOPE-299): the chain, the frozen copies and the round trip, in a throwaway
database (the nehn-003 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import STUDENT_ACCESS_FEATURES, STUDENT_PAYMENT_STATES
from app.services import student_access
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_018_migration_0206", VERSIONS / "0206_student_access_rules.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0206_student_access_rules", "0205_enquiry_list_indexes"
GRANTS = "SELECT role, resource, action FROM role_permissions WHERE resource = 'student_access'"


def test_migration_chains_after_0205_and_matches_the_model():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}
    assert (_migration.FEATURES, _migration.STATES, _migration.DEFAULT_MIN_STATE) == (STUDENT_ACCESS_FEATURES, STUDENT_PAYMENT_STATES, student_access.DEFAULT_MIN_STATE)


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"nehn018_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "student_access_rules" not in _tables(url) and _sql(url, GRANTS) == []
    command.upgrade(cfg, HEAD)
    assert sorted(tuple(r) for r in _sql(url, "SELECT feature, min_state FROM student_access_rules")) == sorted((f, "partially_paid") for f in STUDENT_ACCESS_FEATURES)
    assert [tuple(r) for r in _sql(url, GRANTS)] == [("it_admin", "student_access", "configure")]
    command.downgrade(cfg, BASE)
    assert "student_access_rules" not in _tables(url) and _sql(url, GRANTS) == []
    command.upgrade(cfg, HEAD)  # and up again: the seed is idempotent
    assert len(_sql(url, "SELECT feature FROM student_access_rules")) == len(STUDENT_ACCESS_FEATURES)

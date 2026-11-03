"""itc-005 -- migration 0244_it_status_labels (DEC-SCOPE-362 S3): one new override table, the single head, the model in step with it,
and a round trip in a throwaway database (the csc-001 pattern; a downgrade never runs against the shared test database)."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import IT_STATUS_LABEL_MAX, ItStatusLabel
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_005_migration_0244", VERSIONS / "0244_it_status_labels.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0244_it_status_labels"


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    assert _migration.LABEL_MAX == IT_STATUS_LABEL_MAX
    assert ItStatusLabel.__tablename__ == "it_status_labels"
    assert [c.name for c in ItStatusLabel.__table__.primary_key.columns] == ["team", "kind", "code"]


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc005_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, _migration.down_revision)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_creates_the_table_and_the_downgrade_drops_it(isolated_db):
    exists = "SELECT to_regclass('public.it_status_labels') IS NOT NULL"
    assert _sql(isolated_db["url"], exists) == [(False,)]
    command.upgrade(isolated_db["cfg"], HEAD)
    assert _sql(isolated_db["url"], exists) == [(True,)]

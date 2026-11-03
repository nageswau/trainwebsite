"""itc-011 -- migration 0243_it_conversion: chain, the seeded template (once), the conversion key's unique index and a round trip, in a
throwaway database (the tel-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_itc_011_migration_0243", VERSIONS / "0243_it_conversion.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = _migration.down_revision, _migration.revision
TABLES = ("SELECT table_name FROM information_schema.tables WHERE table_name IN ('it_conversions', 'it_onboarding_items', "
          "'it_onboarding_template_items') ORDER BY 1")  # fmt: skip
ALL = [("it_conversions",), ("it_onboarding_items",), ("it_onboarding_template_items",)]
SEEDED = "SELECT label FROM it_onboarding_template_items ORDER BY position"


def test_migration_is_in_the_single_head_chain():
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg, original = _config(), settings.database_url
    name = f"itc011_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)  # 0001's create_all already holds the tables: 0243 only seeds the empty template
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_seed_unique_key_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, TABLES) == ALL
    assert [row[0] for row in _sql(url, SEEDED)] == list(_migration.DEFAULT_ITEMS)
    unique = _sql(url, "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_it_conversions_lead_key'")
    assert "UNIQUE" in unique[0][0] and "idempotency_key" in unique[0][0]

    command.downgrade(cfg, BASE)
    assert _sql(url, TABLES) == []
    command.upgrade(cfg, HEAD)
    assert _sql(url, TABLES) == ALL
    assert len(_sql(url, SEEDED)) == len(_migration.DEFAULT_ITEMS)  # seeded once, not twice

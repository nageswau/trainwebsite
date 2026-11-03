"""itc-014 -- migration 0245_fee_discount_requests: chain, the CHECKs, the one-pending-request index, the seeded grant and a round trip, in
a throwaway database (the tel-001 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_itc_014_migration_0245", VERSIONS / "0245_fee_discount_requests.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = _migration.down_revision, "0245_fee_discount_requests"
TABLE = "SELECT table_name FROM information_schema.tables WHERE table_name = 'fee_discount_requests'"
GRANT = "SELECT role FROM role_permissions WHERE resource = 'discounts' AND action = 'approve'"


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg, original = _config(), settings.database_url
    name = f"itc014_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)  # 0001's create_all already holds today's table: start from a true 0243 shape
        command.upgrade(cfg, HEAD)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_constraints_one_pending_index_grant_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, TABLE) == [("fee_discount_requests",)]
    assert _sql(url, GRANT) == [("it_admin",)]
    index = _sql(url, "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_fee_discount_requests_one_pending'")[0][0]
    assert "UNIQUE" in index and "status" in index and "pending" in index
    checks = {row[0] for row in _sql(url, "SELECT conname FROM pg_constraint WHERE conrelid = 'fee_discount_requests'::regclass AND contype = 'c'")}
    assert {"ck_fee_discount_requests_amount", "ck_fee_discount_requests_status"} <= checks

    command.downgrade(cfg, BASE)
    assert _sql(url, TABLE) == [] and _sql(url, GRANT) == []
    command.upgrade(cfg, HEAD)
    assert _sql(url, TABLE) == [("fee_discount_requests",)] and _sql(url, GRANT) == [("it_admin",)]

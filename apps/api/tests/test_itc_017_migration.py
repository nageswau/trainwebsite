"""itc-017 -- migration 0248_accounts_grants: chain, the accountant's three payment grants, the `payments.paid_at` index and a round trip,
in a throwaway database (the tel-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core import rbac
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_itc_017_migration_0248", VERSIONS / "0248_accounts_grants.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = _migration.down_revision, "0248_accounts_grants"
GRANTS = "SELECT action FROM role_permissions WHERE role = 'accountant' AND resource = 'payments' ORDER BY 1"
INDEX = "SELECT indexname FROM pg_indexes WHERE indexname = 'ix_payments_paid_at'"


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_seed_is_a_frozen_copy_of_the_accountant_defaults():
    assert {f"{r}.{a}" for _, r, a in _migration.SEED} == set(rbac.DEFAULT_GRANTS["accountant"])


@pytest.fixture
def isolated_db():
    cfg, original = _config(), settings.database_url
    name = f"itc017_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_grants_index_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, GRANTS) == [("add",), ("refund",), ("view",)]
    assert _sql(url, INDEX) == [("ix_payments_paid_at",)]
    command.downgrade(cfg, BASE)
    assert _sql(url, GRANTS) == [] and _sql(url, INDEX) == []
    command.upgrade(cfg, HEAD)  # guarded: replays cleanly
    assert _sql(url, GRANTS) == [("add",), ("refund",), ("view",)] and _sql(url, INDEX) == [("ix_payments_paid_at",)]

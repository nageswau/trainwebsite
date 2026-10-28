"""ccrm-049 -- migration 0216_payment_proof_documents (DEC-SCOPE-326): the chain and the round trip in a throwaway database (the
nehn-019 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_049_migration_0216", VERSIONS / "0216_payment_proof_documents.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0216_payment_proof_documents", "0215_payment_discount_ledger"
FK = """SELECT rc.delete_rule FROM information_schema.referential_constraints rc
JOIN information_schema.key_column_usage k ON k.constraint_name = rc.constraint_name
WHERE k.table_name = 'payments' AND k.column_name = 'proof_document_id'"""


def test_migration_chains_after_0215():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm049_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _has_column(url) -> bool:
    return bool(_sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'payments' AND column_name = 'proof_document_id'"))


def test_ac5_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _has_column(url) and [r[0] for r in _sql(url, FK)] == ["SET NULL"]  # nullable, ON DELETE SET NULL
    command.downgrade(cfg, BASE)
    assert not _has_column(url)
    command.upgrade(cfg, HEAD)
    assert _has_column(url) and [r[0] for r in _sql(url, FK)] == ["SET NULL"]

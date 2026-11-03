"""itc-015 -- migration 0244_fee_adjustments: chain, the CHECKs, one reversal per payment, the `payments.refund` grant and a round trip,
in a throwaway database (the tel-001 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_itc_015_migration_0244", VERSIONS / "0244_fee_adjustments.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = _migration.down_revision, "0244_fee_adjustments"
TABLE = "SELECT table_name FROM information_schema.tables WHERE table_name = 'fee_adjustments'"
GRANT = "SELECT role FROM role_permissions WHERE resource = 'payments' AND action = 'refund' ORDER BY 1"


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg, original = _config(), settings.database_url
    name = f"itc015_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)  # 0001's create_all already holds today's shape: 0244 must be a no-op on top of it (bar the grant)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _row(url: str, **values) -> None:
    cols = {"id": "gen_random_uuid()", "enrollment_id": "gen_random_uuid()", "kind": "'credit_note'", "amount": "10", "applied_amount": "0", "reason": "'r'",
            "approved_by_id": "gen_random_uuid()", **values}  # fmt: skip
    _sql(url, f"INSERT INTO fee_adjustments ({', '.join(cols)}) VALUES ({', '.join(cols.values())})")


def test_constraints_grant_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, TABLE) == [("fee_adjustments",)]
    assert _sql(url, GRANT) == [("it_admin",)]
    for fk in ("enrollment_id", "approved_by_id"):  # the CHECKs alone are under test
        _sql(url, f"ALTER TABLE fee_adjustments DROP CONSTRAINT IF EXISTS fee_adjustments_{fk}_fkey")
    with pytest.raises(Exception, match="ck_fee_adjustments_kind"):
        _row(url, kind="'discount'")
    with pytest.raises(Exception, match="ck_fee_adjustments_amount"):
        _row(url, amount="0")
    with pytest.raises(Exception, match="ck_fee_adjustments_applied"):
        _row(url, amount="10", applied_amount="11")
    with pytest.raises(Exception, match="ck_fee_adjustments_mode"):
        _row(url, kind="'refund'", payment_mode="'razorpay'")
    unique = _sql(url, "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_fee_adjustments_reversal'")
    assert "UNIQUE" in unique[0][0] and "payment_id" in unique[0][0] and "reversal" in unique[0][0]

    command.downgrade(cfg, BASE)
    assert _sql(url, TABLE) == [] and _sql(url, GRANT) == []
    command.upgrade(cfg, HEAD)
    assert _sql(url, TABLE) == [("fee_adjustments",)] and _sql(url, GRANT) == [("it_admin",)]

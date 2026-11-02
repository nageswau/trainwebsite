"""itc-013 -- migration 0230_payment_mode (DEC-SCOPE-346): chain, the frozen mode list, the CHECK, the backfill of paid gateway rows and a
round trip, in a throwaway database (the tel-001 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_itc_013_migration_0230", VERSIONS / "0230_payment_mode.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0229_it_student_profiles", "0230_payment_mode"
COLUMN = "SELECT column_name FROM information_schema.columns WHERE table_name = 'payments' AND column_name = 'payment_mode'"


def test_migration_chains_after_0229_and_keeps_the_modes_in_step():
    from app.models import PAYMENT_MODES

    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}
    assert _migration.MODES == PAYMENT_MODES


@pytest.fixture
def isolated_db():
    cfg, original = _config(), settings.database_url
    name = f"itc013_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)  # 0001's create_all already holds today's shape: 0230 must be a no-op on top of it
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _payment(url, provider: str, status: str) -> str:
    user_id, payment_id = uuid.uuid4(), uuid.uuid4()
    _sql(url, f"INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile, created_at, updated_at) "
              f"VALUES ('{user_id}', '{user_id}@t.test', 'x', 'T', 'it_student', 'it', true, true, 'en', '{{}}', now(), now())")  # fmt: skip
    _sql(url, f"INSERT INTO payments (id, user_id, division, reference_type, amount, currency, provider, status, is_manual, discount_amount, created_at, updated_at) "
              f"VALUES ('{payment_id}', '{user_id}', 'it', 'enrollment_fee', 100, 'INR', '{provider}', '{status}', false, 0, now(), now())")  # fmt: skip
    return str(payment_id)


def test_check_backfill_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    row = _payment(url, "manual", "pending")
    with pytest.raises(Exception, match="ck_payments_payment_mode"):
        _sql(url, f"UPDATE payments SET payment_mode = 'bitcoin' WHERE id = '{row}'")
    command.downgrade(cfg, BASE)
    assert _sql(url, COLUMN) == []
    paid_online, pending_online, paid_manual = _payment(url, "razorpay", "paid"), _payment(url, "razorpay", "pending"), _payment(url, "manual", "paid")
    command.upgrade(cfg, HEAD)
    assert _sql(url, COLUMN) == [("payment_mode",)]
    modes = dict(_sql(url, f"SELECT id::text, payment_mode FROM payments WHERE id IN ('{paid_online}', '{pending_online}', '{paid_manual}')"))
    # only a confirmed gateway payment is known to be razorpay; an offline payment's mode was never recorded, so it stays unknown
    assert modes == {paid_online: "razorpay", pending_online: None, paid_manual: None}

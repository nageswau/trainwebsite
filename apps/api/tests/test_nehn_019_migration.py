"""nehn-019 -- migration 0215_payment_discount_ledger (DEC-SCOPE-312): the chain, the round trip and the backfill (D12), in a throwaway
database (the nehn-018 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_019_migration_0215", VERSIONS / "0215_payment_discount_ledger.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0215_payment_discount_ledger", "0211_student_access_rules"
COLUMNS = {"discount_amount", "discount_reason", "discounted_by_id", "paid_at"}


def test_migration_chains_after_0211():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"nehn019_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'payments'")}


def test_round_trip_with_backfill(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not COLUMNS & _columns(url)
    admin, student = uuid.uuid4(), uuid.uuid4()
    for uid, role in ((admin, "it_admin"), (student, "it_student")):
        _sql(
            url,
            f"INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile, created_at, updated_at, session_version) VALUES ('{uid}', '{uid}@m.local', 'x', 'U', '{role}', 'it', true, true, 'en-GB', '{{}}', now(), now(), 0)",
            autocommit=True,
        )
    discounted, paid, plain = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for pid, amount, status in ((discounted, 7500, "pending"), (paid, 900, "paid"), (plain, 400, "pending")):
        _sql(
            url,
            f"INSERT INTO payments (id, user_id, division, reference_type, amount, currency, provider, status, is_manual, created_at, updated_at) VALUES ('{pid}', '{student}', 'it', 'service_fee', {amount}, 'INR', 'manual', '{status}', true, now(), now())",
            autocommit=True,
        )
    # two discount steps (10000 -> 8000 -> 7500): gross comes from the first, reason/actor from the latest
    for original, new, reason, at in ((10000, 8000, "first", "2026-01-01"), (8000, 7500, "latest", "2026-01-02")):
        _sql(
            url,
            f"""INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id, outcome, metadata_json, created_at) VALUES ('{uuid.uuid4()}', '{admin}', 'payment.discount', 'payment', '{discounted}', 'recorded', '{{"original_amount": {original}, "discounted_amount": {new}, "reason": "{reason}"}}', '{at}')""",
            autocommit=True,
        )
    _sql(
        url,
        f"INSERT INTO receipts (id, payment_id, user_id, division, receipt_no, amount, currency, file_url, issued_at, created_at, updated_at) VALUES ('{uuid.uuid4()}', '{paid}', '{student}', 'it', 'RCPT-OLD', 900, 'INR', '/x', '2026-02-03 10:00:00+00', now(), now())",
        autocommit=True,
    )

    command.upgrade(cfg, HEAD)
    assert COLUMNS <= _columns(url)
    rows = {str(r[0]): r[1:] for r in _sql(url, "SELECT id, discount_amount, discount_reason, discounted_by_id, paid_at FROM payments")}
    assert float(rows[str(discounted)][0]) == 2500 and rows[str(discounted)][1] == "latest" and rows[str(discounted)][2] == admin
    assert rows[str(paid)][3] is not None and rows[str(paid)][3].isoformat().startswith("2026-02-03")
    assert float(rows[str(plain)][0]) == 0 and rows[str(plain)][1:] == (None, None, None)

    command.downgrade(cfg, BASE)
    assert not COLUMNS & _columns(url)
    command.upgrade(cfg, HEAD)  # and up again
    assert COLUMNS <= _columns(url)

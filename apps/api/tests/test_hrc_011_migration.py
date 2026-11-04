"""hrc-011 -- migration 0251_candidate_compensation (DEC-SCOPE-372): the chain, the frozen checks, the backfill (C9: an existing amount
was rupees a year) and the round trip, in a throwaway database (the hrc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from decimal import Decimal

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import CANDIDATE_PACKAGE_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_011_migration_0251", VERSIONS / "0251_candidate_compensation.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0251_candidate_compensation", "0250_compensation_grant"


def test_migration_chains_after_0250():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_are_a_frozen_copy_of_the_model():
    assert _migration.CHECKS == CANDIDATE_PACKAGE_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc011_migration_{uuid.uuid4().hex[:8]}"
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
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'candidates'")}


def test_backfill_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "expected_annual_inr" not in _columns(url)
    user, candidate = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :e, '!', 'Mig', 'placement_team', 'it', true, true, 'en', '{}')",
        {"id": user, "e": f"{user.hex}@example.local"},
    )
    source = _sql(url, "SELECT id FROM rec_candidate_sources LIMIT 1")[0][0]
    _sql(url, "INSERT INTO candidates (id, candidate_code, name, email, current_salary, expected_salary, source_id, created_by_user_id, status, opted_in, preferred_locations) "
              "VALUES (:id, 'CAN-M11', 'Mig', 'mig11@example.local', 500000, NULL, :s, :u, 'available', false, '[]')", {"id": candidate, "s": source, "u": user})  # fmt: skip
    command.upgrade(cfg, HEAD)
    row = _sql(
        url,
        "SELECT current_salary, current_salary_currency, current_salary_period, current_annual_inr, expected_salary_currency, expected_annual_inr, minimum_salary FROM candidates WHERE id = :id",
        {"id": candidate},
    )[0]
    assert tuple(row) == (Decimal("500000.00"), "INR", "year", Decimal("500000.00"), None, None, None)
    assert _sql(url, "SELECT count(*) FROM rec_fx_rates")[0][0] == 0  # C1: no rate is invented
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert "expected_annual_inr" not in _columns(url) and "minimum_salary" not in _columns(url)
    assert _sql(url, "SELECT current_salary FROM candidates WHERE id = :id", {"id": candidate})[0][0] == Decimal("500000.00")  # untouched
    command.upgrade(cfg, HEAD)

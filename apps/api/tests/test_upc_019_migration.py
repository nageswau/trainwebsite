"""upc-019 -- migration 0144_commission_receipts (spec §2). Round trip, constraints and the downgrade refusal run in a throwaway
database built from scratch (the rec-008 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql
from tests.test_upc_026_migration import _setup

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_upc_019_migration_0144", VERSIONS / "0144_commission_receipts.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0143_university_probability", "0144_commission_receipts"
COLUMNS = {"id", "university_id", "amount", "currency", "received_on", "reference", "note", "application_ids", "created_by_user_id", "created_at", "updated_at"}


def test_migration_chains_after_0143_and_there_is_a_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import COMMISSION_CURRENCIES, COMMISSION_RECEIPT_CHECKS, UniversityCommissionReceipt

    assert _migration.CURRENCIES == COMMISSION_CURRENCIES and _migration.CHECKS == COMMISSION_RECEIPT_CHECKS
    table = UniversityCommissionReceipt.__table__
    assert {c.name for c in table.columns} == COLUMNS
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(COMMISSION_RECEIPT_CHECKS) | {"ix_university_commission_receipts_university", "uq_university_commission_receipts_reference"} <= names
    for name, sql in COMMISSION_RECEIPT_CHECKS.items():
        assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"upc019_migration_{uuid.uuid4().hex[:8]}"
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


def _receipt(url, uni_id, user_id, **over) -> None:
    values = {"id": uuid.uuid4(), "u": uni_id, "by": user_id, "amount": 2700, "cur": "GBP", "ref": f"REM-{uuid.uuid4().hex[:6]}", "note": None} | over
    _sql(
        url,
        "INSERT INTO university_commission_receipts (id, university_id, amount, currency, received_on, reference, note, application_ids, "
        "created_by_user_id, created_at, updated_at) VALUES (:id, :u, :amount, :cur, current_date, :ref, :note, '[]', :by, now(), now())",
        values,
    )


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('university_commission_receipts')") == [(None,)]
    command.upgrade(cfg, HEAD)
    uni_id, user_id = _setup(url)
    _receipt(url, uni_id, user_id, ref="JAN-2026")
    for over, check in (
        ({"amount": 0}, "ck_university_commission_receipts_amount"),
        ({"amount": -5}, "ck_university_commission_receipts_amount"),
        ({"cur": "XYZ"}, "ck_university_commission_receipts_currency"),
        ({"note": "x" * 501}, "ck_university_commission_receipts_note"),
        ({"ref": "jan-2026"}, "uq_university_commission_receipts_reference"),  # one reference per university, any case
    ):
        with pytest.raises(Exception, match=check):
            _receipt(url, uni_id, user_id, **over)
    _sql(url, "DELETE FROM university_commission_receipts")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('university_commission_receipts')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_receipts_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    uni_id, user_id = _setup(url)
    _receipt(url, uni_id, user_id)
    with pytest.raises(Exception, match="commission receipts exist"):
        command.downgrade(cfg, BASE)

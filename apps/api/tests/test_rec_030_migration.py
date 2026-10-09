"""rec-030 -- migration 0139_recruiter_contracts (spec §2). Round trip and downgrade refusal run in a throwaway database built from scratch
(the rec-028 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_rec_030_migration_0139", VERSIONS / "0139_recruiter_contracts.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0138_offer_management", "0139_recruiter_contracts"
CONTRACT_COLUMNS = {
    "id", "company_id", "created_by_user_id", "status", "status_changed_at", "agreement_type", "start_date", "end_date", "fee_basis",
    "fee_value", "payment_terms", "replacement_policy", "contract_document_key", "contract_document_content_type", "contract_document_name",
    "contract_document_uploaded_at", "mou_document_key", "mou_document_content_type", "mou_document_name", "mou_document_uploaded_at",
    "is_current", "created_at", "updated_at",
}


def test_migration_chains_after_0138_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import RECRUITER_CONTRACT_CHECKS, RECRUITER_CONTRACT_EVENT_KINDS, RECRUITER_CONTRACT_STATUSES, RecruiterContract, RecruiterContractEvent

    assert _migration.CHECKS == RECRUITER_CONTRACT_CHECKS
    assert _migration.STATUSES == RECRUITER_CONTRACT_STATUSES and _migration.EVENT_KINDS == RECRUITER_CONTRACT_EVENT_KINDS
    assert {c.name for c in RecruiterContract.__table__.columns} == CONTRACT_COLUMNS
    constraints = {c.name: c for t in (RecruiterContract.__table__, RecruiterContractEvent.__table__) for c in t.constraints}
    for name, sql in _migration.CHECKS.items():
        assert str(constraints[name].sqltext) == sql
    indexes = {i.name for t in (RecruiterContract.__table__, RecruiterContractEvent.__table__) for i in t.indexes}
    assert {"uq_recruiter_contracts_current", "ix_recruiter_contracts_company", "ix_recruiter_contract_events_contract"} <= indexes


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec030_migration_{uuid.uuid4().hex[:8]}"
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


def _setup(url) -> tuple[uuid.UUID, uuid.UUID]:
    company_id, user_id = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', now(), now())",
        {"id": company_id, "n": f"Co {company_id.hex[:6]}"},
    )
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'x', 'R', 'placement_team', 'it', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"{user_id.hex[:8]}@example.local"},
    )
    return company_id, user_id


def _contract(url, company_id, user_id, columns: str = "", values: str = "", **params) -> uuid.UUID:
    row = uuid.uuid4()
    _sql(
        url,
        f"INSERT INTO recruiter_contracts (id, company_id, created_by_user_id, is_current{columns}) VALUES (:id, :c, :u, false{values})",
        {"id": row, "c": company_id, "u": user_id, **params},
    )
    return row


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('recruiter_contracts')") == [(None,)]
    command.upgrade(cfg, HEAD)
    company_id, user_id = _setup(url)
    _contract(url, company_id, user_id)
    assert _sql(url, "SELECT status FROM recruiter_contracts") == [("discussion",)]
    cases = {
        "ck_recruiter_contracts_status": (", status", ", 'expired'"),  # Expired is derived, never stored (CT2)
        "ck_recruiter_contracts_window": (", start_date, end_date", ", DATE '2026-05-01', DATE '2026-04-01'"),
        "ck_recruiter_contracts_fee_pair": (", fee_basis", ", 'fixed'"),
        "ck_recruiter_contracts_fee_basis": (", fee_basis, fee_value", ", 'hourly', 10"),
        "ck_recruiter_contracts_fee_value": (", fee_basis, fee_value", ", 'percent_of_ctc', 101"),
        "ck_recruiter_contracts_signed_document": (", status", ", 'signed'"),
        "ck_recruiter_contracts_active_window": (", status, contract_document_key, contract_document_content_type", ", 'active', 'k', 'application/pdf'"),
        "ck_recruiter_contracts_contract_document": (", contract_document_key", ", 'k'"),
    }
    for name, (columns, values) in cases.items():
        with pytest.raises(Exception, match=name):
            _contract(url, company_id, user_id, columns, values)
    _sql(url, "UPDATE recruiter_contracts SET is_current = true")
    with pytest.raises(Exception, match="uq_recruiter_contracts_current"):  # CT7: one current contract per company (is_current defaults true)
        _sql(url, "INSERT INTO recruiter_contracts (id, company_id, created_by_user_id) VALUES (:id, :c, :u)", {"id": uuid.uuid4(), "c": company_id, "u": user_id})
    _sql(url, "DELETE FROM recruiter_contracts")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('recruiter_contracts')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_contracts_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _contract(url, *_setup(url))
    with pytest.raises(Exception, match="contracts exist"):
        command.downgrade(cfg, BASE)

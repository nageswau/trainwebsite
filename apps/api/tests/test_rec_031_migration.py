"""rec-031 -- migration 0146_recruiter_revenue (spec §2). Round trip and downgrade refusal run in a throwaway database built from scratch
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
_spec = importlib.util.spec_from_file_location("_rec_031_migration_0146", VERSIONS / "0146_recruiter_revenue.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0145_university_onboarding", "0146_recruiter_revenue"
INVOICE_COLUMNS = {
    "id",
    "job_id",
    "invoice_number",
    "invoice_date",
    "due_date",
    "amount",
    "note",
    "created_by_user_id",
    "cancelled_at",
    "cancelled_by_user_id",
    "cancel_reason",
    "created_at",
    "updated_at",
}
PAYMENT_COLUMNS = {"id", "invoice_id", "received_on", "amount", "reference", "created_by_user_id", "created_at"}


def test_migration_chains_after_0145_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import JOB_FEE_CHECKS, RECRUITER_INVOICE_CHECKS, RECRUITER_PAYMENT_CHECKS, Job, RecruiterInvoice, RecruiterPayment

    assert _migration.JOB_CHECKS == JOB_FEE_CHECKS
    assert _migration.INVOICE_CHECKS == RECRUITER_INVOICE_CHECKS and _migration.PAYMENT_CHECKS == RECRUITER_PAYMENT_CHECKS
    assert {"fee_basis", "fee_value"} <= {c.name for c in Job.__table__.columns}
    assert {c.name for c in RecruiterInvoice.__table__.columns} == INVOICE_COLUMNS
    assert {c.name for c in RecruiterPayment.__table__.columns} == PAYMENT_COLUMNS
    tables = (Job.__table__, RecruiterInvoice.__table__, RecruiterPayment.__table__)
    constraints = {c.name: c for t in tables for c in t.constraints}
    for name, sql in {**_migration.JOB_CHECKS, **_migration.INVOICE_CHECKS, **_migration.PAYMENT_CHECKS}.items():
        assert str(constraints[name].sqltext) == sql
    indexes = {i.name for t in tables for i in t.indexes}
    assert {"uq_recruiter_invoices_number", "ix_recruiter_invoices_job", "ix_recruiter_payments_invoice"} <= indexes


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec031_migration_{uuid.uuid4().hex[:8]}"
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
    company_id, job_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', now(), now())",
        {"id": company_id, "n": f"Co {company_id.hex[:6]}"},
    )
    _sql(
        url,
        "INSERT INTO jobs (id, company_id, title, location, description, skills, status, created_at, updated_at) VALUES (:id, :c, 'Dev', 'Pune', '', '[]', 'requirement_received', now(), now())",
        {"id": job_id, "c": company_id},
    )
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'x', 'R', 'placement_team', 'it', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"{user_id.hex[:8]}@example.local"},
    )
    return job_id, user_id


def _invoice(url, job_id, user_id, number: str, extra: str = "", values: str = "", amount: str = "100") -> uuid.UUID:
    row = uuid.uuid4()
    _sql(
        url,
        f"INSERT INTO recruiter_invoices (id, job_id, invoice_number, invoice_date, due_date, amount, created_by_user_id{extra}) "
        f"VALUES (:id, :j, :n, DATE '2026-04-01', DATE '2026-05-01', {amount}, :u{values})",
        {"id": row, "j": job_id, "n": number, "u": user_id},
    )
    return row


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('recruiter_invoices')") == [(None,)]
    command.upgrade(cfg, HEAD)
    job_id, user_id = _setup(url)
    invoice = _invoice(url, job_id, user_id, "INV-1")
    with pytest.raises(Exception, match="uq_recruiter_invoices_number"):  # RV6: unique ignoring case
        _invoice(url, job_id, user_id, "inv-1")
    with pytest.raises(Exception, match="ck_recruiter_invoices_amount"):
        _invoice(url, job_id, user_id, "INV-2", amount="0")
    with pytest.raises(Exception, match="ck_recruiter_invoices_due"):
        _sql(url, "UPDATE recruiter_invoices SET due_date = DATE '2026-03-01'")
    with pytest.raises(Exception, match="ck_recruiter_invoices_cancel"):
        _sql(url, "UPDATE recruiter_invoices SET cancelled_at = now()")
    with pytest.raises(Exception, match="ck_recruiter_payments_amount"):
        _sql(
            url,
            "INSERT INTO recruiter_payments (id, invoice_id, received_on, amount, created_by_user_id) VALUES (:id, :i, DATE '2026-04-02', -1, :u)",
            {"id": uuid.uuid4(), "i": invoice, "u": user_id},
        )
    for sql, name in (
        ("UPDATE jobs SET fee_basis = 'fixed'", "ck_jobs_fee_pair"),
        ("UPDATE jobs SET fee_basis = 'hourly', fee_value = 1", "ck_jobs_fee_basis"),
        ("UPDATE jobs SET fee_basis = 'percent_of_ctc', fee_value = 101", "ck_jobs_fee_value"),
    ):
        with pytest.raises(Exception, match=name):
            _sql(url, sql)
    _sql(url, "DELETE FROM recruiter_invoices")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('recruiter_invoices')") == [(None,)]
    assert _sql(url, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'jobs' AND column_name = 'fee_basis'") == [(0,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_revenue_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    job_id, user_id = _setup(url)
    _sql(url, "UPDATE jobs SET fee_basis = 'fixed', fee_value = 50000")
    with pytest.raises(Exception, match="revenue data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE jobs SET fee_basis = NULL, fee_value = NULL")
    _invoice(url, job_id, user_id, "INV-9")
    with pytest.raises(Exception, match="revenue data exists"):
        command.downgrade(cfg, BASE)

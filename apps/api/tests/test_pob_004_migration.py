"""pob-004 -- migration 0303_company_bd_stages (DEC-SCOPE-417). Round trip, backfill and downgrade refusal run in a throwaway database built from
scratch (the rec-005 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.recruiter_stages import CLIENT_ORDER, ORDER
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_pob_004_migration", VERSIONS / "0303_company_bd_stages.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0302_bd_activity", "0303_company_bd_stages"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_migration_chains_and_there_is_one_head():
    script = ScriptDirectory.from_config(_config())
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_frozen_copies_match_the_models():
    from app.models import COMPANY_PIPELINE_CHECKS

    assert _migration.STAGES == ORDER
    assert COMPANY_PIPELINE_CHECKS["ck_companies_stage"] == _migration._stage_sql(ORDER)
    for name, sql in _migration.CHECKS.items():
        assert COMPANY_PIPELINE_CHECKS[name] == sql
    assert _migration.CHECKS["ck_companies_client_status"] == "client_status IN (" + ", ".join(f"'{s}'" for s in CLIENT_ORDER) + ")"


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob004_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)  # the real 0302 shape of `companies`
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _company(url, name="Co", **columns) -> uuid.UUID:
    company_id = uuid.uuid4()
    extra = "".join(f", {c}" for c in columns)
    values = "".join(f", :{c}" for c in columns)
    _sql(url, f"INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at{extra}) VALUES (:id, :n, 'recruiter', 'internal', :t, :t{values})",
         {"id": company_id, "n": f"{name} {company_id.hex[:6]}", "t": NOW, **columns})  # fmt: skip
    return company_id


def _job(url, company_id, received_on=None) -> uuid.UUID:
    job_id = uuid.uuid4()
    _sql(url, "INSERT INTO jobs (id, company_id, title, description, location, skills, status, created_at, updated_at) VALUES (:id, :c, 'Dev', 'Role', 'Pune', '[]', 'sourcing', :t, :t)", {"id": job_id, "c": company_id, "t": NOW})
    if received_on:
        _sql(url, "INSERT INTO job_status_history (id, job_id, to_status, created_at) VALUES (:id, :j, 'requirement_received', :t)", {"id": uuid.uuid4(), "j": job_id, "t": received_on})
    return job_id


def _joined(url, job_id, on: date) -> None:
    candidate, application = uuid.uuid4(), uuid.uuid4()
    _sql(url, "INSERT INTO candidates (id, candidate_code, source_id, name, email, preferred_locations, created_at, updated_at) SELECT :id, :code, s.id, 'Cand', :e, '[]', :t, :t FROM rec_candidate_sources s LIMIT 1", {"id": candidate, "code": candidate.hex[:12], "e": f"{candidate.hex}@x.test", "t": NOW})
    _sql(url, "INSERT INTO job_applications (id, job_id, candidate_id, status, created_at, updated_at) VALUES (:id, :j, :c, 'joined', :t, :t)", {"id": application, "j": job_id, "c": candidate, "t": NOW})
    _sql(url, "INSERT INTO job_offers (id, application_id, currency, offered_on, status, joining_status, actual_joining_date, created_at, updated_at) VALUES (:id, :a, 'INR', :d, 'accepted', 'joined', :d, :t, :t)",
         {"id": uuid.uuid4(), "a": application, "d": on, "t": NOW})  # fmt: skip


def _status(url, company_id) -> str:
    return _sql(url, "SELECT client_status FROM companies WHERE id = :id", {"id": company_id})[0][0]


def test_upgrade_seeds_the_lists_widens_the_stage_and_keeps_every_stage(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    at_stage = _company(url, stage="interested")
    lost = _company(url, lost_at=NOW, lost_reason="Typed long ago")
    with pytest.raises(Exception, match="ck_companies_stage"):
        _sql(url, "UPDATE companies SET stage = 'vendor_registration' WHERE id = :id", {"id": at_stage})
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT stage, client_status FROM companies WHERE id = :id", {"id": at_stage}) == [("interested", "prospect")]
    assert _sql(url, "SELECT lost_reason, lost_reason_id FROM companies WHERE id = :id", {"id": lost}) == [("Typed long ago", None)]
    for table, names in _migration.SEED.items():
        assert [r[0] for r in _sql(url, f"SELECT name FROM {table} ORDER BY sort_order")] == list(names)
    _sql(url, "UPDATE companies SET stage = 'vendor_registration' WHERE id = :id", {"id": at_stage})
    with pytest.raises(Exception, match="ck_companies_inactive"):
        _sql(url, "UPDATE companies SET inactive_at = now() WHERE id = :id", {"id": at_stage})
    with pytest.raises(Exception, match="ck_companies_client_status"):
        _sql(url, "UPDATE companies SET client_status = 'won' WHERE id = :id", {"id": at_stage})


def test_backfill_reads_current_clients_from_their_history(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    prospect = _company(url)
    _job(url, prospect)  # a requirement that never reached Requirement Received
    received = _company(url)
    _job(url, received, NOW)
    signed = _company(url)
    user = uuid.uuid4()
    _sql(url, "INSERT INTO users (id, email, full_name, password_hash, role, division, profile, locale, email_verified, active, created_at, updated_at) VALUES (:id, :e, 'U', 'x', 'super_admin', 'global', '{}', 'en', true, true, :t, :t)", {"id": user, "e": f"{user.hex}@x.test", "t": NOW})
    _sql(url, "INSERT INTO recruiter_contracts (id, company_id, status, contract_document_key, contract_document_content_type, created_by_user_id, created_at, updated_at) VALUES (:id, :c, 'signed', 'k', 'application/pdf', :u, :t, :t)", {"id": uuid.uuid4(), "c": signed, "u": user, "t": NOW})
    repeat = _company(url)
    _joined(url, _job(url, repeat, NOW), date(2026, 2, 1))
    _job(url, repeat, datetime(2026, 3, 1, tzinfo=UTC))
    earlier = _company(url)  # the second requirement arrived BEFORE the joining: not repeat business
    _joined(url, _job(url, earlier, NOW), date(2026, 5, 1))
    _job(url, earlier, datetime(2026, 3, 1, tzinfo=UTC))
    command.upgrade(cfg, HEAD)
    assert [_status(url, c) for c in (prospect, received, signed, repeat, earlier)] == ["prospect", "active_client", "active_client", "repeat_business", "active_client"]


def test_round_trip_and_idempotent_at_head(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    company = _company(url)
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    columns = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'companies'")}
    assert not {"client_status", "inactive_at", "inactive_reason", "inactive_reason_id", "lost_reason_id"} & columns
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name IN ('rec_company_lost_reasons', 'rec_company_inactive_reasons')")
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT stage, client_status FROM companies WHERE id = :id", {"id": company}) == [("new_lead", "prospect")]


@pytest.mark.parametrize("change", ["UPDATE companies SET stage = 'research_completed'", "UPDATE companies SET inactive_at = now(), inactive_reason = 'x'"])
def test_downgrade_refuses_while_new_data_exists(isolated_db, change):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    _company(url)
    command.upgrade(cfg, HEAD)
    _sql(url, change)
    with pytest.raises(Exception, match="0303_company_bd_stages"):
        command.downgrade(cfg, BASE)

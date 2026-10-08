"""rec-003 -- migration 0106_rec_companies (spec §3; AC8). Round trip, backfill and downgrade refusal run in a throwaway database built
from scratch (the rec-002 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_003_migration_0106", VERSIONS / "0106_rec_companies.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0105_university_master", "0106_rec_companies"
NEW_COLUMNS = {
    "company_code",
    "linkedin_url",
    "industry_id",
    "company_size_id",
    "employee_count",
    "city",
    "state",
    "country",
    "head_office",
    "branches",
    "description",
    "lead_source_id",
    "campaign_id",
    "priority",
    "assigned_recruiter_user_id",
    "assigned_bdm_user_id",
    "created_by_user_id",
    "archived_at",
}


def test_migration_chains_after_0105_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import Company, CompanyAssignmentHistory

    table = Company.__table__
    assert NEW_COLUMNS <= {c.name for c in table.columns}
    assert not table.c.company_code.nullable
    assert all(table.c[name].nullable for name in NEW_COLUMNS - {"company_code"})
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(_migration.CHECKS) | set(_migration.INDEXES) | {"uq_companies_code"} <= names
    for name, sql in _migration.CHECKS.items():
        assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql
    history = CompanyAssignmentHistory.__table__
    assert {c.name for c in history.columns} == {"id", "company_id", "from_user_id", "to_user_id", "changed_by_user_id", "created_at"}
    assert history.c.from_user_id.nullable and not history.c.to_user_id.nullable


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec003_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        # 0001's create_all builds today's models; going to head and back down gives the real 0105 shape of `companies`.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _company(url, name, created_at):
    _sql(url, "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', :t, :t)", {"id": uuid.uuid4(), "n": name, "t": created_at})


def test_backfill_codes_existing_companies_in_creation_order(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    columns = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'companies'")}
    assert not NEW_COLUMNS & columns  # the real 0105 shape
    _company(url, "Second Ltd", datetime(2026, 2, 1, tzinfo=UTC))
    _company(url, "First Ltd", datetime(2026, 1, 1, tzinfo=UTC))
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT name, company_code FROM companies ORDER BY company_code") == [("First Ltd", "CMP-000001"), ("Second Ltd", "CMP-000002")]
    _company(url, "Third Ltd", datetime(2026, 3, 1, tzinfo=UTC))  # a new insert path that knows nothing of codes (EMP-001, /workflows/it/jobs)
    assert _sql(url, "SELECT company_code FROM companies WHERE name = 'Third Ltd'") == [("CMP-000003",)]
    with pytest.raises(Exception, match="ck_companies_priority"):
        _sql(url, "UPDATE companies SET priority = 'urgent'")
    with pytest.raises(Exception, match="uq_companies_code"):
        _sql(url, "UPDATE companies SET company_code = 'CMP-000001'")


def test_round_trip_without_recruiter_data(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    _company(url, "Round Trip Ltd", datetime(2026, 1, 1, tzinfo=UTC))
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'company_code'") == [(0,)]
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT company_code FROM companies") == [("CMP-000001",)]  # the sequence was dropped and restarts


@pytest.mark.parametrize("change", ["UPDATE companies SET city = 'Pune'", "UPDATE companies SET priority = 'hot'"])
def test_downgrade_refuses_while_recruiter_data_exists(isolated_db, change):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    _company(url, "Kept Ltd", datetime(2026, 1, 1, tzinfo=UTC))
    command.upgrade(cfg, HEAD)
    _sql(url, change)
    with pytest.raises(Exception, match="recruiter company data"):
        command.downgrade(cfg, BASE)

"""rec-005 -- migration 0111_company_pipeline (spec §3). Round trip, backfill and downgrade refusal run in a throwaway database built from
scratch (the rec-003 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.recruiter_stages import STAGES
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_005_migration_0111", VERSIONS / "0111_company_pipeline.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0110_company_contacts", "0111_company_pipeline"
NEW_COLUMNS = {"stage", "stage_changed_at", "lost_at", "lost_reason"}


def test_migration_chains_after_0110_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_migration_keeps_a_frozen_copy_of_the_catalogue():
    assert _migration.STAGES == tuple(key for key, _, _ in STAGES)


def test_models_match_the_migration():
    from app.models import Company, CompanyStageHistory

    table = Company.__table__
    assert NEW_COLUMNS <= {c.name for c in table.columns}
    assert not table.c.stage.nullable and not table.c.stage_changed_at.nullable
    assert table.c.lost_at.nullable and table.c.lost_reason.nullable
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(_migration.CHECKS) | {_migration.INDEX} <= names
    for name, sql in _migration.CHECKS.items():
        assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql
    history = CompanyStageHistory.__table__
    assert {c.name for c in history.columns} == {"id", "company_id", "from_stage", "to_stage", "event", "actor_user_id", "reason", "position", "created_at"}
    assert history.c.actor_user_id.nullable and history.c.reason.nullable


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec005_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)  # the real 0110 shape of `companies`
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _company(url, name, created_at):
    _sql(url, "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', :t, :t)", {"id": uuid.uuid4(), "n": name, "t": created_at})


def test_existing_companies_start_at_new_lead_changed_when_created(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    columns = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'companies'")}
    assert not NEW_COLUMNS & columns
    created = datetime(2026, 1, 1, tzinfo=UTC)
    _company(url, "Old Ltd", created)
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT stage, stage_changed_at, lost_at FROM companies") == [("new_lead", created, None)]
    _company(url, "New Ltd", datetime(2026, 3, 1, tzinfo=UTC))  # an insert path that knows nothing of stages (EMP-001)
    assert _sql(url, "SELECT stage FROM companies WHERE name = 'New Ltd'") == [("new_lead",)]
    with pytest.raises(Exception, match="ck_companies_stage"):
        _sql(url, "UPDATE companies SET stage = 'won'")
    with pytest.raises(Exception, match="ck_companies_lost"):
        _sql(url, "UPDATE companies SET lost_at = now()")


def test_round_trip_without_pipeline_data(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    _company(url, "Round Trip Ltd", datetime(2026, 1, 1, tzinfo=UTC))
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'stage'") == [(0,)]
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT stage FROM companies") == [("new_lead",)]


@pytest.mark.parametrize("change", ["UPDATE companies SET stage = 'contacted'", "UPDATE companies SET lost_at = now(), lost_reason = 'x'"])
def test_downgrade_refuses_while_pipeline_data_exists(isolated_db, change):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    _company(url, "Kept Ltd", datetime(2026, 1, 1, tzinfo=UTC))
    command.upgrade(cfg, HEAD)
    _sql(url, change)
    with pytest.raises(Exception, match="pipeline data"):
        command.downgrade(cfg, BASE)

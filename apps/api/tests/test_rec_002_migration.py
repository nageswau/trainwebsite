"""rec-002 -- migration 0102_rec_catalogues (spec §3; AC1). Round trip, seed and downgrade refusal run in a throwaway database built from
scratch (the tel-002 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_002_migration_0102", VERSIONS / "0102_rec_catalogues.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0101_country_master", "0102_rec_catalogues"
# EVID-018, in source order (AC1: names and order exactly), plus the owner's C2 bands; industries start empty (C1).
SEED = {
    "rec_lead_sources": [
        "LinkedIn",
        "College visits",
        "Job fairs",
        "Recruitment events",
        "Company visits",
        "Website",
        "Google",
        "Social media",
        "Referrals",
        "Existing clients",
        "BDM network",
        "Corporate database",
        "Cold calling",
        "Email campaigns",
        "WhatsApp campaigns",
    ],
    "rec_candidate_sources": [
        "College placements",
        "Edusphere students",
        "IT training students",
        "Job portals",
        "LinkedIn",
        "Referral",
        "Walk-ins",
        "Social media",
        "Career fairs",
        "Campus drives",
        "Database",
        "Employee referrals",
    ],
    "rec_industries": [],
    "rec_job_categories": ["IT", "Sales", "Marketing", "Finance", "HR", "Engineering"],
    "rec_contact_roles": ["HR Manager", "Talent Acquisition Manager", "Recruiter", "Hiring Manager", "HR Head"],
    "rec_company_sizes": ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001+"],
}
D1, D30 = date(2026, 9, 1), date(2026, 9, 30)


def _seeded(url: str, table: str) -> list[str]:
    return [row[0] for row in _sql(url, f"SELECT name FROM {table} ORDER BY sort_order, lower(name)")]


def test_migration_chains_after_0101_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_migration_seed_is_the_source_list():
    assert {table: list(names) for table, names in _migration.SEED.items()} == SEED


def test_models_match_the_migration():
    from app.models import REC_CATALOGUE_MODELS, RecCampaign

    assert {m.__tablename__ for m in REC_CATALOGUE_MODELS.values()} == set(SEED)
    for model in REC_CATALOGUE_MODELS.values():
        table = model.__table__
        assert {c.name for c in table.columns} == {"id", "name", "active", "sort_order", "created_at", "updated_at"}
        assert not table.c.name.nullable
        assert f"uq_{table.name}_name" in {i.name for i in table.indexes}
    campaign = RecCampaign.__table__
    assert {c.name for c in campaign.columns} == {"id", "name", "lead_source_id", "start_date", "end_date", "active", "created_at", "updated_at"}
    assert campaign.c.end_date.nullable and not campaign.c.start_date.nullable and not campaign.c.lead_source_id.nullable
    names = {i.name for i in campaign.indexes} | {c.name for c in campaign.constraints}
    assert {"uq_rec_campaigns_name", "ix_rec_campaigns_lead_source", "ck_rec_campaigns_dates"} <= names


@pytest.mark.asyncio
async def test_seed_is_in_the_shared_database(db_session):
    """AC1: the shared test database was upgraded to head, so every seed value is there (other tests add more; never fewer)."""
    from app.models import REC_CATALOGUE_MODELS

    for model in REC_CATALOGUE_MODELS.values():
        names = set((await db_session.scalars(select(model.name))).all())
        assert set(SEED[model.__tablename__]) <= names


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec002_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        # 0001's create_all builds today's models (these tables included); going to head and back down gives the real 0100 shape.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _migration_seed_again(url):
    """The seed statements on their own, as a fresh database built by 0001 would run them on already-seeded tables."""
    for statement, params in _migration.seed_statements():
        _sql(url, statement, params)


def test_seed_round_trip_and_idempotence(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    assert {table: _seeded(url, table) for table in SEED} == SEED
    _sql(url, "UPDATE rec_job_categories SET active = false WHERE name = 'HR'")
    _migration_seed_again(url)  # nothing duplicated, and a manager's edit is never overwritten
    assert {table: _seeded(url, table) for table in SEED} == SEED
    assert _sql(url, "SELECT active FROM rec_job_categories WHERE name = 'HR'") == [(False,)]
    _sql(url, "UPDATE rec_job_categories SET active = true WHERE name = 'HR'")
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    assert {table: _seeded(url, table) for table in SEED} == SEED


def test_constraints_hold(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="uq_rec_job_categories_name"):
        _sql(url, "INSERT INTO rec_job_categories (id, name) VALUES (:id, 'it')", {"id": uuid.uuid4()})
    _sql(url, "INSERT INTO rec_candidate_sources (id, name) VALUES (:id, 'Website')", {"id": uuid.uuid4()})  # per-list uniqueness only
    source = _sql(url, "SELECT id FROM rec_lead_sources WHERE name = 'LinkedIn'")[0][0]
    insert = "INSERT INTO rec_campaigns (id, name, lead_source_id, start_date, end_date) VALUES (:id, :n, :s, :a, :b)"
    with pytest.raises(Exception, match="ck_rec_campaigns_dates"):
        _sql(url, insert, {"id": uuid.uuid4(), "n": "C1", "s": source, "a": D30, "b": D1})
    with pytest.raises(Exception, match="rec_campaigns_lead_source_id_fkey"):
        _sql(url, insert, {"id": uuid.uuid4(), "n": "C1", "s": uuid.uuid4(), "a": D1, "b": None})
    _sql(url, insert, {"id": uuid.uuid4(), "n": "C1", "s": source, "a": D1, "b": None})
    with pytest.raises(Exception, match="uq_rec_campaigns_name"):
        _sql(url, insert, {"id": uuid.uuid4(), "n": "c1", "s": source, "a": D1, "b": None})


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE rec_contact_roles SET active = false WHERE name = 'HR Head'",
        "UPDATE rec_company_sizes SET name = '1001-5000' WHERE name = '1001+'",
        "INSERT INTO rec_industries (id, name) VALUES (gen_random_uuid(), 'Fintech')",
        "INSERT INTO rec_campaigns (id, name, lead_source_id, start_date) SELECT gen_random_uuid(), 'C', id, '2026-09-01' FROM rec_lead_sources LIMIT 1",
    ],
)
def test_downgrade_refuses_while_manager_data_exists(isolated_db, change):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, change)
    with pytest.raises(Exception, match="manager data"):
        command.downgrade(cfg, BASE)

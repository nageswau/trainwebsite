"""tel-002 -- migration 0076_tel_catalogue (spec §3; AC1, AC4, AC7). Round trip, seed and downgrade refusal run in a throwaway database
built from scratch (the tel-001 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_tel_002_migration_0076", VERSIONS / "0076_tel_catalogue.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0075_telecaller_profiles", "0076_tel_catalogue"
SEED = {
    ("it", "Digital Marketing", "it"), ("it", "SAP", "it"), ("it", "Cyber Security", "it"), ("it", "Python Full Stack", "it"), ("it", "Java", "it"),
    ("overseas", "UK", "overseas"), ("overseas", "USA", "overseas"), ("overseas", "Canada", "overseas"), ("overseas", "Australia", "overseas"),
    ("overseas", "New Zealand", "overseas"), ("overseas", "Germany", "overseas"), ("overseas", "Japan", "overseas"),
    ("overseas", "South Korea", "overseas"), ("overseas", "Dubai", "overseas"),
    ("other", "Career Guidance", None), ("other", "Job Assistance", "it"), ("other", "Career Change", "it"), ("other", "General Enquiry", None),
}
D1, D30 = date(2026, 9, 1), date(2026, 9, 30)
PRODUCTS = "SELECT product_group, name, team FROM tel_products"


def test_migration_chains_after_0075_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]


def test_models_match_the_migration():
    from app.models import TelCampaign, TelProduct

    product, campaign = TelProduct.__table__, TelCampaign.__table__
    assert {c.name for c in product.columns} == {"id", "product_group", "name", "team", "program_id", "active", "sort_order", "created_at", "updated_at"}
    assert {c.name for c in campaign.columns} == {"id", "name", "source", "product_id", "start_date", "end_date", "active", "created_at", "updated_at"}
    assert product.c.team.nullable and product.c.program_id.nullable and not product.c.name.nullable
    assert campaign.c.end_date.nullable and not campaign.c.start_date.nullable and not campaign.c.product_id.nullable
    names = {i.name for t in (product, campaign) for i in t.indexes} | {c.name for t in (product, campaign) for c in t.constraints}
    assert {
        "uq_tel_products_group_name", "ck_tel_products_group", "ck_tel_products_team", "ck_tel_products_team_matches_group",
        "ck_tel_products_program_it_only", "uq_tel_campaigns_name", "ck_tel_campaigns_source", "ck_tel_campaigns_dates", "ix_tel_campaigns_product",
    } <= names


@pytest.mark.asyncio
async def test_seed_is_in_the_shared_database(db_session):
    """AC1: the shared test database was upgraded to head, so every §3 value is there with its T18 team."""
    from app.models import TelProduct

    rows = {(p.product_group, p.name, p.team) for p in (await db_session.scalars(select(TelProduct))).all()}
    assert SEED <= rows


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel002_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _insert_product(url, group, name, team, program=None):
    _sql(url, "INSERT INTO tel_products (id, product_group, name, team, program_id) VALUES (:id, :g, :n, :t, :p)",
         {"id": uuid.uuid4(), "g": group, "n": name, "t": team, "p": program})


def test_seed_round_trip_and_idempotence(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    assert set(_sql(url, PRODUCTS)) == SEED and len(_sql(url, PRODUCTS)) == 18
    _migration_seed_again(url)
    assert len(_sql(url, PRODUCTS)) == 18
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    assert set(_sql(url, PRODUCTS)) == SEED


def _migration_seed_again(url):
    """The seed statement on its own, as a fresh database built by 0001 would run it on an already-seeded table."""
    for statement, params in _migration.seed_statements():
        _sql(url, statement, params)


def test_constraints_hold(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="uq_tel_products_group_name"):
        _insert_product(url, "it", "cyber security", "it")
    _insert_product(url, "overseas", "Cyber Security", "overseas")  # the same name in another group is fine
    with pytest.raises(Exception, match="ck_tel_products_team_matches_group"):
        _insert_product(url, "it", "Rust", "overseas")
    with pytest.raises(Exception, match="ck_tel_products_group"):
        _insert_product(url, "global", "Rust", None)
    program = uuid.uuid4()
    _sql(url, "INSERT INTO programs (id, slug, category, title, summary, duration, eligibility, fees, certification, curriculum, "
              "placement_assistance, trainer_name, active) VALUES (:id, :slug, 'it', 'P', 's', 'd', 'e', 1, 'c', '[]', 'p', 't', true)",
         {"id": program, "slug": f"p-{program.hex[:8]}"})
    with pytest.raises(Exception, match="ck_tel_products_program_it_only"):
        _insert_product(url, "other", "Coaching", None, program)
    product = _sql(url, "SELECT id FROM tel_products WHERE name = 'SAP'")[0][0]
    insert = "INSERT INTO tel_campaigns (id, name, source, product_id, start_date, end_date) VALUES (:id, :n, :s, :p, :a, :b)"
    with pytest.raises(Exception, match="ck_tel_campaigns_dates"):
        _sql(url, insert, {"id": uuid.uuid4(), "n": "C1", "s": "instagram", "p": product, "a": D30, "b": D1})
    with pytest.raises(Exception, match="ck_tel_campaigns_source"):
        _sql(url, insert, {"id": uuid.uuid4(), "n": "C1", "s": "tiktok", "p": product, "a": D1, "b": None})
    _sql(url, insert, {"id": uuid.uuid4(), "n": "C1", "s": "walk_in", "p": product, "a": D1, "b": None})
    with pytest.raises(Exception, match="uq_tel_campaigns_name"):
        _sql(url, insert, {"id": uuid.uuid4(), "n": "c1", "s": "bdm", "p": product, "a": D1, "b": None})


def test_downgrade_refuses_while_manager_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, "UPDATE tel_products SET team = 'overseas' WHERE name = 'Career Guidance'")
    with pytest.raises(Exception, match="manager data"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE tel_products SET team = NULL WHERE name = 'Career Guidance'")
    product = _sql(url, "SELECT id FROM tel_products WHERE name = 'SAP'")[0][0]
    _sql(url, "INSERT INTO tel_campaigns (id, name, source, product_id, start_date) VALUES (:id, 'C', 'google', :p, :a)",
         {"id": uuid.uuid4(), "p": product, "a": D1})
    with pytest.raises(Exception, match="manager data"):
        command.downgrade(cfg, BASE)

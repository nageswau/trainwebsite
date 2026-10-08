"""upc-002 -- migration 0101_country_master (design §2; U12, Q-06). The ISO data, model parity, and a round trip in a throwaway database
built from scratch (the tel-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

API = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_upc_002_migration_0101", API / "alembic" / "versions" / "0101_country_master.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0100_recruiter_profiles", "0101_country_master"
CATALOGUE_SEED = json.loads((API / "seed" / "countries.json").read_text())


def test_migration_chains_after_0100_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_iso_list_is_complete_unique_and_every_row_has_a_known_region():  # upc-002-AC2
    rows = _migration.ISO_COUNTRIES
    codes = [code for code, _, _ in rows]
    assert len(rows) == 249 and len(set(codes)) == 249
    assert all(len(code) == 2 and code.isascii() and code.isupper() for code in codes)
    assert {region for _, _, region in rows} == set(_migration.REGIONS)
    slugs = [_migration.slug_for(code, name) for code, name, _ in rows]
    assert len(set(slugs)) == 249 and all(s and s == s.lower() and " " not in s for s in slugs)


def test_regions_are_the_nine_q06_values_and_uk_stands_alone():
    by_code = {code: region for code, _, region in _migration.ISO_COUNTRIES}
    assert _migration.REGIONS == ("UK", "Europe", "North America", "Latin America & Caribbean", "Middle East", "Asia", "Oceania", "Africa", "Antarctica")
    assert [code for code, region in by_code.items() if region == "UK"] == ["GB"]
    assert (by_code["AE"], by_code["IE"], by_code["MX"], by_code["TR"], by_code["EG"], by_code["JP"], by_code["AU"], by_code["AQ"]) == (
        "Middle East", "Europe", "Latin America & Caribbean", "Middle East", "Africa", "Asia", "Oceania", "Antarctica")


def test_the_twelve_catalogue_slugs_map_to_their_iso_rows_and_the_seed_agrees():  # edge: "Dubai (UAE)" -> AE
    by_code = {code: region for code, _, region in _migration.ISO_COUNTRIES}
    assert {row[0] for row in CATALOGUE_SEED} == set(_migration.CATALOGUE_SLUGS)
    for slug, name, *_, iso2, region in CATALOGUE_SEED:
        assert _migration.CATALOGUE_SLUGS[slug] == iso2 and by_code[iso2] == region, slug
        assert _migration.slug_for(iso2, name) == slug  # a fresh database's placeholder already has the catalogue slug
    assert _migration.CATALOGUE_SLUGS["dubai-uae"] == "AE" and _migration.CATALOGUE_SLUGS["usa"] == "US"


def test_model_matches_the_migration():
    from app.models import COUNTRY_REGIONS, Country

    table = Country.__table__
    assert {"iso2", "region", "catalogue_visible"} <= {c.name for c in table.columns}
    assert table.c.iso2.nullable and table.c.region.nullable and not table.c.catalogue_visible.nullable
    assert {"uq_countries_iso2", "ck_countries_iso2", "ck_countries_region"} <= {c.name for c in table.constraints}
    assert COUNTRY_REGIONS == _migration.REGIONS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"upc002_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _old_country(url: str, slug: str, name: str, overview: str = "Catalogue text") -> None:
    _sql(url, "INSERT INTO countries (id, slug, name, overview, tuition, living_expenses, visa_process, work_opportunities, post_study_work, "
         f"pr_opportunities, faq) VALUES ('{uuid.uuid4()}', '{slug}', '{name}', '{overview}', 't', 'l', '[]', 'w', 'p', 'r', '[]')")


def test_downgrade_returns_the_base_shape(isolated_db):
    columns = {row[0] for row in _sql(isolated_db["url"], "SELECT column_name FROM information_schema.columns WHERE table_name = 'countries'")}
    assert not {"iso2", "region", "catalogue_visible"} & columns
    assert _sql(isolated_db["url"], "SELECT count(*) FROM countries") == [(0,)]


def test_round_trip_backfills_the_catalogue_and_seeds_internal_iso_rows(isolated_db):  # upc-002-AC1/AC2
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    _old_country(url, "germany", "Germany")
    _old_country(url, "dubai-uae", "Dubai (UAE)")
    _old_country(url, "agn-test-country", "Testland")  # a dev/test row: kept, visible, no code
    command.upgrade(cfg, HEAD)
    rows = dict(((slug), (iso2, region, visible, name, overview)) for slug, iso2, region, visible, name, overview in _sql(
        url, "SELECT slug, iso2, region, catalogue_visible, name, overview FROM countries"))
    assert rows["germany"] == ("DE", "Europe", True, "Germany", "Catalogue text")
    assert rows["dubai-uae"] == ("AE", "Middle East", True, "Dubai (UAE)", "Catalogue text")
    assert rows["agn-test-country"] == (None, None, True, "Testland", "Catalogue text")
    assert rows["japan"] == ("JP", "Asia", False, "Japan", "")
    assert rows["united-kingdom"][:3] == ("GB", "UK", False)
    assert _sql(url, "SELECT count(*), count(DISTINCT iso2) FROM countries WHERE iso2 IS NOT NULL") == [(249, 249)]
    assert _sql(url, "SELECT count(*) FROM countries WHERE catalogue_visible") == [(3,)]
    with pytest.raises(sa.exc.IntegrityError):  # negative: a second row with an existing code is refused by the database
        _sql(url, "UPDATE countries SET iso2 = 'DE' WHERE slug = 'japan'")
    with pytest.raises(sa.exc.IntegrityError):
        _sql(url, "UPDATE countries SET region = 'Atlantis' WHERE slug = 'japan'")
    command.downgrade(cfg, BASE)
    assert sorted(r[0] for r in _sql(url, "SELECT slug FROM countries")) == ["agn-test-country", "dubai-uae", "germany"]


def test_an_existing_row_that_holds_an_iso_slug_fails_the_migration_loudly(isolated_db):  # negative scenario
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    _old_country(url, "japan", "Not Japan")
    with pytest.raises(RuntimeError, match="japan"):
        command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_a_university_uses_an_internal_country(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, "INSERT INTO universities (id, country_id, slug, name, city, overview, eligibility, requirements, deadlines, scholarships) "
         f"SELECT '{uuid.uuid4()}', id, 'upc002-u', 'U', '', '', '', '[]', '[]', '[]' FROM countries WHERE iso2 = 'JP'")
    with pytest.raises(RuntimeError, match="internal country"):
        command.downgrade(cfg, BASE)

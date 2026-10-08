"""upc-004 -- migration 0106_university_duplicates and the name key (spec §2). The round trip, backfill, report and downgrade refusal run in
a throwaway database (the upc-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.core.identifiers import normalize_key
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_upc_004_migration_0106", VERSIONS / "0106_university_duplicates.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0105_university_master", "0106_university_duplicates"


def test_migration_chains_after_0105_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]


def test_normalize_key_folds_case_spacing_and_width():
    assert normalize_key("  ABC   University ", 200) == "abc university"
    assert normalize_key("ＡＢＣ University", 200) == "abc university"  # full-width (NFKC)
    assert normalize_key("Straße", 200) == "strasse"
    assert normalize_key("x" * 300, 200) == "x" * 200


def test_the_bdm_service_uses_the_same_key():
    from app.services import bdm_organizations

    assert bdm_organizations.normalize_key is normalize_key


def test_model_keeps_the_name_key_in_sync():
    from app.models import University

    uni = University(name="  ABC  University ")
    assert uni.name_key == "abc university"
    uni.name = "Other College"
    assert uni.name_key == "other college"


def test_model_matches_the_migration():
    from app.models import BdmOrganization, University

    assert not University.__table__.c.name_key.nullable
    assert "ix_universities_duplicate_key" in {i.name for i in University.__table__.indexes}
    column = BdmOrganization.__table__.c.university_id
    assert column.nullable and {fk.column.table.name for fk in column.foreign_keys} == {"universities"}
    checks = {c.name: str(c.sqltext) for c in BdmOrganization.__table__.constraints if c.name == _migration.LINK_CHECK}
    assert checks == {_migration.LINK_CHECK: _migration.LINK_SQL}


@pytest.mark.asyncio
async def test_columns_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    uni_cols, uni_idx, org_cols, org_idx = await conn.run_sync(
        lambda sync: (
            {c["name"] for c in inspect(sync).get_columns("universities")},
            {i["name"] for i in inspect(sync).get_indexes("universities")},
            {c["name"] for c in inspect(sync).get_columns("bdm_organizations")},
            {i["name"] for i in inspect(sync).get_indexes("bdm_organizations")},
        )
    )
    assert "name_key" in uni_cols and "ix_universities_duplicate_key" in uni_idx
    assert "university_id" in org_cols and "ix_bdm_organizations_university" in org_idx


@pytest.fixture
def isolated_db():
    """A fresh database at 0105 holding two same-named universities in one country and a matching BDM University org."""
    cfg = _config()
    original = settings.database_url
    name = f"upc004_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        country = _sql(url, "SELECT id FROM countries WHERE iso2 = 'GB'")[0][0]
        for slug, uni_name in (("abc-university", "ABC University"), ("abc-university-2", "abc  university")):
            _sql(
                url,
                "INSERT INTO universities (id, country_id, slug, name, city, overview, eligibility, requirements, deadlines, scholarships) "
                "VALUES (gen_random_uuid(), :country, :slug, :name, 'London', '', '', '[]', '[]', '[]')",
                {"country": country, "slug": slug, "name": uni_name},
            )
        user = _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (gen_random_uuid(), :e, 'x', 'B', 'bdm', 'it', true, true, 'en-GB', '{}') RETURNING id",
            {"e": f"{name}@example.local"},
        )[0][0]
        _sql(
            url,
            "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id) "
            "VALUES (gen_random_uuid(), 'ORG-990001', 'university', 'college', 'ABC University', 'abc university', 'Pune', 'pune', :u, :u)",
            {"u": user},
        )
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_backfills_keys_reports_and_round_trips(isolated_db, capfd):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    capfd.readouterr()
    command.upgrade(cfg, HEAD)  # alembic.ini's logging config writes the report to stderr
    assert sorted(r[0] for r in _sql(url, "SELECT name_key FROM universities WHERE slug LIKE 'abc-university%'")) == ["abc university", "abc university"]
    report = capfd.readouterr().err
    assert "1 duplicate group" in report and "1 unlinked BDM University organization" in report
    assert _sql(url, "SELECT count(*) FROM bdm_organizations WHERE university_id IS NOT NULL")[0][0] == 0  # reported, never linked
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)


def test_link_check_holds_and_downgrade_refuses_while_linked(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    uni = _sql(url, "SELECT id FROM universities WHERE slug = 'abc-university'")[0][0]
    with pytest.raises(Exception, match=_migration.LINK_CHECK):
        _sql(url, "UPDATE bdm_organizations SET university_id = :u, org_type = 'college'", {"u": uni})
    _sql(url, "UPDATE bdm_organizations SET university_id = :u", {"u": uni})
    with pytest.raises(Exception, match="linked to the University Master"):
        command.downgrade(cfg, BASE)

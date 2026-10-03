"""bdm-003 -- migration 0068_bdm_org_profiles (spec §4). Round trip and the downgrade refusal run in a throwaway database (the
bdm-002 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
BASE = "0067_audit_entity_index"
HEAD = "0068_bdm_org_profiles"
NEW_COLUMNS = {"address", "country", "territory", "source", "staff_count", "board", "school_type", "grade_from", "grade_to", "affiliation", "college_type", "courses"}


def _migration():
    spec = importlib.util.spec_from_file_location("_bdm_003_migration_0068", VERSIONS / f"{HEAD}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _model_checks() -> dict[str, str]:
    from app.models import BdmOrganization

    return {c.name: str(c.sqltext) for c in BdmOrganization.__table__.constraints if isinstance(c, CheckConstraint)}


def test_model_has_the_profile_columns_and_checks():
    from app.models import BDM_PROFILE_CHECKS, BdmOrganization

    assert NEW_COLUMNS <= {c.name for c in BdmOrganization.__table__.columns}
    assert all(BdmOrganization.__table__.c[name].nullable for name in NEW_COLUMNS)
    assert set(BDM_PROFILE_CHECKS) == {
        "ck_bdm_organizations_source", "ck_bdm_organizations_staff_count", "ck_bdm_organizations_board", "ck_bdm_organizations_school_type",
        "ck_bdm_organizations_grades", "ck_bdm_organizations_college_type", "ck_bdm_organizations_agent_profile",
        "ck_bdm_organizations_school_profile", "ck_bdm_organizations_college_profile",
    }
    assert BDM_PROFILE_CHECKS.items() <= _model_checks().items()


def _sql(url: str, sql: str, params: dict | None = None, *, autocommit: bool = False):
    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text(sql), params or {})
                return result.fetchall() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def test_chains_after_0067_and_is_the_single_head():
    migration = _migration()
    assert (migration.revision, migration.down_revision) == (HEAD, BASE)
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_migration_checks_equal_the_model():
    from app.models import BDM_PROFILE_CHECKS, BdmOrganization

    migration = _migration()
    assert migration.CHECKS == BDM_PROFILE_CHECKS
    assert {name for name, _ in migration.COLUMNS} == NEW_COLUMNS
    for name, type_ in migration.COLUMNS:  # same SQL type and length as the model
        assert str(type_) == str(BdmOrganization.__table__.c[name].type), name


@pytest.mark.asyncio
async def test_columns_and_checks_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_columns("bdm_organizations")})
    checks = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_check_constraints("bdm_organizations")})
    assert NEW_COLUMNS <= columns
    assert set(_migration().CHECKS) <= checks


@pytest.fixture
def isolated_db():
    """A fresh database at 0067 with one bdm user."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"bdm003_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user_id = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": user_id, "email": f"bdm-{name}@example.local"},
        )
        yield {"cfg": cfg, "url": url, "user": user_id}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


INSERT = (
    "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id{extra_cols}) "
    "VALUES (:id, :code, :org_type, 'school', 'A', 'a', 'K', 'k', :u, :u{extra_vals})"
)


def _insert(db, org_type: str, **values):
    sql = INSERT.format(extra_cols="".join(f", {k}" for k in values), extra_vals="".join(f", :{k}" for k in values))
    _sql(db["url"], sql, {"id": uuid.uuid4(), "code": f"ORG-{uuid.uuid4().hex[:8]}", "org_type": org_type, "u": db["user"], **values})


def test_round_trip_runs_the_real_ddl_keeps_rows_and_enforces_every_check(isolated_db):
    """0001 builds BASE from the current models (columns already there), so go up, down to 0067 (the migration drops them), and up again:
    the CHECKs below are 0068's own DDL, not create_all's."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    cols = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'bdm_organizations'")}
    assert not (NEW_COLUMNS & cols)
    _sql(url, INSERT.format(extra_cols="", extra_vals=""), {"id": uuid.uuid4(), "code": "ORG-KEEP", "org_type": "college", "u": isolated_db["user"]})
    before = _sql(url, "SELECT id, code, org_type, name FROM bdm_organizations ORDER BY id")
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT id, code, org_type, name FROM bdm_organizations ORDER BY id") == before  # no row read or written
    bad = [
        ("school", {"board": "XX"}, "ck_bdm_organizations_board"),
        ("school", {"school_type": "charter"}, "ck_bdm_organizations_school_type"),
        ("school", {"grade_from": -3}, "ck_bdm_organizations_grades"),
        ("school", {"grade_to": 13}, "ck_bdm_organizations_grades"),
        ("school", {"grade_from": 8, "grade_to": 6}, "ck_bdm_organizations_grades"),
        ("agent", {"source": "tv"}, "ck_bdm_organizations_source"),
        ("agent", {"staff_count": -1}, "ck_bdm_organizations_staff_count"),
        ("agent", {"staff_count": 100_001}, "ck_bdm_organizations_staff_count"),
        ("college", {"college_type": "law"}, "ck_bdm_organizations_college_type"),
        ("college", {"board": "CBSE"}, "ck_bdm_organizations_school_profile"),
        ("school", {"country": "India"}, "ck_bdm_organizations_agent_profile"),
        ("agent", {"courses": "MBA"}, "ck_bdm_organizations_college_profile"),
    ]
    for org_type, values, check in bad:
        with pytest.raises(Exception, match=check):
            _insert(isolated_db, org_type, **values)
    _insert(isolated_db, "university", affiliation="VTU", college_type="engineering", courses="B.Tech CSE\nMBA")
    _insert(isolated_db, "school", board="CBSE", grade_from=-2, grade_to=12, address="1 Main Rd")


def test_downgrade_refuses_while_profile_values_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _insert(isolated_db, "agent", country="India")
    with pytest.raises(Exception, match="profile values exist"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE bdm_organizations SET country = NULL")
    command.downgrade(cfg, BASE)  # nothing entered any more: allowed

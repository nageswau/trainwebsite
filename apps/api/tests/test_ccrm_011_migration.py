"""ccrm-011 -- migration 0166_application_codes (DEC-SCOPE-238). Round trip and backfill order run in a throwaway database built from
scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from datetime import UTC, datetime

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_011_migration_0166", VERSIONS / "0166_application_codes.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0165_overseas_student_counselors", "0166_application_codes"
APPS = "SELECT id, intake, status FROM overseas_applications ORDER BY id"


def test_migration_chains_after_0165_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_model_matches_the_migration():
    from app.models import APPLICATION_CODE_DEFAULT, OverseasApplication

    column = OverseasApplication.__table__.c.application_code
    assert not column.nullable
    assert APPLICATION_CODE_DEFAULT == _migration.CODE_DEFAULT
    assert str(column.server_default.arg) == APPLICATION_CODE_DEFAULT


@pytest.mark.asyncio
async def test_column_and_unique_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns, uniques = await conn.run_sync(
        lambda sync: (
            {c["name"]: c for c in inspect(sync).get_columns("overseas_applications")},
            {u["name"] for u in inspect(sync).get_unique_constraints("overseas_applications")},
        )
    )
    assert not columns["application_code"]["nullable"]
    assert "uq_overseas_applications_code" in uniques


@pytest.fixture
def isolated_db():
    """A fresh database at 0165 holding two applications, the later-created one inserted first."""
    cfg = _config()
    original = settings.database_url
    name = f"ccrm011_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        country = _sql(url, "SELECT id FROM countries WHERE iso2 = 'GB'")[0][0]
        university = _sql(
            url,
            "INSERT INTO universities (id, country_id, slug, name, name_key, city, overview, eligibility, requirements, deadlines, scholarships) "
            "VALUES (gen_random_uuid(), :country, 'uni', 'Uni', 'uni', 'London', 'An overview', '', '[]', '[]', '[]') RETURNING id",
            {"country": country},
        )[0][0]
        for intake, created in (("Later", datetime(2026, 2, 1, tzinfo=UTC)), ("Earlier", datetime(2026, 1, 1, tzinfo=UTC))):
            _sql(
                url,
                "INSERT INTO overseas_applications (id, university_id, status, intake, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :u, 'enquiry', :intake, :created, :created)",
                {"u": university, "intake": intake, "created": created},
            )
        yield {"cfg": cfg, "url": url, "university": university}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_backfills_codes_in_created_order_and_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, APPS)
    command.upgrade(cfg, HEAD)
    rows = _sql(url, "SELECT intake, application_code FROM overseas_applications ORDER BY application_code")
    assert rows == [("Earlier", "APP-000001"), ("Later", "APP-000002")]
    new = _sql(
        url,
        "INSERT INTO overseas_applications (id, university_id, status, intake, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :u, 'enquiry', 'New', now(), now()) RETURNING application_code",
        {"u": isolated_db["university"]},
    )
    assert new == [("APP-000003",)]
    with pytest.raises(Exception, match="uq_overseas_applications_code"):
        _sql(url, "UPDATE overseas_applications SET application_code = 'APP-000001'")
    command.downgrade(cfg, BASE)
    assert {r[0] for r in _sql(url, APPS)} >= {r[0] for r in before}
    command.upgrade(cfg, HEAD)
    assert len({r[0] for r in _sql(url, "SELECT application_code FROM overseas_applications")}) == 3

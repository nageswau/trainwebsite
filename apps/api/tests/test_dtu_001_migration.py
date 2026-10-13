"""dtu-001 -- migration 0157_direct_tieups (spec §3). Round trip runs in a throwaway database (the upc-023 pattern)."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql
from tests.test_upc_008_migration import _university

_spec = importlib.util.spec_from_file_location("_dtu_001_migration_0157", VERSIONS / "0157_direct_tieups.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0156_marketing_budgets", "0157_direct_tieups"
UNI_COLUMNS = {"logo_url", "campuses", "fee_structure", "agent_commission_percent", "agent_commission_amount", "agent_commission_currency", "agent_commission_note"}
COURSE_COLUMNS = {"campus", "fee_text", "intake_text"}


def test_migration_chains_after_0156_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import UNIVERSITY_AGENT_COMMISSION_CHECKS, OverseasCourse, University

    assert UNIVERSITY_AGENT_COMMISSION_CHECKS == _migration.CHECKS
    assert UNI_COLUMNS == {name for name, _ in _migration.UNIVERSITY_COLUMNS}
    assert COURSE_COLUMNS == {name for name, _ in _migration.COURSE_COLUMNS}
    assert UNI_COLUMNS <= {c.name for c in University.__table__.columns}
    assert COURSE_COLUMNS <= {c.name for c in OverseasCourse.__table__.columns}
    by_name = {c.name: str(c.sqltext) for c in University.__table__.constraints if getattr(c, "sqltext", None) is not None}
    for name, sql in _migration.CHECKS.items():
        assert by_name[name] == sql


@pytest.mark.asyncio
async def test_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    uni, course, checks = await conn.run_sync(lambda s: (
        {c["name"] for c in inspect(s).get_columns("universities")},
        {c["name"] for c in inspect(s).get_columns("overseas_courses")},
        {c["name"] for c in inspect(s).get_check_constraints("universities")},
    ))
    assert UNI_COLUMNS <= uni and COURSE_COLUMNS <= course and set(_migration.CHECKS) <= checks


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"dtu001_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip(isolated_db):
    command.upgrade(isolated_db["cfg"], HEAD)
    rows = _sql(isolated_db["url"], "SELECT column_name FROM information_schema.columns WHERE table_name = 'universities'")
    assert UNI_COLUMNS <= {r[0] for r in rows}
    command.downgrade(isolated_db["cfg"], BASE)
    rows = _sql(isolated_db["url"], "SELECT column_name FROM information_schema.columns WHERE table_name = 'universities'")
    assert not (UNI_COLUMNS & {r[0] for r in rows})


def test_downgrade_refuses_while_an_agent_commission_exists(isolated_db):
    command.upgrade(isolated_db["cfg"], HEAD)
    uni = _university(isolated_db["url"])
    _sql(isolated_db["url"], "UPDATE universities SET agent_commission_percent = 10 WHERE id = :u", {"u": uni})
    with pytest.raises(RuntimeError, match="agent commissions exist"):
        command.downgrade(isolated_db["cfg"], BASE)


@pytest.mark.parametrize(
    "assignment",
    [
        "agent_commission_percent = 10, agent_commission_amount = 5, agent_commission_currency = 'USD'",
        "agent_commission_percent = 0",
        "agent_commission_percent = 101",
        "agent_commission_amount = 5",
        "agent_commission_amount = 5, agent_commission_currency = 'XXX'",
    ],
)
def test_check_constraints_reject_invalid_agent_commissions(isolated_db, assignment):
    url = isolated_db["url"]
    command.upgrade(isolated_db["cfg"], HEAD)
    uni = _university(url)
    with pytest.raises(Exception, match="ck_universities_agent_commission"):
        _sql(url, f"UPDATE universities SET {assignment} WHERE id = :u", {"u": uni})
    # valid shapes still pass
    _sql(url, "UPDATE universities SET agent_commission_amount = 5, agent_commission_currency = 'AED' WHERE id = :u", {"u": uni})

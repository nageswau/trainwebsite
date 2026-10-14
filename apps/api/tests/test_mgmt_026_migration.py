"""mgmt-026 -- migration 0159_management_plans (spec §5). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_mgmt_026_migration_0159", VERSIONS / "0159_management_plans.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0158_social_proof", "0159_management_plans"


def test_migration_chains_after_0158_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import PLAN_ITEM_CHECKS, PLAN_STATUSES, PLAN_VERTICALS, ManagementPlan, ManagementPlanItem

    assert PLAN_STATUSES == _migration.STATUSES == ("draft", "active", "closed")
    assert PLAN_VERTICALS == _migration.VERTICALS == ("abroad", "it", "school", "recruitment", "other")
    assert PLAN_ITEM_CHECKS == _migration.ITEM_CHECKS
    assert {c.name for c in ManagementPlan.__table__.columns} == {"id", "month", "status", "created_by_user_id", "updated_by_user_id", "created_at", "updated_at"}
    assert {c.name for c in ManagementPlanItem.__table__.columns} == {
        "id", "plan_id", "vertical", "text", "kpi", "target", "done", "position", "created_by_user_id", "updated_by_user_id", "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_tables_and_index_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables, indexes = await conn.run_sync(lambda sync: (set(inspect(sync).get_table_names()), {i["name"] for i in inspect(sync).get_indexes("management_plan_items")}))
    assert {"management_plans", "management_plan_items"} <= tables
    assert "ix_management_plan_items_plan_order" in indexes


@pytest.fixture
def isolated_db():
    """A fresh database at 0158."""
    cfg = _config()
    original = settings.database_url
    name = f"mgmt026_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_checks_hold_and_downgrade_refuses_while_plans_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'management_plans'")
    command.upgrade(cfg, HEAD)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 'p@example.local', 'x', 'P', 'partner', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    with pytest.raises(Exception, match="ck_management_plans_month"):
        _sql(url, "INSERT INTO management_plans (id, month, created_by_user_id, updated_by_user_id) VALUES (gen_random_uuid(), '2026-10-02', :p, :p)", {"p": user})
    plan = _sql(url, "INSERT INTO management_plans (id, month, created_by_user_id, updated_by_user_id) VALUES (gen_random_uuid(), '2026-10-01', :p, :p) RETURNING id, status", {"p": user})[0]
    assert plan[1] == "draft"
    insert = (
        "INSERT INTO management_plan_items (id, plan_id, vertical, text, kpi, target, done, position, created_by_user_id, updated_by_user_id) "
        "VALUES (gen_random_uuid(), :plan, 'abroad', 'Recruit 30 new agents', :kpi, :target, :done, 1, :p, :p)"
    )
    with pytest.raises(Exception, match="ck_management_plan_items_kpi_target"):
        _sql(url, insert, {"plan": plan[0], "p": user, "kpi": None, "target": 30, "done": False})
    with pytest.raises(Exception, match="ck_management_plan_items_done"):
        _sql(url, insert, {"plan": plan[0], "p": user, "kpi": "agents", "target": 30, "done": True})
    _sql(url, insert, {"plan": plan[0], "p": user, "kpi": "agents", "target": 30, "done": False})
    with pytest.raises(Exception, match="plans exist"):
        command.downgrade(cfg, BASE)

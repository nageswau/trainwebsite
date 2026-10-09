"""upc-021 -- migration 0131_partnership_targets (spec §3) and the §21 KPI catalogue (spec TG1). Round trip and the downgrade refusal run
in a throwaway database built from scratch (the upc-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from datetime import date

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_upc_021_migration_0131", VERSIONS / "0131_partnership_targets.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0130_university_meetings", "0131_partnership_targets"
SEPT = date(2026, 9, 1)


def test_migration_chains_after_0130_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_catalogue_is_the_source_list():
    """EVID-020 §21 (L703-L715): the 7 KPIs in source order (TG1)."""
    from app.partnership_target_kpis import KPI_KEYS, KPIS

    assert [k.label for k in KPIS] == [
        "New universities identified", "Contacted", "Meetings", "Proposals", "Negotiations", "MoUs", "New active universities",
    ]  # fmt: skip
    assert KPI_KEYS == ("new_universities", "contacted", "meetings", "proposals", "negotiations", "mous", "new_active")
    assert all(k.tracked for k in KPIS)  # T3 Meetings counts upc-009's completed meetings (TG13)


def test_model_matches_the_migration():
    from app.models import PARTNERSHIP_TARGET_CHECKS, PartnershipTarget

    assert PARTNERSHIP_TARGET_CHECKS == _migration.CHECKS
    assert {c.name for c in PartnershipTarget.__table__.columns} == {
        "id", "manager_user_id", "month", "kpi_key", "target", "set_by_user_id", "set_at", "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_table_and_unique_key_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables, uniques = await conn.run_sync(lambda sync: (set(inspect(sync).get_table_names()), {u["name"] for u in inspect(sync).get_unique_constraints("partnership_targets")}))
    assert "partnership_targets" in tables and "uq_partnership_targets_manager_month_kpi" in uniques


@pytest.fixture
def isolated_db():
    """A fresh database at 0130."""
    cfg = _config()
    original = settings.database_url
    name = f"upc021_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_and_downgrade_refuses_while_targets_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'partnership_targets'")
    command.upgrade(cfg, HEAD)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 't@example.local', 'x', 'T', 'partnership_head', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    insert = "INSERT INTO partnership_targets (id, manager_user_id, month, kpi_key, target, set_by_user_id) VALUES (gen_random_uuid(), :u, :m, :k, :t, :u)"
    with pytest.raises(Exception, match="ck_partnership_targets_kpi"):
        _sql(url, insert, {"u": user, "m": SEPT, "k": "revenue", "t": 5})
    with pytest.raises(Exception, match="ck_partnership_targets_month_start"):
        _sql(url, insert, {"u": user, "m": date(2026, 9, 2), "k": "mous", "t": 5})
    with pytest.raises(Exception, match="ck_partnership_targets_target_range"):
        _sql(url, insert, {"u": user, "m": SEPT, "k": "mous", "t": 100001})
    _sql(url, insert, {"u": user, "m": SEPT, "k": "mous", "t": 5})
    with pytest.raises(Exception, match="uq_partnership_targets_manager_month_kpi"):
        _sql(url, insert, {"u": user, "m": SEPT, "k": "mous", "t": 6})
    with pytest.raises(Exception, match="targets exist"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM partnership_targets")
    command.downgrade(cfg, BASE)

"""mgmt-011 -- migration 0154_salaries (spec §3; re-chained after mgmt-028). The chain, the model/migration match and the shared
database's state; the round trip runs in a throwaway database built from scratch (the upc-001 pattern). Plain tests: alembic/env.py calls
asyncio.run()."""

import importlib.util
import uuid
from datetime import date

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_mgmt_011_migration_0154", VERSIONS / "0154_salaries.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0153_management_tasks", "0154_salaries"


def test_migration_chains_after_0153_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import SALARY_CHECKS, Department, SalaryMonthTotal

    assert SALARY_CHECKS == _migration.CHECKS
    assert {c.name for c in Department.__table__.columns} == {"id", "name", "active", "created_by_user_id", "updated_by_user_id", "created_at", "updated_at"}
    assert {c.name for c in SalaryMonthTotal.__table__.columns} == {
        "id", "month", "department_id", "headcount", "payable", "paid", "incentives", "commissions", "employer_cost",
        "created_by_user_id", "updated_by_user_id", "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_tables_seed_and_salaries_category_in_the_shared_database(db_session):
    from app.models import Department, LedgerCategory

    conn = await db_session.connection()
    tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    assert {"departments", "salary_month_totals"} <= tables
    names = set((await db_session.scalars(select(Department.name))).all())
    assert set(_migration.SEED) <= names
    active = await db_session.scalar(select(LedgerCategory.active).where(LedgerCategory.kind == "expense", LedgerCategory.name == "Salaries"))
    assert active is False  # SM9: salary cost reaches the ledger only through the salary page


SALARIES = "SELECT active FROM ledger_categories WHERE kind = 'expense' AND name = 'Salaries'"


@pytest.fixture
def isolated_db():
    """A fresh database at 0153."""
    cfg = _config()
    original = settings.database_url
    name = f"mgmt011_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_seeds_and_downgrade_reactivates_then_refuses_with_salary_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, SALARIES)[0][0] is True
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'departments'")
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT count(*) FROM departments")[0][0] == len(_migration.SEED)
    assert _sql(url, SALARIES)[0][0] is False
    command.downgrade(cfg, BASE)
    assert _sql(url, SALARIES)[0][0] is True
    command.upgrade(cfg, HEAD)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 'a@example.local', 'x', 'A', 'accountant', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    department = _sql(url, "SELECT id FROM departments ORDER BY name LIMIT 1")[0][0]
    insert = (
        "INSERT INTO salary_month_totals (id, month, department_id, headcount, payable, paid, incentives, commissions, employer_cost, "
        "created_by_user_id, updated_by_user_id) VALUES (gen_random_uuid(), :month, :d, 3, 10, :paid, 0, 0, 0, :u, :u)"
    )
    with pytest.raises(Exception, match="ck_salary_month_totals_money"):
        _sql(url, insert, {"month": date(2026, 1, 1), "d": department, "paid": -1, "u": user})
    with pytest.raises(Exception, match="ck_salary_month_totals_month"):
        _sql(url, insert, {"month": date(2026, 1, 2), "d": department, "paid": 1, "u": user})
    _sql(url, insert, {"month": date(2026, 1, 1), "d": department, "paid": 1, "u": user})
    with pytest.raises(Exception, match="salary rows exist"):
        command.downgrade(cfg, BASE)

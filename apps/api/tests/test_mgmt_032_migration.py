"""mgmt-032 -- migration 0163_monthly_reviews (spec MR2). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from datetime import UTC, date, datetime

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_mgmt_032_migration_0163", VERSIONS / "0163_monthly_reviews.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0162_school_values", "0163_monthly_reviews"


def test_migration_chains_after_0162_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import REVIEW_CHECKS, MonthlyReview

    assert REVIEW_CHECKS == _migration.CHECKS
    assert {c.name for c in MonthlyReview.__table__.columns} == {
        "id", "month", "status", "snapshot", "narrative", "generated_at", "finalised_at", "finalised_by_user_id", "updated_by_user_id",
        "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    conn = await db_session.connection()
    assert "monthly_reviews" in await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))


@pytest.fixture
def isolated_db():
    """A fresh database at 0162_school_values."""
    cfg = _config()
    original = settings.database_url
    name = f"mgmt032_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_checks_hold_and_downgrade_refuses_while_a_final_review_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'monthly_reviews'")
    command.upgrade(cfg, HEAD)
    insert = "INSERT INTO monthly_reviews (id, month, status, snapshot, finalised_at) VALUES (gen_random_uuid(), :month, :status, '{}', :at)"
    with pytest.raises(Exception, match="ck_monthly_reviews_month"):
        _sql(url, insert, {"month": date(2026, 9, 2), "status": "draft", "at": None})
    with pytest.raises(Exception, match="ck_monthly_reviews_status"):
        _sql(url, insert, {"month": date(2026, 9, 1), "status": "done", "at": None})
    with pytest.raises(Exception, match="ck_monthly_reviews_final"):
        _sql(url, insert, {"month": date(2026, 9, 1), "status": "final", "at": None})
    _sql(url, insert, {"month": date(2026, 9, 1), "status": "draft", "at": None})
    assert _sql(url, "SELECT narrative::text FROM monthly_reviews")[0][0] == "{}"
    command.downgrade(cfg, BASE)  # drafts only: they are regenerated from the ledger, so dropping them loses nothing
    command.upgrade(cfg, HEAD)
    _sql(url, insert, {"month": date(2026, 9, 1), "status": "final", "at": datetime(2026, 10, 2, 4, 30, tzinfo=UTC)})
    with pytest.raises(Exception, match="final reviews exist"):
        command.downgrade(cfg, BASE)

"""bdm-015 -- migration 0092_bdm_daily_reports (spec §4). The round trip and the downgrade refusal run in a throwaway database (the
bdm-009 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_bdm_015_migration_0092", VERSIONS / "0092_bdm_daily_reports.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0091_lead_appointments", "0092_bdm_daily_reports"
TABLE = "bdm_daily_reports"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0091_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import BDM_DAILY_REPORT_CHECKS, BdmDailyReport

    table = BdmDailyReport.__table__
    assert {c.name for c in table.columns} == {
        "id",
        "bdm_user_id",
        "report_date",
        "bdm_type",
        "counts",
        "note",
        "submitted_at",
        "manager_comment",
        "manager_comment_by_user_id",
        "manager_commented_at",
        "created_at",
        "updated_at",
    }
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"uq_bdm_daily_reports_bdm_date", *BDM_DAILY_REPORT_CHECKS} <= names
    assert _migration.CHECKS == BDM_DAILY_REPORT_CHECKS  # the migration's frozen copy stays identical
    fks = {fk.parent.name: fk.ondelete for fk in table.foreign_keys}
    assert fks == {"bdm_user_id": "RESTRICT", "manager_comment_by_user_id": "RESTRICT"}


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    rows = (await db_session.execute(sa.text(f"SELECT relname FROM pg_class WHERE relname = '{TABLE}'"))).all()
    assert rows == [(TABLE,)]


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


@pytest.fixture
def isolated_db():
    """A fresh database at 0091 with one BDM user."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm015_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        owner = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Owner', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": owner, "email": f"owner-{name}@example.local"},
        )
        yield {"cfg": cfg, "url": url, "owner": owner}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


REPORT = (
    f"INSERT INTO {TABLE} (id, bdm_user_id, report_date, bdm_type, counts, manager_comment, manager_comment_by_user_id, "
    "manager_commented_at) VALUES (:id, :owner, :day, :bdm_type, '[]', :comment, :by, :at)"
)


def _report(db, **over) -> dict:
    params = {"id": uuid.uuid4(), "owner": db["owner"], "day": date(2026, 10, 1), "bdm_type": "college", "comment": None, "by": None, "at": None}
    params.update(over)
    return params


def test_round_trip_and_downgrade_refuses_while_reports_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, f"SELECT count(*) FROM pg_class WHERE relname = '{TABLE}'")[0][0] == 0
    command.upgrade(cfg, HEAD)
    for over, constraint in (
        ({"bdm_type": "corporate"}, "ck_bdm_daily_reports_bdm_type"),
        ({"comment": "Good day"}, "ck_bdm_daily_reports_comment"),
    ):
        with pytest.raises(Exception, match=constraint):
            _sql(url, REPORT, _report(isolated_db, **over))
    _sql(url, REPORT, _report(isolated_db))
    with pytest.raises(Exception, match="uq_bdm_daily_reports_bdm_date"):
        _sql(url, REPORT, _report(isolated_db))
    with pytest.raises(RuntimeError, match="daily reports exist"):
        command.downgrade(cfg, BASE)

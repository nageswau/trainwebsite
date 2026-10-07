"""tel-009 -- migration 0089_lead_qualifications (spec §2). The round trip runs in a throwaway database (the tel-004 pattern); a downgrade
never runs against the shared test database. 0001 builds a fresh database from the current models, so each test first downgrades to
0088_bdm_appointment_trip to reach the real pre-tel-009 shape."""

import asyncio
import importlib.util
import uuid
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
_spec = importlib.util.spec_from_file_location("_tel_009_migration_0089", VERSIONS / "0089_lead_qualifications.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0088_bdm_appointment_trip", "0089_lead_qualifications"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


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


def test_migration_chains_after_0088_bdm_appointment_trip_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import LeadQualification

    table = LeadQualification.__table__
    assert {c.name for c in table.columns} == {
        "lead_id", "current_org", "work_experience_years", "it_skill_level", "career_objective", "preferred_batch", "budget_range",
        "preferred_mode", "study_level", "preferred_course", "intake", "academic_percentage", "english_test_status", "passport_status",
        "updated_by_user_id", "created_at", "updated_at",
    }
    assert [c.name for c in table.primary_key] == ["lead_id"] and not table.c.updated_by_user_id.nullable
    fks = {fk.parent.name: (fk.column.table.name, fk.ondelete) for fk in table.foreign_keys}
    assert fks == {"lead_id": ("enquiries", "CASCADE"), "updated_by_user_id": ("users", "RESTRICT")}
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks == _migration.CHECKS


@pytest.fixture
def base_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel009_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


LEAD = ("INSERT INTO enquiries (id, division, name, email, subject, message, source, status, crm_sync_status, metadata_json) "
        "VALUES (:id, 'it', 'Asha', 'asha@example.local', 'Python', '', 'walk_in', 'new', 'pending', '{}')")
USER = ("INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'Tel', 'telecaller', 'it', true, true, 'en-GB', '{}')")
QUAL = ("INSERT INTO lead_qualifications (lead_id, updated_by_user_id, academic_percentage) "
        "SELECT e.id, u.id, :pct FROM enquiries e, users u")


def test_upgrade_adds_the_table_with_its_checks_and_downgrade_drops_it(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    assert _sql(url, "SELECT to_regclass('lead_qualifications')") == [(None,)]
    command.upgrade(cfg, HEAD)
    _sql(url, LEAD, {"id": uuid.uuid4()})
    _sql(url, USER, {"id": uuid.uuid4(), "email": f"{uuid.uuid4().hex[:8]}@example.local"})
    with pytest.raises(Exception, match="ck_lead_qualifications_percentage"):
        _sql(url, QUAL, {"pct": 120})
    _sql(url, QUAL, {"pct": 72.5})
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('lead_qualifications')") == [(None,)]
    assert _sql(url, "SELECT count(*) FROM enquiries") == [(1,)]  # the leads themselves are untouched

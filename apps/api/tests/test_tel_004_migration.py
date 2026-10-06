"""tel-004 -- migration 0080_lead_stage_pipeline (spec §3; PL1, AC7). The legacy mapping, the CHECK, the round trip and the downgrade
refusal run in a throwaway database (the tel-003 pattern); a downgrade never runs against the shared test database.

0001 builds a fresh database from the current models, which already carry the table and the CHECK, so each test first downgrades to
0079_bdm_mous to reach the real pre-tel-004 shape, inserts legacy rows there, and then runs the real upgrade."""

import asyncio
import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
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
_spec = importlib.util.spec_from_file_location("_tel_004_migration_0080", VERSIONS / "0080_lead_stage_pipeline.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0079_bdm_mous", "0080_lead_stage_pipeline"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0079_bdm_mous_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.lead_stages import STAGES
    from app.models import LEAD_STATUS_CHECK, Enquiry, LeadStageHistory

    assert _migration.STAGES == STAGES  # the frozen copy still equals the live catalogue
    assert LEAD_STATUS_CHECK == _migration.STATUS_CHECK
    checks = {c.name: str(c.sqltext) for c in Enquiry.__table__.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks["ck_enquiries_status"] == _migration.STATUS_CHECK
    table = LeadStageHistory.__table__
    assert {"id", "lead_id", "from_stage", "to_stage", "event", "actor_user_id", "reason", "position", "created_at"} == {c.name for c in table.columns}
    assert table.c.actor_user_id.nullable and table.c.reason.nullable and not table.c.event.nullable
    fks = {fk.parent.name: (fk.column.table.name, fk.ondelete) for fk in table.foreign_keys}
    assert fks == {"lead_id": ("enquiries", "RESTRICT"), "actor_user_id": ("users", "RESTRICT")}
    assert "ix_lead_stage_history_lead" in {i.name for i in table.indexes}


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


STUDENT = ("INSERT INTO users (id, email, full_name, password_hash, role, division, active, email_verified, locale, profile, created_at, "
           "updated_at) VALUES (:id, :email, 'Stu Dent', 'x', 'it_student', 'it', true, true, 'en-GB', '{}', now(), now())")
LEGACY = (
    "INSERT INTO enquiries (id, division, name, email, subject, message, source, status, crm_sync_status, metadata_json, created_at, "
    "converted_user_id, converted_at, converted_by_user_id) VALUES (:id, 'it', :name, 'web@example.local', 'Python', 'Hi', 'website', "
    ":status, 'pending', CAST(:meta AS json), :at, :linked, CASE WHEN CAST(:linked AS uuid) IS NULL THEN NULL ELSE now() END, :linked)"
)
# (name, legacy status, linked to a student?) -> the PL1 stage
ROWS = (
    ("Fresh", "new", False, "new"),
    ("Called", "contacted", False, "contacted"),
    ("Good", "qualified", False, "qualified"),
    ("Gone", "lost", False, "lost"),
    ("Linked", "converted", True, "application_enrollment"),
    ("Unlinked", "converted", False, "follow_up"),
    ("Odd", "Call back Monday", False, "new"),
)


@pytest.fixture
def legacy_db():
    """A fresh database at 0079_bdm_mous (the real pre-tel-004 shape) holding one enquiry per legacy status."""
    cfg = _config()
    original = settings.database_url
    name = f"tel004_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)
        command.downgrade(cfg, BASE)  # 0001's create_all already built the table and the CHECK; drop them to reach the legacy shape
        for i, (row_name, status, linked, _) in enumerate(ROWS):
            student = None
            if linked:
                student = uuid.uuid4()
                _sql(url, STUDENT, {"id": student, "email": f"stu-{student.hex[:8]}@example.local"})
            _sql(url, LEGACY, {"id": uuid.uuid4(), "name": row_name, "status": status, "meta": '{"utm": "x"}',
                               "at": datetime.now(UTC) - timedelta(days=10 - i), "linked": student})
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_downgrade_to_0079_leaves_the_legacy_shape(legacy_db):
    url = legacy_db["url"]
    assert _sql(url, "SELECT to_regclass('lead_stage_history')") == [(None,)]
    assert _sql(url, "SELECT count(*) FROM pg_constraint WHERE conname = 'ck_enquiries_status'") == [(0,)]


def test_upgrade_maps_legacy_statuses_by_meaning_with_history(legacy_db):
    cfg, url = legacy_db["cfg"], legacy_db["url"]
    command.upgrade(cfg, HEAD)
    rows = _sql(url, "SELECT name, status, metadata_json FROM enquiries ORDER BY created_at")
    assert [(n, s) for n, s, _ in rows] == [(n, stage) for n, _, _, stage in ROWS]
    meta = {n: m for n, _, m in rows}
    assert meta["Fresh"] == {"utm": "x"}  # unchanged rows keep their metadata as it was
    assert meta["Linked"] == {"utm": "x", "legacy_status": "converted"}
    assert meta["Odd"] == {"utm": "x", "legacy_status": "Call back Monday"}
    history = _sql(url, "SELECT e.name, h.from_stage, h.to_stage, h.event, h.actor_user_id, h.reason FROM lead_stage_history h "
                        "JOIN enquiries e ON e.id = h.lead_id ORDER BY e.created_at")
    assert history == [
        ("Linked", "converted", "application_enrollment", "legacy_mapping", None, None),
        ("Unlinked", "converted", "follow_up", "legacy_mapping", None, None),
        ("Odd", "Call back Monday", "new", "legacy_mapping", None, None),
    ]


def test_status_check_holds_after_upgrade(legacy_db):
    cfg, url = legacy_db["cfg"], legacy_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="ck_enquiries_status"):
        _sql(url, "UPDATE enquiries SET status = 'Call back Monday'")


def test_clean_downgrade_restores_the_legacy_status(legacy_db):
    cfg, url = legacy_db["cfg"], legacy_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    rows = _sql(url, "SELECT name, status, metadata_json FROM enquiries ORDER BY created_at")
    assert [(n, s) for n, s, _ in rows] == [(n, status) for n, status, _, _ in ROWS]
    assert all(m == {"utm": "x"} for _, _, m in rows)
    assert _sql(url, "SELECT to_regclass('lead_stage_history')") == [(None,)]


def test_downgrade_refuses_after_a_real_stage_change(legacy_db):
    cfg, url = legacy_db["cfg"], legacy_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, "INSERT INTO lead_stage_history (id, lead_id, from_stage, to_stage, event) "
              "SELECT :id, id, 'new', 'qualified', 'manual' FROM enquiries WHERE name = 'Fresh'", {"id": uuid.uuid4()})
    with pytest.raises(RuntimeError, match="stage history exists"):
        command.downgrade(cfg, BASE)


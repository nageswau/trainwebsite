"""bdm-007 -- migration 0072_bdm_meeting_reports (spec §4). Isolated database per test (the bdm-006 pattern)."""

import asyncio
import importlib.util
import uuid
from datetime import UTC, date, datetime
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
_spec = importlib.util.spec_from_file_location("_bdm_007_migration_0072", VERSIONS / "0072_bdm_meeting_reports.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0071_bdm_activities"
HEAD = "0072_bdm_meeting_reports"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0071_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())  # bdm-017's 0073 follows; 0072 stays on the single chain
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_models_match_the_migration():
    from app.models import BDM_TASK_KINDS, BDM_TASK_SOURCES, BDM_TASK_STATUSES, BdmMeetingReport, BdmTask

    report = BdmMeetingReport.__table__
    assert {c.name for c in report.columns} == {
        "id", "appointment_id", "author_user_id", "discussion", "requirements", "opportunity", "next_action", "responsible_person",
        "legacy", "submitted_at", "created_at", "updated_at",
    }
    names = {c.name for c in report.constraints}
    assert {"uq_bdm_meeting_reports_appointment", "ck_bdm_meeting_reports_discussion"} <= names
    task = BdmTask.__table__
    assert {c.name for c in task.columns} == {
        "id", "kind", "title", "due_on", "organization_id", "source", "source_appointment_id", "assignee_user_id", "status",
        "completed_at", "created_at", "updated_at",
    }
    names = {i.name for i in task.indexes} | {c.name for c in task.constraints}
    assert {
        "uq_bdm_tasks_source_appointment", "ck_bdm_tasks_kind", "ck_bdm_tasks_source", "ck_bdm_tasks_status", "ck_bdm_tasks_source_link",
        "ck_bdm_tasks_completed", "ix_bdm_tasks_assignee_status_due",
    } <= names
    assert (_migration.TASK_KINDS, _migration.TASK_SOURCES, _migration.TASK_STATUSES) == (BDM_TASK_KINDS, BDM_TASK_SOURCES, BDM_TASK_STATUSES)


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


APPT = (
    "INSERT INTO bdm_appointments (id, code, bdm_user_id, organization_id, contact_name, starts_at, appointment_type, status, outcome, "
    "next_follow_up_on) VALUES (:id, :code, :u, :org, 'C', now() - interval '2 days', 'college_meeting', :status, :outcome, :follow)"
)


@pytest.fixture
def isolated_db():
    """A fresh database at 0071 whose 0072 tables were dropped (0001's create_all builds them from the models), holding one BDM,
    one organization and three appointments: completed with a follow-up date, completed without, and scheduled."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm007_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        _sql(url, "DROP TABLE IF EXISTS bdm_tasks, bdm_meeting_reports")
        user, org = uuid.uuid4(), uuid.uuid4()
        _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')", {"id": user, "email": f"bdm-{name}@example.local"})
        _sql(url, "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id) VALUES (:id, 'ORG-9', 'college', 'college', 'A', 'a', 'K', 'k', :u, :u)", {"id": org, "u": user})
        appts = {"followed": uuid.uuid4(), "plain": uuid.uuid4(), "open": uuid.uuid4()}
        base = {"u": user, "org": org}
        _sql(url, APPT, {**base, "id": appts["followed"], "code": "APT-1", "status": "completed", "outcome": "interested", "follow": date(2026, 9, 22)})
        _sql(url, APPT, {**base, "id": appts["plain"], "code": "APT-2", "status": "completed", "outcome": "other", "follow": None})
        _sql(url, APPT, {**base, "id": appts["open"], "code": "APT-3", "status": "scheduled", "outcome": None, "follow": None})
        _sql(url, "INSERT INTO bdm_appointment_events (id, appointment_id, actor_user_id, from_status, to_status, created_at) VALUES (:id, :a, :u, 'scheduled', 'completed', :at)", {"id": uuid.uuid4(), "a": appts["followed"], "u": user, "at": datetime(2026, 9, 20, 10, tzinfo=UTC)})
        yield {"cfg": cfg, "url": url, "user": user, "org": org, "appts": appts}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_backfills_one_legacy_report_per_completed_appointment(isolated_db):
    url, appts = isolated_db["url"], isolated_db["appts"]
    command.upgrade(isolated_db["cfg"], HEAD)
    rows = _sql(url, "SELECT appointment_id, legacy, discussion, author_user_id, submitted_at FROM bdm_meeting_reports ORDER BY submitted_at")
    assert {r[0] for r in rows} == {appts["followed"], appts["plain"]}  # AC1: every completed appointment, nothing else
    assert all(r[1] is True and r[2] is None and r[3] == isolated_db["user"] for r in rows)
    followed = next(r for r in rows if r[0] == appts["followed"])
    assert followed[4].isoformat().startswith("2026-09-20T10:00")  # the completion event's time
    tasks = _sql(url, "SELECT source_appointment_id, kind, source, status, due_on::text, title, organization_id FROM bdm_tasks")
    assert tasks == [(appts["followed"], "follow_up", "appointment_outcome", "open", "2026-09-22", "Follow up on APT-1", isolated_db["org"])]


def test_backfill_is_idempotent_and_the_round_trip_keeps_appointments(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, "SELECT id, status, outcome, next_follow_up_on FROM bdm_appointments ORDER BY id")
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)  # only legacy rows: allowed
    assert _sql(url, "SELECT id, status, outcome, next_follow_up_on FROM bdm_appointments ORDER BY id") == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT count(*) FROM bdm_meeting_reports") == [(2,)]
    assert _sql(url, "SELECT count(*) FROM bdm_tasks") == [(1,)]


def test_constraints_hold_and_downgrade_refuses_while_reports_exist(isolated_db):
    cfg, url, appts, user = isolated_db["cfg"], isolated_db["url"], isolated_db["appts"], isolated_db["user"]
    command.upgrade(cfg, HEAD)
    report = "INSERT INTO bdm_meeting_reports (id, appointment_id, author_user_id, discussion, legacy) VALUES (:id, :a, :u, :d, :legacy)"
    with pytest.raises(Exception, match="uq_bdm_meeting_reports_appointment"):
        _sql(url, report, {"id": uuid.uuid4(), "a": appts["plain"], "u": user, "d": "x", "legacy": False})
    with pytest.raises(Exception, match="ck_bdm_meeting_reports_discussion"):
        _sql(url, report, {"id": uuid.uuid4(), "a": appts["open"], "u": user, "d": None, "legacy": False})
    task = (
        "INSERT INTO bdm_tasks (id, kind, title, due_on, source, source_appointment_id, assignee_user_id, status) "
        "VALUES (:id, 'follow_up', 'T', '2030-01-01', :source, :a, :u, 'open')"
    )
    with pytest.raises(Exception, match="uq_bdm_tasks_source_appointment"):
        _sql(url, task, {"id": uuid.uuid4(), "source": "appointment_outcome", "a": appts["followed"], "u": user})
    with pytest.raises(Exception, match="ck_bdm_tasks_source_link"):
        _sql(url, task, {"id": uuid.uuid4(), "source": "manual", "a": appts["plain"], "u": user})
    _sql(url, report, {"id": uuid.uuid4(), "a": appts["open"], "u": user, "d": "Filed", "legacy": False})
    with pytest.raises(Exception, match="meeting reports exist"):
        command.downgrade(cfg, BASE)

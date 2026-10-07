"""tel-016 -- migration 0091_lead_appointments (spec §2). The round trip runs in a throwaway database (the tel-004 pattern); a downgrade
never runs against the shared test database. 0001 builds a fresh database from the current models, so each test first downgrades to
0090_lead_follow_ups to reach the real pre-tel-016 shape."""

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
_spec = importlib.util.spec_from_file_location("_tel_016_migration_0091", VERSIONS / "0091_lead_appointments.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0090_lead_follow_ups", "0091_lead_appointments"


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


def test_migration_chains_after_0090_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import LEAD_APPOINTMENT_OPEN, Appointment, AppointmentEvent

    table = Appointment.__table__
    assert {"lead_id", "appointment_code", "purpose", "meeting_link", "location", "remarks", "booked_by_user_id", "duration_minutes"} <= {
        c.name for c in table.columns}
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks == _migration.CHECKS
    assert {i.name for i in table.indexes} >= {"ix_appointments_staff_scheduled", "ix_appointments_lead", "uq_appointments_lead_open"}
    assert tuple(_migration.OPEN) == LEAD_APPOINTMENT_OPEN
    assert {c.name for c in AppointmentEvent.__table__.columns} == {
        "id", "appointment_id", "actor_user_id", "from_status", "to_status", "old_scheduled_at", "new_scheduled_at", "reason", "position",
        "created_at",
    }


def test_the_released_event_returns_a_scheduled_lead_to_follow_up():
    from app.lead_stages import EVENTS

    assert EVENTS["appointment_released"] == (frozenset({"counselling_scheduled"}), "follow_up")


@pytest.fixture
def base_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel016_migration_{uuid.uuid4().hex[:8]}"
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


USER = ("INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'U', :role, 'overseas', true, true, 'en-GB', '{}')")
LEAD = ("INSERT INTO enquiries (id, division, name, email, subject, message, source, status, crm_sync_status, metadata_json) "
        "VALUES (:id, 'overseas', 'Asha', 'asha@example.local', 'UK', '', 'walk_in', 'new', 'pending', '{}')")
STUDENT_APPT = ("INSERT INTO appointments (id, division, student_id, staff_id, scheduled_at, appointment_type, mode, status) "
                "VALUES (:id, 'overseas', :student, :staff, now(), 'Career Counseling', 'Online', 'Done-ish')")
LEAD_APPT = ("INSERT INTO appointments (id, division, lead_id, staff_id, scheduled_at, appointment_type, mode, status, appointment_code) "
             "VALUES (:id, 'overseas', :lead, :staff, now(), 'overseas_counselling', 'Online', :status, :code)")


def _user(url, role):
    uid = uuid.uuid4()
    _sql(url, USER, {"id": uid, "email": f"{uuid.uuid4().hex[:8]}@example.local", "role": role})
    return uid


def test_upgrade_keeps_legacy_rows_and_adds_the_lead_link(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    student, staff, lead = _user(url, "overseas_student"), _user(url, "counselor"), uuid.uuid4()
    _sql(url, LEAD, {"id": lead})
    legacy = uuid.uuid4()
    _sql(url, STUDENT_APPT, {"id": legacy, "student": student, "staff": staff})
    command.upgrade(cfg, HEAD)
    # the legacy row keeps its free-text status and gets the 60-minute default; no code
    assert _sql(url, "SELECT status, duration_minutes, appointment_code, lead_id FROM appointments WHERE id = :id", {"id": legacy}) == [
        ("Done-ish", 60, None, None)]
    # neither a student nor a lead -> refused
    with pytest.raises(Exception, match="ck_appointments_subject"):
        _sql(url, "INSERT INTO appointments (id, division, scheduled_at, appointment_type, mode, status) "
                  "VALUES (:id, 'it', now(), 'x', 'Online', 'scheduled')", {"id": uuid.uuid4()})
    _sql(url, LEAD_APPT, {"id": uuid.uuid4(), "lead": lead, "staff": staff, "status": "scheduled", "code": "CAP-000001"})
    # one open appointment per lead
    with pytest.raises(Exception, match="uq_appointments_lead_open"):
        _sql(url, LEAD_APPT, {"id": uuid.uuid4(), "lead": lead, "staff": staff, "status": "confirmed", "code": "CAP-000002"})
    _sql(url, LEAD_APPT, {"id": uuid.uuid4(), "lead": lead, "staff": staff, "status": "cancelled", "code": "CAP-000003"})
    assert _sql(url, "SELECT nextval('appointment_code_seq') > 0") == [(True,)]
    # a downgrade never orphans lead bookings
    with pytest.raises(Exception, match="lead appointments"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM appointments WHERE lead_id IS NOT NULL")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('appointment_events')") == [(None,)]
    assert _sql(url, "SELECT count(*) FROM appointments") == [(1,)]

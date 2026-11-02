"""itc-020 -- migration 0228_batch_timetable (DEC-SCOPE-344): the slot and cancellation tables. Round trip in a throwaway database built
from scratch (the upc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import BatchTimetableCancellation, BatchTimetableSlot
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_020_migration_0228", VERSIONS / "0228_batch_timetable.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0228_batch_timetable"
BASE = "0227_lead_counseling_records"
TABLES = "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'batch_timetable%' ORDER BY 1"
CHECKS = "SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_batch_timetable_slots_%' ORDER BY 1"


def test_migration_chains_after_0227_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    assert {c.name for c in BatchTimetableSlot.__table__.constraints if c.name and c.name.startswith("ck_")} == {
        "ck_batch_timetable_slots_weekday",
        "ck_batch_timetable_slots_times",
        "ck_batch_timetable_slots_mode",
        "ck_batch_timetable_slots_room",
    }
    assert "uq_batch_timetable_cancellations_slot_day" in {c.name for c in BatchTimetableCancellation.__table__.constraints}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc020_migration_{uuid.uuid4().hex[:8]}"
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


def _slot_sql(batch: str, mode: str = "online", room: str = "NULL", start: str = "19:00", end: str = "21:00") -> str:
    return f"INSERT INTO batch_timetable_slots (id, batch_id, weekday, start_time, end_time, mode, room) VALUES ('{uuid.uuid4()}', '{batch}', 0, '{start}', '{end}', '{mode}', {room})"


def test_round_trip_creates_the_tables_and_checks_and_refuses_to_drop_a_timetable(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, TABLES) == []
    command.upgrade(cfg, HEAD)
    assert [r[0] for r in _sql(url, TABLES)] == ["batch_timetable_cancellations", "batch_timetable_slots"]
    assert len(_sql(url, CHECKS)) == 4
    command.downgrade(cfg, BASE)  # empty: drops cleanly
    assert _sql(url, TABLES) == []
    command.upgrade(cfg, HEAD)
    program, batch = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        f"INSERT INTO programs (id, slug, category, title, summary, duration, eligibility, fees, certification, curriculum, placement_assistance, trainer_name, active, syllabus_modules, created_at, updated_at) "
        f"VALUES ('{program}', 'm-{program.hex[:6]}', 'c', 't', '', '', '', 1, '', '[]', '', '', true, '[]', now(), now())",
        autocommit=True,
    )
    _sql(
        url,
        f"INSERT INTO batches (id, program_id, name, start_date, end_date, schedule, timezone, capacity, enrollment_open, mode, status, created_at, updated_at) "
        f"VALUES ('{batch}', '{program}', 'b-{batch.hex[:6]}', '2026-12-01', '2027-01-31', '', 'Asia/Kolkata', 20, true, 'Online', 'upcoming', now(), now())",
        autocommit=True,
    )
    with pytest.raises(Exception, match="ck_batch_timetable_slots_room"):
        _sql(url, _slot_sql(batch, mode="offline"), autocommit=True)
    with pytest.raises(Exception, match="ck_batch_timetable_slots_times"):
        _sql(url, _slot_sql(batch, start="21:00", end="19:00"), autocommit=True)
    _sql(url, _slot_sql(batch, mode="offline", room="'Lab 2'"), autocommit=True)
    with pytest.raises(RuntimeError, match="batch timetables exist"):
        command.downgrade(cfg, BASE)

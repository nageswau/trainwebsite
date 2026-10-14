"""mgmt-029 -- migration 0161_management_meetings (spec §3). Round trip and the downgrade refusal run in a throwaway database built from
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

_spec = importlib.util.spec_from_file_location("_mgmt_029_migration_0161", VERSIONS / "0161_management_meetings.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0160_management_plans", "0161_management_meetings"


def test_migration_chains_after_0160_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from typing import get_args

    from app.models import APPOINTMENT_MODES, MEETING_KINDS, MEETING_STATUSES, ManagementDiscussion, ManagementMeeting
    from app.schemas import MgmtMeetingKind

    assert MEETING_KINDS == _migration.KINDS and MEETING_STATUSES == _migration.STATUSES == ("scheduled", "completed", "cancelled")
    assert APPOINTMENT_MODES == _migration.MODES and get_args(MgmtMeetingKind) == MEETING_KINDS
    assert {c.name for c in ManagementMeeting.__table__.columns} == {
        "id", "title", "kind", "starts_at", "mode", "location", "meeting_url", "agenda", "minutes", "minutes_recorded_at", "status",
        "created_by_user_id", "updated_by_user_id", "created_at", "updated_at",
    }  # fmt: skip
    assert "meeting_id" in ManagementDiscussion.__table__.columns


@pytest.mark.asyncio
async def test_tables_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()

    def read(sync):
        found = inspect(sync)
        return set(found.get_table_names()), {i["name"] for i in found.get_indexes("management_meetings")}, {i["name"] for i in found.get_indexes("management_discussions")}

    tables, indexes, discussion_indexes = await conn.run_sync(read)
    assert {"management_meetings", "management_meeting_participants"} <= tables
    assert {"ix_management_meetings_starts_at", "ix_management_meetings_status_starts_at"} <= indexes
    assert "ix_management_discussions_meeting_id" in discussion_indexes


@pytest.fixture
def isolated_db():
    """A fresh database at 0160."""
    cfg = _config()
    original = settings.database_url
    name = f"mgmt029_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_and_downgrade_refuses_while_meetings_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'management_meetings'")
    assert not _sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'management_discussions' AND column_name = 'meeting_id'")
    command.upgrade(cfg, HEAD)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 'p@example.local', 'x', 'P', 'partner', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    insert = "INSERT INTO management_meetings (id, title, kind, starts_at, mode, created_by_user_id, updated_by_user_id) VALUES (gen_random_uuid(), 'Partner meeting', :kind, now(), :mode, :p, :p)"
    with pytest.raises(Exception, match="ck_management_meetings_kind"):
        _sql(url, insert, {"p": user, "kind": "board", "mode": "Online"})
    with pytest.raises(Exception, match="ck_management_meetings_mode"):
        _sql(url, insert, {"p": user, "kind": "partner", "mode": "Fax"})
    _sql(url, insert, {"p": user, "kind": "partner", "mode": "Online"})
    assert _sql(url, "SELECT status FROM management_meetings")[0][0] == "scheduled"
    with pytest.raises(Exception, match="meetings exist"):
        command.downgrade(cfg, BASE)

"""upc-009 -- migration 0127_university_meetings (spec §2) and the §7 meeting catalogue (MG1, MG4). Round trip and the downgrade refusal
run in a throwaway database built from scratch (the upc-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from datetime import date
from typing import get_args

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_upc_009_migration_0127", VERSIONS / "0127_university_meetings.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0126_partnership_tasks", "0127_university_meetings"


def test_migration_chains_after_0126_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_catalogue_is_the_source_in_order():
    """§7 (L288-L312): the twelve meeting types in source order; Online/Offline."""
    from app.partnership_meeting_types import MODES, STATUSES, TYPES

    assert TYPES == (
        "introduction", "partnership_discussion", "commercial_discussion", "mou_discussion", "product_presentation",
        "student_recruitment_discussion", "application_process_discussion", "marketing_discussion", "university_visit", "campus_visit",
        "webinar", "training_session",
    )  # fmt: skip
    assert MODES == ("online", "offline") and STATUSES == ("scheduled", "completed", "cancelled")


def test_model_matches_the_migration():
    from app.models import UNIVERSITY_MEETING_CHECKS, UniversityMeeting, UniversityMeetingEvent, UniversityMeetingParticipant
    from app.partnership_meeting_types import MODES, TYPES
    from app.schemas import UniversityMeetingMode, UniversityMeetingType

    assert UNIVERSITY_MEETING_CHECKS == _migration.CHECKS
    assert get_args(UniversityMeetingType) == TYPES and get_args(UniversityMeetingMode) == MODES
    assert {c.name for c in UniversityMeeting.__table__.columns} == {
        "id", "code", "university_id", "contact_id", "contact_name", "contact_designation", "meeting_type", "starts_at", "mode",
        "location", "meeting_url", "agenda", "notes", "discussion_points", "decisions", "next_action", "next_action_due_on",
        "next_meeting_date", "responsible_user_id", "created_by_user_id", "status", "completed_at", "completed_by_user_id",
        "cancelled_at", "cancel_reason", "created_at", "updated_at",
    }  # fmt: skip
    assert {c.name for c in UniversityMeetingParticipant.__table__.columns} == {"id", "meeting_id", "contact_id", "user_id"}
    assert {c.name for c in UniversityMeetingEvent.__table__.columns} == {
        "id", "meeting_id", "event", "old_starts_at", "new_starts_at", "reason", "actor_user_id", "position", "created_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_tables_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()

    def read(sync):
        insp = inspect(sync)
        return set(insp.get_table_names()), {i["name"] for i in insp.get_indexes("university_meetings")}

    tables, indexes = await conn.run_sync(read)
    assert {"university_meetings", "university_meeting_participants", "university_meeting_events"} <= tables
    assert {"ix_university_meetings_university_starts", "ix_university_meetings_status_starts", "ix_university_meetings_responsible"} <= indexes


@pytest.fixture
def isolated_db():
    """A fresh database at 0126."""
    cfg = _config()
    original = settings.database_url
    name = f"upc009_migration_{uuid.uuid4().hex[:8]}"
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
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'university_meetings'")
    command.upgrade(cfg, HEAD)
    country = _sql(url, "SELECT id FROM countries WHERE iso2 = 'GB'")[0][0]
    uni = _sql(
        url,
        "INSERT INTO universities (id, country_id, slug, name, name_key, city, overview, eligibility, requirements, deadlines, scholarships) "
        "VALUES (gen_random_uuid(), :c, 'abc', 'ABC', 'abc', 'London', '', '', '[]', '[]', '[]') RETURNING id",
        {"c": country},
    )[0][0]
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 't@example.local', 'x', 'T', 'partnership_head', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    insert = (
        "INSERT INTO university_meetings (id, code, university_id, meeting_type, starts_at, mode, responsible_user_id, created_by_user_id, "
        "next_action, next_action_due_on) VALUES (gen_random_uuid(), :code, :u, 'introduction', now() + interval '1 day', 'online', :p, :p, "
        ":na, :due)"
    )
    with pytest.raises(Exception, match="ck_university_meetings_next_action"):
        _sql(url, insert, {"code": "UMT-1", "u": uni, "p": user, "na": "Send the MoU", "due": None})
    with pytest.raises(Exception, match="ck_university_meetings_outcome"):  # outcome fields only on a completed meeting
        _sql(url, insert, {"code": "UMT-1", "u": uni, "p": user, "na": "Send the MoU", "due": date(2030, 1, 1)})
    _sql(url, insert, {"code": "UMT-1", "u": uni, "p": user, "na": None, "due": None})
    assert _sql(url, "SELECT nextval('university_meeting_code_seq')")[0][0] == 1
    with pytest.raises(Exception, match="meetings exist"):
        command.downgrade(cfg, BASE)

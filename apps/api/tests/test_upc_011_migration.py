"""upc-011 -- migration 0136_partnership_events (spec §2) and the §9 event kinds (CL1). Round trip and the downgrade refusal run in a
throwaway database built from scratch (the upc-001 pattern); a downgrade never runs against the shared test database."""

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

_spec = importlib.util.spec_from_file_location("_upc_011_migration_0136", VERSIONS / "0136_partnership_events.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0135_resume_extraction", "0136_partnership_events"


def test_migration_chains_after_0135_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_kinds_are_the_source_in_order():
    """§9 (L358-L363): the six kinds that are not meetings or visits, in source order."""
    from app.partnership_event_kinds import KINDS, STATUSES

    assert KINDS == ("conference", "education_fair", "partner_meeting", "mou_signing", "webinar", "university_presentation")
    assert STATUSES == ("scheduled", "cancelled")


def test_model_matches_the_migration():
    from app.models import PARTNERSHIP_EVENT_CHECKS, PartnershipEvent, PartnershipEventParticipant
    from app.partnership_event_kinds import KINDS
    from app.schemas import PartnershipEventKind

    assert PARTNERSHIP_EVENT_CHECKS == _migration.CHECKS
    assert get_args(PartnershipEventKind) == KINDS
    assert {c.name for c in PartnershipEvent.__table__.columns} == {
        "id", "code", "kind", "title", "university_id", "starts_on", "ends_on", "location", "notes", "owner_user_id", "created_by_user_id",
        "status", "cancelled_at", "cancel_reason", "created_at", "updated_at",
    }  # fmt: skip
    assert {c.name for c in PartnershipEventParticipant.__table__.columns} == {"event_id", "user_id"}


@pytest.mark.asyncio
async def test_tables_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()

    def read(sync):
        insp = inspect(sync)
        return set(insp.get_table_names()), {i["name"] for i in insp.get_indexes("partnership_events")}

    tables, indexes = await conn.run_sync(read)
    assert {"partnership_events", "partnership_event_participants"} <= tables
    assert {"ix_partnership_events_dates", "ix_partnership_events_owner", "ix_partnership_events_university"} <= indexes


@pytest.fixture
def isolated_db():
    """A fresh database at 0135."""
    cfg = _config()
    original = settings.database_url
    name = f"upc011_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_and_downgrade_refuses_while_events_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'partnership_events'")
    command.upgrade(cfg, HEAD)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 't@example.local', 'x', 'T', 'partnership_head', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    insert = (
        "INSERT INTO partnership_events (id, code, kind, title, starts_on, ends_on, owner_user_id, created_by_user_id, status, cancel_reason) "
        "VALUES (gen_random_uuid(), :code, 'education_fair', 'Fair', DATE '2030-01-05', :ends, :p, :p, :status, :reason)"
    )
    with pytest.raises(Exception, match="ck_partnership_events_dates"):
        _sql(url, insert, {"code": "PEV-1", "ends": date(2030, 1, 4), "p": user, "status": "scheduled", "reason": None})
    with pytest.raises(Exception, match="ck_partnership_events_cancelled"):  # cancelled needs its time and reason
        _sql(url, insert, {"code": "PEV-1", "ends": date(2030, 1, 7), "p": user, "status": "cancelled", "reason": "Called off"})
    _sql(url, insert, {"code": "PEV-1", "ends": date(2030, 1, 7), "p": user, "status": "scheduled", "reason": None})
    assert _sql(url, "SELECT nextval('partnership_event_code_seq')")[0][0] == 1
    with pytest.raises(Exception, match="events exist"):
        command.downgrade(cfg, BASE)

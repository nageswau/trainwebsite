"""upc-010 -- migration 0113_university_visits (spec §2). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from typing import get_args

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_upc_010_migration_0113", VERSIONS / "0113_university_visits.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0112_company_pipeline", "0113_university_visits"


def test_migration_chains_after_0112_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import UNIVERSITY_VISIT_STATUS_CHECK, UNIVERSITY_VISIT_STATUSES, UniversityVisit, UniversityVisitEvent
    from app.schemas import VisitStatus

    assert UNIVERSITY_VISIT_STATUSES == ("planned", "approved", "travel_booked", "visit_completed", "follow_up", "closed")
    assert UNIVERSITY_VISIT_STATUS_CHECK == _migration.STATUS_CHECK
    assert get_args(VisitStatus) == UNIVERSITY_VISIT_STATUSES
    assert {c.name for c in UniversityVisit.__table__.columns} == {
        "id", "code", "university_id", "city", "purpose", "lead_user_id", "created_by_user_id", "proposed_date", "confirmed_date",
        "travel_required", "travel_notes", "hotel_required", "hotel_notes", "agenda", "expected_outcome", "follow_up_date", "status",
        "submitted_at", "rejection_reason", "decided_by_user_id", "decided_at", "close_reason", "created_at", "updated_at",
    }  # fmt: skip
    assert {c.name for c in UniversityVisitEvent.__table__.columns} == {
        "id", "visit_id", "action", "from_status", "to_status", "actor_user_id", "reason", "created_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_tables_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables, indexes = await conn.run_sync(lambda sync: (set(inspect(sync).get_table_names()), {i["name"] for i in inspect(sync).get_indexes("university_visits")}))
    assert {"university_visits", "university_visit_participants", "university_visit_contacts", "university_visit_events"} <= tables
    assert {"ix_university_visits_university", "ix_university_visits_lead", "ix_university_visits_pending"} <= indexes


@pytest.fixture
def isolated_db():
    """A fresh database at 0112."""
    cfg = _config()
    original = settings.database_url
    name = f"upc010_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_and_downgrade_refuses_while_visits_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'university_visits'")
    command.upgrade(cfg, HEAD)
    country = _sql(url, "SELECT id FROM countries WHERE iso2 = 'GB'")[0][0]
    uni = _sql(
        url,
        # name_key: NOT NULL since upc-004's 0109 (the normalised name)
        "INSERT INTO universities (id, country_id, slug, name, name_key, city, overview, eligibility, requirements, deadlines, scholarships) "
        "VALUES (gen_random_uuid(), :c, 'abc', 'ABC', 'abc', 'London', '', '', '[]', '[]', '[]') RETURNING id",
        {"c": country},
    )[0][0]
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 'v@example.local', 'x', 'V', 'partnership_head', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    insert = (
        "INSERT INTO university_visits (id, code, university_id, city, purpose, lead_user_id, created_by_user_id, proposed_date, status) "
        "VALUES (gen_random_uuid(), :code, :u, 'London', 'MoU', :p, :p, current_date, :s)"
    )
    with pytest.raises(Exception, match="ck_university_visits_status"):
        _sql(url, insert, {"code": "VIS-X1", "u": uni, "p": user, "s": "booked"})
    _sql(url, insert, {"code": "VIS-X2", "u": uni, "p": user, "s": "planned"})
    assert _sql(url, "SELECT nextval('university_visit_code_seq')")[0][0] >= 1
    with pytest.raises(Exception, match="visits exist"):
        command.downgrade(cfg, BASE)

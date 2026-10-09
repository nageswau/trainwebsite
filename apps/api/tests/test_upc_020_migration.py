"""upc-020 -- migration 0126_partnership_tasks (spec §2) and the Q-22 rule catalogue (spec §1). Round trip and the downgrade refusal run in
a throwaway database built from scratch (the upc-001 pattern); a downgrade never runs against the shared test database."""

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

_spec = importlib.util.spec_from_file_location("_upc_020_migration_0126", VERSIONS / "0126_partnership_tasks.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0125_university_comms", "0126_partnership_tasks"


def test_migration_chains_after_0125_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import PARTNERSHIP_TASK_CHECKS, PartnershipTask
    from app.partnership_task_rules import KINDS, PRIORITIES, SOURCES, STATUSES
    from app.schemas import PartnershipTaskKind, PartnershipTaskPriority

    assert PARTNERSHIP_TASK_CHECKS == _migration.CHECKS
    assert KINDS == ("follow_up", "task") and PRIORITIES == ("high", "medium", "low") and STATUSES == ("open", "done", "cancelled")
    assert SOURCES == ("manual", "stage", "meeting", "visit", "agreement")
    assert get_args(PartnershipTaskKind) == KINDS and get_args(PartnershipTaskPriority) == PRIORITIES
    assert {c.name for c in PartnershipTask.__table__.columns} == {
        "id", "university_id", "kind", "title", "notes", "assignee_user_id", "created_by_user_id", "due_on", "priority", "status",
        "source", "rule", "completed_at", "cancelled_at", "cancel_reason", "created_at", "updated_at",
    }  # fmt: skip


def test_rule_catalogue_covers_the_source():
    """§19's twelve titles in source order; Q-22 rules only name catalogue stages, offsets are positive."""
    from app.partnership_stages import STAGE_KEYS
    from app.partnership_task_rules import STAGE_RULES, TITLES

    assert TITLES == (
        "Follow up with university", "Send partnership proposal", "Schedule meeting", "Send MoU", "Follow up on MoU",
        "Arrange university visit", "Collect documents", "Negotiate commission", "Activate university", "Conduct training",
        "Send student applications", "Follow up on offers",
    )  # fmt: skip
    assert set(STAGE_RULES) <= set(STAGE_KEYS)
    assert STAGE_RULES["proposal_sent"].title == "Follow up on proposal" and STAGE_RULES["proposal_sent"].kind == "follow_up"
    assert all(r.days > 0 and r.priority in ("high", "medium", "low") for r in STAGE_RULES.values())


@pytest.mark.asyncio
async def test_table_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables, indexes = await conn.run_sync(lambda sync: (set(inspect(sync).get_table_names()), {i["name"] for i in inspect(sync).get_indexes("partnership_tasks")}))
    assert "partnership_tasks" in tables
    assert {"ix_partnership_tasks_assignee_status_due", "ix_partnership_tasks_university_status_due", "uq_partnership_tasks_open_rule"} <= indexes


@pytest.fixture
def isolated_db():
    """A fresh database at 0125."""
    cfg = _config()
    original = settings.database_url
    name = f"upc020_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_and_downgrade_refuses_while_tasks_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'partnership_tasks'")
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
        "INSERT INTO partnership_tasks (id, university_id, kind, title, assignee_user_id, created_by_user_id, due_on, source, rule) "
        "VALUES (gen_random_uuid(), :u, 'follow_up', 'Call', :p, :p, current_date, :s, :r)"
    )
    with pytest.raises(Exception, match="ck_partnership_tasks_rule"):
        _sql(url, insert, {"u": uni, "p": user, "s": "stage", "r": None})
    _sql(url, insert, {"u": uni, "p": user, "s": "stage", "r": "stage:proposal_sent"})
    with pytest.raises(Exception, match="uq_partnership_tasks_open_rule"):
        _sql(url, insert, {"u": uni, "p": user, "s": "stage", "r": "stage:proposal_sent"})
    with pytest.raises(Exception, match="tasks exist"):
        command.downgrade(cfg, BASE)

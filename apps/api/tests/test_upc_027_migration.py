"""upc-027 -- migration 0145_university_onboarding (spec §2) and the §29 onboarding catalogue (spec OB1). Round trip and the downgrade
refusal run in a throwaway database built from scratch (the upc-001 pattern); a downgrade never runs against the shared test database."""

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

_spec = importlib.util.spec_from_file_location("_upc_027_migration_0145", VERSIONS / "0145_university_onboarding.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0144_commission_receipts", "0145_university_onboarding"
TABLE = "university_onboarding_items"


def test_migration_chains_after_0144_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_catalogue_is_the_source_list():
    """EVID-020 §29 (L946-L968): ten items in source order and wording; three statuses."""
    from app.partnership_onboarding import AUTO_ITEM, ITEM_KEYS, ITEMS, STATUS_LABELS, STATUSES

    assert [i.label for i in ITEMS] == [
        "Counselor training", "Application team training", "Product training", "University portal access", "Application process",
        "Marketing material", "Course database updated", "Commission setup", "University contact setup", "First student campaign",
    ]  # fmt: skip
    assert len(set(ITEM_KEYS)) == 10 and AUTO_ITEM in ITEM_KEYS
    assert STATUSES == ("not_started", "in_progress", "completed")
    assert list(STATUS_LABELS.values()) == ["Not Started", "In Progress", "Completed"]


def test_model_matches_the_migration():
    from app.models import UNIVERSITY_ONBOARDING_CHECKS, UniversityOnboardingItem
    from app.partnership_onboarding import ITEM_KEYS, STATUSES
    from app.schemas import OnboardingItemKind, OnboardingStatus

    assert UNIVERSITY_ONBOARDING_CHECKS == _migration.CHECKS
    assert get_args(OnboardingItemKind) == ITEM_KEYS and get_args(OnboardingStatus) == STATUSES
    assert {c.name for c in UniversityOnboardingItem.__table__.columns} == {
        "id", "university_id", "kind", "status", "owner_user_id", "due_date", "note", "completed_on", "updated_by_user_id", "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_table_and_unique_index_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables, uniques = await conn.run_sync(lambda sync: (set(inspect(sync).get_table_names()), {u["name"] for u in inspect(sync).get_unique_constraints(TABLE)}))
    assert TABLE in tables and "uq_university_onboarding_items_kind" in uniques


@pytest.fixture
def isolated_db():
    """A fresh database at 0144."""
    cfg = _config()
    original = settings.database_url
    name = f"upc027_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_and_downgrade_refuses_while_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, f"SELECT 1 FROM information_schema.tables WHERE table_name = '{TABLE}'")
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
    insert = f"INSERT INTO {TABLE} (id, university_id, kind, status, completed_on, updated_by_user_id) VALUES (gen_random_uuid(), :u, :k, :s, :c, :p)"
    with pytest.raises(Exception, match="ck_university_onboarding_items_kind"):
        _sql(url, insert, {"u": uni, "k": "launch", "s": "not_started", "c": None, "p": user})
    with pytest.raises(Exception, match="ck_university_onboarding_items_status"):
        _sql(url, insert, {"u": uni, "k": "product_training", "s": "done", "c": None, "p": user})
    with pytest.raises(Exception, match="ck_university_onboarding_items_completed"):
        _sql(url, insert, {"u": uni, "k": "product_training", "s": "completed", "c": None, "p": user})
    _sql(url, insert, {"u": uni, "k": "product_training", "s": "in_progress", "c": None, "p": user})
    with pytest.raises(Exception, match="uq_university_onboarding_items_kind"):
        _sql(url, insert, {"u": uni, "k": "product_training", "s": "in_progress", "c": None, "p": user})
    with pytest.raises(Exception, match="onboarding progress exists"):
        command.downgrade(cfg, BASE)
    _sql(url, f"DELETE FROM {TABLE}")
    command.downgrade(cfg, BASE)

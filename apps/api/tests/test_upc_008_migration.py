"""upc-008 -- migration 0127_university_milestones (spec §2) and the §6 milestone catalogue (spec MS1). Round trip and the downgrade refusal
run in a throwaway database built from scratch (the upc-001 pattern); a downgrade never runs against the shared test database."""

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

_spec = importlib.util.spec_from_file_location("_upc_008_migration_0127", VERSIONS / "0127_university_milestones.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0126_partnership_tasks", "0127_university_milestones"
EXPECTED_COLUMNS = {"target_partnership_date", "expected_intake", "expected_agreement_date", "expected_recruitment_start"}


def test_migration_chains_after_0126_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_catalogue_is_the_source_list():
    """EVID-020 §6 (L216-L240): 13 milestones in source order and wording; auto sources only per MS4."""
    from app.partnership_milestones import AUTO_SOURCES, MILESTONE_KEYS, MILESTONES

    assert [m.label for m in MILESTONES] == [
        "University Contacted", "Meeting", "Presentation", "Proposal", "Documents", "Negotiation", "Agreement", "Signed", "Onboarding",
        "Student Recruitment", "First Application", "First Admission", "Active Partnership",
    ]  # fmt: skip
    assert len(set(MILESTONE_KEYS)) == 13
    assert AUTO_SOURCES == {"proposal": "stage", "first_application": "application", "first_admission": "admission"}


def test_model_matches_the_migration():
    from app.models import UNIVERSITY_MILESTONE_CHECKS, University, UniversityMilestone
    from app.partnership_milestones import MILESTONE_KEYS
    from app.schemas import MilestoneKind

    assert UNIVERSITY_MILESTONE_CHECKS == _migration.CHECKS
    assert get_args(MilestoneKind) == MILESTONE_KEYS
    assert EXPECTED_COLUMNS <= {c.name for c in University.__table__.columns}
    assert {c.name for c in UniversityMilestone.__table__.columns} == {
        "id", "university_id", "kind", "target_date", "achieved_on", "updated_by_user_id", "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_table_columns_and_index_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables, uni_cols, indexes = await conn.run_sync(
        lambda sync: (
            set(inspect(sync).get_table_names()),
            {c["name"] for c in inspect(sync).get_columns("universities")},
            {i["name"] for i in inspect(sync).get_indexes("university_milestones")} | {u["name"] for u in inspect(sync).get_unique_constraints("university_milestones")},
        )
    )
    assert "university_milestones" in tables and EXPECTED_COLUMNS <= uni_cols
    assert "uq_university_milestones_kind" in indexes


@pytest.fixture
def isolated_db():
    """A fresh database at 0126."""
    cfg = _config()
    original = settings.database_url
    name = f"upc008_migration_{uuid.uuid4().hex[:8]}"
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


def _university(url: str) -> str:
    country = _sql(url, "SELECT id FROM countries WHERE iso2 = 'GB'")[0][0]
    return _sql(
        url,
        "INSERT INTO universities (id, country_id, slug, name, name_key, city, overview, eligibility, requirements, deadlines, scholarships) "
        "VALUES (gen_random_uuid(), :c, 'abc', 'ABC', 'abc', 'London', '', '', '[]', '[]', '[]') RETURNING id",
        {"c": country},
    )[0][0]


def test_upgrade_round_trips_and_downgrade_refuses_while_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'university_milestones'")
    assert not _sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'universities' AND column_name = 'expected_intake'")
    command.upgrade(cfg, HEAD)
    uni = _university(url)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 't@example.local', 'x', 'T', 'partnership_head', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    insert = "INSERT INTO university_milestones (id, university_id, kind, target_date, updated_by_user_id) VALUES (gen_random_uuid(), :u, :k, current_date, :p)"
    with pytest.raises(Exception, match="ck_university_milestones_kind"):
        _sql(url, insert, {"u": uni, "k": "launch", "p": user})
    _sql(url, insert, {"u": uni, "k": "proposal", "p": user})
    with pytest.raises(Exception, match="uq_university_milestones_kind"):
        _sql(url, insert, {"u": uni, "k": "proposal", "p": user})
    with pytest.raises(Exception, match="milestones or expected"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM university_milestones")
    _sql(url, "UPDATE universities SET expected_intake = 'Jan 2027'")
    with pytest.raises(Exception, match="milestones or expected"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE universities SET expected_intake = NULL")
    command.downgrade(cfg, BASE)

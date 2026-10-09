"""rec-015 -- migration 0141_talent_pools (spec §2). Round trip, the seed's idempotency and the downgrade refusal run in a throwaway
database built from scratch (the rec-030 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_015_migration_0141", VERSIONS / "0141_talent_pools.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0140_joining_management", "0141_talent_pools"
SEEDED = {"Java Developers", "Python Developers", "Full Stack Developers", "Cloud Engineers", "Freshers", "Experienced Professionals"}


def test_migration_chains_after_0140_and_there_is_a_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_model_matches_the_migration():
    from app.models import TALENT_POOL_EXPERIENCE_CHECK, TalentPool

    assert _migration.EXPERIENCE_CHECK == TALENT_POOL_EXPERIENCE_CHECK
    assert {c.name for c in TalentPool.__table__.columns} == {
        "id", "name", "all_terms", "any_terms", "experience_min_months", "experience_max_months", "active", "created_by_user_id",
        "updated_by_user_id", "created_at", "updated_at",
    }
    assert "uq_talent_pools_name" in {i.name for i in TalentPool.__table__.indexes}


def test_every_seeded_term_is_a_seeded_skill():
    """P3: the seed only names skills the 0104 Skills Master seeds, so no seeded pool starts with an unavailable term."""
    spec = importlib.util.spec_from_file_location("_rec_015_skills_0104", VERSIONS / "0104_skills_master.py")
    skills_migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skills_migration)
    seeded_skills = {s for names in skills_migration.CATEGORIES.values() for s in names}
    for _, all_terms, any_terms, _, _ in _migration.SEED:
        assert {*all_terms, *(t for group in any_terms for t in group)} <= seeded_skills


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec015_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_seed_and_downgrade_refusal(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('talent_pools')") == [(None,)]
    command.upgrade(cfg, HEAD)
    assert {r[0] for r in _sql(url, "SELECT name FROM talent_pools")} == SEEDED
    assert _sql(url, "SELECT experience_min_months, experience_max_months FROM talent_pools WHERE name = 'Freshers'") == [(None, 11)]
    with pytest.raises(Exception, match="ck_talent_pools_experience"):
        _sql(url, "INSERT INTO talent_pools (id, name, all_terms, any_terms, experience_min_months, experience_max_months) "
                  "VALUES (:id, 'Bad', '[]', '[]', 24, 12)", {"id": uuid.uuid4()})
    with pytest.raises(Exception, match="uq_talent_pools_name"):
        _sql(url, "INSERT INTO talent_pools (id, name, all_terms, any_terms) VALUES (:id, 'JAVA DEVELOPERS', '[]', '[]')", {"id": uuid.uuid4()})
    # the seed is idempotent and never overwrites an edit: rename one, re-run the seed statements
    _sql(url, "UPDATE talent_pools SET all_terms = '[\"Core Java\"]' WHERE name = 'Java Developers'")
    for sql, params in _migration.seed_statements():
        _sql(url, sql, params)
    assert _sql(url, "SELECT count(*) FROM talent_pools") == [(len(SEEDED),)]
    assert _sql(url, "SELECT all_terms::text FROM talent_pools WHERE name = 'Java Developers'") == [('["Core Java"]',)]
    # seed-only data downgrades; a manager's pool blocks it
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    user_id = uuid.uuid4()
    _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
              "VALUES (:id, :e, 'x', 'M', 'placement_manager', 'global', true, true, 'en-GB', '{}')", {"id": user_id, "e": f"{user_id.hex[:8]}@example.local"})
    _sql(url, "UPDATE talent_pools SET updated_by_user_id = :u WHERE name = 'Freshers'", {"u": user_id})
    with pytest.raises(Exception, match="talent pools"):
        command.downgrade(cfg, BASE)

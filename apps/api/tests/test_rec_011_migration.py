"""rec-011 -- migration 0120_candidate_skills (spec §2). Round trip, constraints and downgrade refusal run in a throwaway database built from
scratch (the tel-002 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_011_migration_0120", VERSIONS / "0120_candidate_skills.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0119_recruiter_meetings", "0120_candidate_skills"


def test_migration_chains_after_rec_028_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import CANDIDATE_SKILL_CHECKS, CandidateSkill

    assert _migration.CHECKS == CANDIDATE_SKILL_CHECKS  # one source of truth for the CHECK text
    table = CandidateSkill.__table__
    assert {c.name for c in table.columns} == {
        "id",
        "candidate_id",
        "skill_id",
        "level",
        "experience_months",
        "last_used_year",
        "source",
        "status",
        "verified_by_user_id",
        "verified_at",
        "added_by_user_id",
        "updated_by_user_id",
        "created_at",
        "updated_at",
    }
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"uq_candidate_skills_skill", "ix_candidate_skills_skill_candidate", *CANDIDATE_SKILL_CHECKS} <= names


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec011_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        # 0001's create_all builds today's models (this table included); going to head and back down gives the real 0119 shape.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _fixture_rows(url) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    user_id, candidate_id = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'U', 'placement_team', 'it', 'x', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"u{user_id.hex[:8]}@example.com"},
    )
    _sql(
        url,
        "INSERT INTO candidates (id, candidate_code, name, email, source_id, created_by_user_id, status, preferred_locations) "
        "VALUES (:id, :code, 'Rahul', :e, (SELECT id FROM rec_candidate_sources WHERE name = 'Referral'), :u, 'available', '[]')",
        {"id": candidate_id, "code": f"T-{candidate_id.hex[:8]}", "e": f"c{candidate_id.hex[:8]}@example.com", "u": user_id},
    )
    skill_id = _sql(url, "SELECT id FROM skills WHERE name = 'Java'")[0][0]
    return user_id, candidate_id, skill_id


INSERT = (
    "INSERT INTO candidate_skills (id, candidate_id, skill_id, level, source, status, verified_by_user_id, verified_at, added_by_user_id, "
    "experience_months, last_used_year) VALUES (:id, :c, :s, :level, :source, :status, :vb, :va, :u, :exp, :year)"
)


def _row(url, user_id, candidate_id, skill_id, *, level="advanced", source="resume", status="claimed", verified=False, exp=None, year=None):
    _sql(
        url,
        INSERT,
        {
            "id": uuid.uuid4(),
            "c": candidate_id,
            "s": skill_id,
            "level": level,
            "source": source,
            "status": status,
            "vb": user_id if verified else None,
            "va": datetime(2026, 10, 8, 10, tzinfo=UTC) if verified else None,
            "u": user_id,
            "exp": exp,
            "year": year,
        },
    )


def test_round_trip_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    user_id, candidate_id, java = _fixture_rows(url)
    _row(url, user_id, candidate_id, java, exp=36, year=2026)
    with pytest.raises(Exception, match="uq_candidate_skills_skill"):
        _row(url, user_id, candidate_id, java)
    other = _sql(url, "SELECT id FROM skills WHERE name = 'Python'")[0][0]
    for kwargs, check in (
        ({"level": "guru"}, "ck_candidate_skills_level"),
        ({"source": "linkedin"}, "ck_candidate_skills_source"),
        ({"status": "verified"}, "ck_candidate_skills_verified"),  # verified needs who and when
        ({"verified": True}, "ck_candidate_skills_verified"),  # claimed carries neither
        ({"exp": 601}, "ck_candidate_skills_experience"),
        ({"year": 1949}, "ck_candidate_skills_last_used"),
    ):
        with pytest.raises(Exception, match=check):
            _row(url, user_id, candidate_id, other, **kwargs)
    _row(url, user_id, candidate_id, other, status="assessed", verified=True)
    with pytest.raises(Exception, match="candidate skills exist"):
        command.downgrade(cfg, BASE)


def test_downgrade_then_upgrade_with_no_rows(isolated_db):
    cfg = isolated_db["cfg"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)

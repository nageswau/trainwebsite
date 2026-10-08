"""rec-009 -- migration 0105_candidates (spec §3). Round trip, constraints and downgrade refusal run in a throwaway database built from
scratch (the tel-002 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

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
_spec = importlib.util.spec_from_file_location("_rec_009_migration_0105", VERSIONS / "0105_candidates.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0103_partnership_profiles", "0105_candidates"


def test_migration_chains_after_upc_001_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import CANDIDATE_CHECKS, Candidate, CandidateResume

    assert _migration.CHECKS == CANDIDATE_CHECKS  # one source of truth for the CHECK text
    table = Candidate.__table__
    assert {c.name for c in table.columns} == {
        "id",
        "candidate_code",
        "name",
        "mobile",
        "mobile_normalized",
        "email",
        "location",
        "qualification",
        "college",
        "passing_year",
        "experience_months",
        "current_company",
        "current_salary",
        "expected_salary",
        "notice_days",
        "preferred_locations",
        "preferred_role",
        "linkedin",
        "source_id",
        "source_detail",
        "status",
        "user_id",
        "opted_in",
        "created_by_user_id",
        "updated_by_user_id",
        "archived_at",
        "archived_by_user_id",
        "created_at",
        "updated_at",
    }
    assert not table.c.name.nullable and not table.c.source_id.nullable and table.c.mobile.nullable and table.c.email.nullable
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"uq_candidates_mobile", "uq_candidates_email", "ix_candidates_source_id", *CANDIDATE_CHECKS} <= names
    resume = CandidateResume.__table__
    assert "uq_candidate_resumes_version" in {c.name for c in resume.constraints}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec009_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        # 0001's create_all builds today's models (these tables included); going to head and back down gives the real 0103 shape.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _user(url) -> uuid.UUID:
    user_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'U', 'placement_team', 'it', 'x', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"u{user_id.hex[:8]}@example.com"},
    )
    return user_id


INSERT = (
    "INSERT INTO candidates (id, candidate_code, name, mobile, mobile_normalized, email, source_id, created_by_user_id, status, preferred_locations) "
    "VALUES (:id, :code, 'Rahul', :m, :mn, :e, (SELECT id FROM rec_candidate_sources WHERE name = 'Referral'), :u, :s, '[]')"
)


def _row(url, user_id, *, m=None, mn=None, e=None, s="available"):
    _sql(url, INSERT, {"id": uuid.uuid4(), "code": f"T-{uuid.uuid4().hex[:8]}", "m": m, "mn": mn, "e": e, "u": user_id, "s": s})


def test_round_trip_constraints_and_sequence(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT nextval('candidate_code_seq')")[0][0] >= 1
    user_id = _user(url)
    _row(url, user_id, m="98765 43210", mn="+919876543210", e="Rahul@Example.com")
    with pytest.raises(Exception, match="uq_candidates_mobile"):
        _row(url, user_id, m="09876543210", mn="+919876543210")
    with pytest.raises(Exception, match="uq_candidates_email"):
        _row(url, user_id, e="rahul@example.COM")
    with pytest.raises(Exception, match="ck_candidates_contact"):
        _row(url, user_id)
    with pytest.raises(Exception, match="ck_candidates_status"):
        _row(url, user_id, e="other@example.com", s="blacklisted")
    _row(url, user_id, e="second@example.com")  # mobile is optional when an email is given
    with pytest.raises(Exception, match="candidates exist"):
        command.downgrade(cfg, BASE)


def test_downgrade_then_upgrade_with_no_candidates(isolated_db):
    cfg = isolated_db["cfg"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)

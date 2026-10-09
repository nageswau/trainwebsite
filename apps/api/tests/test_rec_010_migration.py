"""rec-010 -- migration 0123_candidate_consents (spec §2). Round trip, the CHECK and the downgrade refusal run in a throwaway database built
from scratch (the tel-002 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

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
_spec = importlib.util.spec_from_file_location("_rec_010_migration_0123", VERSIONS / "0123_candidate_consents.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0122_candidate_skills", "0123_candidate_consents"


def test_migration_chains_after_rec_011_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import CANDIDATE_CONSENT_CHECKS, CandidateConsent

    assert _migration.CHECKS == CANDIDATE_CONSENT_CHECKS  # one source of truth for the CHECK text
    table = CandidateConsent.__table__
    assert {c.name for c in table.columns} == {"id", "candidate_id", "user_id", "action", "consent_version", "ip_address", "created_at"}
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"ix_candidate_consents_candidate", *CANDIDATE_CONSENT_CHECKS} <= names


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec010_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        # 0001's create_all builds today's models (this table included); going to head and back down gives the real 0122 shape.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _fixture_rows(url) -> tuple[uuid.UUID, uuid.UUID]:
    user_id, candidate_id = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) VALUES (:id, :e, 'U', 'it_student', 'it', 'x', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"u{user_id.hex[:8]}@example.com"},
    )
    _sql(
        url,
        "INSERT INTO candidates (id, candidate_code, name, email, source_id, created_by_user_id, status, preferred_locations, user_id, opted_in) "
        "VALUES (:id, :code, 'Rahul', :e, (SELECT id FROM rec_candidate_sources WHERE name = 'Referral'), :u, 'available', '[]', :u, true)",
        {"id": candidate_id, "code": f"T-{candidate_id.hex[:8]}", "e": f"c{candidate_id.hex[:8]}@example.com", "u": user_id},
    )
    return user_id, candidate_id


def _row(url, user_id, candidate_id, action="opt_in"):
    _sql(
        url,
        "INSERT INTO candidate_consents (id, candidate_id, user_id, action, consent_version) VALUES (:id, :c, :u, :a, 'v1')",
        {"id": uuid.uuid4(), "c": candidate_id, "u": user_id, "a": action},
    )


def test_round_trip_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    user_id, candidate_id = _fixture_rows(url)
    _row(url, user_id, candidate_id)
    _row(url, user_id, candidate_id, "opt_out")
    with pytest.raises(Exception, match="ck_candidate_consents_action"):
        _row(url, user_id, candidate_id, "maybe")
    assert _sql(url, "SELECT count(*) FROM candidate_consents WHERE created_at IS NOT NULL")[0][0] == 2
    with pytest.raises(Exception, match="consent history exists"):
        command.downgrade(cfg, BASE)


def test_downgrade_then_upgrade_with_no_rows(isolated_db):
    cfg = isolated_db["cfg"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)

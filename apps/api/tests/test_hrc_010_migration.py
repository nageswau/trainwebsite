"""hrc-010 -- migration 0260_candidate_profile (DEC-SCOPE-383): the chain, the frozen checks, the P11 backfill (education row 1 from the
legacy fields, `preferred_roles` from the preferred role) and the round trip, in a throwaway database (the hrc-011 pattern)."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import CANDIDATE_CERTIFICATION_CHECKS, CANDIDATE_EMPLOYMENT_CHECKS, CANDIDATE_PROFILE_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_010_migration_0260", VERSIONS / "0260_candidate_profile.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0260_candidate_profile", "0259_candidate_ownership"


def test_migration_chains_after_0259():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_are_frozen_copies_of_the_model():
    assert _migration.CHECKS == CANDIDATE_PROFILE_CHECKS
    assert _migration.EMPLOYMENT_CHECKS == CANDIDATE_EMPLOYMENT_CHECKS
    assert _migration.CERTIFICATION_CHECKS == CANDIDATE_CERTIFICATION_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc010_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'candidates'")}


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def test_backfill_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "city" not in _columns(url) and "candidate_education" not in _tables(url)
    user = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :e, '!', 'Mig', 'placement_team', 'it', true, true, 'en', '{}')",
        {"id": user, "e": f"{user.hex}@example.local"},
    )
    source = _sql(url, "SELECT id FROM rec_candidate_sources LIMIT 1")[0][0]
    full, bare = uuid.uuid4(), uuid.uuid4()
    for cid, code, qualification, college, year, role in ((full, "CAN-M10A", "B.Tech", "JNTU", 2018, "Tester"), (bare, "CAN-M10B", None, None, None, None)):
        _sql(url, "INSERT INTO candidates (id, candidate_code, name, email, qualification, college, passing_year, preferred_role, source_id, created_by_user_id, status, opted_in, preferred_locations) "
                  "VALUES (:id, :code, 'Mig', :e, :q, :c, :y, :r, :s, :u, 'available', false, '[]')",
             {"id": cid, "code": code, "e": f"{code}@example.local", "q": qualification, "c": college, "y": year, "r": role, "s": source, "u": user})  # fmt: skip
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT position, degree, institution, year FROM candidate_education WHERE candidate_id = :id", {"id": full}) == [(1, "B.Tech", "JNTU", 2018)]
    assert _sql(url, "SELECT count(*) FROM candidate_education WHERE candidate_id = :id", {"id": bare})[0][0] == 0
    assert _sql(url, "SELECT preferred_roles::text, tools::text FROM candidates WHERE id = :id", {"id": full})[0] == ('["Tester"]', "[]")
    assert _sql(url, "SELECT qualification FROM candidates WHERE id = :id", {"id": full})[0][0] == "B.Tech"  # legacy untouched
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert "city" not in _columns(url) and "preferred_roles" not in _columns(url)
    assert not {"candidate_education", "candidate_employment", "candidate_certifications"} & _tables(url)
    assert _sql(url, "SELECT qualification, college FROM candidates WHERE id = :id", {"id": full})[0] == ("B.Tech", "JNTU")
    command.upgrade(cfg, HEAD)

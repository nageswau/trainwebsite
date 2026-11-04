"""hrc-024 -- migration 0270_candidate_routing (DEC-SCOPE-393). The round trip runs in a throwaway database built from scratch (the rec-006
pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_hrc_017_migration import _config, _sql

API_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_hrc_024_migration_0270", API_ROOT / "alembic" / "versions" / "0270_candidate_routing.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0269_match_engine", "0270_candidate_routing"
TABLES = ("candidate_routing_rules", "candidate_routing_settings", "candidate_routing_cursors")


def test_migration_chains_after_match_engine_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import (
        CANDIDATE_ASSIGNMENT_REASONS,
        CANDIDATE_ROUTING_KINDS,
        CANDIDATE_ROUTING_RULE_CHECKS,
        CANDIDATE_ROUTING_STRATEGIES,
        CandidateAssignmentHistory,
        CandidateRoutingRule,
    )

    assert (CANDIDATE_ROUTING_KINDS, CANDIDATE_ROUTING_STRATEGIES) == (_migration.KINDS, _migration.STRATEGIES)
    assert CANDIDATE_ROUTING_RULE_CHECKS == _migration.RULE_CHECKS
    assert {c.name for c in CandidateRoutingRule.__table__.constraints} >= set(CANDIDATE_ROUTING_RULE_CHECKS)
    assert _migration.NEW_REASONS == f"reason IN ({', '.join(repr(r) for r in CANDIDATE_ASSIGNMENT_REASONS)})"
    assert CandidateAssignmentHistory.__table__.columns["changed_by_user_id"].nullable


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc024_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'candidate_routing_%'")}


def test_round_trip_checks_and_system_history_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    assert _tables(url) == set(TABLES)
    user = _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES "
                     f"('{uuid.uuid4()}', 'r24@example.local', '!', 'R', 'placement_team', 'it', true, true, 'en', '{{}}') RETURNING id")[0][0]  # fmt: skip
    rule = "INSERT INTO candidate_routing_rules (id, kind, location, source_id, recruiter_user_id) VALUES ('{id}', '{kind}', 'Pune', {source}, '{user}')"
    _sql(url, rule.format(id=uuid.uuid4(), kind="location", source="NULL", user=user))
    with pytest.raises(Exception, match="uq_candidate_routing_rules_rule"):
        _sql(url, rule.format(id=uuid.uuid4(), kind="location", source="NULL", user=user).replace("'Pune'", "'PUNE'"))
    with pytest.raises(Exception, match="ck_candidate_routing_rules_value"):
        _sql(url, rule.format(id=uuid.uuid4(), kind="source", source="NULL", user=user))
    with pytest.raises(Exception, match="ck_candidate_routing_settings_strategy"):
        _sql(url, "INSERT INTO candidate_routing_settings (id, strategy) VALUES (1, 'random')")
    with pytest.raises(Exception, match="ck_candidate_routing_settings_one_row"):
        _sql(url, "INSERT INTO candidate_routing_settings (id) VALUES (2)")

    source = _sql(url, "SELECT id FROM rec_candidate_sources LIMIT 1")[0][0]
    candidate = _sql(url, "INSERT INTO candidates (id, candidate_code, name, email, preferred_locations, source_id) VALUES "
                          f"('{uuid.uuid4()}', 'C24MIG', 'X', 'c24@example.com', '[]', '{source}') RETURNING id")[0][0]  # fmt: skip
    history = "INSERT INTO candidate_assignment_history (id, candidate_id, kind, to_user_id, changed_by_user_id, reason) VALUES ('{id}', '{c}', 'owner', '{u}', {by}, '{reason}')"
    _sql(url, history.format(id=uuid.uuid4(), c=candidate, u=user, by="NULL", reason="route"))
    _sql(url, history.format(id=uuid.uuid4(), c=candidate, u=user, by=f"'{user}'", reason="assign"))

    command.downgrade(cfg, BASE)
    assert _tables(url) == set()
    assert _sql(url, "SELECT reason FROM candidate_assignment_history") == [("assign",)]  # the system rows go; the others stay
    nullable = _sql(url, "SELECT is_nullable FROM information_schema.columns WHERE table_name = 'candidate_assignment_history' AND column_name = 'changed_by_user_id'")
    assert nullable == [("NO",)]
    command.upgrade(cfg, HEAD)
    assert _tables(url) == set(TABLES)

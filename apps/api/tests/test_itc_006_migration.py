"""itc-006 -- migration 0223_tel_source_workload: chain, constraints, the refused downgrade and a round trip, in a throwaway database
(the tel-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql
from tests.test_tel_007_migration import _user

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_itc_006_migration_0223", VERSIONS / "0223_tel_source_workload.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0222_it_student_counselors", "0223_tel_source_workload"
RULE = "INSERT INTO tel_distribution_rules (id, team, kind, product_id, city, source, telecaller_user_id) VALUES (:id, 'it', :kind, NULL, :city, :source, :user)"


def test_migration_chains_after_0222_and_keeps_the_sources_in_step():
    from app.models import TEL_STRATEGIES
    from app.tel_sources import TEL_SOURCES

    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert HEAD in {r.revision for r in ScriptDirectory.from_config(_config()).walk_revisions()}
    assert _migration.SOURCES == TEL_SOURCES and TEL_STRATEGIES == ("round_robin", "workload")


@pytest.fixture
def isolated_db():
    cfg, original = _config(), settings.database_url
    name = f"itc006_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)  # 0001's create_all already holds today's shape: 0223 must be a no-op on top of it
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _rule(url, user, **overrides):
    row = {"id": uuid.uuid4(), "kind": "source", "city": None, "source": "instagram", "user": user} | overrides
    _sql(url, RULE, row)


def test_constraints_refused_downgrade_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT DISTINCT distribution_strategy FROM tel_settings") == [("round_robin",)]
    user = _user(url)
    _rule(url, user)
    with pytest.raises(Exception, match="uq_tel_distribution_rules_source"):
        _rule(url, user)
    for constraint, overrides in {
        "ck_tel_distribution_rules_source": {"source": "tiktok"},
        "ck_tel_distribution_rules_shape": {"source": None},
    }.items():
        with pytest.raises(Exception, match=constraint):
            _rule(url, user, **overrides)
    with pytest.raises(Exception, match="ck_tel_distribution_rules_shape"):
        _rule(url, user, kind="city", city="Pune", source="google")
    with pytest.raises(Exception, match="ck_tel_settings_distribution_strategy"):
        _sql(url, "UPDATE tel_settings SET distribution_strategy = 'fastest'")
    _sql(url, "UPDATE tel_settings SET distribution_strategy = 'workload' WHERE team = 'it'")

    with pytest.raises(Exception, match="itc-006 downgrade refused"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM tel_distribution_rules WHERE kind = 'source'")
    command.downgrade(cfg, BASE)
    columns = _sql(url, "SELECT table_name, column_name FROM information_schema.columns WHERE "
                        "(table_name, column_name) IN (('tel_distribution_rules', 'source'), ('tel_settings', 'distribution_strategy'))")
    assert columns == []
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT DISTINCT distribution_strategy FROM tel_settings") == [("round_robin",)]  # existing teams keep today's behaviour
    _rule(url, user)
